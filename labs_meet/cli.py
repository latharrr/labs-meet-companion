import argparse
import json
import os
import sys
import time
from pathlib import Path
from .store import Store
from .service import Companion
from .adapters import Vexa
from .core import minutes
from .ai import GroundedAI


def main(argv=None):
    p = argparse.ArgumentParser(description="Lathar Labs Meet companion. Live effects off by default.")
    p.add_argument("--db", default=".local/labs.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create"); c.add_argument("link"); c.add_argument("--title", required=True); c.add_argument("--consent", required=True)
    for name in ["join", "leave", "sync", "notes", "ai-notes", "delete"]:
        c = sub.add_parser(name); c.add_argument("meeting")
    c = sub.add_parser("watch"); c.add_argument("meeting"); c.add_argument("--interval", type=int, default=10); c.add_argument("--cycles", type=int, default=12)
    c = sub.add_parser("import"); c.add_argument("meeting"); c.add_argument("file"); c.add_argument("--baseline", action="store_true")
    c = sub.add_parser("deliver"); c.add_argument("meeting"); c.add_argument("--kind", choices=["email","whatsapp"], required=True); c.add_argument("--to", required=True)
    c = sub.add_parser("review"); c.add_argument("outbox")
    c = sub.add_parser("approve"); c.add_argument("outbox"); c.add_argument("--digest", required=True)
    for name in ["execute", "reconcile"]:
        c = sub.add_parser(name); c.add_argument("outbox")
    sub.add_parser("config-status")
    sub.add_parser("recover")
    sub.add_parser("list")
    sub.add_parser("demo")
    c = sub.add_parser("serve"); c.add_argument("--port", type=int, default=8765)
    a = p.parse_args(argv)
    store = Store(a.db)
    vexa = Vexa(os.environ["LABS_VEXA_URL"], os.environ["LABS_VEXA_KEY"]) if os.environ.get("LABS_VEXA_URL") and os.environ.get("LABS_VEXA_KEY") else None
    ai = GroundedAI(os.environ.get("LABS_AI_URL", "https://api.groq.com/openai/v1"), os.environ["LABS_AI_KEY"], os.environ.get("LABS_AI_MODEL", "openai/gpt-oss-20b")) if os.environ.get("LABS_AI_KEY") else None
    app = Companion(store, vexa, ai)
    result = None
    if a.cmd == "create": result = {"meeting": app.create(a.title, a.link, a.consent)}
    elif a.cmd in ("join", "leave"):
        result = {"outbox": app.stage_join(a.meeting) if a.cmd == "join" else store.stage(a.meeting, "leave", {"code": store.meeting(a.meeting)["code"]})}
    elif a.cmd == "sync": result = {"chat_drafts": app.sync(a.meeting, baseline=True)}
    elif a.cmd == "watch":
        if a.interval < 5 or not 1 <= a.cycles <= 360:
            raise ValueError("Use interval >=5 seconds and 1..360 cycles")
        app.sync(a.meeting, baseline=True)  # Never respond to historical backlog.
        for _ in range(a.cycles):
            time.sleep(a.interval)
            print(json.dumps({"chat_drafts": app.sync(a.meeting)}), flush=True)
        return
    elif a.cmd == "import": result = {"chat_drafts": app.ingest(a.meeting, json.loads(Path(a.file).read_text()), a.baseline)}
    elif a.cmd == "ai-notes": result = app.generate_notes(a.meeting)
    elif a.cmd == "notes": result = store.ai_notes(a.meeting) or minutes(store.segments(a.meeting))
    elif a.cmd == "deliver": result = {"outbox": app.stage_whatsapp_chunks(a.meeting, a.to) if a.kind == "whatsapp" else [app.stage_delivery(a.meeting, a.kind, a.to)]}
    elif a.cmd == "review": result = store.out(a.outbox)
    elif a.cmd == "approve": store.approve(a.outbox, a.digest); result = {"status": "approved, not sent"}
    elif a.cmd == "execute": result = app.execute(a.outbox)
    elif a.cmd == "reconcile": result = app.reconcile_chat(a.outbox)
    elif a.cmd == "delete": store.delete(a.meeting); result = {"status": "local meeting deleted; provider data/backups are separate"}
    elif a.cmd == "config-status":
        from .config import status
        result = status()
    elif a.cmd == "recover": result = {"unknown": store.recover(), "note": "Reconcile provider before retry. Stop other workers before recovery."}
    elif a.cmd == "list": result = {"meetings": [dict(r) for r in store.db.execute("SELECT * FROM meetings ORDER BY created DESC")]}
    elif a.cmd == "demo":
        existing = store.db.execute("SELECT id FROM meetings WHERE title='Private-call rehearsal (synthetic)' LIMIT 1").fetchone()
        if existing: result = {"meeting": existing[0], "mode": "synthetic"}
        else:
            mid = app.create("Private-call rehearsal (synthetic)", "https://meet.google.com/abc-defg-hij", "Synthetic fixture. No participants, no real call.")
            drafts = app.ingest(mid, json.loads((Path(__file__).parent / "fixtures/demo.json").read_text()))
            delivery = app.stage_delivery(mid, "whatsapp", "+918221016809")
            result = {"meeting": mid, "chat_drafts": drafts, "delivery_draft": delivery, "mode": "synthetic"}
    elif a.cmd == "serve":
        from .web import serve
        store.db.close()
        serve(a.db, a.port)
        return
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        sys.exit(1)
