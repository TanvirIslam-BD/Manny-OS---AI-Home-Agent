#!/usr/bin/env bash
# Load the ALSA loopback driver so the real audio adapters can be exercised
# without a sound card.
#
# snd-aloop pairs a playback device with a capture device: anything written to
# hw:Loopback,0,0 is readable from hw:Loopback,1,0. That gives arecord and aplay
# a genuine ALSA pipeline, which is enough to catch device-string and format
# mistakes that unit tests against mocks cannot see.
#
# This is a development and CI aid. It is not a substitute for a Raspberry Pi:
# a real codec can still disagree about sample rates or arrive muted.
#
# Usage:  sudo ./scripts/setup_audio_loopback.sh
#         ./scripts/setup_audio_loopback.sh --check

set -uo pipefail

if [[ "${1:-}" == "--check" ]]; then
  if command -v arecord >/dev/null 2>&1 && arecord -l 2>/dev/null | grep -q Loopback; then
    printf 'ALSA loopback is available\n'
    exit 0
  fi
  printf 'ALSA loopback is not loaded\n' >&2
  exit 1
fi

if [[ "$(uname -s)" != Linux ]]; then
  printf 'snd-aloop is a Linux kernel module; this host is %s\n' "$(uname -s)" >&2
  exit 1
fi

if [[ "${EUID}" -ne 0 ]]; then
  printf 'Run with sudo: modprobe needs root.\n' >&2
  exit 1
fi

if ! command -v arecord >/dev/null 2>&1; then
  printf 'Installing alsa-utils...\n'
  apt-get update -qq && apt-get install -y -qq alsa-utils
fi

if ! modprobe snd-aloop 2>/dev/null; then
  printf 'modprobe snd-aloop failed; installing matching kernel modules...\n' >&2
  apt-get install -y -qq "linux-modules-extra-$(uname -r)" 2>/dev/null || true
  if ! modprobe snd-aloop; then
    printf 'Could not load snd-aloop. The audio adapter tests will skip.\n' >&2
    exit 1
  fi
fi

printf 'snd-aloop loaded.\n\n'
arecord -l | sed 's/^/  /'
printf '\nPlayback into hw:Loopback,0,0 is captured from hw:Loopback,1,0\n'
