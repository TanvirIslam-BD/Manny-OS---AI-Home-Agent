#!/usr/bin/env bash
# Manny hardware bring-up check.
#
# Presence checks confirm a prerequisite is installed. Function checks actually
# drive the device: they record real audio, play real sound, capture a real
# frame, and transcribe what the microphone heard. A binary being present tells
# you nothing about whether ALSA picked the right card or the mixer is muted,
# which is where first boot usually goes wrong.
#
# Usage:
#   ./scripts/verify_hardware.sh              presence + function checks
#   ./scripts/verify_hardware.sh --quick      presence checks only
#   ./scripts/verify_hardware.sh --no-audio   skip checks that emit sound
#   ./scripts/verify_hardware.sh --loopback   also verify the speaker reaches the mic

set -uo pipefail

quick=0
audio=1
loopback=0
for argument in "$@"; do
  case "${argument}" in
    --quick) quick=1 ;;
    --no-audio) audio=0 ;;
    --loopback) loopback=1 ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'unknown option: %s\n' "${argument}" >&2; exit 2 ;;
  esac
done

missing=0
failed=0
workspace="$(mktemp -d)"
trap 'rm -rf "${workspace}"' EXIT

: "${MANNY_AUDIO_DEVICE:=default}"
: "${MANNY_LED_STATE_PATH:=}"
: "${MANNY_DISPLAY_BRIGHTNESS_PATH:=}"
: "${MANNY_LLM_BASE_URL:=http://127.0.0.1:8080}"
capture_seconds=2

section() { printf '\n== %s ==\n' "$1"; }
ok()      { printf '  ok       %s\n' "$1"; }
skip()    { printf '  skip     %s%s\n' "$1" "${2:+ ($2)}"; }
absent()  { printf '  MISSING  %s\n' "$1" >&2; missing=$((missing + 1)); }
broken()  { printf '  FAILED   %s%s\n' "$1" "${2:+ - $2}" >&2; failed=$((failed + 1)); }

check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then ok "${label}"; else absent "${label}"; fi
}

# Root-mean-square of signed 16-bit little-endian PCM, 0.0 to 1.0.
pcm_level() {
  python3 - "$1" <<'PY' 2>/dev/null || printf '0'
import array, math, sys
raw = open(sys.argv[1], "rb").read()
samples = array.array("h")
samples.frombytes(raw[: len(raw) // 2 * 2])
if not samples:
    print("0")
else:
    print(f"{math.sqrt(sum(v * v for v in samples) / len(samples)) / 32768:.4f}")
PY
}

louder_than() {
  python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) >= float(sys.argv[2]) else 1)' "$1" "$2"
}

section 'Platform'
check 'ARM64 kernel' bash -c 'test "$(uname -m)" = aarch64'
check 'Raspberry Pi model' bash -c 'grep -qi raspberry /proc/device-tree/model'
check 'Python 3.12 or newer' python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'

section 'Prerequisites'
check 'camera command' command -v rpicam-hello
check 'camera detected' rpicam-hello --list-cameras
check 'audio capture utility' command -v arecord
check 'audio playback utility' command -v aplay
check 'audio capture device' bash -c 'arecord -l | grep -q card'
check 'audio playback device' bash -c 'aplay -l | grep -q card'
check 'Chromium kiosk' command -v chromium
check 'llama.cpp server' test -x /opt/manny/llama.cpp/build/bin/llama-server
check 'Gemma model' test -r /opt/manny/models/gemma-3-1b-it-Q4_K_M.gguf
check 'whisper.cpp CLI' test -x /opt/manny/whisper.cpp/build/bin/whisper-cli
check 'multilingual Whisper model' test -r /opt/manny/models/ggml-base.bin
check 'eSpeak NG' command -v espeak-ng

if (( quick == 1 )); then
  section 'Summary'
  printf '  %s missing\n' "${missing}"
  (( missing > 0 )) && exit 1
  printf '  presence checks passed; rerun without --quick to exercise the hardware\n'
  exit 0
fi

section 'Microphone capture'
recording="${workspace}/capture.raw"
if ! command -v arecord >/dev/null 2>&1; then
  skip 'record from the microphone' 'arecord not installed'
elif arecord -D "${MANNY_AUDIO_DEVICE}" -t raw -f S16_LE -r 16000 -c 1 \
      -d "${capture_seconds}" -q "${recording}" >/dev/null 2>&1; then
  level="$(pcm_level "${recording}")"
  if louder_than "${level}" 0.0005; then
    ok "record from the microphone (level ${level})"
  else
    broken 'record from the microphone' "silence captured (level ${level}); check the mixer is unmuted and MANNY_AUDIO_DEVICE=${MANNY_AUDIO_DEVICE} is the right card"
  fi
else
  broken 'record from the microphone' "arecord failed on device ${MANNY_AUDIO_DEVICE}"
fi

section 'Speech to text'
if [[ ! -s "${recording}" ]]; then
  skip 'transcribe the recording' 'nothing was captured'
elif [[ ! -x /opt/manny/whisper.cpp/build/bin/whisper-cli ]]; then
  skip 'transcribe the recording' 'whisper-cli not installed'
else
  wav="${workspace}/capture.wav"
  if python3 - "${recording}" "${wav}" <<'PY' >/dev/null 2>&1
import sys, wave
raw = open(sys.argv[1], "rb").read()
with wave.open(sys.argv[2], "wb") as out:
    out.setnchannels(1)
    out.setsampwidth(2)
    out.setframerate(16000)
    out.writeframes(raw)
