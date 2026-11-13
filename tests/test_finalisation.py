"""Regression tests for the code-first finalisation pass.

Synthetic / loopback / no-network only. No live Meet, provider, model
or delivery call is made here. A fake Vexa stub stands in for the
meeting service; the real HTTP double lives in test_http_integration.
"""
import base64
from http.server import HTTPServer
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from labs_meet.core import meeting_code, normalize
from labs_meet.store import Store
from labs_meet.service import Companion
from labs_meet.config import status as config_status

ROOT = Path(__file__).parent.parent
FIXTURE = json.loads((ROOT / "fixtures/demo.json").read_text())
FICTIONAL_PHONE = "+15555550199"


def make_app(tmp):
    store = Store(Path(tmp) / "data.db")
    app = Companion(store)
    mid = app.create("Test", "https://meet.google.com/abc-defg-hij", "Synthetic test only")
    return store, app, mid


class FakeVexa:
    """Minimal Vexa stub. perform() returns a request_id for chat only."""

    def __init__(self, transcript=None):
        self._transcript = transcript or FIXTURE
        self.calls = []

    def transcript(self, code):
        return self._transcript

    def perform(self, kind, payload):
        self.calls.append(kind)
        if kind == "chat":
            return {"status": "queued", "request_id": "result-1"}
        return {"status": "starting" if kind == "join" else "stopping"}

    def chat_status(self, code, request_id):
        return {"status": "posted", "request_id": request_id}


class NoRequestIdVexa(FakeVexa):
    def perform(self, kind, payload):
        return {}


class ValidationTests(unittest.TestCase):
    def test_meet_link_rejects_fragment_and_non_string(self):
        with self.assertRaises(ValueError):
            meeting_code("https://meet.google.com/abc-defg-hij#section")
        with self.assertRaises(ValueError):
            meeting_code(None)
        with self.assertRaises(ValueError):
            meeting_code(123)

    def test_normalize_rejects_bad_timing_types(self):
        for start, end in [(None, 1), ("x", 1), (True, 1), (0, None), (0, "y")]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                normalize({"segments": [{"completed": True, "text": "x", "start": start, "end": end}]})

    def test_ingest_rejects_non_dict_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, app, mid = make_app(tmp)
            with self.assertRaises(ValueError):
                app.ingest(mid, [{"segments": []}])
            with self.assertRaises(ValueError):
                app.ingest(mid, None)
            store.db.close()

    def test_no_dotenv_loading_in_package(self):
        for path in (ROOT / "labs_meet").rglob("*.py"):
            text = path.read_text()
            self.assertNotIn("dotenv", text, path.name)
            self.assertNotIn("load_dotenv", text, path.name)

    def test_old_demo_phone_number_is_gone(self):
        # The removed number is assembled here so this test file itself
        # does not contain the literal it is checking for.
        old = "+91" + "82210" + "16809"
        for path in ROOT.rglob("*"):
            if ".git" in path.parts or "__pycache__" in path.parts or path.is_dir():
                continue
            if path.resolve() == Path(__file__).resolve():
                continue
            if path.suffix in (".py", ".md", ".json", ".txt", ".toml"):
                self.assertNotIn(old, path.read_text(errors="ignore"), str(path))

    def test_package_resources_present(self):
        import labs_meet

        self.assertEqual(labs_meet.__version__, "0.1.0")
        self.assertTrue((ROOT / "labs_meet" / "fixtures" / "demo.json").exists())
        self.assertTrue((ROOT / "labs_meet" / "static" / "app.js").exists())


