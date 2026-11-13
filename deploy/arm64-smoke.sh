#!/usr/bin/env bash
# Separately approved follow-up to a successful native build. No meeting or network.
set -euo pipefail
[[ ${LABS_ARM_SMOKE_APPROVED:-} == yes ]] || { echo 'Separate smoke-stage approval/review required'; exit 2; }
[[ $(uname -m) == aarch64 ]] || { echo 'Native ARM host required'; exit 2; }
IMAGE=${1:?Pass exact retained probe image tag}
[[ $IMAGE == labs-meet-arm-probe:* ]] || { echo 'Refuse a production image tag'; exit 2; }
[[ $(docker image inspect "$IMAGE" --format '{{.Architecture}}') == arm64 ]] || { echo 'Wrong image arch'; exit 2; }
NAME=labs-arm-smoke-$(date +%Y%m%d%H%M%S)
cleanup(){ docker rm -f "$NAME" 2>/dev/null || true; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Existing host owner must keep the same pressure/service-health watchdog active.
# No env-file or secret is accepted. No host volumes/networks/ports, no paid calls.
timeout --signal=TERM --kill-after=10s 120s docker run --name "$NAME" \
  --network none --cpus 1 --memory 2g --memory-swap 2g --pids-limit 512 \
  --shm-size 1g --read-only --tmpfs /tmp:rw,nosuid,nodev,size=768m \
  --entrypoint /bin/bash "$IMAGE" -lc '
set -euo pipefail
[[ $(uname -m) == aarch64 ]]
[[ $(node -p process.arch) == arm64 ]]
[[ $(id -u) != 0 ]]
export HOME=/tmp DISPLAY=:99 XDG_RUNTIME_DIR=/tmp/runtime
mkdir -p /tmp/.X11-unix "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
Xvfb :99 -screen 0 1280x720x24 >/tmp/xvfb.log 2>&1 &
XV=$!
trap "kill $XV 2>/dev/null || true" EXIT
for n in $(seq 1 30); do [[ -S /tmp/.X11-unix/X99 ]] && break; sleep .1; done
[[ -S /tmp/.X11-unix/X99 ]]
pulseaudio --start --exit-idle-time=-1
pactl info
pactl load-module module-null-sink sink_name=labs_probe_sink >/tmp/sink-id
[[ -s /app/browser-utils.global.js ]]
cd /app/core/meetings/services/bot
node --input-type=module <<'"'"'JS'"'"'
import {createRequire} from "node:module";
const require=createRequire("/app/core/meetings/modules/remote-browser/package.json");
const {chromium}=require("playwright-extra");
const browser=await chromium.launch({headless:false,chromiumSandbox:true,args:["--autoplay-policy=no-user-gesture-required"]});
try{
 const page=await browser.newPage();
 await page.setContent("<!doctype html><title>Labs synthetic smoke</title><button>Audio test</button>");
 await page.addScriptTag({path:"/app/browser-utils.global.js"});
 const before=await page.evaluate(()=>({bundle:typeof window.VexaBrowserUtils,audio:typeof AudioContext,mediaRecorder:typeof MediaRecorder}));
 if(before.bundle==="undefined"||before.audio!=="function"||before.mediaRecorder!=="function")throw Error("Browser media/capture bundle missing");
 const samples=await page.evaluate(async()=>{const c=new AudioContext();await c.resume();const osc=c.createOscillator();const sink=c.createMediaStreamDestination();osc.connect(sink);osc.start();const tracks=sink.stream.getAudioTracks().length;osc.stop();await c.close();return tracks;});
 if(samples!==1)throw Error("Synthetic audio track missing");
 console.log(JSON.stringify({architecture:process.arch,syntheticBrowser:true,captureBundle:before.bundle,audioTrack:samples,network:"none",realMeet:false}));
}finally{await browser.close()}
JS
'
echo 'Synthetic ARM browser/audio smoke passed. Real Meet and upstream services remain untested.'
