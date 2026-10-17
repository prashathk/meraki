#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3.13}"
"$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3,13), "Python 3.13 required"'
node -e 'if(Number(process.versions.node.split(".")[0])!==22)process.exit(1)'
if [ ! -d .venv ]; then "$PYTHON" -m venv .venv; fi
.venv/bin/python -m pip install -r backend/requirements.lock.txt
mkdir -p data output
if [ ! -f .env ]; then cp .env.example .env; fi
.venv/bin/python -m scripts.configure_local
(cd frontend && npm ci && npm run build)
printf '%s\n' 'Setup complete. See HANDOVER.md for API/worker startup and optional ontology migration. Existing .env was preserved.'
