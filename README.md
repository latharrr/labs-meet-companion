# Lathar Labs Meet companion

Build v0.1. Native ARM image build passed. Sandboxed ARM Chromium and synthetic audio smoke passed; this is not a deployed or end-to-end tested Google Meet bot.

Built around Vexa main commit `6b26f7b921756d6db128d42cd70b4b7046381407`, not the older release tags. Vexa is an external service: this archive does not bundle or run its browser fleet, speech models or GPU service.

## Run locally, without an account or API cost

Python 3.10+ is enough. There are no runtime pip dependencies.

```sh
python -m unittest discover -s tests -v
python -m labs_meet.cli demo
python -m labs_meet.cli serve
```

Open the loopback URL printed by `serve`. The UI defaults to read-only. Separately enabled authenticated owner mode provides meeting-link entry, staging and exact-item review/approval. Live execution remains separately gated. See docs/OPERATIONS.md. The demo contains invented dialogue and a delivery draft addressed to the owner's verified number. Nothing is sent. Stop with Ctrl-C.

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
- Intended private repository: labs-meet-companion. Intended host: meetbot.143.lat. Repository publication does not deploy the bot.

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

## Tests and CI status

Run `python -m unittest discover -s tests -v` locally. All65tests passed at this source milestone. Automatic GitHub CI is not active: the current GitHub credential cannot publish workflow files. The workflow is preserved separately for later setup; it is deliberately absent from this repository and all initial pushed history. This does not change the need for real provider/meeting acceptance tests.
