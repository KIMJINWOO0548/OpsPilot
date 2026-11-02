"""Tiny deterministic fixture validation, NOT external research or a benchmark.

python scripts/eval_smoke.py --output evaluation/reports/local_smoke.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from opspilot_x.eie import evaluate
from opspilot_x.schema import AnalyzeRequest

parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
path=root/'evaluation/datasets/SMOKE_ONLY_cases.jsonl'
cases=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
checks=[]
for c in cases:
    actor={"user_id":"eval-test-user","role":c['role'],"tenant":"demo","team":"team_a"}
    q=AnalyzeRequest.model_validate({"actor":actor,"asset_id":c['asset_id'],
        "claim_key":"inspection_priority", "effective_at":c['effective_at'], "known_as_of":c['known_as_of']})
    answer=evaluate(q)
    correct=(answer.state==c['expected_state'] and answer.recommended_action==c['expected_action'])
    checks.append({"case_id":c['case_id'],"pass":correct,"expected_state":c['expected_state'],
                   "predicted_state":answer.state,"expected_action":c['expected_action'],
                   "predicted_action":answer.recommended_action})
result={"result_type":"SYNTHETIC_SMOKE_CHECK_NOT_BENCHMARK", "case_count":len(checks),
        "pass_count":sum(x['pass'] for x in checks),"fixture_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "executed_at_utc":datetime.now(timezone.utc).isoformat(), "checks":checks,
        "warning":"Test labels and deterministic rules share the same authored fixtures. Never claim accuracy or generalization from this file."}
if args.output:
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2,ensure_ascii=False))
if len(checks)!=len(cases) or any(not x['pass'] for x in checks):
    raise SystemExit(1)
