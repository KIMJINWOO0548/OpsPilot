"""Read-only bitemporal comparison keeps caller ACL and execution state intact."""
from contextlib import closing
import sqlite3

from fastapi.testclient import TestClient
import pytest

from conftest import PASSWORD, login
from opspilot_x.api import create_app
from opspilot_x.auth import create_user
from opspilot_x.comparison import compare_snapshots
from opspilot_x.eie import load_seed
from opspilot_x.evidence_store import initialize_evidence
from opspilot_x.schema import Analysis, Citation
from test_api import approve, draft


ENDPOINT = "/api/v1/analysis/compare"


def comparison(**updates):
    return {
        "asset_id": "A-104",
        "claim_key": "inspection_priority",
        "effective_at": "2026-09-20T12:00:00+09:00",
        "before_known_as_of": "2026-09-20T12:00:00+09:00",
        "after_known_as_of": "2026-10-06T12:00:00+09:00",
        **updates,
    }


def ids(citations):
    return [item["evidence_id"] for item in citations]


def post_comparison(client, **updates):
    response = client.post(ENDPOINT, json=comparison(**updates))
    assert response.status_code == 200, response.text
    return response.json()


def assert_unchanged(report):
    assert report["changed"] is False
    assert report["changes"] == {
        "state_changed": False, "action_changed": False,
        "added_citations": [], "removed_citations": [],
    }


def test_retroactive_correction_compares_actions_and_visible_citations(client):
    report = post_comparison(client)
    before, after = report["before"], report["after"]
    assert before["state"] == after["state"] == "SUPPORTED"
    assert before["recommended_action"] == "manual_inspection"
    assert after["recommended_action"] == "sensor_diagnostic_first"
    assert before["effective_at"] == after["effective_at"]
    assert before["known_as_of"] != after["known_as_of"]
    assert ids(before["citations"]) == ["SOP-A104-v1"]
    assert ids(after["citations"]) == ["SOP-A104-correction"]
    assert report["changed"] is True
    assert report["changes"] == {
        "state_changed": False, "action_changed": True,
        "added_citations": after["citations"], "removed_citations": before["citations"],
    }


@pytest.mark.parametrize("after", [
    "2026-09-20T12:00:00+09:00", "2026-09-21T12:00:00+09:00",
])
def test_identical_decision_is_unchanged_even_with_different_cutoffs(client, after):
    report = post_comparison(client, after_known_as_of=after)
    assert report["before"]["recommended_action"] == "manual_inspection"
    assert report["after"]["recommended_action"] == "manual_inspection"
    assert_unchanged(report)


def test_comparison_reports_state_change_when_revision_becomes_known(client):
    report = post_comparison(
        client, asset_id="A-103", effective_at="2026-10-02T12:00:00+09:00",
        before_known_as_of="2026-10-02T12:00:00+09:00",
        after_known_as_of="2026-10-04T12:00:00+09:00",
    )
    assert report["before"]["state"] == "STALE"
    assert report["before"]["recommended_action"] is None
    assert report["after"]["state"] == "SUPPORTED"
    assert report["after"]["recommended_action"] == "sensor_diagnostic_first"
    assert report["changed"] is True
    assert report["changes"]["state_changed"] is True
    assert report["changes"]["action_changed"] is True
    assert ids(report["changes"]["added_citations"]) == ["SOP-A103-v2"]
    assert report["changes"]["removed_citations"] == []


def test_comparison_preserves_conflict_instead_of_selecting_an_action(client):
    report = post_comparison(
        client, asset_id="A-105", effective_at="2026-10-19T12:00:00+09:00",
        before_known_as_of="2026-10-18T12:00:00+09:00",
        after_known_as_of="2026-10-19T12:00:00+09:00",
    )
    for snapshot in (report["before"], report["after"]):
        assert snapshot["state"] == "CONFLICT"
        assert snapshot["recommended_action"] is None
        assert ids(snapshot["citations"]) == ["SOP-A105-a", "SOP-A105-b"]
    assert_unchanged(report)


def business_rows(path):
    with closing(sqlite3.connect(path)) as db:
        return {table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                for table in ("proposals", "work_orders", "audit")}


