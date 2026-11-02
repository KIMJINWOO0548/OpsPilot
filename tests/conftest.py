import pytest
from fastapi.testclient import TestClient
from opspilot_x.api import create_app
from opspilot_x.auth import create_user

PASSWORD = "test-only-password-2026"
USERS = [
    {"user_id":"engineer-1","tenant":"demo","team":"team_a","role":"engineer"},
    {"user_id":"approver-1","tenant":"demo","team":"team_a","role":"approver"},
    {"user_id":"other-approver","tenant":"demo","team":"another_team","role":"approver"},
    {"user_id":"other-tenant","tenant":"elsewhere","team":"team_a","role":"approver"},
]

def seed_users(path):
    for actor in USERS:
        create_user(path, username=actor["user_id"], password=PASSWORD, **actor)

def login(client, user_id):
    response = client.post("/api/v1/auth/login", json={"username": user_id, "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "test.sqlite3"
    seed_users(path)
    with TestClient(create_app(path)) as c:
        login(c, "engineer-1")
        yield c

@pytest.fixture
def engineer():
    return {"user_id":"engineer-1","tenant":"demo","team":"team_a","role":"engineer"}

@pytest.fixture
def approver():
    return {"user_id":"approver-1","tenant":"demo","team":"team_a","role":"approver"}

@pytest.fixture
def current(engineer):
    return {"actor": engineer, "asset_id": "A-103", "claim_key":"inspection_priority",
            "effective_at":"2026-10-19T18:00:00+09:00", "known_as_of":"2026-10-19T18:00:00+09:00"}
