# Isolated deployment handoff - source/docs only

This is a handoff checklist for an owner/operator to use *after* this
code pass. It contains no live proof, no host diagnostics, no account
data, no keys and no transcripts. Nothing in this file deploys, starts
or joins anything. Do not assume a full ARM meeting-service image
exists: Gate M1 in `deploy/ROLLOUT-GATES.md` is still open.

Source is public; meeting data and the hosted owner UI must remain
private. No redistribution licence has been chosen for the new
companion code, so the code is visible but no reuse rights are granted.

## 1. Components and contracts

| Component | Contract in this repo | Notes |
|---|---|---|
| Companion (Python, stdlib only, SQLite) | `labs_meet/`; CLI `python3 -m labs_meet.cli --help`; loopback UI on `127.0.0.1` only | No runtime pip dependencies. No `.env` auto-loading. Live/AI effects off unless `LABS_LIVE_EFFECTS=explicitly-approved` / `LABS_AI_EFFECTS=explicitly-approved` are set by the operator. |
| Meeting service (Vexa, pinned) | Vexa source `6b26f7b921756d6db128d42cd70b4b7046381407`; gateway routes in `deploy/meeting-gateway.py` (7 routes only); `deploy/prepare-meeting-only.py` generates a meeting-only review tree, it does not build or deploy | Stock Vexa bot release image is amd64-only; the full ARM meeting-server image has not completed. Do not claim a boot from the worker/synthetic smoke alone. |
| Speech | Groq `whisper-large-v3-turbo` through Vexa's transcription client; `TRANSCRIPTION_SERVICE_URL=https://api.groq.com/openai`, `TRANSCRIPTION_MODEL=whisper-large-v3-turbo` | One speech pipeline. Verify terms, audio/text data route, quota and cost before using credentials. No live audio test has passed. |
| Text AI | Groq `openai/gpt-oss-20b` at `/openai/v1/chat/completions`; grounded answers must cite exact transcript quotes | No tool calls, no cross-meeting memory, transcript text is data not instructions. No live model quality test has passed. |
| Email | Resend `POST /emails`, idempotency key `labs-meet/<outbox-id>`, sender from `LABS_EMAIL_FROM` | `accepted` is API acceptance, not delivery/read. Owner test destination only. |
| WhatsApp | Separate OpenWA 0.23.3 session/bridge, `POST /api/sessions/{sessionId}/messages/send-text`, verified owner test chat ID only | Never reuse the existing receptionist session. Unofficial-API ban/compliance risk remains; a separate session reduces coupling, not that risk. `sent` is engine acceptance, not delivery/read. |
| State | SQLite, file mode 0600, parent dirs 0700, WAL | Not encrypted by the app. One trusted operator, one effect worker per database. Local deletion does not erase upstream copies or backups. |

Keep the WhatsApp receptionist separate at every step: separate
session, key, chat ID, credentials and test destination. No shared
session, no shared provider key, no shared database.

## 2. Configuration that must be provisioned separately

All values are injected by the operator/secret manager, never committed
and never pasted into chat, a terminal history or a source file.
`config-status` reports only whether fields are present and whether
their *format* is valid; it never checks account access or quota.

- Vexa: `LABS_VEXA_URL` (HTTPS, or loopback HTTP), `LABS_VEXA_KEY` (dedicated)
- AI: `LABS_AI_URL` (default `https://api.groq.com/openai/v1`), `LABS_AI_KEY` (dedicated), `LABS_AI_MODEL` (default `openai/gpt-oss-20b`)
- Email: `LABS_RESEND_KEY` (dedicated, send-only, scoped to 143.lat when supported), `LABS_EMAIL_FROM` (verified 143.lat sender), `LABS_TEST_EMAIL` (one owner-confirmed address)
- WhatsApp: `LABS_OPENWA_URL`, `LABS_OPENWA_KEY`, `LABS_OPENWA_SESSION` (dedicated), `LABS_OPENWA_TEST_CHAT_ID` (verified, never guessed from a phone number), `LABS_TEST_PHONE` (owner-confirmed E.164)
- Owner UI: `LABS_UI_USER` + `LABS_UI_PASSWORD` (both together, or neither), `LABS_UI_HOST` (plain DNS hostname, e.g. `meetbot.143.lat`), `LABS_UI_OPERATIONS=explicitly-approved`
- Gates: `LABS_LIVE_EFFECTS=explicitly-approved`, `LABS_AI_EFFECTS=explicitly-approved` - technical switches only, not consent or spending authority
- Meeting service (from `deploy/meeting-entrypoint.py`): separate
  `DB_*`, `REDIS_PASSWORD`, `ADMIN_API_TOKEN`, `INTERNAL_API_SECRET`,
  `RUNTIME_API_TOKEN`, `VEXA_TERMINAL_SESSION_SECRET` - each at least
  32 URL-safe characters, provisioned separately. Forbidden inherited
  fields (including any `LABS_RESEND_*`, `LABS_OPENWA_*`, `LABS_AI_*`,
  `ANTHROPIC_*` / `CLAUDE_*` values) are stripped by the entrypoint.

Before any live step, record: provider quotas and current costs,
exact 143.lat sender, owner test destinations, transcript/audio
retention window, and the measured capacity of the actual target host.
Decide retention *before* the first real call; the proposed default is
to avoid raw-audio retention unless needed and approved.

## 3. Health / readiness checks (no live call needed to run these)

Run in order, stop on the first failure, and record the evidence
for each check. A passed check here does not prove a later gate.

