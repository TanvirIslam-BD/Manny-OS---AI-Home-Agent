#!/usr/bin/env bash
set -euo pipefail

failures=0
check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'ok: %s\n' "$label"
  else
    printf 'missing: %s\n' "$label" >&2
    failures=$((failures + 1))
  fi
}

check 'ARM64 kernel' bash -c 'test "$(uname -m)" = aarch64'
check 'Raspberry Pi model' bash -c 'grep -qi raspberry /proc/device-tree/model'
check 'camera command' command -v rpicam-hello
check 'camera detected' rpicam-hello --list-cameras
check 'audio capture utility' command -v arecord
check 'audio playback utility' command -v aplay
check 'audio capture device' bash -c 'arecord -l | grep -q card'
check 'audio playback device' bash -c 'aplay -l | grep -q card'
check 'Chromium kiosk' command -v chromium
check 'llama.cpp server' test -x /opt/manny/llama.cpp/build/bin/llama-server
check 'Gemma model' test -r /opt/manny/models/gemma-3-1b-it-Q4_K_M.gguf

if (( failures > 0 )); then
  printf '%s hardware checks failed; see docs/hardware.md\n' "$failures" >&2
  exit 1
fi
printf 'Manny hardware prerequisites detected. Run physical acceptance tests next.\n'
