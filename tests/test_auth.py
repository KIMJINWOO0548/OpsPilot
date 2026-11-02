import sqlite3
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from opspilot_x.api import create_app
from opspilot_x import auth
from conftest import login


def test_missing_expired_and_logout_session(client, tmp_path):
    assert client.get('/api/v1/auth/me').status_code == 200
    assert client.post('/api/v1/auth/logout').status_code == 200
    assert client.get('/api/v1/auth/me').status_code == 401
    login(client, 'engineer-1')
    with sqlite3.connect(tmp_path / 'test.sqlite3') as db:
        db.execute('UPDATE sessions SET expires_at=0')
    assert client.get('/api/v1/auth/me').status_code == 401
    with TestClient(create_app(tmp_path / 'empty.sqlite3')) as anonymous:
        assert anonymous.get('/api/v1/demo/scenarios').status_code == 401
        assert anonymous.get('/api/v1/proposals').status_code == 401


def test_forged_actor_and_csrf(client, approver):
    now = datetime.now(timezone.utc).isoformat()
    body = {'actor': dict(approver, tenant='elsewhere'), 'asset_id': 'A-103',
            'effective_at': now, 'known_as_of': now}
    p = client.post('/api/v1/proposals', json={'request': body})
    assert p.status_code == 201
    assert client.get('/api/v1/proposals').json()['items'][0]['owner_user'] == 'engineer-1'
    decision = {'actor': approver, 'decision': 'approve', 'expected_hash': p.json()['fingerprint']}
    endpoint = '/api/v1/proposals/' + p.json()['proposal_id']
    assert client.post(endpoint + '/decision', json=decision).status_code == 403
    assert client.post('/api/v1/analysis', json=body, headers={'X-CSRF-Token': ''}).status_code == 403
    assert client.post('/api/v1/analysis', json=body, headers={'Origin':'https://evil.example'}).status_code == 403
    for user in ('other-approver', 'other-tenant'):
        login(client, user)
        assert client.get(endpoint).status_code == 404
        assert client.get(endpoint + '/audit').status_code == 404
        assert client.get('/api/v1/proposals').json() == {'items': []}
    login(client, 'approver-1')
    assert client.get(endpoint + '/audit').json()['items'][0]['kind'] == 'CREATED'


def test_credentials_hashed_cookie_and_rate_limit(client, tmp_path):
    response = login(client, 'engineer-1')
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie
    token = client.cookies.get(auth.COOKIE)
    with sqlite3.connect(tmp_path / 'test.sqlite3') as db:
        assert db.execute('SELECT token_hash FROM sessions WHERE token_hash=?', (auth.token_hash(token),)).fetchone()
        assert not db.execute('SELECT token_hash FROM sessions WHERE token_hash=?', (token,)).fetchone()
        assert db.execute('SELECT password_hash FROM users LIMIT 1').fetchone()[0] != 'test-only-password-2026'
    for _ in range(10):
        assert client.post('/api/v1/auth/login', json={'username':'engineer-1', 'password':'wrong'}).status_code == 401
    assert client.post('/api/v1/auth/login', json={'username':'engineer-1', 'password':'wrong'}).status_code == 401
    assert client.post('/api/v1/auth/login', json={'username':'engineer-1', 'password':'test-only-password-2026'}).status_code == 401
    assert client.post('/api/v1/auth/login', content='x' * 9000).status_code == 413


def test_foreign_proposal_write_hides_existence(client, engineer):
    from test_api import draft
    proposal = draft(client, engineer)
    login(client, 'other-tenant')
    for suffix, body in [('decision', {'decision': 'approve', 'expected_hash': proposal['fingerprint']}),
                         ('execute', {}), ('reconcile', {})]:
        for proposal_id in (proposal['proposal_id'], 'nonexistent'):
            assert client.post('/api/v1/proposals/' + proposal_id + '/' + suffix, json=body).status_code == 404


def test_search_rejects_oversized_query(client):
    assert client.get('/api/v1/evidence', params={'q': 'a' * 1001}).status_code == 422


def test_stored_action_tamper_blocks_approval_and_execution(client, engineer, approver, tmp_path):
    from test_api import draft, approve
    for already_approved in (False, True):
        login(client, 'engineer-1')
        proposal = draft(client, engineer)
        if already_approved:
            assert approve(client, proposal, approver).status_code == 200
        with sqlite3.connect(tmp_path / 'test.sqlite3') as db:
            db.execute('UPDATE proposals SET action=? WHERE id=?', ('unapproved_action', proposal['proposal_id']))
        if already_approved:
            response = client.post('/api/v1/proposals/' + proposal['proposal_id'] + '/execute', json={})
        else:
            response = approve(client, proposal, approver)
        assert response.status_code == 409
        with sqlite3.connect(tmp_path / 'test.sqlite3') as db:
            assert db.execute('SELECT COUNT(*) FROM work_orders').fetchone()[0] == 0