class OutboxConcurrencyTests(unittest.TestCase):
    def test_concurrent_stage_returns_same_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.db"
            store, app, mid = make_app(tmp)
            payload = {"code": "abc-defg-hij", "consent": "x", "notice": "n"}
            # Stage once so the payload exists, then race five fresh writers.
            first = store.stage(mid, "join", payload)
            store.db.close()
            results, errors = [], []
            barrier = threading.Barrier(5)

            def worker():
                try:
                    barrier.wait(timeout=10)
                    s = Store(path)
                    try:
                        results.append(s.stage(mid, "join", payload))
                    finally:
                        s.db.close()
                except Exception as exc:  # noqa: BLE001 - record for assertion
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=20)
            self.assertEqual(errors, [])
            self.assertEqual(set(results), {first})
            s = Store(path)
            try:
                self.assertEqual(s.db.execute("SELECT count(*) FROM outbox").fetchone()[0], 1)
            finally:
                s.db.close()

    def test_concurrent_claim_only_one_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.db"
            store, app, mid = make_app(tmp)
            oid = app.stage_join(mid)
            store.approve(oid, store.out(oid)["digest"])
            store.db.close()
            successes, failures = [], []
            barrier = threading.Barrier(5)

            def worker():
                try:
                    barrier.wait(timeout=10)
                    s = Store(path)
                    try:
                        s.claim(oid)
                        successes.append(True)
                    finally:
                        s.db.close()
                except ValueError:
                    failures.append(True)

            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=20)
            self.assertEqual(len(successes), 1)
            self.assertEqual(len(failures), 4)

    def test_final_status_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, app, mid = make_app(tmp)
            with patch.dict(os.environ, {"LABS_EMAIL_FROM": "Synthetic <test@example.test>"}):
                app.ingest(mid, FIXTURE)
                oid = app.stage_delivery(mid, "email", "owner@example.test")
            store.approve(oid, store.out(oid)["digest"])
            store.claim(oid)
            store.settle(oid, "sent", {"id": "email-1"})
            with self.assertRaises(ValueError):
                store.settle(oid, "unknown", {"reason": "late"})
            self.assertEqual(store.out(oid)["status"], "sent")
            store.db.close()


class WhatsAppChunkTests(unittest.TestCase):
    def _long_meeting(self, tmp):
        store, app, mid = make_app(tmp)
        segments = [
            {"segment_id": f"s{i}", "start": i * 10, "end": i * 10 + 5,
             "completed": True, "speaker": "Demo", "text": "word " * 400}
            for i in range(50)
        ]
        app.ingest(mid, {"segments": segments})
        return store, app, mid

    def test_too_many_chunks_leaves_original_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, app, mid = self._long_meeting(tmp)
            with patch.dict(os.environ, {"LABS_EMAIL_FROM": "Synthetic <test@example.test>"}):
                original = app.stage_delivery(mid, "whatsapp", FICTIONAL_PHONE)
            self.assertEqual(store.out(original)["status"], "draft")
            with self.assertRaises(ValueError):
                app.stage_whatsapp_chunks(mid, FICTIONAL_PHONE)
            self.assertEqual(store.out(original)["status"], "draft")
            store.db.close()

    def test_approved_delivery_cannot_be_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, app, mid = self._long_meeting(tmp)
            with patch.dict(os.environ, {"LABS_EMAIL_FROM": "Synthetic <test@example.test>"}):
                original = app.stage_delivery(mid, "whatsapp", FICTIONAL_PHONE)
            store.approve(original, store.out(original)["digest"])
            with self.assertRaises(ValueError):
                app.stage_whatsapp_chunks(mid, FICTIONAL_PHONE)
            self.assertEqual(store.out(original)["status"], "approved")
            store.db.close()

    def test_normal_split_supersedes_parent_only_after_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A delivery long enough to split, but under the 20-chunk cap.
            store, app, mid = make_app(tmp)
            segments = [
                {"segment_id": f"s{i}", "start": i * 10, "end": i * 10 + 5,
                 "completed": True, "speaker": "Demo", "text": "word " * 400}
                for i in range(3)
            ]
            app.ingest(mid, {"segments": segments})
            with patch.dict(os.environ, {"LABS_EMAIL_FROM": "Synthetic <test@example.test>"}):
                original = app.stage_delivery(mid, "whatsapp", FICTIONAL_PHONE)
                chunks = app.stage_whatsapp_chunks(mid, FICTIONAL_PHONE)
            self.assertGreater(len(chunks), 1)
            self.assertEqual(store.out(original)["status"], "superseded")
            for chunk_id in chunks:
                self.assertEqual(store.out(chunk_id)["status"], "draft")
            store.db.close()


