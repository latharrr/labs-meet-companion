import json
import os
import re
import time
from .core import meeting_code, normalize, named_question, answer, minutes, delivery_text, digest
from .adapters import Vexa, whatsapp_send, resend_send


class Companion:
    def __init__(self, store, vexa=None, ai=None):
        self.store, self.vexa, self.ai = store, vexa, ai

    def create(self, title, link, consent):
        return self.store.create(title, meeting_code(link), consent)

    def stage_join(self, mid):
        m = self.store.meeting(mid)
        return self.store.stage(mid, "join", {"code": m["code"], "consent": m["consent"],
             "notice": "A visible Lathar Labs bot takes notes. Organizer must notify participants and obtain required consent."})

    def ingest(self, mid, snapshot, baseline=False):
        m = self.store.meeting(mid)
        if snapshot.get("native_meeting_id", m["code"]) != m["code"]:
            raise ValueError("Transcript belongs to another meeting")
        old = self.store.segments(mid)
        rows = normalize(snapshot)
        if digest([s.__dict__ for s in old]) == digest([s.__dict__ for s in rows]):
            return []
        self.store.ingest(mid, rows)
        drafts = []
        for s in rows:
            if s.source != "chat":
                continue
            if self.store.seen(mid, s.id) or baseline:
                continue
            question = named_question(s.text, s.speaker)
            if question:
                # Only evidence preceding the request; never include later conversation.
                context = [r for r in rows if r.start <= s.start]
                try:
                    reply = self.ai.answer(question, context) if self.ai else answer(question, context)
                except (ValueError, RuntimeError, OSError):
                    reply = {**answer(question, context), "fallback": "AI unavailable or grounding check failed; extractive draft only"}
                drafts.append(self.store.stage(mid, "chat", {"code": m["code"], **reply,
                    "question": question, "requester": s.speaker, "event": s.id}))
        return drafts

    def sync(self, mid, baseline=False):
        if not self.vexa:
            raise ValueError("Configure Vexa endpoint and key")
        m = self.store.meeting(mid)
        snapshot = self.vexa.transcript(m["code"])
        drafts = self.ingest(mid, snapshot, baseline)
        with self.store.db:
            self.store.db.execute("UPDATE meetings SET status=? WHERE id=?", (str(snapshot.get("status", "unknown")), mid))
        return drafts

    def generate_notes(self, mid):
        if not self.ai:
            raise ValueError("Configure the selected Groq-compatible AI provider first")
        value = self.ai.minutes(self.store.segments(mid))
        self.store.save_notes(mid, value)
        return value

    def stage_delivery(self, mid, kind, to):
        if kind == "email":
            if not re.fullmatch(r"[^\s@<>;,\r\n]+@[^\s@<>;,\r\n]+\.[^\s@<>;,\r\n]+", to):
                raise ValueError("One plain email address required")
        elif kind == "whatsapp":
            if not re.fullmatch(r"\+[1-9][0-9]{7,14}", to):
                raise ValueError("Use one verified E.164 number")
        else:
            raise ValueError("Choose email or whatsapp")
        m = self.store.meeting(mid)
        segs = self.store.segments(mid)
        if not segs:
            raise ValueError("No confirmed transcript")
        note = self.store.ai_notes(mid)
        text = delivery_text(m["title"], minutes(segs), segs)
        if note:
            text = m["title"] + "\nAI DRAFT: organizer review required\n"
            for key in ("summary", "decisions", "actions"):
                text += "\n" + key.title() + "\n"
                for item in note[key]:
                    text += item["text"] + " [" + ", ".join(c["id"] for c in item["citations"]) + "]\n"
            text += "\nConfirmed transcript\n" + "\n".join(f"[{s.start:.1f}s] {s.speaker}: {s.text}" for s in segs)
        payload = {"to": to, "subject": "Meeting notes: " + m["title"], "text": text,
                   "evidence_digest": digest([s.__dict__ for s in segs])}
        if kind == "whatsapp" and os.environ.get("LABS_OPENWA_TEST_CHAT_ID"):
            payload["chat_id"] = os.environ["LABS_OPENWA_TEST_CHAT_ID"]
        if kind == "email":
            sender = os.environ.get("LABS_EMAIL_FROM")
            if not sender or "\r" in sender or "\n" in sender:
                raise ValueError("Configure the verified LABS_EMAIL_FROM identity before drafting email")
            payload.update({"from": sender, "provider": "resend"})
        return self.store.stage(mid, kind, payload)

    def stage_whatsapp_chunks(self, mid, to):
        original = self.stage_delivery(mid, "whatsapp", to)
        item = self.store.out(original)
        text = item["payload"]["text"]
        if len(text) <= 4096:
            return [original]
        # No send of the parent. Every numbered chunk gets its own exact-word approval.
        self.store.settle(original, "superseded", {"reason": "Split into individually reviewed WhatsApp chunks"})
        parts = [text[i:i+3700] for i in range(0, len(text), 3700)]
        if len(parts) > 20:
            raise ValueError("Too many WhatsApp chunks; use reviewed email or a private file instead")
        return [self.store.stage(mid, "whatsapp", {**item["payload"], "text": f"({i+1}/{len(parts)}) " + part}) for i, part in enumerate(parts)]

    def execute(self, oid):
        if os.environ.get("LABS_LIVE_EFFECTS") != "explicitly-approved":
            raise ValueError("Live effects disabled. Export/review first; obtain deployment and per-effect approval.")
        out = self.store.out(oid)
        kind, payload = out["kind"], out["payload"]
        if kind in ("email", "whatsapp"):
            # A separately configured owner-confirmed test destination is required.
            allowed = os.environ.get("LABS_TEST_EMAIL" if kind == "email" else "LABS_TEST_PHONE")
            if not allowed or payload["to"] != allowed:
                raise ValueError("Only the configured owner test destination is allowed in this build")
        if kind in ("join", "leave", "chat") and not self.vexa:
            raise ValueError("Vexa not configured")
        if kind == "whatsapp":
            if not payload.get("chat_id") or payload["chat_id"] != os.environ.get("LABS_OPENWA_TEST_CHAT_ID"):
                raise ValueError("Verify the owner test chat ID and restage for review first")
            if len(payload["text"]) > 4096:
                raise ValueError("WhatsApp payload too long; stage reviewed chunks")
        if kind == "whatsapp":
            last = self.store.db.execute("SELECT created FROM outbox WHERE kind='whatsapp' AND status IN ('sending','sent','unknown') AND id!=? ORDER BY created DESC LIMIT 1", (oid,)).fetchone()
            if last and time.time() - last[0] < 10:
                raise ValueError("Wait before another WhatsApp send; minimum 10-second review pacing")
        self.store.claim(oid)
        try:
            if kind in ("join", "leave", "chat"):
                result = self.vexa.perform(kind, payload)
                # Queued chat is not posted; join request is not admission.
                status = "queued" if kind == "chat" else "submitted"
            elif kind == "email":
                result, status = resend_send(payload, "labs-meet/" + oid), "accepted"
            elif kind == "whatsapp":
                result, status = whatsapp_send(payload), "sent"
            else:
                raise ValueError("Unsupported effect")
        except Exception:
            self.store.settle(oid, "unknown", {"reason": "Attempt failed or response missing. Reconcile upstream before any retry."})
            raise
        self.store.settle(oid, status, result)
        return self.store.out(oid)

    def reconcile_chat(self, oid):
        out = self.store.out(oid)
        if out["kind"] != "chat" or out["status"] != "queued":
            raise ValueError("Only a queued chat with a provider request ID can be reconciled")
        result = json.loads(out["result"])
        request_id = result.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("No provider request ID; manual reconciliation required")
        res = self.vexa.chat_status(out["payload"]["code"], request_id)
        status = res.get("status")
        if status not in ("queued", "posted", "failed", "unconfirmed"):
            raise ValueError("Unknown provider status")
        self.store.settle(oid, status, res)
        return self.store.out(oid)
