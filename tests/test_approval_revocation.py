from contextlib import closing
from datetime import datetime, timezone
import sqlite3

from fastapi.testclient import TestClient

from opspilot_x import auth
from opspilot_x.api import create_app
from conftest import login, seed_users


def test_live_session_revocation_between_authentication_and_approval(tmp_path, monkeypatch):
    path = tmp_path / "revoke.db"
    seed_users(path)
    with TestClient(create_app(path)) as client:
        login(client, "engineer-1")
        now = datetime.now(timezone.utc).isoformat()
        draft = client.post("/api/v1/proposals", json={"request": {
            "asset_id": "A-103", "effective_at": now, "known_as_of": now,
        }}).json()
        login(client, "approver-1")
        original = auth.session

        def revoke_after_read(database, token):
            result = original(database, token)
            auth.disable_user(path, "approver-1")
            return result

        monkeypatch.setattr(auth, "session", revoke_after_read)
        response = client.post(f"/api/v1/proposals/{draft['proposal_id']}/decision", json={
            "decision": "approve", "expected_hash": draft["fingerprint"],
        })
        assert response.status_code == 401
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT state,decided_by FROM proposals").fetchone() == ("PENDING_APPROVAL", None)
        assert db.execute("SELECT kind FROM audit").fetchall() == [("CREATED",)]


def test_draft_intent_resumes_at_different_desktop_origin(tmp_path):
    path = tmp_path / "intent.db"
    seed_users(path)
    now = datetime.now(timezone.utc).isoformat()
    request = {"asset_id": "A-103", "claim_key": "inspection_priority",
               "effective_at": now, "known_as_of": now}
    with TestClient(create_app(path), base_url="http://127.0.0.1:43911") as before:
        login(before, "engineer-1")
        staged = before.post("/api/v1/draft-intent", json={"request": request})
        assert staged.status_code == 200
        attempt = staged.json()["attempt"]
        assert attempt["request"]["asset_id"] == "A-103"
        first = before.post("/api/v1/proposals", headers={"Idempotency-Key": attempt["key"]},
                            json={"request": attempt["request"]})
        assert first.status_code == 201
    with TestClient(create_app(path), base_url="http://127.0.0.1:43912") as after:
        login(after, "other-approver")
        assert after.get("/api/v1/draft-intent").status_code == 403
        login(after, "engineer-1")
        assert after.get("/api/v1/draft-intent").json() == {"attempt": attempt}
        different = after.post("/api/v1/draft-intent",
                               json={"request": dict(request, asset_id="A-105")})
        assert different.json() == {"attempt": attempt}
        retry = after.post("/api/v1/proposals", headers={"Idempotency-Key": attempt["key"]},
                           json={"request": attempt["request"]})
        assert retry.json()["proposal_id"] == first.json()["proposal_id"]
        assert after.post("/api/v1/draft-intent/clear", json={"key": attempt["key"]}).json() == {"ok": True}
        assert after.get("/api/v1/draft-intent").json() == {"attempt": None}
        assert after.post("/api/v1/proposals", headers={"Idempotency-Key": attempt["key"]},
                          json={"request": attempt["request"]}).json()["proposal_id"] == first.json()["proposal_id"]
        unused = after.post("/api/v1/draft-intent", json={"request": request}).json()["attempt"]
        assert after.post("/api/v1/draft-intent/clear", json={"key": unused["key"]}).status_code == 200
        stale = after.post("/api/v1/proposals", headers={"Idempotency-Key": unused["key"]},
                           json={"request": unused["request"]})
        assert stale.status_code == 409
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM proposals").fetchone() == (1,)
        assert db.execute("SELECT kind FROM audit").fetchall() == [("CREATED",)]
