# Release gates: source demo to private Meet bot

This is a release checklist, not approval to build, deploy, provision credentials, spend, join a call or send messages. The local companion works for development. The live meeting product is unfinished. Public source does not make private meeting data public.

## Gate 0: clean local development

Independent finalisation checks, based on source checkpoint 67b835e3317206ae3f6542b84211b0374fe09963:
- Clean source extraction: 114 Python tests and compilation pass.
- Synthetic demo and configuration-status commands run without provider credentials.
- README explains clone, setup, review workflow and limitations.
- Runtime is Python standard library plus SQLite; Vexa and provider services are separate.

These checks use local synthetic data, mocks and loopback contract doubles. They do not prove a real Meet call or provider delivery.

## M1: full native ARM image

Still open. A worker image and synthetic browser/audio smoke passed, and a GitHub ARM runner capability probe passed. Neither is the complete meeting-server image.

Before considering this gate passed:
- Obtain the required approval for one bounded full build and its resource/allowance limits.
- Produce a reproducible pinned-source ARM image; record its immutable digest.
- Validate Linux/ARM metadata, expected init/entrypoint and reduced service set.
- Run the reviewed no-network synthetic image checks and verify their structured success output, not only a zero exit code.
- Verify the intended image audience and a permitted retrieval route. No public-image workaround or credential widening.
- Stop on failure or resource limits. Do not infer permission for another VPS build or a paid fallback.

## M2: isolated service boot and capacity

Still open. Prove private database/storage initialization, authenticated internal routes, one-call concurrency enforcement under simultaneous requests, process cleanup and restart behavior. Measure idle and one-call peak CPU/RAM/disk on the actual target. Existing apps, sessions and data must remain separate. No Docker socket or unrelated account credentials may be exposed to the service.

## M3: private hosted owner access

Still open. Configure the approved hostname with TLS, owner authentication, proxy abuse limits and loopback/private service ports. Verify unauthenticated denial, Host/Origin/CSRF checks, no caching of protected data and an undo path. A read-only page or screenshot is not a deployed bot.

## M4: consenting real Meet acceptance

Still open. Use a deliberately approved test call with organizer authority and required participant notice/consent. Verify admission/denial/timeouts, visible bot identity, English/Hinglish speech, confirmed transcript and corrections, meeting isolation, named-chat draft/approval/posting, leave and withdrawal. Do not bypass lobby or meeting policies.

Automatic named-chat answering is a desired later mode. The current implementation requires exact reply review and approval; do not describe it as unattended automation.

## M5: approved owner delivery

Still open. Verify current provider terms, quotas, data routes and dedicated credentials. Confirm the exact email sender and owner test destinations. Test approved email/WhatsApp content once, record provider IDs and inspect actual outcomes. Submitted/queued/accepted/sent are not interchangeable with posted/delivered/read. Unknown sends must not be retried blindly. Keep the existing WhatsApp receptionist separate.

Participant self-service delivery needs verified identity/entitlement and opt-in. A chat address or phone number alone does not authorize sharing meeting notes.

## M6: private MVP acceptance

Still open. Complete all preceding gates, document retention/deletion and upstream/backups limits, confirm start/stop/recovery and failure reporting, and obtain owner acceptance. No multiuser/public-service launch is implied. A documentation commit or successful test suite is not acceptance of the live product.

## If a gate fails

Report the exact check, result and remaining work. Preserve safe evidence without publishing secrets or meeting content. Stop the affected action; do not silently change provider, audience, resource limits, credentials or cost. Keep the next step bounded and approved.
