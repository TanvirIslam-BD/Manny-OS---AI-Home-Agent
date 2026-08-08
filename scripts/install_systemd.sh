#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo 'Run with sudo after reviewing the unit files.' >&2
  exit 1
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
install -m 0644 "${root}/systemd/manny-core.service" /etc/systemd/system/manny-core.service
install -m 0644 "${root}/systemd/manny-kiosk.service" /etc/systemd/system/manny-kiosk.service
install -m 0644 "${root}/systemd/manny-llm.service" /etc/systemd/system/manny-llm.service
systemctl daemon-reload
echo 'Units installed but not enabled. Configure /opt/manny/.env, then enable manny-llm, manny-core, and manny-kiosk explicitly.'
