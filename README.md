# Lathar Labs Meet companion

Review-first Google Meet companion and customer-workspace foundation. **The hosted meeting engine is not running and this is not ready for a real call or public customer launch.** Source saved here is separate from deployment and acceptance.

## Saved checkpoint: 13 November 2026

- Local companion: Meet-link parsing, transcript review, source-linked notes, an exact-message approval queue, provider adapters and a synthetic demo.
- SaaS foundation: animated landing page, private workspace UI, Google identity verification, four-digit WhatsApp OTP login, secure sessions, CSRF/origin checks and logout.
- Isolation guards: workspace ownership checks, separate tenant stores, explicit upstream credential ownership, global one-meeting reservation and no shared-owner-token fallback.
- OTP safeguards: default-deny recipient allowlist, private persistent attempt ledger, one approved test identity, pacing/budget/health checks and no automatic retry after an uncertain send. Customer OTP activation is not enabled.
- Native ARM meeting-only image: built and passed the no-network synthetic checks. Its publication workflow failed the audience check after the image appeared public. Public access was removed and anonymous retrieval was denied. The existing image was then downloaded privately and independently hash-checked. The temporary read-only download credential was revoked and removed. This was not a clean publication success or an engine boot.
- Actual sign-in checks completed in restricted test windows: Google login/session/workspace/logout, and one owner-only WhatsApp OTP request/verification/workspace/logout. Post-logout protected-route denial was observed for Google, not independently recorded for the OTP test. Login checks are not meeting acceptance.
- A later isolated-runtime attempt affected the host's default Docker bridge even with `bridge: none`. Only the new services were stopped; the known bridge configuration was restored and existing app health checked. The same-host-network-namespace second-daemon route is **withdrawn and must not be retried**. No engine image import, engine boot or real Meet call was completed.

The target is `bot.143.lat`, currently a maintenance endpoint, not a working meeting service. All hosted auth, meeting operations and provider activation remain off outside separately approved tests. Do not wait on the website for a live meeting test.

The checked-in build workflow is manual-only and retained unchanged as historical build evidence. Its one approved build is complete; do not dispatch it again. Its first-publish-private assumption proved unsafe. Saving or pushing this code starts no build. Another build, credential, deployment or external test requires its own authority.

## Local demo: no account or provider calls

Requirements: Git and Python 3.10 or newer. Core companion and synthetic tests use the standard library and SQLite. Google verification has a separate optional dependency extra.

```sh
git clone https://github.com/latharrr/labs-meet-companion.git
cd labs-meet-companion
python3 -m unittest discover -s tests -v
python3 -m labs_meet.cli --db .local/demo.db demo
python3 -m labs_meet.cli --db .local/demo.db serve
```

Open `http://127.0.0.1:8765` on that computer. The demo is invented dialogue, joins no call and sends nothing. The local UI is read-only by default. Ctrl-C stops it. Use a separate private database for any real data; never commit databases, provider responses, keys or copied production configuration.

## SaaS code, not a production start command

`labs_meet/saas_runtime.py` is the separate loopback runtime; `--check` validates private configuration without starting the meeting engine. `deploy/saas-config.example.json` contains disabled features and placeholders only. Google requires the `google` optional extra, a dedicated approved client and official token verification. There is no Google client secret in the browser.

Public landing-page assets use synthetic examples. The private workspace loads account-specific records from authenticated endpoints, not the marketing demo. Browsers cannot choose upstream credentials or another tenant. The app refuses meeting operations unless upstream isolation is explicitly verified and capacity is one. These source checks do not prove a working upstream multi-tenant service.

The private OTP collector and host-specific operating configuration are deliberately not included. Do not point this code at an existing WhatsApp receptionist or copy its database/session credentials. The broker's one-test recipient and identity must come from separately approved private configuration. Changing an identity or replacing its ledger is not permission to resend.

Customer email/WhatsApp delivery remains disabled in the SaaS path. Legacy CLI delivery adapters are gated owner-test tools, not arbitrary participant delivery. Staging and approving an item do not send it. Unknown provider outcomes require reconciliation, not blind retries.

## Tests and evidence limits

Run the suite above from a clean checkout. Unit and loopback contract tests cover identity/nonce/session checks, OTP safeguards, concurrent reservations, cross-workspace denial, review digests, stale approvals and uncertain outcomes. Tests use mocks and synthetic data; they make no real Meet, email, WhatsApp or model calls.

The ARM synthetic check verified image imports and the reduced eight-route gateway, including exact transcript-by-ID lookup. It did not verify database initialization, complete engine startup, worker cleanup, real audio/transcription, consent, customer quotas or delivery.

## Remaining gates

1. Prove a safe runtime away from existing live apps. Separate data directories and cgroups alone do not isolate a second Docker daemon's networking. No approved independent rehearsal environment is currently established.
2. Verify engine, database, workers, storage, network egress, control plane, one-call concurrency, full process resource accounting and rollback. Preserve existing apps; no global-daemon restart or cap increase is a fallback.
3. Verify real tenant-owned upstream records and exact transcript isolation. Per-account local databases alone are insufficient when upstream credentials or Meet-code lookups are shared.
4. Run an explicitly approved consenting Meet call, with visible bot, organizer authority and required participant notice, then check audio, transcript quality, chat, leave and cleanup.
5. Approve actual data processing, retention, support and deletion behavior. No fixed automatic deletion or backup erasure is promised. The private privacy draft is not a published policy and is not included here.
6. Verify approved sender/destinations, provider policies/quotas and delivery outcomes before enabling customer effects. No spending or account permission is implied by source publication.

## Source map

- `labs_meet/`: local companion, auth, SaaS boundary checks and runtime.
- `labs_meet/public/`: landing page and private workspace assets.
- `tests/`: synthetic and mocked tests.
- `deploy/SAAS-RUNTIME.md`: source configuration contract, not deployment authority.
- `docs/STATUS.md`: current acceptance boundary and withdrawn runtime route.
- `docs/OPERATIONS.md`, `docs/ACCEPTANCE.md`, `docs/DEPLOYMENT-HANDOFF.md`: earlier local/legacy operating references. Current status and withdrawal warnings take precedence over their historical checkpoints.

Built around separately deployed Vexa source `6b26f7b921756d6db128d42cd70b4b7046381407`. Speech and AI integrations are optional, network-gated and not quality-tested live. No paid fallback is selected. See `docs/SOURCES.md`, `docs/DEPENDENCIES.md` and adjacent upstream licence notices. No redistribution licence has been selected for the new companion code.

**Public source, private data:** the repository is intentionally public. Credentials, user identities, live phone numbers, transcripts, server access details, private operator tools and incident evidence are not source deliverables.
