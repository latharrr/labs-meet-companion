"""Non-secret configuration checks. This never validates account access or quota."""
import os
from .adapters import endpoint


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
    return result
