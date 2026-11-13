# Acceptance status, 13 November 2026

Source checkpoint only. Not live-product acceptance.

| Area | Verified boundary | Still open |
|---|---|---|
| Local companion and SaaS source | Synthetic/unit/loopback tests; separate customer workspaces and review guards | Real upstream service and customer acceptance |
| Landing/private workspace UI | Local HTTPS browser journeys and responsive review | Public launch and production workload |
| Google login | Restricted actual sign-in, verified session/workspace, logout and later protected-route denial | Public OAuth readiness, privacy/support/deletion process |
| WhatsApp OTP | One approved owner request, verification, session/workspace and logout | OTP post-logout protected-route check, customer activation and delivery guarantees |
| ARM image | Native build and no-network synthetic checks; private verified download retained | Engine import/start, database, worker accounting and real call |
| Image publication | Unexpected public audience contained; anonymous access blocked; temporary download credential revoked | Safe preventive publication design, not default-private assumptions |
| Live service | Maintenance only; new runtime services stopped | Safe isolated engine, consenting Meet test and delivery |

## Withdrawn runtime route

Do not run a second Docker daemon in the live host's network namespace, even with separate roots/sockets, a shared five-GiB cgroup cap, no iptables changes and `bridge: none`. That combination removed the existing default bridge during the attempted idle qualification. The new services were stopped before image import or engine startup, and the known bridge configuration was restored. Prior MAC/ifindex identity was not recorded, so exact identity restoration is not claimed.

Evidence sources for the failure mode:
- https://github.com/moby/moby/issues/54134
- https://github.com/moby/moby/pull/54157

The former private runtime plan is withdrawn and is not included as runnable instructions. No private host logs, keys, configuration, image blobs or operator files belong in this repository. An independent disposable rehearsal with complete network namespace separation is only a research proposal, not a validated replacement or permission for another live-host attempt.

All further setup keeps the established whole-stack resource limit and existing-app protections. No automatic retry, new build, credential creation, spending, call joining or message sending follows from this commit. Provider acceptance is not delivery, and source tests are not deployment evidence.
