#!/usr/bin/env bash
set -euo pipefail

archive="${1:?usage: verify_update.sh ARCHIVE PUBLIC_KEY}"
public_key="${2:?usage: verify_update.sh ARCHIVE PUBLIC_KEY}"
sha256sum --check "${archive}.sha256"
test -f "${archive}.minisig"
minisign -V -p "${public_key}" -m "${archive}"
echo 'Checksum and signature verified. Installation remains a separate explicit action.'
