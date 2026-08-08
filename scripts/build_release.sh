#!/usr/bin/env bash
set -euo pipefail
python -m pytest
(cd apps/ui && npm run build)
echo 'Phase 0 development artifacts built successfully.'