def test_historical_comparison_has_no_writes_and_preserves_receipt_recovery(
    client, tmp_path, engineer, approver,
):
    proposal = draft(client, engineer)
    assert approve(client, proposal, approver).status_code == 200
    proposal_endpoint = "/api/v1/proposals/" + proposal["proposal_id"]
    lost = client.post(proposal_endpoint + "/execute", json={"simulate_response_loss": True})
    assert lost.json()["state"] == "UNKNOWN_RECONCILE"
    before_rows = business_rows(tmp_path / "test.sqlite3")
    receipt = before_rows["work_orders"][0][2]

    report = post_comparison(client)
    assert report["changed"] is True
    assert business_rows(tmp_path / "test.sqlite3") == before_rows
    for key in ("proposal_id", "fingerprint", "receipt_id"):
        assert key not in report

    recovered = client.post(proposal_endpoint + "/reconcile", json={})
    assert recovered.status_code == 200
    assert recovered.json() == {"state": "SUCCEEDED", "receipt_id": receipt}
    assert len(business_rows(tmp_path / "test.sqlite3")["work_orders"]) == 1


def test_comparison_requires_session_and_csrf(client, tmp_path):
    with TestClient(create_app(tmp_path / "anonymous.sqlite3")) as anonymous:
        assert anonymous.post(ENDPOINT, json=comparison()).status_code == 401
    assert client.post(ENDPOINT, json=comparison(),
                       headers={"X-CSRF-Token": ""}).status_code == 403
    assert client.post(ENDPOINT, json=comparison(),
                       headers={"Origin": "https://untrusted.example"}).status_code == 403


def test_forged_actor_cannot_change_visible_scope(client, approver, tmp_path):
    forged = dict(approver, tenant="elsewhere")
    assert post_comparison(client, actor=forged) == post_comparison(client)

    source = load_seed()[1].model_copy(update={
        "evidence_id": "compare-hidden-sop", "source_id": "compare-hidden-source",
        "asset_id": "COMPARE-RESTRICTED", "locator": "compare-hidden-location",
        "supersedes": [], "readable_roles": ["approver"],
    })
    initialize_evidence(tmp_path / "test.sqlite3", [source])
    times = {
        "effective_at": "2026-10-19T12:00:00+09:00",
        "before_known_as_of": "2026-10-18T12:00:00+09:00",
        "after_known_as_of": "2026-10-19T12:00:00+09:00",
    }
    hidden = post_comparison(client, actor=approver, asset_id=source.asset_id, **times)
    missing = post_comparison(client, asset_id="DOES-NOT-EXIST", **times)
    assert hidden == missing
    for key in (source.evidence_id, source.source_id, source.locator, source.checksum, source.text):
        assert key not in str(hidden)


@pytest.mark.parametrize("principal,asset", [
    ("other-tenant", "A-104"), ("compare-viewer", "A-105"),
])
def test_hidden_evidence_is_indistinguishable_from_missing(client, tmp_path, principal, asset):
    if principal == "compare-viewer":
        create_user(tmp_path / "test.sqlite3", username=principal, user_id=principal,
                    password=PASSWORD, tenant="demo", team="team_a", role="viewer")
    login(client, principal)
    times = {
        "effective_at": "2026-10-19T12:00:00+09:00",
        "before_known_as_of": "2026-10-18T12:00:00+09:00",
        "after_known_as_of": "2026-10-19T12:00:00+09:00",
    }
    hidden = post_comparison(client, asset_id=asset, **times)
    assert hidden == post_comparison(client, asset_id="DOES-NOT-EXIST", **times)
    for snapshot in (hidden["before"], hidden["after"]):
        assert snapshot["state"] == "INSUFFICIENT"
        assert snapshot["recommended_action"] is None
        assert snapshot["citations"] == []
    assert_unchanged(hidden)


@pytest.mark.parametrize("field", [
    "effective_at", "before_known_as_of", "after_known_as_of",
])
def test_comparison_rejects_timestamps_without_timezone(client, field):
    response = client.post(ENDPOINT, json=comparison(**{field: "2026-09-20T12:00:00"}))
    assert response.status_code == 422


def test_comparison_rejects_reversed_observation_cutoffs(client):
    response = client.post(ENDPOINT, json=comparison(
        before_known_as_of="2026-10-06T12:00:00+09:00",
        after_known_as_of="2026-09-20T12:00:00+09:00",
    ))
    assert response.status_code == 422


def test_each_snapshot_filters_acl_and_known_cutoff_before_evaluation(client, monkeypatch):
    import opspilot_x.api as api
    real_evaluate = api.evaluate
    seen = []

    def capture(request, *, seed):
        seen.append((request.actor.user_id, request.known_as_of,
                     {item.evidence_id for item in seed}))
        return real_evaluate(request, seed=seed)

    monkeypatch.setattr(api, "evaluate", capture)
    post_comparison(client)
    assert len(seen) == 2
    assert all(user == "engineer-1" for user, _, _ in seen)
    assert seen[0][1] < seen[1][1]
    assert seen[0][2] == {"SOP-A104-v1"}
    assert seen[1][2] == {"SOP-A104-v1", "SOP-A104-correction"}


