#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="${1:-dev}"
output="${root}/release"
mkdir -p "${output}"

python -m pytest
(cd "${root}/apps/ui" && npm ci && npm run lint && npm run test && npm run build)
python -m build --outdir "${output}"
archive="${output}/manny-os-${version}.tar.gz"
tar --exclude='.git' --exclude='.venv' --exclude='node_modules' --exclude='data' \
  --exclude='release' -czf "${archive}" -C "${root}" .
sha256sum "${archive}" > "${archive}.sha256"

if [[ -n "${MANNY_MINISIGN_SECRET_KEY:-}" ]]; then
  command -v minisign >/dev/null
  minisign -S -s "${MANNY_MINISIGN_SECRET_KEY}" -m "${archive}"
  echo 'Signed release created.'
else
  echo 'Unsigned development release created; production distribution requires MANNY_MINISIGN_SECRET_KEY.'
fi
