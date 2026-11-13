# Lathar Labs Meet companion

Private, single-owner Google Meet companion. **The hosted bot is not live yet.** The review UI and local demo work; joining a real meeting and live transcription, email and WhatsApp delivery still need the full service setup and acceptance tests.

Built around Vexa source commit `6b26f7b921756d6db128d42cd70b4b7046381407`. Vexa is a separate service, not bundled with this Python app. The native ARM worker image and synthetic browser/audio smoke passed. The full meeting-server image has not completed. A separate private GitHub ARM capability probe passed, but it did not build or deploy the bot.

## Start here: local demo, no accounts or API cost

Requirements: Git and Python 3.10 or newer. The companion has no runtime pip dependencies. These commands do not install or start Vexa and do not join a meeting.

```sh
git clone https://github.com/latharrr/labs-meet-companion.git
cd labs-meet-companion
python3 --version
python3 -m unittest discover -s tests -v
python3 -m labs_meet.cli --db .local/demo.db demo
python3 -m labs_meet.cli --db .local/demo.db serve
```

This repository is private: cloning requires an authorized GitHub login. Never put an access token in a clone URL or a README command. If your system uses `python` rather than `python3`, use that name after checking its version.

Open `http://127.0.0.1:8765` on the same computer. You should see a synthetic meeting, its transcript and review items. The unauthenticated local UI is read-only by default. No real call is created and nothing is sent. Keep the terminal open; Ctrl-C stops the server. Use `serve --port 8766` if that local port is occupied.

Use a separate database for real work. Do not copy a demo database into a hosted service or commit it. The demo includes invented dialogue and a delivery draft to the owner's test number, not permission to send it.

## What you can do now

- Run the demo and tests without credentials or external API calls.
- Import an approved local transcript snapshot, inspect notes and stage exact delivery drafts.
- Run the loopback review UI. Authenticated operations can stage, review and approve items after the operator provisions separate UI credentials.
- Inspect `python3 -m labs_meet.cli config-status` for missing configuration. It does not test provider access or quota and does not print keys.

You cannot paste a Meet URL into the default demo and expect a bot to join. A separately configured, working Vexa service is required. There is no automatic background joining or unattended named-chat reply mode in this version.

## Use with a configured private meeting service

Read [Operations](docs/OPERATIONS.md) and [Acceptance checks](docs/ACCEPTANCE.md) before any real call. An operator must first finish the isolated ARM meeting-service build and service setup, configure private storage/Postgres and a one-bot quota, provision dedicated credentials, set up private TLS/authentication, and verify current provider quotas and costs. The planned address `meetbot.143.lat` is not a working deployment supplied by this repository.

`.env.example` lists configuration names, not secrets. The app **does not auto-load `.env`**. Use approved secret injection, not pasted keys in a terminal history, source file or chat. Keep all network-effect switches off until the owner has approved that test and its data routes. Do not connect the existing WhatsApp receptionist session.

There are separate gates:

| Gate | Meaning |
|---|---|
| `LABS_UI_USER` + `LABS_UI_PASSWORD` | Required together for authenticated owner operations |
| `LABS_UI_OPERATIONS=explicitly-approved` | Enables authenticated staging/review controls, not provider calls |
| `LABS_UI_HOST` | Exact private TLS hostname; listener still stays on loopback |
| `LABS_LIVE_EFFECTS=explicitly-approved` | Technical switch for approved join/chat/email/WhatsApp execution |
| `LABS_AI_EFFECTS=explicitly-approved` | Separate switch for approved model calls/data sharing |

A technical switch is not consent or spending authority. Do not expose the loopback HTTP server directly to the internet. Hosted use needs TLS, restricted access and proxy rate limits.

### Normal owner workflow, after setup

