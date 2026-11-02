from pathlib import Path
import json
from opspilot_x.eie import evaluate
from opspilot_x.schema import AnalyzeRequest


def test_smoke_fixtures_are_consistent():
    root=Path(__file__).resolve().parents[1]
    lines=(root/'evaluation/datasets/SMOKE_ONLY_cases.jsonl').read_text().splitlines()
    for line in lines:
        case=json.loads(line)
        actor={"user_id":"test","role":case['role'],"tenant":"demo","team":"team_a"}
        request=AnalyzeRequest.model_validate({"actor":actor,"asset_id":case['asset_id'],
            "claim_key":"inspection_priority","effective_at":case['effective_at'],
            "known_as_of":case['known_as_of']})
        actual=evaluate(request)
        assert actual.state==case['expected_state'],case['case_id']
        assert actual.recommended_action==case['expected_action'],case['case_id']