class ExecuteAndReconcileTests(unittest.TestCase):
    def test_unsupported_kind_stays_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, app, mid = make_app(tmp)
            oid = store.stage(mid, "mystery", {"x": 1})
            store.approve(oid, store.out(oid)["digest"])
            with patch.dict(os.environ, {"LABS_LIVE_EFFECTS": "explicitly-approved"}):
                with self.assertRaises(ValueError):
                    app.execute(oid)
            self.assertEqual(store.out(oid)["status"], "approved")
            store.db.close()

    def test_chat_without_request_id_is_unknown_not_queued(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "data.db")
            app = Companion(store, NoRequestIdVexa())
            mid = app.create("Test", "https://meet.google.com/abc-defg-hij", "Synthetic")
            drafts = app.ingest(mid, FIXTURE)
            self.assertEqual(len(drafts), 1)
            oid = drafts[0]
            store.approve(oid, store.out(oid)["digest"])
            with patch.dict(os.environ, {"LABS_LIVE_EFFECTS": "explicitly-approved"}):
                with self.assertRaises(RuntimeError):
                    app.execute(oid)
            self.assertEqual(store.out(oid)["status"], "unknown")
            store.db.close()

    def test_reconcile_without_vexa_or_result_is_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, app, mid = make_app(tmp)
            drafts = app.ingest(mid, FIXTURE)
            oid = drafts[0]
            store.db.execute("UPDATE outbox SET status='queued', result=NULL WHERE id=?", (oid,))
            store.db.commit()
            with self.assertRaises(ValueError):
                app.reconcile_chat(oid)
            # With a result but no Vexa configured, the error is still a
            # ValueError, not an AttributeError from a None adapter.
            store.db.execute("UPDATE outbox SET result=? WHERE id=?", ('{"request_id":"r1"}', oid))
            store.db.commit()
            with self.assertRaises(ValueError):
                app.reconcile_chat(oid)
            store.db.close()

    def test_resolve_unknown_and_close_submitted_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "data.db")
            app = Companion(store, FakeVexa())
            mid = app.create("Test", "https://meet.google.com/abc-defg-hij", "Synthetic")
            with patch.dict(os.environ, {"LABS_EMAIL_FROM": "Synthetic <test@example.test>"}):
                app.ingest(mid, FIXTURE)
                oid = app.stage_delivery(mid, "email", "owner@example.test")
            store.approve(oid, store.out(oid)["digest"])
            store.claim(oid)
            store.settle(oid, "unknown", {"reason": "timeout"})
            out = app.resolve_unknown(oid, "accepted", provider_id="email-123")
            self.assertEqual(out["status"], "accepted")
            self.assertTrue(json.loads(out["result"])["manual_reconciliation"])
            # A final item cannot be resolved again.
            with self.assertRaises(ValueError):
                app.resolve_unknown(oid, "sent", provider_id="email-123")
            store.db.close()


class OneCallQuotaTests(unittest.TestCase):
    def test_second_join_blocked_until_leave_or_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "data.db")
            app = Companion(store, FakeVexa())
            mid_a = app.create("A", "https://meet.google.com/aaa-bbbb-ccc", "Synthetic A")
            mid_b = app.create("B", "https://meet.google.com/ddd-eeee-fff", "Synthetic B")
            with patch.dict(os.environ, {"LABS_LIVE_EFFECTS": "explicitly-approved"}):
                join_a = app.stage_join(mid_a)
                store.approve(join_a, store.out(join_a)["digest"])
                self.assertEqual(app.execute(join_a)["status"], "submitted")
                join_b = app.stage_join(mid_b)
                store.approve(join_b, store.out(join_b)["digest"])
                with self.assertRaises(ValueError):
                    app.execute(join_b)
                self.assertEqual(store.out(join_b)["status"], "approved")
                leave_a = store.stage(mid_a, "leave", {"code": "aaa-bbbb-ccc"})
                store.approve(leave_a, store.out(leave_a)["digest"])
                self.assertEqual(app.execute(leave_a)["status"], "submitted")
                self.assertEqual(app.execute(join_b)["status"], "submitted")
                # A submitted join can be closed as failed, releasing quota.
                join_c_mid = app.create("C", "https://meet.google.com/ggg-hhhh-iii", "Synthetic C")
                join_c = app.stage_join(join_c_mid)
                store.approve(join_c, store.out(join_c)["digest"])
                with self.assertRaises(ValueError):
                    app.execute(join_c)
                app.resolve_unknown(join_b, "failed", reason="Host denied admission")
                self.assertEqual(app.execute(join_c)["status"], "submitted")
            store.db.close()


