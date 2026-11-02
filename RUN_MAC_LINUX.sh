#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
command -v pnpm >/dev/null || { echo 'Install Node.js 24 and pnpm 11 first.'; exit 1; }
python -m pip install -c requirements-runtime.lock -e '.[dev]'
(cd web && pnpm install --frozen-lockfile && pnpm build)
python -m pytest -q
python scripts/smoke_demo.py
echo 'Provision engineer and independent approver accounts: see docs/DEPLOYMENT.md.'
echo 'Open http://127.0.0.1:8000. Ctrl+C stops server.'
python -m uvicorn opspilot_x.api:app --host 127.0.0.1 --port 8000
