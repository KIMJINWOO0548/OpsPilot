"""Validate essential source files before local setup and development."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
mandatory=["AGENTS.md","START_HERE.md","docs/reference/Plan_v2.0.md",
           "docs/TASK_BOARD.md","docs/architecture/EIE_CONTRACT.md","docs/evaluation/EVAL_PROTOCOL.md",
           "src/opspilot_x/eie.py","src/opspilot_x/api.py","src/opspilot_x/auth.py",
           "src/opspilot_x/evidence_store.py","tests/test_eie.py","tests/test_auth.py",
           "web/package.json","web/pnpm-lock.yaml","web/src/main.tsx","Dockerfile",
           "docker-compose.yml","requirements-runtime.lock","docs/DEPLOYMENT.md",
           "src/opspilot_x/database_backup.py","scripts/backup_db.py",
           "tests/test_account_lifecycle.py","tests/test_database_backup.py",
           "evaluation/datasets/SMOKE_ONLY_cases.jsonl"]
missing=[p for p in mandatory if not (root/p).is_file()]
print('Required files:',len(mandatory),'missing:',missing)
if missing:raise SystemExit(1)
