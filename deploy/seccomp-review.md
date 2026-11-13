# Scoped profile, not authorization to run

2026-11-13. Base: Moby Docker29.9.0 vendored github.com/moby/profiles/seccomp v0.2.4, Apache2.0 (licence adjacent).
https://raw.githubusercontent.com/moby/moby/docker-v29.9.0/vendor/github.com/moby/profiles/seccomp/default.json
Base SHA256785b2429264afba4d594320337cb17f144f3c7d51585f9805eef72e28f4f9334.

Changed file seccomp-docker29.9-userns.json adds ONLY one SCMP_ACT_ALLOW rule for clone/unshare/chroot when CAP_SYS_ADMIN is absent, the namespace sandbox rule from pinned Vexa. All host29.9 baseline socket argument restrictions remain. The older Vexa29.6.2-based whole profile would otherwise relax socket(AF>40) vs current explicit41..45 allowlist. Do not use the old profile unexamined. Rule permits all clone/unshare flags, not solely CLONE_NEWUSER; it is the upstream sandbox rule, with kernel/AppArmor restrictions still active. No extra capability granted.

Run verify-seccomp-diff.py BASE CUSTOM before any proposed trial. Adapted SHA2564b1440bc256276749105e97341d077e91c991a01cf9af336df82003b1aeeb663. Host owner must independently match Docker daemon build/package to this upstream29.9 baseline; a custom patched host remains unverified. An isolated no-network smoke using this exact profile passed on the tested Docker29.9 ARM host. That does not authorize further execution or production use.

Proposed use only after review/approval: same120second isolated smoke, same image/nonroot/no-network/no host mounts/1CPU2GiB/watchdogs, per-container seccomp absolute path, docker-default AppArmor still enforced, no host sysctl/daemon/profile edit. Remove disposable container to undo. Refuse silent fallback if browser sandbox fails again. No real meeting or credentials. Namespace kernel attack surface remains a risk even with sandbox gains.
