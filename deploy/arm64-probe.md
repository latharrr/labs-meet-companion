# Proposed ARM64 feasibility probe - approval required

This is not a deployment. It builds and probes an isolated image with no API keys, WhatsApp session, Meet link, public port or existing production network. Nothing here was run on the VPS.

## Source facts

- Audited Vexa commit: `6b26f7b921756d6db128d42cd70b4b7046381407`.
- Stock release validation says the meeting bot is amd64-only. ARM validation covers control-plane/Lite front doors, not a call.
- MCR manifest at `https://mcr.microsoft.com/v2/playwright/manifests/v1.56.0-noble` lists both linux/amd64 and linux/arm64. A native source build is therefore plausible, not proven.
- The bot needs Chromium + X11 + audio, Node native modules and an AWS CLI binary. A successful image build still does not prove Meet admission/media.

## Host baseline, November 13 2026 16:26 IST

ARM64, 2 CPU cores. RAM 11,927 MiB total, 2,800 MiB used, 9,126 MiB available. Swap 866 MiB in use. Root disk 61 GiB available. This is historical evidence for the proposal; recheck immediately before execution.

## Requested test envelope

- One native build at a time, no emulation. One disposable BuildKit container with CPU quota 1 core and memory hard cap 3 GiB; no parallel companion/Vexa startup.
- Build timeout 25 minutes including base/runtime image work. Package downloads can make this insufficient; timeout is an inconclusive result, not evidence ARM cannot work.
- Estimated added build memory: unknown, bounded at 3 GiB for BuildKit children. Docker daemon/image extraction overhead is outside that cap and must be monitored. This is not an all-host hard cap. No claim that the image builds inside it.
- Disk allowance: up to 16 GiB extra before stop/cleanup. Image/layer size is unmeasured. Check host disk every 5 seconds, cancel if free space falls below 45 GiB or incremental use exceeds 16 GiB. No disk quota guarantee for image extraction; preserve margin and stop promptly.
- After build only, one no-network smoke container: 1 CPU, 2 GiB RAM, 1 GiB shared memory, no swap allowance beyond RAM, non-root upstream UID, no host mounts, no host network, no published ports. Timeout 120 seconds. No live call.
- Stop build/probe if available host RAM <4 GiB, swap rises >256 MiB from the fresh starting value, production health changes, or CPU/load pressure disrupts existing services. Use the existing production owner's read-only health observations, not restarts.

A 3 GiB BuildKit cap is around 3,072 MiB in addition to the current 2,800 MiB used, plus unmeasured daemon overhead. It is a test ceiling, not a predicted peak or a working runtime requirement. A separate admitted-call measurement is required before final resource planning.

## Probe steps

1. Fresh host/mount/free-space/production-health check. Refuse non-aarch64. No packages installed on host.
2. Checkout exact commit under a new isolated workspace. Preserve licences and record hashes. Use an isolated buildx builder; never select it as the global default.
3. Build ARM-native join-env from the pinned Playwright base, then bot from the same commit using that environment. Do not publish images or change service configuration.
4. Verify `uname -m`, Node arch, browser executable architecture and native dependencies in the image.
5. Run Chromium against a local synthetic HTML fixture only, Xvfb/audio daemon startup, capture bundle existence, browser script load, audio API availability and clean SIGTERM teardown. No Meet URL or provider credentials.
6. Record image size, peak builder/probe RSS, CPU, duration, host RAM/swap before/after and production health. Missing browser/media proof is a failed/inconclusive probe, not ready.
7. Remove only the uniquely named probe container, disposable builder and probe image tags/workspace. Never run broad `docker system prune`, remove production volumes, or restart Docker/nginx/WhatsApp.

## Next gate

If this probe passes, request a separate approved deployment resource plan and consenting private-call test. ARM image smoke success does not prove real Meet capture, transcript quality, Groq account quota, Resend identity, WhatsApp bridge safety or actual message delivery.
