#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -m)" != aarch64 ]] || ! grep -qi raspberry /proc/device-tree/model; then
  echo 'This bootstrap only runs on an ARM64 Raspberry Pi.' >&2
  exit 1
fi
if [[ "${EUID}" -ne 0 ]]; then
  echo 'Run with sudo after reviewing this script.' >&2
  exit 1
fi
read -r -p 'Install Manny OS prerequisites and service user? [y/N] ' answer
[[ "${answer}" == y || "${answer}" == Y ]] || exit 0

apt-get update
apt-get install -y --no-install-recommends python3-venv python3-pip nodejs npm chromium alsa-utils rpicam-apps rsync
id manny >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin manny
install -d -o manny -g manny -m 0750 /opt/manny
echo 'Prerequisites installed. Run install_app_pi.sh from the reviewed Manny source tree.'