1. Start the companion with a private database and approved configuration. Open the authenticated owner UI through its private TLS address.
2. Enter a Google Meet link and meeting title. Record organizer approval and required participant notice/consent before capture. Stage the join request.
3. Review the exact queued item, approve its current digest, then execute it. Submission is not admission: the host may still need to admit the bot.
4. Refresh the confirmed transcript. The first refresh is a historical baseline, so old chat questions do not trigger replies. CLI `watch` can monitor a configured Vexa transcript endpoint and create drafts; it does not automatically approve or send them.
5. A new leading `@Lathar Labs` chat question creates a context-based reply draft. Review and approve the exact reply before execution. A queued chat item needs reconciliation before claiming it was posted.
6. Generate notes locally or, with the separate approved model gate, AI notes. Corrected transcripts invalidate unsent approvals; regenerate and review again.
7. Stage the summary/tasks as email or WhatsApp drafts. Only configured, owner-confirmed test destinations are supported. Review each exact email or WhatsApp chunk, approve, execute, then inspect its provider status.
8. Stage and approve leave when finished. Local deletion is separate from deleting provider copies or backups.

### CLI example: staging is not sending

These are operator examples for a configured service, not a shortcut around the setup above. Replace placeholders with the IDs printed by each command. Put `--db` before the command and keep using the same database.

```sh
python3 -m labs_meet.cli --db .local/private.db create https://meet.google.com/abc-defg-hij --title 'Consenting test call' --consent 'Record the actual organizer approval and participant notice here'
python3 -m labs_meet.cli --db .local/private.db join MEETING_ID
python3 -m labs_meet.cli --db .local/private.db review OUTBOX_ID
python3 -m labs_meet.cli --db .local/private.db approve OUTBOX_ID --digest EXACT_REVIEWED_DIGEST
```

The placeholder link is an example, not a booked call. `approve` does not send. Only after the real test and exact effect are approved and all setup is complete:

```sh
python3 -m labs_meet.cli --db .local/private.db execute OUTBOX_ID
python3 -m labs_meet.cli --db .local/private.db sync MEETING_ID
python3 -m labs_meet.cli --db .local/private.db notes MEETING_ID
```

See [Operations](docs/OPERATIONS.md) for `watch`, local snapshot import, delivery, reconciliation, recovery and deletion. Never retry an unknown send blindly. Email acceptance and WhatsApp engine `sent` do not prove delivery or read status.

## Current build and hosting status

| Check | State |
|---|---|
| Python companion, owner UI and mocked provider adapters | Implemented; local unit/integration tests |
| Native ARM worker image | Built; synthetic browser/audio smoke passed |
| Full meeting-only server image | Not completed; two VPS attempts stopped on late safety-check updates |
| Private GitHub ARM runner probe | Passed; capability check only, no full build |
| Additional full GitHub build/private image publication | Offline proposal only, not authorized or installed |
| `meetbot.143.lat` service | Not deployed |
| Real Meet/audio/transcription/chat/model tests | Not done |
| Real Resend email and separate WhatsApp delivery | Not done |

Old deployment scripts are review/evidence material, not an instruction to retry builds or start services. No CI build is automatically enabled by publishing this README.

## Implemented

- Strict Google Meet link parser and explicit organizer-consent record.
- Vexa HTTP adapters for join, confirmed transcript snapshots, leave, chat send and chat-send status.
- Snapshot replacement, transcript revisions/retractions, pending-speech exclusion, meeting isolation.
- Leading `@Lathar Labs` chat trigger. Historical backlog is suppressed by `watch`'s baseline sync.
- Meeting-context replies as exact quoted evidence, with timestamps. Summary/decision/task queries have conservative extractive handlers.
- Extractive highlights and decision/task candidates with source IDs. No invented task owners or deadlines.
- Persistent SQLite review queue. Exact payload digest approval, once-only claim, stale approval invalidation, unknown-send recovery without automatic retry.
- Concrete Resend email API with stable idempotency key, reviewed sender identity and one configured owner test destination. No CC/BCC. Not live tested.
- OpenWA0.23.3 adapter against the verified send-text contract, with separately configured session/key and verified owner test chat ID. Long notes split into separately reviewed chunks. No existing receptionist credentials reused. Not live tested.
- Authenticated owner UI: meeting link/consent entry, join/leave staging, transcript refresh, AI notes, delivery drafts and human-readable exact-item review/approval/execution controls. No third-party scripts/fonts.
- Local deletion command for transcript/state. Provider copies, backups and disk remanence are separate.

