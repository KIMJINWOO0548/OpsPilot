"""Proposal review uses each caller's current document ACL, not the drafter's."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from conftest import login, seed_users
from opspilot_x.api import create_app
from opspilot_x.eie import load_seed
from opspilot_x.evidence_store import initialize_evidence
from test_api import live_request


@pytest.fixture
def review_case(tmp_path, engineer):
    path = tmp_path / "review.sqlite3"
    seed_users(path)
    app = create_app(path)
    source = load_seed()[1].model_copy(update={
        "evidence_id": "review-only-sop", "source_id": "review-only-source",
        "asset_id": "REVIEW-ASSET", "locator": "review-only-location",
        "supersedes": [], "readable_roles": ["engineer", "approver"],
    })
    initialize_evidence(path, [source])
    with TestClient(app) as client:
        login(client, engineer["user_id"])
        request = live_request(engineer)
        request["asset_id"] = source.asset_id
        response = client.post("/api/v1/proposals", json={"request": request})
        assert response.status_code == 201
        yield client, path, source, response.json()


def restrict_reviewer(path, source):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("DELETE FROM evidence_acl WHERE evidence_id=? AND role='approver'",
                   (source.evidence_id,))


def endpoint(proposal):
    return "/api/v1/proposals/" + proposal["proposal_id"]


def decision(client, proposal):
    return client.post(endpoint(proposal) + "/decision", json={
        "decision": "approve", "expected_hash": proposal["fingerprint"],
    })


def assert_no_hidden_metadata(response, source):
    for value in (source.evidence_id, source.source_id, source.locator,
                  source.checksum, source.text):
        assert value not in response.text


def assert_no_work_orders(path):
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0] == 0


def test_detail_filters_before_evaluation_using_current_principal(review_case, monkeypatch):
    client, path, source, proposal = review_case
    restrict_reviewer(path, source)
    login(client, "approver-1")
    assert client.get("/api/v1/evidence", params={"asset_id": source.asset_id}).json() == {
        "items": [],
    }
    import opspilot_x.api as api
    real_evaluate = api.evaluate
    seen = []

    def evaluate_visible(request, *, seed):
        seen.append((request.actor.user_id, {item.evidence_id for item in seed}))
        return real_evaluate(request, seed=seed)

    monkeypatch.setattr(api, "evaluate", evaluate_visible)
    response = client.get(endpoint(proposal))
    assert response.status_code == 200
    assert response.json()["evidence_reviewable"] is False
    assert response.json()["citations"] == []
    assert_no_hidden_metadata(response, source)
    assert seen and all(actor == "approver-1" and source.evidence_id not in ids
                        for actor, ids in seen)


@pytest.mark.parametrize("stage", ["decision", "execute"])
@pytest.mark.parametrize("change", ["revoke", "delete", "expire"])
def test_changed_evidence_blocks_review_and_first_execution(
    review_case, stage, change, monkeypatch,
):
    client, path, source, proposal = review_case
    login(client, "approver-1")
    if stage == "execute":
        assert decision(client, proposal).status_code == 200
    if change == "revoke":
        restrict_reviewer(path, source)
    elif change == "delete":
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("DELETE FROM evidence_acl WHERE evidence_id=?", (source.evidence_id,))
            db.execute("DELETE FROM evidence_documents WHERE evidence_id=?", (source.evidence_id,))
    else:
        import opspilot_x.api as api
        cutoff = datetime.now(timezone.utc) + timedelta(minutes=1)
        payload = source.model_dump(mode="json")
        payload["valid_to"] = cutoff.isoformat()
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE evidence_documents SET payload=? WHERE evidence_id=?",
                       (json.dumps(payload), source.evidence_id))

        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return (cutoff + timedelta(minutes=1)).astimezone(tz)

        monkeypatch.setattr(api, "datetime", Later)
    detail = client.get(endpoint(proposal))
    assert detail.status_code == 200
    assert detail.json()["state"] == ("APPROVED" if stage == "execute" else "PENDING_APPROVAL")
    assert detail.json()["evidence_reviewable"] is False
    response = (decision(client, proposal) if stage == "decision" else
                client.post(endpoint(proposal) + "/execute", json={}))
    assert response.status_code == 409
    assert_no_hidden_metadata(response, source)
    assert client.get(endpoint(proposal)).json()["state"] == "EXPIRED"
    assert_no_work_orders(path)


def test_visible_sources_preserve_independent_approval_and_receipt_recovery(review_case):
    client, path, source, proposal = review_case
    assert decision(client, proposal).status_code == 403
    login(client, "approver-1")
    detail = client.get(endpoint(proposal)).json()
    assert detail["evidence_reviewable"] is True
    assert detail["fingerprint"] == proposal["fingerprint"]
    assert [item["evidence_id"] for item in detail["citations"]] == [source.evidence_id]
    assert decision(client, proposal).status_code == 200
    lost = client.post(endpoint(proposal) + "/execute", json={"simulate_response_loss": True})
    assert lost.json() == {"state": "UNKNOWN_RECONCILE", "receipt_id": None}
    # Receipt recovery must not repeat an external write after document ACL changes.
    restrict_reviewer(path, source)
    unavailable = client.get(endpoint(proposal))
    assert unavailable.json()["state"] == "UNKNOWN_RECONCILE"
    assert unavailable.json()["evidence_reviewable"] is False
    assert unavailable.json()["citations"] == []
    assert_no_hidden_metadata(unavailable, source)
    recovered = client.post(endpoint(proposal) + "/reconcile", json={})
    retry = client.post(endpoint(proposal) + "/execute", json={})
    assert recovered.status_code == retry.status_code == 200
    assert recovered.json()["receipt_id"] == retry.json()["receipt_id"]
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0] == 1


@pytest.mark.parametrize("already_approved", [False, True])
def test_detail_rejects_stored_action_tamper_before_mutation(review_case, already_approved):
    client, path, source, proposal = review_case
    login(client, "approver-1")
    if already_approved:
        assert decision(client, proposal).status_code == 200
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE proposals SET action=? WHERE id=?",
                   ("unapproved_action", proposal["proposal_id"]))
    detail = client.get(endpoint(proposal))
    assert detail.status_code == 200
    assert detail.json()["state"] == ("APPROVED" if already_approved else "PENDING_APPROVAL")
    assert detail.json()["evidence_reviewable"] is False
    assert_no_work_orders(path)