PY
  then
    if /opt/manny/whisper.cpp/build/bin/whisper-cli -m /opt/manny/models/ggml-base.bin \
        -f "${wav}" -l auto -np -nt >"${workspace}/stt.txt" 2>/dev/null; then
      ok "transcribe the recording ($(tr -d '\n' < "${workspace}/stt.txt" | cut -c1-48))"
    else
      broken 'transcribe the recording' 'whisper-cli returned an error'
    fi
  else
    broken 'transcribe the recording' 'could not wrap the capture as WAV'
  fi
fi

section 'Text to speech'
spoken="${workspace}/spoken.wav"
if ! command -v espeak-ng >/dev/null 2>&1; then
  skip 'synthesize speech' 'espeak-ng not installed'
elif espeak-ng --stdout -v en "Manny hardware check" >"${spoken}" 2>/dev/null && [[ -s "${spoken}" ]]; then
  ok "synthesize speech ($(stat -c%s "${spoken}") bytes)"
else
  broken 'synthesize speech' 'espeak-ng produced no audio'
fi

section 'Speaker playback'
if (( audio == 0 )); then
  skip 'play through the speaker' '--no-audio'
elif ! command -v aplay >/dev/null 2>&1; then
  skip 'play through the speaker' 'aplay not installed'
elif [[ ! -s "${spoken}" ]]; then
  skip 'play through the speaker' 'nothing to play'
elif aplay -D "${MANNY_AUDIO_DEVICE}" -q "${spoken}" >/dev/null 2>&1; then
  ok 'play through the speaker (you should have heard a voice)'
else
  broken 'play through the speaker' "aplay failed on device ${MANNY_AUDIO_DEVICE}"
fi

if (( loopback == 1 && audio == 1 )); then
  section 'Acoustic loopback'
  echoed="${workspace}/echo.raw"
  arecord -D "${MANNY_AUDIO_DEVICE}" -t raw -f S16_LE -r 16000 -c 1 -d 3 -q "${echoed}" &
  recorder=$!
  sleep 0.3
  aplay -D "${MANNY_AUDIO_DEVICE}" -q "${spoken}" >/dev/null 2>&1
  wait "${recorder}" 2>/dev/null
  level="$(pcm_level "${echoed}")"
  if louder_than "${level}" 0.01; then
    ok "microphone hears the speaker (level ${level})"
  else
    broken 'microphone hears the speaker' "level ${level}; check placement and volume"
  fi
fi

section 'Camera'
if ! command -v rpicam-still >/dev/null 2>&1; then
  skip 'capture a frame' 'rpicam-still not installed'
else
  frame="${workspace}/frame.jpg"
  if rpicam-still --nopreview --immediate --width 640 --height 480 \
      -o "${frame}" >/dev/null 2>&1 && [[ -s "${frame}" ]]; then
    ok "capture a frame ($(stat -c%s "${frame}") bytes)"
  else
    broken 'capture a frame' 'rpicam-still produced no image'
  fi
fi

if python3 -c 'import picamera2' >/dev/null 2>&1; then
  ok 'picamera2 importable (required by the runtime adapter)'
else
  absent 'picamera2 python module'
fi

if python3 -c 'import cv2' >/dev/null 2>&1; then
  ok 'opencv importable (MANNY_PERSON_DETECTOR=opencv_hog)'
else
  skip 'opencv person detector' 'python3-opencv not installed; presence stays 0'
fi

section 'Display and indicators'
if [[ -n "${MANNY_DISPLAY_BRIGHTNESS_PATH}" ]]; then
  if [[ -w "${MANNY_DISPLAY_BRIGHTNESS_PATH}" ]]; then
    ok "display brightness writable (${MANNY_DISPLAY_BRIGHTNESS_PATH})"
  else
    broken 'display brightness writable' "${MANNY_DISPLAY_BRIGHTNESS_PATH} is not writable by this user"
  fi
else
  skip 'display brightness' 'MANNY_DISPLAY_BRIGHTNESS_PATH unset'
fi

if [[ -n "${MANNY_LED_STATE_PATH}" ]]; then
  if [[ -w "${MANNY_LED_STATE_PATH}" ]]; then
    ok "LED state writable (${MANNY_LED_STATE_PATH})"
  else
    broken 'LED state writable' "${MANNY_LED_STATE_PATH} is not writable by this user"
  fi
else
  skip 'LED indicator' 'MANNY_LED_STATE_PATH unset'
fi

section 'Local model'
if curl -sf --max-time 5 "${MANNY_LLM_BASE_URL}/health" >/dev/null 2>&1; then
  reply="$(curl -sf --max-time 60 "${MANNY_LLM_BASE_URL}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d '{"messages":[{"role":"user","content":"Reply with the word ready."}],"max_tokens":8,"stream":false}' 2>/dev/null)"
  if [[ -n "${reply}" ]]; then
    ok 'llama-server answers a completion'
  else
    broken 'llama-server answers a completion' 'health passed but generation failed'
  fi
else
  skip 'llama-server' "not responding on ${MANNY_LLM_BASE_URL}; start manny-llm first"
fi

section 'Configuration'
if python3 -c 'import manny.config' >/dev/null 2>&1; then
  if MANNY_CONFIG_PROFILE=raspberrypi python3 -c \
      'from manny.config import Settings; from manny.config import _read_profile; Settings(config_profile="raspberrypi", **_read_profile("raspberrypi"))' \
      >/dev/null 2>&1; then
    ok 'raspberrypi profile loads and validates'
  else
    broken 'raspberrypi profile' 'settings failed validation; check /opt/manny/.env'
  fi
else
  skip 'configuration' 'manny package not importable from here'
fi

section 'Summary'
printf '  %s missing, %s failed\n' "${missing}" "${failed}"
if (( missing > 0 || failed > 0 )); then
  printf '  see docs/hardware.md and docs/troubleshooting.md\n' >&2
  exit 1
fi
printf '  Hardware verified. Enable manny-llm, manny-core, and manny-kiosk when ready.\n'
