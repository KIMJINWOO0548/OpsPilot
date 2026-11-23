from contextlib import closing
import sqlite3

from fastapi.testclient import TestClient

from conftest import login, seed_users
from opspilot_x.api import create_app
from opspilot_x.hybrid import HybridRag


def test_hybrid_api_authorizes_and_preserves_the_decision_contract(tmp_path, current, approver):
    path = tmp_path / "hybrid.sqlite3"
    seed_users(path)
    model_contexts = []

    def generate(query, sources):
        model_contexts.append((query, sources))
        citation = next(item for item in sources if item["action"])
        return {
            "action": citation["action"],
            "citations": [{"evidence_id": citation["evidence_id"], "quote": citation["text"][:80]}],
        }

    hybrid = HybridRag(lambda texts: [[1.0, 1.0] for _ in texts], generate)
    body = dict(current, actor=approver, query="  sensor maintenance  ")
    with TestClient(create_app(path, hybrid=hybrid)) as client:
        assert client.post("/api/v1/analysis/hybrid", json=body).status_code == 401
        login(client, "other-tenant")
        blocked = client.post("/api/v1/analysis/hybrid", json=body)
        assert blocked.status_code == 200
        assert blocked.json()["model_status"] == "POLICY_BLOCKED"
        assert not model_contexts
        login(client, "engineer-1")
        ready = client.post("/api/v1/analysis/hybrid", json=body)
        assert ready.status_code == 200, ready.text
        result = ready.json()
        assert result["model_status"] == "DRAFT_READY"
        assert model_contexts[0][0] == "sensor maintenance"
        assert result["analysis"] == client.post("/api/v1/analysis", json=current).json()
        assert result["draft"]["action"] == result["analysis"]["recommended_action"]


def test_hybrid_disabled_keeps_standard_analysis_available(client, current):
    response = client.post("/api/v1/analysis/hybrid", json=dict(current, query="sensor"))
    assert response.status_code == 503
    assert client.post("/api/v1/analysis", json=current).status_code == 200


def test_inference_does_not_return_evidence_after_acl_revocation(tmp_path, current):
    path = tmp_path / "changed.sqlite3"
    seed_users(path)

    def generate(query, sources):
        citation = next(item for item in sources if item["action"])
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("DELETE FROM evidence_acl WHERE evidence_id=? AND role='engineer'",
                       (citation["evidence_id"],))
        return {
            "action": citation["action"],
            "citations": [{"evidence_id": citation["evidence_id"], "quote": citation["text"][:80]}],
        }

    hybrid = HybridRag(lambda texts: [[1.0] for _ in texts], generate)
    with TestClient(create_app(path, hybrid=hybrid)) as client:
        login(client, "engineer-1")
        response = client.post("/api/v1/analysis/hybrid", json=dict(current, query="sensor"))
        assert response.status_code == 409
        assert "SOP-A103" not in response.text
