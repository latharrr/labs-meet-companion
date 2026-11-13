"""Explicitly configured network adapters. No secrets in stored payloads or logs."""
import json
import os
from urllib.parse import urlsplit, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def endpoint(base):
    p = urlsplit(base)
    if not p.hostname:
        raise ValueError("Endpoint needs a hostname")
    if p.username or p.password or p.query or p.fragment:
        raise ValueError("Endpoint cannot contain credentials/query/fragment")
    if not (p.scheme == "https" or p.scheme == "http" and p.hostname in ("localhost", "127.0.0.1", "::1")):
        raise ValueError("Use HTTPS, or loopback HTTP")
    return base.rstrip("/")


def request(base, path, key, method="GET", body=None, header="X-API-Key", extra_headers=None):
    url = endpoint(base) + path
    raw = None if body is None else json.dumps(body).encode()
    req = Request(url, data=raw, method=method, headers={header: key, "Content-Type": "application/json", **(extra_headers or {})})
    try:
        with build_opener(NoRedirect).open(req, timeout=20) as res:
            data = res.read(4_000_001)
            if len(data) > 4_000_000:
                raise ValueError("Response too large")
            return json.loads(data) if data else {}
    except HTTPError as e:
        # Never echo upstream content or secret-bearing URLs.
        code = e.code
        e.close()
        raise RuntimeError(f"Upstream HTTP {code}; no automatic retry") from None


class Vexa:
    def __init__(self, base, key):
        self.base, self.key = endpoint(base), key

    def transcript(self, code):
        return request(self.base, "/transcripts/google_meet/" + quote(code, safe=""), self.key)

    def perform(self, kind, payload):
        code = quote(payload["code"], safe="")
        if kind == "join":
            return request(self.base, "/bots", self.key, "POST", {
                "platform": "google_meet", "native_meeting_id": payload["code"],
                "bot_name": "Lathar Labs | Notes"})
        if kind == "leave":
            return request(self.base, "/bots/google_meet/" + code, self.key, "DELETE")
        if kind == "chat":
            return request(self.base, "/bots/google_meet/" + code + "/chat", self.key, "POST", {"text": payload["text"]})
        raise ValueError("Unknown Vexa operation")

    def chat_status(self, code, request_id):
        return request(self.base, f'/bots/google_meet/{quote(code,safe="")}/chat/{quote(request_id,safe="")}', self.key)


def whatsapp_send(payload):
    # Verified OpenWA 0.23.3 contract. Configure a dedicated test deployment/session/key.
    sid = os.environ["LABS_OPENWA_SESSION"]
    if not payload.get("chat_id") or payload["chat_id"] != os.environ.get("LABS_OPENWA_TEST_CHAT_ID"):
        raise ValueError("A live verified owner test chat ID is required; do not guess a WhatsApp lid")
    if len(payload["text"]) > 4096:
        raise ValueError("OpenWA text exceeds 4096 characters; review separate chunks first")
    result = request(os.environ["LABS_OPENWA_URL"], "/api/sessions/" + quote(sid, safe="") + "/messages/send-text",
                     os.environ["LABS_OPENWA_KEY"], "POST", {"chatId": payload["chat_id"], "text": payload["text"]})
    if not isinstance(result, dict) or not isinstance(result.get("messageId"), str):
        raise RuntimeError("Missing OpenWA message ID; uncertain outcome must be reconciled")
    return {"status": "sent", "provider": "openwa", "messageId": result["messageId"],
            "timestamp": result.get("timestamp"), "meaning": "Engine accepted/persisted SENT; not delivered/read"}


def resend_send(payload, idempotency_key):
    # Fixed official service base. No transcript-controlled URL, CC/BCC or attachments.
    result = request("https://api.resend.com", "/emails", "Bearer " + os.environ["LABS_RESEND_KEY"], "POST", {
        "from": payload["from"], "to": [payload["to"]], "subject": payload["subject"], "text": payload["text"]
    }, "Authorization", {"Idempotency-Key": idempotency_key})
    if not isinstance(result, dict) or not isinstance(result.get("id"), str):
        raise RuntimeError("No Resend email ID; outcome must be reconciled")
    return {"status": "accepted", "provider": "resend", "id": result["id"],
            "meaning": "API accepted; delivered/read not yet verified"}