def test_comparison_uses_one_acl_snapshot_and_next_request_sees_revocation(
    client, tmp_path, monkeypatch,
):
    import opspilot_x.api as api
    path = tmp_path / "test.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    real_query = api.authorized_evidence
    calls = 0

    def revoke_after_first_read(*args, **kwargs):
        nonlocal calls
        candidates = real_query(*args, **kwargs)
        calls += 1
        if calls == 1:
            # An independent writer commits between the two snapshot reads. WAL
            # lets this finish while the comparison's existing read view stays open.
            with closing(sqlite3.connect(path)) as writer, writer:
                writer.execute("DELETE FROM evidence_acl WHERE evidence_id=? AND role=?",
                               ("SOP-A104-correction", "engineer"))
        return candidates

    monkeypatch.setattr(api, "authorized_evidence", revoke_after_first_read)
    in_progress = post_comparison(client)
    assert calls == 2
    assert in_progress["before"]["recommended_action"] == "manual_inspection"
    assert in_progress["after"]["recommended_action"] == "sensor_diagnostic_first"

    next_request = post_comparison(client)
    assert calls == 4
    assert next_request["before"]["recommended_action"] == "manual_inspection"
    assert next_request["after"]["recommended_action"] == "manual_inspection"
    assert "SOP-A104-correction" not in str(next_request)
    assert_unchanged(next_request)


def decision_snapshot(citations):
    return Analysis(
        state="SUPPORTED", recommended_action="manual_inspection", reason="Visible SOP",
        citations=citations, effective_at="2026-09-20T12:00:00+09:00",
        known_as_of="2026-09-20T12:00:00+09:00",
    )


@pytest.mark.parametrize("field,value", [
    ("source_id", "different-source"), ("source_version", "2"),
    ("locator", "changed-location"), ("checksum", "b" * 64),
])
def test_citation_metadata_change_is_detected_even_with_same_evidence_id(field, value):
    original = Citation(evidence_id="same-id", source_id="source", source_version="1",
                        locator="section-1", checksum="a" * 64)
    updated = original.model_copy(update={field: value})
    result = compare_snapshots(decision_snapshot([original]), decision_snapshot([updated]))
    assert result.changed is True
    assert result.changes.state_changed is False
    assert result.changes.action_changed is False
    assert result.changes.removed_citations == [original]
    assert result.changes.added_citations == [updated]


def test_reordering_same_citations_does_not_report_a_decision_change():
    first = Citation(evidence_id="first", source_id="source", source_version="1",
                     locator="section-1", checksum="a" * 64)
    second = first.model_copy(update={"evidence_id": "second"})
    result = compare_snapshots(
        decision_snapshot([first, second]), decision_snapshot([second, first]),
    )
    assert_unchanged(result.model_dump(mode="json"))


def test_saved_review_comparison_preserves_context_and_response_loss_recovery(client, engineer, approver):
    from datetime import datetime, timezone
    proposal = draft(client, engineer)
    login(client, approver["user_id"])
    url = '/api/v1/proposals/' + proposal['proposal_id']
    saved = client.get(url).json()
    context = saved['review_context']
    assert saved['evidence_reviewable'] is True
    response = client.post(ENDPOINT, json={
        'asset_id': saved['asset_id'], 'claim_key': context['claim_key'],
        'effective_at': context['effective_at'],
        'before_known_as_of': context['known_as_of'],
        'after_known_as_of': datetime.now(timezone.utc).isoformat(),
    })
    assert response.status_code == 200
    assert response.json()['before']['citations'] == saved['citations']
    unchanged = client.get(url).json()
    assert unchanged == saved, 'read-only comparison must not alter draft or readiness'
    assert approve(client, proposal, approver).status_code == 200
    lost = client.post(url + '/execute', json={'simulate_response_loss': True})
    assert lost.status_code == 200
    assert lost.json() == {'state': 'UNKNOWN_RECONCILE', 'receipt_id': None}
    recovered = client.post(url + '/reconcile', json={})
    assert recovered.status_code == 200
    again = client.post(url + '/reconcile', json={})
    assert again.status_code == 200
    assert recovered.json() == again.json()
