from copy import deepcopy
import pytest

from opspilot_x.eie import evaluate, load_seed
from opspilot_x.schema import AnalyzeRequest


def test_current_revision_uses_v2(current):
    outcome=evaluate(AnalyzeRequest.model_validate(current))
    assert outcome.state=="SUPPORTED"
    assert outcome.recommended_action=="sensor_diagnostic_first"
    assert [c.evidence_id for c in outcome.citations]==["SOP-A103-v2"]


def test_historical_cutoff_does_not_know_retroactive_correction(current):
    request=deepcopy(current)
    request.update(asset_id="A-104",effective_at="2026-09-20T12:00:00+09:00",known_as_of="2026-09-20T12:00:00+09:00")
    before=evaluate(AnalyzeRequest.model_validate(request))
    assert before.recommended_action=="manual_inspection"
    request['known_as_of']="2026-10-19T12:00:00+09:00"
    after=evaluate(AnalyzeRequest.model_validate(request))
    assert after.recommended_action=="sensor_diagnostic_first"


def test_valid_time_boundary_when_revision_not_known_yet(current):
    request=deepcopy(current)
    request.update(effective_at="2026-10-02T12:00:00+09:00",known_as_of="2026-10-02T12:00:00+09:00")
    outcome=evaluate(AnalyzeRequest.model_validate(request))
    assert outcome.state=="STALE" and outcome.recommended_action is None


def test_conflict_prevents_action(current):
    request={**current,'asset_id':'A-105'}
    result=evaluate(AnalyzeRequest.model_validate(request))
    assert result.state=='CONFLICT'
    assert result.recommended_action is None
    assert len(result.citations)==2


def test_acl_filtered_before_any_explanation(current):
    request={**current,'asset_id':'SECRET-1'}
    result=evaluate(AnalyzeRequest.model_validate(request))
    assert result.state=='INSUFFICIENT'
    assert result.citations==[]
    assert 'PRIVATE' not in result.model_dump_json()


def test_viewer_cannot_see_engineer_conflict(current):
    request=deepcopy(current)
    request['actor']['role']='viewer'
    request['asset_id']='A-105'
    assert evaluate(AnalyzeRequest.model_validate(request)).state=='INSUFFICIENT'


def test_embedded_prompt_injection_is_not_an_instruction(current):
    request={**current,'asset_id':'A-106'}
    result=evaluate(AnalyzeRequest.model_validate(request))
    assert result.recommended_action=='manual_inspection'
    assert result.state=='SUPPORTED'
    assert 'Ignore all safety' not in result.model_dump_json()


def test_naive_dates_rejected(current):
    request={**current,'effective_at':'2026-10-19T18:00:00'}
    with pytest.raises(ValueError):AnalyzeRequest.model_validate(request)


def test_fixture_checksum_integrity(current):
    import hashlib
    for e in load_seed():
        assert hashlib.sha256(e.text.encode()).hexdigest() == e.checksum