class CliSyncTests(unittest.TestCase):
    def test_cli_sync_drafts_only_after_first_baseline_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "data.db")
            new_question = {
                "segment_id": "c2", "start": 50, "end": 50, "completed": True,
                "speaker": "Demo teammate", "source": "chat",
                "text": "@Lathar Labs, what about Hinglish?",
            }
            second = json.loads(json.dumps(FIXTURE))
            second["segments"].append(new_question)
            calls = {"n": 0}

            class SequencedVexa:
                def transcript(self, code):
                    calls["n"] += 1
                    return FIXTURE if calls["n"] == 1 else second

                def perform(self, kind, payload):
                    return {"status": "starting"}

                def chat_status(self, code, request_id):
                    return {"status": "posted", "request_id": request_id}

            from labs_meet import cli as cli_module

            env = {"LABS_VEXA_URL": "http://127.0.0.1:9", "LABS_VEXA_KEY": "test"}
            with patch.dict(os.environ, env, clear=True), patch.object(
                cli_module, "Vexa", return_value=SequencedVexa()
            ):
                out = io.StringIO()
                with redirect_stdout(out):
                    cli_module.main(["--db", db, "create", "https://meet.google.com/abc-defg-hij",
                                     "--title", "T", "--consent", "Synthetic"])
                mid = json.loads(out.getvalue())["meeting"]
                out = io.StringIO()
                with redirect_stdout(out):
                    cli_module.main(["--db", db, "sync", mid])
                self.assertEqual(json.loads(out.getvalue())["chat_drafts"], [])
                out = io.StringIO()
                with redirect_stdout(out):
                    cli_module.main(["--db", db, "sync", mid])
                drafts = json.loads(out.getvalue())["chat_drafts"]
                self.assertEqual(len(drafts), 1)


class ConfigAndAdapterTests(unittest.TestCase):
    def test_config_flags_malformed_destinations(self):
        env = {"LABS_TEST_EMAIL": "not-an-email", "LABS_EMAIL_FROM": "also-bad",
               "LABS_TEST_PHONE": "123"}
        with patch.dict(os.environ, env, clear=True):
            invalid = config_status()["invalid_fields"]
        self.assertIn("LABS_TEST_EMAIL", invalid)
        self.assertIn("LABS_EMAIL_FROM", invalid)
        self.assertIn("LABS_TEST_PHONE", invalid)
        with patch.dict(os.environ, {"LABS_EMAIL_FROM": "Labs <test@example.test>"}, clear=True):
            self.assertNotIn("LABS_EMAIL_FROM", config_status().get("invalid_fields", []))

    def test_missing_provider_keys_raise_value_error_not_key_error(self):
        from labs_meet.adapters import whatsapp_send, resend_send

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                whatsapp_send({"chat_id": "x", "text": "hi"})
            with self.assertRaises(ValueError):
                resend_send({"from": "a@b.test", "to": "c@d.test", "subject": "s", "text": "t"}, "k")


class WebAuthTests(unittest.TestCase):
    def test_post_without_auth_is_401(self):
        from labs_meet.web import handler

        with tempfile.TemporaryDirectory() as tmp:
            env = {"LABS_UI_USER": "owner", "LABS_UI_PASSWORD": "local-test-only",
                   "LABS_UI_HOST": "meetbot.143.lat", "LABS_UI_OPERATIONS": "explicitly-approved"}
            with patch.dict(os.environ, env, clear=True):
                server = HTTPServer(("127.0.0.1", 0), handler(tmp + "/notes.db", 8765))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    from urllib.request import Request, urlopen
                    from urllib.error import HTTPError

                    url = f"http://127.0.0.1:{server.server_port}/api/operate"
                    req = Request(url, headers={"Host": "meetbot.143.lat", "Content-Type": "application/json",
                                                "Origin": "https://meetbot.143.lat", "X-Labs-CSRF": "x"},
                                  data=b'{"action":"create"}')
                    with self.assertRaises(HTTPError) as ctx:
                        urlopen(req)
                    self.assertEqual(ctx.exception.code, 401)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()


if __name__ == "__main__":
    unittest.main()