1. Clean clone: `git clone https://github.com/latharrr/labs-meet-companion.git`,
   `python3 -m unittest discover -s tests`, demo + loopback UI smoke
   (see §6). All providers unconfigured, live/AI effects off.
2. `python3 -m labs_meet.cli config-status` - every required field
   present, no field in `invalid_fields`, no secrets echoed.
3. Meeting-service image: digest recorded, required services start in
   isolation, safe teardown works, private image retrieval verified.
   No host Docker socket or unrelated credentials exposed. **Not yet
   done - Gate M1 is open.**
4. Service readiness: PostgreSQL ready (bounded `pg_isready` check in
   the entrypoint), Valkey/Redis ready, gateway route contract matches
   `deploy/meeting-gateway.py` (7 routes; omitted routes 404,
   unauthenticated requests 401, wrong methods 405 - see
   `deploy/test-gateway-contract.py`, which needs the pinned gateway
   venv and is not a live test).
5. Owner UI: TLS at the proxy, HTTP Basic on every request, exact
   Origin + per-process CSRF on writes, Host allow-list, no-store
   responses, loopback-only listener. Unauthenticated requests must
   not read transcripts or operate the bot. Test the negative cases.
6. One-call quota: Vexa owner cap is exactly 1
   (`deploy/bootstrap-owner.py` refuses any other cap and refuses to
   mint a duplicate token), *and* the companion's DB-backed guard is
   exercised - see §4. Both caps must be set; neither alone is proof.
7. Retention/deletion: `delete MEETING_ID` removes local segments,
   outbox, dedupe and notes, then checkpoints and vacuums. Verify
   separately what remains upstream (Vexa recordings, provider logs,
   backups) - local deletion is not upstream deletion.

## 4. One-call quota tests (synthetic, in this repo)

`tests/test_finalisation.py::OneCallQuotaTests` proves the companion
guard with a fake Vexa stub, not with a live service:

- a second join fails while a first join is submitted, sending or unknown;
- simultaneous distinct join claims serialize, so only one claims;
- a leave still sending does not release the guard;
- the second join stays approved (not claimed, not sent);
- leaving the first meeting releases the guard, and the second join
  then succeeds;
- a submitted join can be closed as failed via
  `resolve OUTBOX_ID --status failed --reason "…"`, which also
  releases the guard.

The live equivalent (to be run only after Gates M1–M3 pass, with a
consenting test call) is: join call 1, attempt join call 2 and confirm
it is refused at both the companion and the Vexa cap, leave call 1,
then join call 2 and confirm it succeeds. Record the provider
responses; do not infer the cap from configuration alone.

## 5. Init / child cleanup

- The companion is a single process; stop it with Ctrl-C / the
  service manager and confirm the loopback port is released and no
  effect worker is still running before `recover`.
- The meeting service uses supervisord (`deploy/prepare-meeting-only.py`
  keeps only `redis`, `admin-api`, `runtime`, `meeting-api`,
  `gateway`; agent/terminal/model-proxy/MCP programs are removed, and
  the runtime agent worker is `/usr/bin/false`). Verify on the target
  that stopping the supervisor stops every child (gateway, meeting
  API, runtime, bot worker, browser worker) and that no orphaned
  Chromium/browser process or bot remains in a meeting. Do not assume
  this from a local test - check it on the target host after M2.
- `recover` in the companion marks `sending` outbox items as
  `unknown` only after all other workers are stopped. Reconcile each
  unknown item with its provider (or with `resolve`, §3 of
  `docs/OPERATIONS.md`) before any retry. There is no automatic retry
  for unknown sends.

## 6. Reproducible no-network checks

All of these run without credentials, a network, or a real meeting:

```sh
git clone https://github.com/latharrr/labs-meet-companion.git
cd labs-meet-companion
python3 --version            # 3.10 or newer; verified on 3.12.3
python3 -m unittest discover -s tests
python3 -m labs_meet.cli --db .local/demo.db demo
python3 -m labs_meet.cli --db .local/demo.db serve   # then open http://127.0.0.1:8765
python3 -m labs_meet.cli --db .local/demo.db config-status
```

Expected: tests pass, the demo creates a synthetic meeting with a
chat draft and a WhatsApp delivery *draft* (not a send), the UI
serves 200 on loopback, and `config-status` shows all providers
unconfigured with live/AI effects off. Use a separate database for
real work; never copy a demo database into a hosted service.

## 7. Rollback

- Code: revert to the last verified commit (record its SHA before
  any deployment step) and re-run §6.
- Configuration: remove the injected secrets for the new service
  from the secret manager; do not leave provider keys in a shell,
  a file, or a chat.
- Service: stop supervisord, confirm no child processes remain,
  remove the meeting-service containers/volumes created for the
  test, and confirm existing apps on the host are unaffected.
- Data: delete the test meeting locally (`delete MEETING_ID`);
  separately reconcile/delete any upstream recordings, provider
  messages and backups created by the test, and record what could
  not be deleted.
- If a step cannot be rolled back cleanly, stop and record that as
  a failed gate rather than working around it.

## 8. What this handoff does not cover

Full ARM image build and boot, hosted TLS/DNS, real Meet admission /
audio / transcription (English and Hinglish), real named-chat posting,
model quality, and real email/WhatsApp delivery. Those are Gates
M1–M5 in `deploy/ROLLOUT-GATES.md` and remain open. No accuracy,
latency, capacity or delivery claim in this repo is proof of them.
