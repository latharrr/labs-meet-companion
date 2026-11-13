> HISTORICAL LOCAL/LEGACY REFERENCE. Read [current status](../docs/STATUS.md) first. Engine not running; same-host-network-namespace second-daemon route is withdrawn. Earlier build/auth/hostname statements below are historical, not current readiness or permission to start anything.

# Deployment source and build evidence

**Not a deployed service. Do not run these scripts as a setup shortcut.** The worker ARM build and synthetic browser/audio smoke passed, but the full meeting-only server build did not complete. Two VPS derivative attempts were stopped and cleaned up. No further VPS build attempt is authorized by these files. The GitHub ARM probe checked capabilities only; a full GitHub build remains a separately approved action.

The following sections describe the original isolated worker feasibility procedure for review and reproducibility, not a new instruction to execute it. Read the main README and docs/OPERATIONS.md first. A future deployment still requires a verified full image, service/storage setup, fresh resource measurements, private TLS/auth, separate credentials and consenting real-call tests.

New source files include the reduced five-program meeting supervisor generator, entrypoint environment filtering, seven-route gateway wrapper and their offline tests. Their presence does not prove an image boots. build-resource-monitor.py and validate-oci-stream.py are historical build-support utilities, not an approved retry plan. The monitor's older external heartbeat arrangement stopped two runs on late updates; do not reuse it as if that issue were proven fixed.

## Original ARM worker feasibility scripts

The build script is an approval-gated feasibility probe, not production deployment.

Before running, inspect it on the host and obtain the explicit isolated-test approval. No secrets are required. It needs existing Docker with buildx, git, Python3 and timeout; if missing, stop and report rather than installing host packages or changing Docker configuration. It does not use the production network, sessions or volumes.

Run under the already-authorized host operator, from this directory, with a NEW workspace path:

```sh
LABS_ARM_PROBE_APPROVED=yes ./arm64-build-probe.sh /opt/labs-arm-probe-UNIQUE_TIMESTAMP
```

BuildKit's container CPU/memory/swap cgroup configuration is read back with docker inspect before source build. The watchdog stops the builder and the parent script on host pressure. Docker daemon/image-extraction overhead is not hard-capped; monitor production health independently and stop on changes. The script does not have the existing application's private health token, so the host owner must cover that check.

The script retains its exact image tag and workspace/logs for review; it removes the disposable builder. This is not a complete rollback until the retained probe image/workspace are removed after evidence is collected. Use the exact tag/path printed in the result. Never use broad prune or remove existing images/volumes.

Do not start the built bot normally: that requires a separate approved deployment. The first follow-up is a 120-second no-network browser/audio smoke test, with no meeting or API credentials. All real-call tests are a later gate.

## Tested sandbox profile

Default Docker seccomp refused Chromium sandbox setup. The reviewed Docker29.9-specific profile in seccomp-docker29.9-userns.json passed isolated no-network/nonroot browser/audio smoke with docker-default AppArmor retained. Run verify-seccomp-diff.py against the adjacent exact baseline before reviewing reuse. This permits clone/unshare/chroot for the browser namespace sandbox but retains all other default rules. No hostwide setting was changed. Runtime deployment remains separate and must preserve these controls. See seccomp-review.md for scope and residual risk.
