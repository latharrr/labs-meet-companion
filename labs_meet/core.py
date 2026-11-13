"""Pure meeting logic. Transcript/chat text is data, never executable instruction."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re
from urllib.parse import urlsplit

BOT_NAME = "Lathar Labs"
BOT_DISPLAY_NAME = "Lathar Labs | Notes"
MEET_CODE = re.compile(r"^[a-z]{3}-[a-z]{4}-[a-z]{3}$")


def meeting_code(link: str) -> str:
    if not isinstance(link, str):
        raise ValueError("Use an https://meet.google.com/abc-defg-hij link")
    p = urlsplit(link)
    code = p.path.strip("/")
    if (p.scheme != "https" or p.hostname != "meet.google.com" or p.username
            or p.password or p.port not in (None, 443) or p.fragment
            or not MEET_CODE.fullmatch(code)):
        raise ValueError("Use an https://meet.google.com/abc-defg-hij link")
    return code


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class Segment:
    id: str
    start: float
    end: float
    text: str
    speaker: str
    source: str = "audio"


def normalize(payload: dict) -> list[Segment]:
    if not isinstance(payload, dict) or not isinstance(payload.get("segments"), list):
        raise ValueError("Expected Vexa transcript object with segments list")
    result = {}
    for raw in payload["segments"]:
        if not isinstance(raw, dict) or raw.get("completed") is not True:
            continue  # pending speech is not evidence
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        if isinstance(raw.get("start"), bool) or isinstance(raw.get("end"), bool):
            raise ValueError("Invalid segment timing")
        try:
            start, end = float(raw.get("start", 0)), float(raw.get("end", raw.get("start", 0)))
        except (TypeError, ValueError):
            raise ValueError("Invalid segment timing") from None
        if not (0 <= start <= end < 1e9):
            raise ValueError("Invalid segment timing")
        source = str(raw.get("source", "audio"))
        # Legacy snapshots lack an ID. Stable times/speaker/source allow text revisions.
        sid = str(raw.get("segment_id") or "legacy-" + digest([start, end, raw.get("speaker"), source])[:20])
        result[sid] = Segment(sid, start, end, text.strip(), str(raw.get("speaker") or "Unknown speaker"), source)
    return sorted(result.values(), key=lambda x: (x.start, x.id))


def named_question(text: str, speaker: str) -> str | None:
    if speaker.strip().casefold() in {BOT_NAME.casefold(), BOT_DISPLAY_NAME.casefold()}:
        return None
    # Only direct leading addresses, not every casual mention of the company.
    m = re.match(r"^\s*@?Lathar\s+Labs\b\s*[:,?!-]?\s*(.+)$", text, re.I | re.S)
    return m.group(1).strip() if m else None


def answer(question: str, segments: list[Segment]) -> dict:
    """Extractive fallback: no external context, tool use, LLM cost or invented answer."""
    words = set(re.findall(r"\w{3,}", question.casefold())) - {
        "what", "the", "was", "were", "and", "did", "who", "this", "meeting", "please", "about"}
    candidates = []
    for s in segments:
        if s.source == "chat":
            continue
        score = len(words & set(re.findall(r"\w{3,}", s.text.casefold())))
        if score:
            candidates.append((score, s))
    chosen = [s for _, s in sorted(candidates, key=lambda x: (-x[0], x[1].start))[:3]]
    if re.search(r"\b(summarize|summarise|recap|summary)\b", question, re.I):
        chosen = [s for s in segments if s.source != "chat"][-4:]
    elif re.search(r"\b(decisions?|decided|agreed)\b", question, re.I):
        chosen = [s for s in segments if s.source != "chat" and re.search(r"\b(decided|agreed|decision)\b", s.text, re.I)][:3]
    elif re.search(r"\b(tasks?|actions?|todo)\b", question, re.I):
        chosen = [s for s in segments if s.source != "chat" and re.search(r"\b(I will|I'll|we need to|action item|todo)\b", s.text, re.I)][:3]
    text = "I couldn't find that in the confirmed meeting notes yet."
    if chosen:
        text = "From the meeting notes:\n" + "\n".join(
            f'[{int(s.start)//60:02d}:{int(s.start)%60:02d}] {s.speaker}: "{s.text[:420]}"' for s in chosen)
    return {"text": text, "evidence": [s.id for s in chosen], "mode": "extractive"}


def minutes(segments: list[Segment]) -> dict:
    """Conservative, reviewable highlights. Candidates are not confirmed decisions/tasks."""
    audio = [s for s in segments if s.source != "chat"]
    def item(s):
        return {"quote": s.text, "evidence": s.id, "speaker": s.speaker,
                "start": s.start, "owner": None, "deadline": None}
    return {
        "status": "draft - organizer review required",
        "summary": [item(s) for s in audio[:8]],
        "decision_candidates": [item(s) for s in audio if re.search(r"\b(decided|agreed|decision|we will go with)\b", s.text, re.I)],
        "action_candidates": [item(s) for s in audio if re.search(r"\b(I will|I'll|we need to|action item|todo)\b", s.text, re.I)],
        "warning": "Extractive candidates, not AI-verified decisions. Owner and deadline stay unstated until reviewed.",
    }


def delivery_text(title: str, note: dict, segments: list[Segment]) -> str:
    lines = [title, "DRAFT: review before sharing", "", "Meeting highlights"]
    lines += [f'[{x["start"]:.1f}s] {x["speaker"]}: {x["quote"]}' for x in note["summary"]]
    for key, label in [("decision_candidates", "Possible decisions"), ("action_candidates", "Possible tasks")]:
        lines += ["", label]
        lines += [f'{x["quote"]} [evidence: {x["evidence"]}; owner/deadline not set]' for x in note[key]] or ["None identified"]
    lines += ["", "Transcript (confirmed segments only)"]
    lines += [f'[{s.start:.1f}s] {s.speaker}: {s.text}' for s in segments]
    return "\n".join(lines)
