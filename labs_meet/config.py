"""Non-secret configuration checks. This never validates account access or quota."""
import os
import re
from .adapters import endpoint

EMAIL_RE = re.compile(r"[^\s@<>;,\r\n]+@[^\s@<>;,\r\n]+\.[^\s@<>;,\r\n]+")
PHONE_RE = re.compile(r"\+[1-9][0-9]{7,14}")


def _email_ok(value):
    if not isinstance(value, str) or not value.strip():
        return False
    if "<" in value and ">" in value:
        try:
            inner = value[value.index("<") + 1:value.index(">")]
        except ValueError:
            return False
        return bool(EMAIL_RE.fullmatch(inner.strip()))
    return bool(EMAIL_RE.fullmatch(value.strip()))


def status():
    required = {
        "vexa": ["LABS_VEXA_URL", "LABS_VEXA_KEY"],
        "groq_ai": ["LABS_AI_KEY"],
        "resend": ["LABS_RESEND_KEY", "LABS_EMAIL_FROM", "LABS_TEST_EMAIL"],
        "openwa": ["LABS_OPENWA_URL", "LABS_OPENWA_KEY", "LABS_OPENWA_SESSION", "LABS_OPENWA_TEST_CHAT_ID", "LABS_TEST_PHONE"],
    }
    result = {"network_checked":False,"live_effects_enabled":os.environ.get("LABS_LIVE_EFFECTS")=="explicitly-approved",
              "ai_network_enabled":os.environ.get("LABS_AI_EFFECTS")=="explicitly-approved", "providers":{}}
    for provider,fields in required.items():
        missing=[f for f in fields if not os.environ.get(f)]
        result["providers"][provider]={"configured":not missing,"missing_fields":missing,"account_access":"unverified","quota":"unverified"}
    # Validate without printing endpoints or secrets.
    for key in ["LABS_VEXA_URL","LABS_AI_URL","LABS_OPENWA_URL"]:
        if os.environ.get(key):
            try:endpoint(os.environ[key])
            except ValueError:result.setdefault("invalid_fields",[]).append(key)
    # A present-but-malformed destination is not "configured": report it
    # instead of letting stage/execute fail later with a confusing error.
    for key in ("LABS_TEST_EMAIL", "LABS_EMAIL_FROM"):
        if os.environ.get(key) and not _email_ok(os.environ[key]):
            result.setdefault("invalid_fields", []).append(key)
    if os.environ.get("LABS_TEST_PHONE") and not PHONE_RE.fullmatch(os.environ["LABS_TEST_PHONE"]):
        result.setdefault("invalid_fields", []).append("LABS_TEST_PHONE")
    return result
