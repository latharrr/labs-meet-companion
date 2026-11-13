# Acceptance gates

## Passed locally

- Unit tests for parsers, confirmed-only evidence, named-chat routing, no future evidence, redacted errors, anti-backlog, stale approvals, dedupe, permissions and deletion.
- Actual HTTP requests against a loopback Vexa-shaped contract double: join -> transcript -> reply draft -> approved queued send -> posted reconciliation -> leave. This proves our wiring against a fake, not Vexa/Google.
-81tests pass. Authenticated real loopback HTTP checks cover auth, Host/Origin/CSRF, consent, digest, stale/disabled effects. Installed wheel exercised in fresh virtualenv with UI/fixture resources.
- Browser UI: notes, transcript and review-queue tabs plus authenticated meeting entry/consent/staging/review/approval exercised. Desktop 1440px and mobile 390px; no JS errors or horizontal overflow. Screenshots visually inspected.
- No new account, paid API, real call or external delivery used. Existing provider metadata verified143.lat without key transfer.

- Native ARM image build and isolated sandboxed Chromium/WebAudio smoke passed. No real meeting/network was used in smoke. No peak-resource claim from a sub-five-second test.

## Required before calling this ready

1. Target: own ARM VPS and meetbot.143.lat, confirmed by owner. Native ARM source build passed; sandboxed Chromium + synthetic audio passed with reviewed Docker29.9-matched namespace profile. No service/DNS deployment yet. Private source repository requested; no public repo by default.
2. Current target RAM/CPU/storage and one-bot peak measured; added memory disclosed vs current usage. Owner approves deployment and any cost.
3. Verify pinned Vexa images build/run together and the gateway contract (header, routes, statuses, real payloads). Main branch chat route is absent from release tags v0.12.28/v0.13.1 checked in earlier research.
4. Select one STT host/model, verify code + model terms and audio retention/private data route. Do not quietly use Vexa hosted transcription.
5. Owner and every test participant understand the visible notes bot; organizer approves admission. Run an English/Hinglish test and measure word/speaker accuracy, lobby timeouts, withdrawal/deletion, denial and hangup.
6. Approved exact chat test only. Verify queued -> posted in real Meet UI; never claim posting from HTTP 200 alone.
7. Groq gpt-oss-20b integration is implemented; verify key/cost/data route and require evidence-linked outputs, no tool authority from transcript text. Current fallback is extractive only.
8. The installed OpenWA0.23.3 send contract has been verified read-only. Configure and test a dedicated bridge/session/key and verify recipient identity. Keep it isolated from the production receptionist, and disclose unofficial-account ban/compliance risk. Until then WhatsApp stays unconnected and effect-gated.
9. Exact email/WhatsApp test to the owner only, with words and destination approved. No third-party recipients or participants silently added.
10. Test retention cleanup, full upstream deletion, watchdog/restart recovery, crash-during-send reconciliation, backup exclusions and an undo path.
11. Production auth, multiuser isolation, organiser sharing policy and verification before any SaaS rollout.

The full user outcome remains open until these integration gates are met. Local source completion is not service readiness.
