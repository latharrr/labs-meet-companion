#!/usr/bin/env bash
# Run ONLY after explicit owner approval. This builds only; no call, service deployment or send.
set -euo pipefail
[[ $(uname -m) == aarch64 ]] || { echo 'Native aarch64 host required'; exit 2; }
[[ ${LABS_ARM_PROBE_APPROVED:-} == yes ]] || { echo 'Explicit approved probe required'; exit 2; }
SECONDS=0
command -v docker
command -v timeout
command -v python3
# Prerequisite check does not install software or start Docker.
docker buildx version
WORK=${1:?Pass a NEW empty workspace directory}
[[ ! -e $WORK ]] || { echo 'Workspace already exists; refuse overwrite'; exit 2; }
START_FREE=$(df -Pm / | awk 'NR==2{print $4}')
START_SWAP=$(awk '/SwapTotal/{t=$2}/SwapFree/{f=$2}END{print int((t-f)/1024)}' /proc/meminfo)
(( START_FREE >= 61440 )) || { echo 'Need at least 60GiB free before proposed16GiB probe'; exit 2; }
AVAILABLE=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
(( AVAILABLE >= 8192 )) || { echo 'Need at least8GiB currently available'; exit 2; }
mkdir -m 700 -p "$WORK"
ROOT=$(cd "$(dirname "$0")" && pwd)
STAMP=$(date +%Y%m%d%H%M%S)
BUILDER=labs-arm-probe-$STAMP
IMAGE=labs-meet-arm-probe:$STAMP
BUILD_PID=''
MON_PID=''
cleanup() {
  set +e
  [[ -z $MON_PID ]] || kill "$MON_PID" 2>/dev/null
  [[ -z $BUILD_PID ]] || kill "$BUILD_PID" 2>/dev/null
  docker buildx rm --force "$BUILDER"
  echo "Probe image retained for separately approved smoke: $IMAGE"
  echo "Remove only this image after review: docker image rm $IMAGE"
  echo "Workspace retained for logs: $WORK"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
MAIN_PID=$$
(
  while sleep 5; do
    free=$(df -Pm / | awk 'NR==2{print $4}')
    avail=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
    swap=$(awk '/SwapTotal/{t=$2}/SwapFree/{f=$2}END{print int((t-f)/1024)}' /proc/meminfo)
    echo "$(date -Is) disk_free_MiB=$free available_MiB=$avail swap_used_MiB=$swap" >> "$WORK/resources.log"
    if (( free < 46080 || START_FREE - free > 16384 || avail < 4096 || swap - START_SWAP > 256 )); then
      echo 'Resource stop threshold reached' | tee "$WORK/STOPPED"
      docker buildx stop "$BUILDER" || true
      kill -TERM "$MAIN_PID"
      exit 1
    fi
  done
) &
MON_PID=$!
# Refuse any mutable main checkout.
timeout --signal=TERM --kill-after=10s 120s git clone --filter=blob:none --no-checkout https://github.com/Vexa-ai/vexa.git "$WORK/vexa"
git -C "$WORK/vexa" checkout 6b26f7b921756d6db128d42cd70b4b7046381407
python3 "$ROOT/prepare-arm64.py" "$WORK/vexa"
# The builder is not made the global default. Driver options cap the BuildKit daemon/children.
docker buildx create --name "$BUILDER" --driver docker-container \
  --driver-opt memory=3g --driver-opt memory-swap=3g \
  --driver-opt cpu-period=100000 --driver-opt cpu-quota=100000
# Bootstrap a disposable builder, then verify hard cgroup settings before source build.
timeout --signal=TERM --kill-after=10s 120s docker buildx inspect --bootstrap "$BUILDER"
LIMITS=$(docker inspect "buildx_buildkit_${BUILDER}0" --format '{{.HostConfig.Memory}} {{.HostConfig.MemorySwap}} {{.HostConfig.CpuPeriod}} {{.HostConfig.CpuQuota}}')
[[ $LIMITS == '3221225472 3221225472 100000 100000' ]] || { echo "BuildKit limits mismatch: $LIMITS"; exit 2; }
REMAINING=$((1500 - SECONDS))
(( REMAINING > 0 )) || { echo 'Total25min budget exhausted'; exit 2; }

timeout --signal=TERM --kill-after=20s "${REMAINING}s" docker buildx build --builder "$BUILDER" \
  --platform linux/arm64 --load --progress plain --tag "$IMAGE" \
  --build-arg VEXA_IMAGE_VERSION=6b26f7b9 \
  -f "$WORK/vexa/Dockerfile.labs-arm64-probe" "$WORK/vexa" > "$WORK/build.log" 2>&1 &
BUILD_PID=$!
wait "$BUILD_PID"
BUILD_PID=''
[[ ! -e $WORK/STOPPED ]] || exit 1
kill "$MON_PID" 2>/dev/null || true
wait "$MON_PID" 2>/dev/null || true
MON_PID=''
docker image inspect "$IMAGE" --format '{{.Architecture}} {{.Size}}'
echo 'Build only complete. No service or smoke container started. Separate approval before smoke.'
