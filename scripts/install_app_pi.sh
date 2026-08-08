#!/usr/bin/env bash
set -euo pipefail

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
install_root="/opt/manny"

if [[ "$(uname -m)" != aarch64 ]] || ! grep -qi raspberry /proc/device-tree/model; then
  echo 'This installer only runs on an ARM64 Raspberry Pi.' >&2
  exit 1
fi
if [[ "${EUID}" -ne 0 ]]; then
  echo 'Run with sudo after reviewing this script.' >&2
  exit 1
fi
if ! id manny >/dev/null 2>&1; then
  echo 'Run bootstrap_pi.sh first to create the manny service user.' >&2
  exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
  echo 'Manny requires Python 3.12 or newer. Upgrade Python before installing.' >&2
  exit 1
fi

read -r -p 'Copy Manny to /opt/manny and install its Python/UI dependencies? [y/N] ' answer
[[ "${answer}" == y || "${answer}" == Y ]] || exit 0

install -d -o manny -g manny -m 0750 "${install_root}"
install -d -o manny -g manny -m 0750 "${install_root}/data" "${install_root}/logs"

if [[ "${source_root}" != "${install_root}" ]]; then
  rsync -a --chown=manny:manny \
    --exclude='.env' --exclude='.git' --exclude='.venv' --exclude='data' \
    --exclude='logs' --exclude='node_modules' --exclude='release' \
    "${source_root}/" "${install_root}/"
fi

runuser -u manny -- python3 -m venv "${install_root}/.venv"
runuser -u manny -- "${install_root}/.venv/bin/python" -m pip install --upgrade pip
runuser -u manny -- "${install_root}/.venv/bin/python" -m pip install "${install_root}"
runuser -u manny -- npm ci --prefix "${install_root}/apps/ui"
runuser -u manny -- npm run build --prefix "${install_root}/apps/ui"

echo 'Manny application installed. Provision /opt/manny/.env, then install Gemma and systemd units.'
