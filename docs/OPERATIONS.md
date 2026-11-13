# Operations and safety

## Scope

This companion is not deployed. Its build work must stay separate from existing services and WhatsApp sessions. Do not deploy without a current target-host resource check and owner approval. Other maintenance on the same VPS is outside this guide.

## Configuration

Use secret environment injection or an operator's secret manager. Never commit keys, passwords, chat databases or transcripts. `.env.example` names fields only. The CLI does not auto-load `.env`.

| Variable | Purpose |
|---|---|
| LABS_VEXA_URL | Explicit Vexa gateway base. HTTPS except loopback HTTP. |
| LABS_VEXA_KEY | A dedicated Vexa key; keep out of chat and source control. |
| LABS_LIVE_EFFECTS | `explicitly-approved` enables effects after separately grounded authorization. Omit for dry-run. |
| LABS_TEST_EMAIL | One owner-confirmed email allowed by the email executor. |
| LABS_EMAIL_FROM | Verified143.lat sender identity, captured in the reviewed email payload. |
| LABS_RESEND_KEY | Dedicated Resend send-only key, scoped to143.lat when supported. |
| LABS_AI_URL | Default `https://api.groq.com/openai/v1`. |
| LABS_AI_KEY / MODEL | Dedicated key and text model; default `openai/gpt-oss-20b`. |
| LABS_AI_EFFECTS | `explicitly-approved` enables AI network calls after cost/data-route approval. |
| LABS_TEST_PHONE | Owner-confirmed test phone, not permission to message it. |
| LABS_OPENWA_URL / KEY / SESSION | Dedicated verified OpenWA deployment/bridge credentials. Not the relay HMAC route. |
| LABS_OPENWA_TEST_CHAT_ID | Actual verified owner recipient ID. Never guess a WhatsApp lid from a phone number. |

Never reuse a personal model subscription for a multiuser hosted service without reviewing the provider terms. No model or speech token has been requested/used by this build.

## CLI workflow

Run `python -m labs_meet.cli --help` for commands. `--db PATH` goes before the command.

```sh
python -m labs_meet.cli create https://meet.google.com/abc-defg-hij --title 'Private test' --consent 'Organizer-approved test; all participants notified and required consent obtained'
python -m labs_meet.cli join MEETING_ID
python -m labs_meet.cli review OUTBOX_ID
python -m labs_meet.cli approve OUTBOX_ID --digest EXACT_REVIEWED_DIGEST
# Only after the live test and this effect are approved:
python -m labs_meet.cli execute OUTBOX_ID
python -m labs_meet.cli watch MEETING_ID --interval 10 --cycles 12
python -m labs_meet.cli notes MEETING_ID
python -m labs_meet.cli deliver MEETING_ID --kind email --to OWNER_CONFIRMED_EMAIL
python -m labs_meet.cli review OUTBOX_ID
```

`watch` polls your separately configured Vexa transcript API, not a logged-in Google account. It drafts replies only. Its first snapshot is a baseline so old chat lines do not cause answers. `sync` alone also uses baseline mode. `import` processes a local Vexa-shaped JSON snapshot; add `--baseline` for historical data.

All effect destinations/words must be reviewed in the outbox. A revision to confirmed notes stales existing unsent chat/delivery approvals. Regenerate/review drafts after corrections. Outbox digests prevent approving a different stored payload under an old approval. Meeting text cannot change recipients, policy, model configuration or run tools.

## Delivery truth

- Join `submitted` is a request, not admission.
- Chat `queued` is not sent. `reconcile` reads the request status; only `posted` is treated as provider-confirmed posting.
- Resend `accepted` with email ID is API acceptance, not inbox delivery/read. Idempotency keys last24hours; this build still does not auto-retry uncertain sends.
- OpenWA `sent` means engine return/persisted SENT with message ID, not recipient delivery/read. No request idempotency guarantee. A timeout stays unknown, never blindly retried.
- Network exceptions become `unknown` and are not automatically retried. Stop all workers before `recover`; then inspect provider state. This build has no safe automatic retry for unknown effects.
- Outbox rows are not an authentication system. Anyone with local OS access can edit the DB. Use one trusted operator and one effect worker per database.

