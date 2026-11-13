> SOURCE CONTRACT ONLY. Current status: [../docs/STATUS.md](../docs/STATUS.md). No engine is running. The same-host-network-namespace second-daemon route is withdrawn. This document does not supply a safe container runtime or authorize starting one.

# Isolated SaaS runtime, offline deployment proposal

This does not authorize deployment, a provider send, an upstream account change, or publishing the draft privacy commitments. Preserve the capacity notice/test-acceptance gate and existing production services.

## Integrated entry point

Install the package with its `google` optional extra, then use `python -m labs_meet.saas_runtime --config PRIVATE_CONFIG`. `--check` validates local configuration only. It may create a private OTP ledger when explicitly enabled, but does not call the collector, gateway or meeting engine. The normal server binds only 127.0.0.1 on its configured port. It does not replace the legacy server or start a meeting-engine process. Reverse-proxy HTTPS must be separately configured and verified.

Start from `saas-config.example.json`, store a real config mode0600 under the app UID, and use separate owner-only files for raw32-byte authentication and OTP-ledger HMAC keys and the gateway API key. No secret environment fallback, repository secret or browser-supplied tenant/upstream key. The sample deliberately has all live features disabled and no Google client ID. Operator configuration supplies the approved exact client ID; it is public but account-specific.

Proxy only the exact bot.143.lat virtual host to the separate port. Preserve existing vhosts and applications. Proxy must overwrite X-Real-IP from the actual network peer, not append a user-provided forwarding header. Secure cookies and origin checks require the real HTTPS origin. DNS/TLS and the selected free port must be checked on the host before installing or starting.

## Explicit enablement fields

Google: `google_client_id` is the approved dedicated sign-in-only web client. Backend uses official Google ID-token verification, not a client secret. Auth bootstrap must remain testing until owner-reviewed privacy, support/deletion process, Google branding/domain settings and actual sign-in acceptance are ready.

OTP: set `otp.enabled` true only after the sender/collector/service-UID and test gates pass. Required fields: `base`, `api_key_file`, `session_id`, `sender_phone`, `ledger_key_file`, `collector_socket`, `collector_uid`, `ipc_gid`. Session and phone are fixed operator values, never customer-selectable. The broker creates only its private local ledger. It performs fresh health/count reads around one request-driven recipient lookup and one send. No retry on an uncertain send. A provider message ID means engine acceptance, not delivery.

The initial app allocation is10 attempts per UTCday globally,3 per number/day,60second per-number cooldown,one durable in-flight reservation,15seconds between reservation timestamps, and an aggregate outgoing-count refusal at150. These are conservative initial app limits, not a WhatsApp ban-safety policy or a promise of global atomic timing/capacity. Variable health/lookup latency means actual POST starts are not guaranteed15seconds apart. Legacy sends do not share the ledger; retain the gateway's own cap and breaker.

Meet operations: explicit `operations_enabled:true`, `upstream_isolation_verified:true`, accepted initial `capacity:1`, `credential_root` and `vexa_base` are required. Per-tenant credentials are read-only private files with expiry, distinct upstream users and key fingerprints. No shared owner-token fallback or automatic provisioning. Provisioning remains an operator workflow requiring separately established authority and ownership acceptance. Customer delivery remains blocked in SaaS even when meeting operations are enabled.

## Collector privilege boundary

Collector implementation and its private host README are separate, not public source. Use a dedicated collector UID with narrowly granted gateway database/WAL/SHM read access and traversal. App UID has no gateway database ACL, group, mount, host root, Docker socket or privileges. Share only an IPC-only group without data rights. Under trusted root-owned /run ancestors, directory is collector:ipc0750; socket collector:ipc0660. Consumer requires exact expected collector UID and IPC GID, rejects same app/collector UID. Bind only that runtime directory into an app container, read-only, if using containers. Do not chmod the database or restart gateway/relay/receptionist as a workaround.

Actual host acceptance must prove: collector reads current WAL data; app gets EACCES opening gateway database/WAL and succeeds with only COUNT socket access; unrelated UID denied; app cannot replace socket; restart/rotation does not expose data; stale/future/wrong-day/session/count/error responses fail closed. Unit tests that mock EUID are not this acceptance.

## Remaining launch gates

- No new deploy until the user receives and approves the resource/capacity plan and tests are accepted. <=5GiB whole new stack/global one meeting with >=4GiB remaining is a proposed budget, not measured fit.
- The ARM image was built and privately downloaded; safe isolated engine startup remains unproven. Exact source author and committer identity remains required. No further build is authorized.
- Test isolated engine boot, memory/CPU/storage/network, live multi-tenant ownership and exact transcript-row isolation. Never use a shared Meet-code newest-row fallback.
- Restricted actual Google and one owner OTP sign-in journeys passed; customer activation, OTP post-logout denial and full meeting acceptance remain open. Unit tests and a client ID are not working-product acceptance.
- The reviewed workspace source is included. Continue using account-specific API records, never marketing demo data, in authenticated workspaces.
- Approve and publish an honest privacy notice and test the actual support/deletion path before claiming public readiness. Do not claim zero retention.

## Owner-only OTP test boundary

When OTP is enabled, private configuration must include `otp.allowed_numbers` as a JSON list containing exactly one canonical E.164 number authorized for that test. Missing, empty, multiple or malformed entries fail startup. The broker defaults to no recipients and rejects outside numbers before health reads, budget reservations, recipient lookup or sends. No real recipient belongs in public source. This does not authorize a send, repeat, customer activation or a higher allocation. Existing daily, pacing, health, aggregate and unknown-outcome locks remain in force.

Enabled runtime also requires `otp.test_id`, an operator-assigned 16-96 character letters/digits/underscore/hyphen identity for the specific approved test. One reservation per identity is stored atomically in the private ledger and never reset by cooldown, day rollover, success, failed lookup or restart. Concurrent processes cannot reserve a second attempt. No automatic ID generation or clearing is provided. Changing this identity or replacing the ledger is not a retry mechanism: a new attempt needs new owner authority. Missing/malformed test identity fails startup before provider-secret access.