## Not implemented / not proven

- No real Meet admission, audio, transcription, Hinglish accuracy or real chat send has been tested.
- No live email/WhatsApp delivery has been tested. The concrete adapters remain gated, owner-test-only and unconnected.
- Groq-compatible AI integration is implemented with exact segment/quote checks, no tool calls and default network-use guard. Selected text model: openai/gpt-oss-20b. Speech: whisper-large-v3-turbo via Vexa. No actual model key is connected or inference quality test completed. Extractive fallback works without external calls.
- No automatic calendar joining, participant email verification, automatic assignments, reminders, cross-meeting memory, account sign-in, multiuser service or public deployment.
- Joining still needs host admission. The app cannot bypass the lobby or meeting policies.
- Single-owner HTTP Basic authentication and Origin/CSRF-gated browser operations are implemented. Hosting still requires TLS, proxy rate limiting, approved secret provisioning and security review. Listener remains loopback-only.
- Private repository: labs-meet-companion. Intended host: meetbot.143.lat. Repository publication does not deploy the bot.

## Controlled integration path

Read `docs/OPERATIONS.md` and `docs/ACCEPTANCE.md` first. Every network effect is off unless `LABS_LIVE_EFFECTS=explicitly-approved` is set by the operator. That switch is a technical guard, not permission: obtain the owner's approval for the deployment, exact messages/destinations and consenting-call test before using it.

1. Configure a separate self-hosted Vexa instance pinned to the audited commit, with one existing speech pipeline. Do not attach the production WhatsApp receptionist.
2. Record an organizer-approved test call and participant notice/consent.
3. Create a meeting, stage a join, inspect `review`, approve that digest, then execute only within the approved test.
4. Sync/watch confirmed notes. Each named-chat answer remains a draft until approved.
5. Reconcile queued chat by provider request ID. queued does not mean posted.
6. Export delivery drafts first. Configure only an owner-confirmed email/phone for tests. WhatsApp execution requires a verified owner test-chat ID in the reviewed payload and dedicated bridge/session/key configuration.

## Licensing and sources

See `docs/SOURCES.md` and `docs/DEPENDENCIES.md`. New companion code has no public redistribution licence chosen yet. The reviewed deployment seccomp files include Apache2.0 upstream material and adjacent licence/attribution. Vexa and the speech engine it supports are external dependencies, not a promise of free compute.

## API/service choices

| Function | Selected interface | Current state |
|---|---|---|
| Join, transcript, chat | Self-hosted Vexa HTTP API at pinned main commit | Adapter and loopback tests. Native ARM image built. Sandbox smoke passed with reviewed Docker29.9-matched container-only profile. Real Meet untested |
| Speech-to-text | Groq `whisper-large-v3-turbo`, through Vexa's configurable transcription client | Source/docs-compatible. no live audio test or account quota check |
| AI notes/answers | Groq `openai/gpt-oss-20b`, `/openai/v1/chat/completions` | Implemented, mock-tested, network calls off by default |
| Email | Resend `POST /emails`,143.lat sender | Implemented. 143.lat domain verified. Exact sender, credential scope, plan/quota and delivery test still open |
| WhatsApp | OpenWA0.23.3 `POST /api/sessions/{sessionId}/messages/send-text` | Verified contract + mocked adapter. no live bridge configured |
| State | Python standard library + SQLite | Works locally. not encrypted/multiuser |

No provider is silently upgraded to a paid plan. No Claude fallback is configured. Quota exhaustion must stop/queue work rather than create unapproved spend. A free endpoint is not guaranteed free capacity.

`python -m labs_meet.cli config-status` reports missing configuration without echoing secrets. It does not contact accounts or establish quota.