## Data

The DB is created with mode 0600. Parent directories newly created by this app are 0700. Data is not encrypted at rest by the app. Restrict the OS account and use encrypted storage before private production meetings. Do not include the DB in a public repository or automated general-purpose backup without approval. Logs contain no transcript by default; UI is no-store.

`delete MEETING_ID` deletes local segments, outbox and dedupe records, checkpoints SQLite and vacuums. This is not forensic secure erase and does not delete Vexa recordings, provider logs or backups. Recording/audio retention must be configured separately before a real call.

## RAM and deployment

A single local companion review process measured 23,144 KiB RSS (about 22.6 MiB) with the tiny synthetic fixture. This is not a capacity benchmark, not Vexa's memory, and not an increment measured on the user's VPS.

The complete Vexa stack adds gateway, meeting service, runtime, admin/identity service, Postgres, Redis, storage and a browser per concurrent call. The pinned README separates GPU transcription from its default CPU control plane. This build does not provide a verified whole-stack RAM requirement. Do not infer it fits from the companion's small RSS.

Before proposing deployment: read current used/available RAM and swap on the actual target; inventory existing containers; measure Vexa idle and one admitted bot under limits; identify the single STT/model host and cost; compare added peak RSS plus a safety margin against free headroom. No deployment recommendation until those numbers exist.

## Groq speech path for Vexa

Vexa appends `/v1/audio/transcriptions` to its transcription base. For Groq configure `TRANSCRIPTION_SERVICE_URL=https://api.groq.com/openai`, a dedicated `TRANSCRIPTION_SERVICE_TOKEN`, `TRANSCRIPTION_MODEL=whisper-large-v3-turbo`. Text AI uses a different base ending in `/openai/v1`. Do not accidentally duplicate `/v1`. Keep one speech pipeline. Real multipart/timestamp output still needs the approved audio test, especially English/Hinglish.

## Current ARM constraint

The user's VPS is ARM64. Stock Vexa bot release image is amd64-only even though control-plane images support ARM. The pinned native worker source build and synthetic sandboxed browser/audio checks passed. The full meeting-only server image has not completed, and no real Meet/audio/transcription test has passed. The private GitHub ARM capability probe succeeded but did not build an image. See `deploy/arm64-probe.md` for earlier worker evidence and `deploy/ROLLOUT-GATES.md` for remaining gates. Do not rerun old build scripts without new approval.

## Private browser workflow

The intended host is meetbot.143.lat, confirmed by the owner. DNS and TLS routing are not yet deployed. The server always binds127.0.0.1. Never publish port8765 directly.

For authenticated owner operations, provision separate LABS_UI_USER/LABS_UI_PASSWORD through approved secret handling, set LABS_UI_HOST=meetbot.143.lat behind the TLS reverse proxy, and set LABS_UI_OPERATIONS=explicitly-approved. No auth secret is shipped. Partial auth configuration and any public hostname without auth fail closed. HTTP Basic is checked for every UI/API request; require TLS at the proxy and limit abuse there. This is a single-owner setup, not multi-user access control. Browser-cached Basic credentials have no instant per-session logout; clear the site credentials or rotate through approved secret handling. Never cache protected responses. HTTPServer is an initial small single-owner service, not a high-concurrency public server.

The browser has meeting title/link entry, organizer/participant consent confirmation, staged join/leave, manual transcript refresh, AI notes, delivery drafting, full payload review, exact-digest approval, separate execution and queued-chat reconciliation. All writes require authentication, explicit operations enablement, exact Origin and a per-process CSRF token. Rendering uses textContent. Unknown sends have no retry button. Live operations remain off unless separately configured and approved. Email/WhatsApp execution remains bound to owner test destinations; this is not arbitrary-participant delivery. The first UI transcript sync establishes a baseline and excludes historical questions. AI notes have their own provider gate and confirmation. Staging/approval alone does not call providers.

A staged read-only host is not the finished bot. Acceptance still requires actual ARM call/audio/chat/inference/owner-delivery tests and any separately approved workflow automation. No code/UI test substitutes for these.
