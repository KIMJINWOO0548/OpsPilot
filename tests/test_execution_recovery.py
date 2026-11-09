"""Missing local receipt evidence must not authorize a replacement mock write."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3

from fastapi.testclient import TestClient
import pytest

from conftest import PASSWORD, login, seed_users
from opspilot_x.api import create_app
from opspilot_x.auth import create_user
from test_api import approve, draft


def prepared(tmp_path, engineer, approver, state=None):
    path = tmp_path / 'execution.sqlite3'
    seed_users(path)
    with TestClient(create_app(path)) as client:
        login(client, 'engineer-1')
        proposal = draft(client, engineer)
        assert approve(client, proposal, approver).status_code == 200
        if state:
            result = client.post('/api/v1/proposals/' + proposal['proposal_id'] + '/execute',
                                 json={'simulate_response_loss': state == 'UNKNOWN_RECONCILE'})
            assert result.status_code == 200 and result.json()['state'] == state
    return path, proposal


def workflow_rows(path):
    with closing(sqlite3.connect(path)) as db:
        return {table: db.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall()
                for table in ('proposals', 'work_orders', 'audit')}


@pytest.mark.parametrize('state', ['UNKNOWN_RECONCILE', 'SUCCEEDED'])
@pytest.mark.parametrize('first_endpoint', ['execute', 'reconcile'])
def test_missing_receipt_after_restart_never_creates_a_replacement(
    tmp_path, engineer, approver, state, first_endpoint,
):
    path, proposal = prepared(tmp_path, engineer, approver, state)
    # Model receipt loss in an owned recovery copy, not a normal atomic crash.
    with closing(sqlite3.connect(path)) as db, db:
        original = db.execute('SELECT * FROM work_orders').fetchone()
        db.execute('DELETE FROM work_orders')
    endpoint = '/api/v1/proposals/' + proposal['proposal_id']
    unknown = {'state': 'UNKNOWN_RECONCILE', 'receipt_id': None}
    with TestClient(create_app(path)) as restarted:
        login(restarted, 'approver-1')
        first = restarted.post(endpoint + '/' + first_endpoint, json={})
        assert first.status_code == 200 and first.json() == unknown
        assert restarted.get(endpoint).json()['state'] == 'UNKNOWN_RECONCILE'

        def retry(index):
            route = '/execute' if index % 2 else '/reconcile'
            return restarted.post(endpoint + route, json={'simulate_response_loss': True})

        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(retry, range(8)))
        assert all(response.status_code == 200 and response.json() == unknown for response in responses)
        assert workflow_rows(path)['work_orders'] == []
        pending_events = [row[2] for row in workflow_rows(path)['audit']]
        assert pending_events.count('RECEIPT_UNAVAILABLE') == (1 if state == 'SUCCEEDED' else 0)
        assert restarted.get(endpoint).json()['state'] == 'UNKNOWN_RECONCILE'

        # Recover the original known receipt; do not manufacture a new operation.
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('INSERT INTO work_orders VALUES (?,?,?,?,?)', original)
        recovered = restarted.post(endpoint + '/reconcile', json={})
        repeated = restarted.post(endpoint + '/execute', json={})
        assert recovered.status_code == repeated.status_code == 200
        assert recovered.json() == repeated.json() == {'state': 'SUCCEEDED', 'receipt_id': original[2]}
        assert workflow_rows(path)['work_orders'] == [original]


@pytest.mark.parametrize('endpoint', ['execute', 'reconcile'])
def test_missing_receipt_recovery_still_requires_the_original_approver(
    tmp_path, engineer, approver, endpoint,
):
    path, proposal = prepared(tmp_path, engineer, approver, 'UNKNOWN_RECONCILE')
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('DELETE FROM work_orders')
    create_user(path, username='second-reviewer', password=PASSWORD, user_id='second-reviewer',
                tenant='demo', team='team_a', role='approver')
    before = workflow_rows(path)
    with TestClient(create_app(path)) as restarted:
        login(restarted, 'second-reviewer')
        response = restarted.post('/api/v1/proposals/' + proposal['proposal_id'] + '/' + endpoint,
                                  json={'actor': approver})
        assert response.status_code == 403
    assert workflow_rows(path) == before


@pytest.mark.parametrize('failure_point', ['before-insert', 'before-commit'])
def test_known_local_transaction_failure_can_retry_only_after_full_rollback(
    tmp_path, engineer, approver, failure_point,
):
    path, proposal = prepared(tmp_path, engineer, approver)
    before = workflow_rows(path)
    trigger = ("BEFORE INSERT ON work_orders" if failure_point == 'before-insert' else
               "BEFORE INSERT ON audit WHEN NEW.kind='SUCCEEDED'")
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TRIGGER injected_failure ' + trigger
                   + " BEGIN SELECT RAISE(ABORT, 'synthetic local transaction failure'); END")
    endpoint = '/api/v1/proposals/' + proposal['proposal_id'] + '/execute'
    with TestClient(create_app(path), raise_server_exceptions=False) as client:
        login(client, 'approver-1')
        assert client.post(endpoint, json={}).status_code == 500
        assert workflow_rows(path) == before
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('DROP TRIGGER injected_failure')
        first = client.post(endpoint, json={})
        again = client.post(endpoint, json={})
        assert first.status_code == again.status_code == 200
        assert first.json() == again.json()
        assert len(workflow_rows(path)['work_orders']) == 1
