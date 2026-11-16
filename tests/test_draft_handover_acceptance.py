"""Product API acceptance checks with synthetic accounts and an owned database."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from threading import Barrier

from fastapi.testclient import TestClient
import pytest

from conftest import PASSWORD, login, seed_users
from opspilot_x import auth
from opspilot_x.api import create_app
from opspilot_x.database_backup import backup_database, restore_database


PROPOSALS = "/api/v1/proposals"
DRAFT_INTENT = "/api/v1/draft-intent"
UNKNOWN = {"state": "UNKNOWN_RECONCILE", "receipt_id": None}


@pytest.fixture
def case(tmp_path):
    path = tmp_path / "handover.sqlite3"
    seed_users(path)
    for user_id, role in [("engineer-2", "engineer"), ("reviewer-2", "approver")]:
        auth.create_user(path, username=user_id, password=PASSWORD, user_id=user_id,
                         tenant="demo", team="team_a", role=role)
    return path, create_app(path)


def current_request():
    now = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    return {"asset_id": "A-103", "claim_key": "inspection_priority",
            "effective_at": now, "known_as_of": now}


def create_draft(client, *, key=None, request=None):
    headers = {"Idempotency-Key": key} if key is not None else {}
    return client.post(PROPOSALS, headers=headers, json={"request": request or current_request()})


def new_proposal(client):
    response = create_draft(client)
    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft["state"] == "PENDING_APPROVAL"
    assert draft["action"] == "sensor_diagnostic_first"
    assert draft["citations"]
    return PROPOSALS + "/" + draft["proposal_id"], draft


def decision(client, endpoint, fingerprint, version=None):
    body = {"decision": "approve", "expected_hash": fingerprint}
    if version is not None:
        body["expected_version"] = version
    return client.post(endpoint + "/decision", json=body)


def handover(client, endpoint, fingerprint, version, reason="Previous reviewer unavailable"):
    return client.post(endpoint + "/handover", json={
        "expected_hash": fingerprint, "expected_version": version, "reason": reason,
    })


def rows(path, sql, args=()):
    with closing(sqlite3.connect(path)) as db:
        return db.execute(sql, args).fetchall()


def test_parallel_draft_retry_and_lost_response_survive_app_restart(case):
    path, app = case
    request = current_request()
    key = "draft-A103-acceptance"
    barrier = Barrier(2, timeout=10)
    with TestClient(app) as first, TestClient(app) as second:
        login(first, "engineer-1")
        login(second, "engineer-1")

        def send(client):
            barrier.wait()
            return create_draft(client, key=key, request=request)

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(send, (first, second)))
    assert [response.status_code for response in outcomes] == [201, 201]
    assert outcomes[0].json() == outcomes[1].json()
    earliest = outcomes[0].json()
    assert earliest["state"] == "PENDING_APPROVAL"
    assert earliest["action"] == "sensor_diagnostic_first"
    assert earliest["citations"]

    with TestClient(create_app(path)) as restarted:
        login(restarted, "engineer-1")
        equivalent = dict(request)
        for field in ("effective_at", "known_as_of"):
            equivalent[field] = datetime.fromisoformat(request[field]).astimezone(
                timezone(timedelta(hours=9)),
            ).isoformat()
        retry = create_draft(restarted, key=key, request={
            **equivalent, "actor": {"user_id": "other", "tenant": "elsewhere",
                                    "team": "other-team", "role": "approver"},
        })
        assert retry.status_code == 201 and retry.json() == earliest
        changed = create_draft(restarted, key=key, request={**request, "asset_id": "A-106"})
        assert changed.status_code == 409
        assert rows(path, "SELECT id FROM proposals") == [(earliest["proposal_id"],)]
        assert rows(path, "SELECT kind FROM audit") == [("CREATED",)]
        assert rows(path, "SELECT * FROM work_orders") == []

        login(restarted, "engineer-2")
        different_owner = create_draft(restarted, key=key, request=request)
        assert different_owner.status_code == 201
        assert different_owner.json()["proposal_id"] != earliest["proposal_id"]
        legacy = [create_draft(restarted, request=request) for _ in range(2)]
        assert [response.status_code for response in legacy] == [201, 201]
        assert legacy[0].json()["proposal_id"] != legacy[1].json()["proposal_id"]


def test_idempotency_key_is_bounded_and_replay_respects_current_evidence_acl(case):
    path, app = case
    with TestClient(app) as client:
        login(client, "engineer-1")
        assert create_draft(client, key="a" * 4096).status_code == 422
        assert rows(path, "SELECT id FROM proposals") == []
        request = current_request()
        result = create_draft(client, key="acl-check", request=request)
        assert result.status_code == 201
        evidence_id = result.json()["citations"][0]["evidence_id"]
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("DELETE FROM evidence_acl WHERE evidence_id=? AND role='engineer'",
                       (evidence_id,))
        replay = create_draft(client, key="acl-check", request=request)
        assert evidence_id not in replay.text
        assert rows(path, "SELECT kind FROM audit") == [("CREATED",)]


def test_concurrent_draft_intents_bind_one_input_and_clear_only_the_matching_owner_key(case):
    path, app = case
    first_request = current_request()
    other_request = {**first_request, "asset_id": "A-106"}
    barrier = Barrier(2, timeout=10)
    with TestClient(app) as first, TestClient(app) as second:
        login(first, "engineer-1")
        login(second, "engineer-1")

        def stage(client, request):
            barrier.wait()
            return client.post(DRAFT_INTENT, json={"request": request})

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_stage = pool.submit(stage, first, first_request)
            second_stage = pool.submit(stage, second, other_request)
            responses = [first_stage.result(), second_stage.result()]
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    attempt = responses[0].json()["attempt"]
    assert attempt["key"]
    assert attempt["request"] in (first_request, other_request)
    winning_request = attempt["request"]
    losing_request = other_request if winning_request == first_request else first_request
    assert rows(path, "SELECT id FROM proposals") == []

    with TestClient(create_app(path)) as restarted, TestClient(app) as different_owner:
        login(restarted, "engineer-1")
        assert restarted.get(DRAFT_INTENT).json() == {"attempt": attempt}
        mismatch = create_draft(restarted, key=attempt["key"], request=losing_request)
        assert mismatch.status_code == 409
        assert rows(path, "SELECT id FROM proposals") == []

        login(different_owner, "engineer-2")
        assert different_owner.get(DRAFT_INTENT).json() == {"attempt": None}
        other_stage = different_owner.post(DRAFT_INTENT, json={"request": losing_request})
        assert other_stage.status_code == 200
        other_attempt = other_stage.json()["attempt"]
        assert other_attempt["key"] != attempt["key"]
        assert other_attempt["request"] == losing_request
        denied_clear = different_owner.post(DRAFT_INTENT + "/clear", json={"key": attempt["key"]})
        assert denied_clear.status_code == 200
        assert different_owner.get(DRAFT_INTENT).json() == {"attempt": other_attempt}
        assert restarted.get(DRAFT_INTENT).json() == {"attempt": attempt}

        submitted = create_draft(restarted, key=attempt["key"], request=winning_request)
        assert submitted.status_code == 201
        cleared = restarted.post(DRAFT_INTENT + "/clear", json={"key": attempt["key"]})
        assert cleared.status_code == 200
        assert restarted.get(DRAFT_INTENT).json() == {"attempt": None}
        next_stage = restarted.post(DRAFT_INTENT, json={"request": losing_request})
        assert next_stage.status_code == 200
        next_attempt = next_stage.json()["attempt"]
        assert next_attempt["key"] not in {attempt["key"], other_attempt["key"]}
        assert next_attempt["request"] == losing_request
        assert restarted.post(DRAFT_INTENT + "/clear", json={"key": attempt["key"]}).status_code == 200
        assert restarted.get(DRAFT_INTENT).json() == {"attempt": next_attempt}
        assert different_owner.get(DRAFT_INTENT).json() == {"attempt": other_attempt}
    assert rows(path, "SELECT id FROM proposals") == [(submitted.json()["proposal_id"],)]
    assert rows(path, "SELECT * FROM work_orders") == []


def test_existing_draft_replays_after_creation_window_while_fresh_key_fails(case, monkeypatch):
    import opspilot_x.api as api

    path, app = case
    with TestClient(app) as client:
        login(client, "engineer-1")
        staged = client.post(DRAFT_INTENT, json={"request": current_request()})
        assert staged.status_code == 200
        attempt = staged.json()["attempt"]
        request = attempt["request"]
        first = create_draft(client, key=attempt["key"], request=request)
        assert first.status_code == 201
        after_window = datetime.fromisoformat(request["known_as_of"]) + timedelta(hours=1, seconds=1)

        class AfterCreationWindow(datetime):
            @classmethod
            def now(cls, tz=None):
                return after_window.astimezone(tz)

        monkeypatch.setattr(api, "datetime", AfterCreationWindow)
        replay = create_draft(client, key=attempt["key"], request=request)
        assert replay.status_code == 201 and replay.json() == first.json()
        new_key = create_draft(client, key="different-draft-after-window", request=request)
        assert new_key.status_code == 422
    assert rows(path, "SELECT id FROM proposals") == [(first.json()["proposal_id"],)]
    assert rows(path, "SELECT kind FROM audit") == [("CREATED",)]
    assert rows(path, "SELECT * FROM work_orders") == []


def test_approved_handover_requires_fresh_review_and_recovers_same_mock_receipt(case):
    path, app = case
    with TestClient(app) as engineer, TestClient(app) as previous, TestClient(app) as successor:
        login(engineer, "engineer-1")
        endpoint, draft = new_proposal(engineer)
        fingerprint = draft["fingerprint"]
        detail = engineer.get(endpoint).json()
        assert detail["review_version"] == 0
        assert detail["assigned_approver"] is None
        assert handover(engineer, endpoint, fingerprint, 0).status_code == 403
        login(previous, "approver-1")
        assert decision(previous, endpoint, fingerprint).status_code == 200
        auth.disable_user(path, "approver-1")
        assert previous.post(endpoint + "/execute", json={}).status_code == 401

        login(successor, "other-approver")
        assert handover(successor, endpoint, fingerprint, 1).status_code == 404
        login(successor, "reviewer-2")
        assert handover(successor, endpoint, fingerprint, 0).status_code == 409
        assert handover(successor, endpoint, "0" * 64, 1).status_code == 409
        moved = handover(successor, endpoint, fingerprint, 1)
        assert moved.status_code == 200, moved.text
        detail = successor.get(endpoint).json()
        assert detail["state"] == "PENDING_APPROVAL"
        assert detail["decided_by"] is None
        assert detail["assigned_approver"] == "reviewer-2"
        assert detail["review_version"] == 2
        assert detail["fingerprint"] == fingerprint
        assert decision(successor, endpoint, fingerprint).status_code == 409
        assert decision(successor, endpoint, fingerprint, 1).status_code == 409
        assert successor.post(endpoint + "/execute", json={}).status_code == 409
        assert rows(path, "SELECT * FROM work_orders") == []
        assert decision(successor, endpoint, fingerprint, 2).status_code == 200
        assert successor.get(endpoint).json()["review_version"] == 3
        assert successor.post(endpoint + "/execute", json={"simulate_response_loss": True}).json() == UNKNOWN
        receipt = rows(path, "SELECT receipt_id FROM work_orders")[0][0]
        recovered = successor.post(endpoint + "/reconcile", json={})
        assert recovered.status_code == 200
        assert recovered.json() == {"state": "SUCCEEDED", "receipt_id": receipt}
        assert rows(path, "SELECT receipt_id FROM work_orders") == [(receipt,)]

        items = successor.get(endpoint + "/audit").json()["items"]
        event, = [item for item in items if item["kind"] == "HANDOVER"]
        assert event["actor"] == "reviewer-2"
        assert datetime.fromisoformat(event["logged_at"]).tzinfo is not None
        assert event["details"] == {"from_approver": "approver-1", "to_approver": "reviewer-2",
                                    "reason": "Previous reviewer unavailable", "version": 2,
                                    "fingerprint": fingerprint, "from_state": "APPROVED",
                                    "to_state": "PENDING_APPROVAL"}


@pytest.mark.parametrize("receipt_available", [True, False])
def test_unknown_handover_changes_reconciler_without_authorizing_an_execution(case, receipt_available):
    path, app = case
    with TestClient(app) as original, TestClient(app) as successor:
        login(original, "engineer-1")
        endpoint, draft = new_proposal(original)
        fingerprint = draft["fingerprint"]
        login(original, "approver-1")
        assert decision(original, endpoint, fingerprint).status_code == 200
        assert original.post(endpoint + "/execute", json={"simulate_response_loss": True}).json() == UNKNOWN
        receipt = rows(path, "SELECT receipt_id FROM work_orders")[0][0]
        if not receipt_available:
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("DELETE FROM work_orders")
        login(successor, "reviewer-2")
        result = handover(successor, endpoint, fingerprint, 1)
        assert result.status_code == 200, result.text
        detail = successor.get(endpoint).json()
        assert detail["state"] == "UNKNOWN_RECONCILE"
        assert detail["decided_by"] == "approver-1"
        assert detail["assigned_approver"] == "reviewer-2"
        assert detail["review_version"] == 2
        assert original.post(endpoint + "/reconcile", json={}).status_code == 403
        assert original.post(endpoint + "/execute", json={}).status_code == 403
        assert successor.post(endpoint + "/execute", json={}).status_code == 403
        outcome = successor.post(endpoint + "/reconcile", json={})
        assert outcome.status_code == 200
        expected = {"state": "SUCCEEDED", "receipt_id": receipt} if receipt_available else UNKNOWN
        assert outcome.json() == expected
        assert successor.post(endpoint + "/reconcile", json={}).json() == expected
        assert rows(path, "SELECT receipt_id FROM work_orders") == ([(receipt,)] if receipt_available else [])


def test_concurrent_handover_and_decision_cannot_both_use_same_review_version(case):
    path, app = case
    with TestClient(app) as original, TestClient(app) as successor:
        login(original, "engineer-1")
        endpoint, draft = new_proposal(original)
        fingerprint = draft["fingerprint"]
        login(original, "approver-1")
        login(successor, "reviewer-2")
        barrier = Barrier(2, timeout=10)

        def approve():
            barrier.wait()
            return decision(original, endpoint, fingerprint, 0)

        def claim():
            barrier.wait()
            return handover(successor, endpoint, fingerprint, 0)

        with ThreadPoolExecutor(max_workers=2) as pool:
            approving = pool.submit(approve)
            claiming = pool.submit(claim)
            approved, claimed = approving.result(), claiming.result()
        assert (approved.status_code, claimed.status_code) in {(200, 409), (409, 200), (403, 200)}
        detail = successor.get(endpoint).json()
        assert detail["review_version"] == 1
        assert detail["state"] == ("APPROVED" if approved.status_code == 200 else "PENDING_APPROVAL")
        events = rows(path, "SELECT kind FROM audit WHERE kind IN ('APPROVED','HANDOVER')")
        expected_event = "APPROVED" if approved.status_code == 200 else "HANDOVER"
        assert events == [(expected_event,)]
        assert rows(path, "SELECT * FROM work_orders") == []


@pytest.mark.parametrize("failure_point", ["event", "details"])
def test_handover_audit_failure_rolls_back_assignment_state_and_version(case, failure_point):
    path, app = case
    with TestClient(app, raise_server_exceptions=False) as client:
        login(client, "engineer-1")
        endpoint, draft = new_proposal(client)
        fingerprint = draft["fingerprint"]
        login(client, "approver-1")
        assert decision(client, endpoint, fingerprint).status_code == 200
        login(client, "reviewer-2")
        previous = client.get(endpoint).json()
        failure_scope = {
            "event": "BEFORE INSERT ON audit WHEN NEW.kind='HANDOVER'",
            "details": "BEFORE INSERT ON audit_details",
        }[failure_point]
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(f"""
                CREATE TRIGGER fail_handover_audit {failure_scope}
                BEGIN SELECT RAISE(ABORT, 'synthetic transaction failure'); END
            """)
        result = handover(client, endpoint, fingerprint, 1)
        assert result.status_code == 500
        assert client.get(endpoint).json() == previous
        assert rows(path, "SELECT kind FROM audit WHERE kind='HANDOVER'") == []
        assert rows(path, "SELECT * FROM work_orders") == []
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("DROP TRIGGER fail_handover_audit")
        assert handover(client, endpoint, fingerprint, 1).status_code == 200


def test_changed_underlying_source_blocks_handover_and_expires_on_execute(case):
    path, app = case
    with TestClient(app) as client:
        login(client, "engineer-1")
        endpoint, draft = new_proposal(client)
        fingerprint = draft["fingerprint"]
        login(client, "approver-1")
        assert decision(client, endpoint, fingerprint).status_code == 200
        evidence_id = draft["citations"][0]["evidence_id"]
        payload = json.loads(rows(path, "SELECT payload FROM evidence_documents WHERE evidence_id=?",
                                  (evidence_id,))[0][0])
        payload["checksum"] = "changed-synthetic-source"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE evidence_documents SET payload=? WHERE evidence_id=?",
                       (json.dumps(payload), evidence_id))
        login(client, "reviewer-2")
        assert handover(client, endpoint, fingerprint, 1).status_code == 409
        assert client.get(endpoint).json()["state"] == "APPROVED"
        login(client, "approver-1")
        assert client.post(endpoint + "/execute", json={}).status_code == 409
        result = client.get(endpoint).json()
        assert result["state"] == "EXPIRED"
        assert result["citations"] == []
        assert rows(path, "SELECT * FROM work_orders") == []
        assert rows(path, "SELECT kind FROM audit WHERE kind='HANDOVER'") == []


def test_only_original_approver_can_cancel_unexecuted_approval(case):
    path, app = case
    with TestClient(app) as client:
        login(client, "engineer-1")
        endpoint, draft = new_proposal(client)
        next_endpoint, next_draft = new_proposal(client)
        fingerprint = draft["fingerprint"]
        login(client, "approver-1")
        assert decision(client, endpoint, fingerprint).status_code == 200
        cancel = {"decision": "cancel", "expected_hash": fingerprint, "expected_version": 1}
        login(client, "reviewer-2")
        assert client.post(endpoint + "/decision", json=cancel).status_code == 403
        login(client, "approver-1")
        assert client.post(endpoint + "/decision", json={**cancel, "expected_version": 0}).status_code == 409
        assert client.post(endpoint + "/decision", json={**cancel, "expected_hash": "0" * 64}).status_code == 409
        canceled = client.post(endpoint + "/decision", json=cancel)
        assert canceled.status_code == 200, canceled.text
        assert canceled.json()["state"] == "CANCELLED"
        assert client.get(endpoint).json()["review_version"] == 2
        assert client.post(endpoint + "/execute", json={}).status_code == 409
        assert rows(path, "SELECT * FROM work_orders") == []
        assert rows(path, "SELECT actor FROM audit WHERE kind='CANCELLED'") == [("approver-1",)]

        assert decision(client, next_endpoint, next_draft["fingerprint"]).status_code == 200
        assert client.post(next_endpoint + "/execute", json={"simulate_response_loss": True}).json() == UNKNOWN
        before = rows(path, "SELECT * FROM work_orders")
        # Model an imported local snapshot that still shows APPROVED beside an existing receipt.
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE proposals SET state='APPROVED' WHERE id=?", (next_draft["proposal_id"],))
        blocked = client.post(next_endpoint + "/decision", json={**cancel, "expected_hash": next_draft["fingerprint"]})
        assert blocked.status_code == 409
        assert rows(path, "SELECT * FROM work_orders") == before


def test_fresh_session_does_not_restore_an_approval_from_a_revoked_generation(case):
    path, app = case
    with TestClient(app) as client:
        login(client, "engineer-1")
        endpoint, draft = new_proposal(client)
        login(client, "approver-1")
        assert decision(client, endpoint, draft["fingerprint"]).status_code == 200
        assert client.get(endpoint).json()["approval_valid"] is True
        auth.revoke_sessions(path, "approver-1")
        assert client.post(endpoint + "/execute", json={}).status_code == 401

        login(client, "approver-1")
        assert client.get(endpoint).json()["approval_valid"] is False
        assert client.post(endpoint + "/execute", json={}).status_code == 409
        assert rows(path, "SELECT * FROM work_orders") == []


def test_restoring_snapshot_quarantines_credentials_and_cannot_repeat_later_write(case):
    path, app = case
    backup, restored = (path.with_name(name) for name in ("backup.sqlite3", "restored.sqlite3"))
    with TestClient(app) as source:
        login(source, "engineer-1")
        endpoint, draft = new_proposal(source)
        login(source, "approver-1")
        assert decision(source, endpoint, draft["fingerprint"]).status_code == 200
        old_token = source.cookies[auth.COOKIE]
        backup_database(path, backup)
        assert source.post(endpoint + "/execute", json={"simulate_response_loss": True}).json() == UNKNOWN
        auth.disable_user(path, "approver-1")
    restore_database(backup, restored)
    with TestClient(create_app(restored)) as recovered:
        recovered.cookies.set(auth.COOKIE, old_token)
        assert recovered.get(endpoint).status_code == 401
        for user_id in ("approver-1", "engineer-1"):
            response = recovered.post("/api/v1/auth/login", json={"username": user_id, "password": PASSWORD})
            assert response.status_code == 401

        auth.create_user(restored, username="new-reviewer", password=PASSWORD, user_id="new-reviewer",
                         tenant="demo", team="team_a", role="approver")
        login(recovered, "new-reviewer")
        detail = recovered.get(endpoint).json()
        assert detail["state"] == "UNKNOWN_RECONCILE"
        assert detail["approval_valid"] is False
        assert handover(recovered, endpoint, draft["fingerprint"], detail["review_version"]).status_code == 200
        assert recovered.post(endpoint + "/execute", json={}).status_code == 403
        receipt_check = recovered.post(endpoint + "/reconcile", json={})
        assert receipt_check.status_code == 200 and receipt_check.json() == UNKNOWN
    assert rows(restored, "SELECT * FROM work_orders") == []
    assert len(rows(path, "SELECT * FROM work_orders")) == 1


@pytest.mark.parametrize("operation", ["execute", "reconcile", "handover"])
def test_live_revocation_after_initial_authentication_blocks_workflow_mutation(case, monkeypatch, operation):
    path, app = case
    with TestClient(app) as client:
        login(client, "engineer-1")
        endpoint, draft = new_proposal(client)
        login(client, "approver-1")
        assert decision(client, endpoint, draft["fingerprint"]).status_code == 200
        user_id = "approver-1"
        if operation == "reconcile":
            lost = client.post(endpoint + "/execute", json={"simulate_response_loss": True})
            assert lost.status_code == 200 and lost.json() == UNKNOWN
        elif operation == "handover":
            user_id = "reviewer-2"
            login(client, user_id)
        before = [rows(path, query) for query in (
            "SELECT state,decided_by FROM proposals",
            "SELECT * FROM audit",
            "SELECT * FROM work_orders",
        )]
        session = auth.session

        def revoke_after_authentication(db_path, token):
            actor = session(db_path, token)
            assert actor["user_id"] == user_id
            auth.disable_user(path, user_id)
            return actor

        monkeypatch.setattr(auth, "session", revoke_after_authentication)
        response = (handover(client, endpoint, draft["fingerprint"], 1) if operation == "handover"
                    else client.post(endpoint + "/" + operation, json={}))
        assert response.status_code == 401
        assert [rows(path, query) for query in (
            "SELECT state,decided_by FROM proposals",
            "SELECT * FROM audit",
            "SELECT * FROM work_orders",
        )] == before
