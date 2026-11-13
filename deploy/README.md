# ARM feasibility scripts

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
