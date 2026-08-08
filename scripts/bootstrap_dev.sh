#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
(cd apps/ui && npm install)
echo 'Development setup complete. Run: make dev'
