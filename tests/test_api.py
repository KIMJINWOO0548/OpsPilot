from conftest import seed_users, login
from datetime import datetime, timezone
import sqlite3
import pytest
from opspilot_x.api import create_app
from fastapi.testclient import TestClient


def live_request(engineer):
    now=datetime.now(timezone.utc).isoformat()
    return {'actor':engineer,'asset_id':'A-103','claim_key':'inspection_priority',
            'effective_at':now,'known_as_of':now}


def draft(client,engineer):
    resp=client.post('/api/v1/proposals',json={'request':live_request(engineer)})
    assert resp.status_code==201,resp.text
    return resp.json()


def approve(client,proposal,approver):
    login(client, approver["user_id"])
    return client.post('/api/v1/proposals/'+proposal['proposal_id']+'/decision',
        json={'actor':approver,'decision':'approve','expected_hash':proposal['fingerprint']})


def test_health_exposes_unverified_status(client):
    assert client.get('/health').json()['production_ready'] is False
    assert client.get('/').status_code==200


@pytest.mark.parametrize('forbidden', [False, True])
def test_database_connections_close_after_success_and_denial(
    tmp_path, engineer, approver, monkeypatch, forbidden
):
    connections = []
    real_connect = sqlite3.connect

    def tracked_connect(*args, **kwargs):
        # Inspect retained connections from the test thread instead of relying on GC.
        kwargs['check_same_thread'] = False
        connection = real_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr('opspilot_x.api.sqlite3.connect', tracked_connect)
    seed_users(tmp_path / 'closed.sqlite3')
    with TestClient(create_app(tmp_path / 'closed.sqlite3')) as c:
        login(c, 'engineer-1')
        p = draft(c, engineer)
        response = approve(c, p, engineer if forbidden else approver)
        assert response.status_code == (403 if forbidden else 200)
        if forbidden:
            assert c.get('/api/v1/proposals/' + p['proposal_id']).json()['state'] == 'PENDING_APPROVAL'
            assert approve(c, p, approver).status_code == 200

    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match='closed database'):
            connection.execute('SELECT 1')


def test_complete_approve_execute_and_idempotent_retry(client,engineer,approver):
    p=draft(client,engineer)
    prop_id=p['proposal_id']
    assert approve(client,p,approver).json()['state']=='APPROVED'
    path='/api/v1/proposals/'+prop_id+'/execute'
    one=client.post(path,json={'actor':approver})
    two=client.post(path,json={'actor':approver})
    assert one.status_code==200 and two.status_code==200
    assert one.json()['receipt_id']==two.json()['receipt_id']
    assert one.json()['state']=='SUCCEEDED'


def test_unapproved_and_rejected_actions_cannot_execute(client,engineer,approver):
    p=draft(client,engineer)
    endpoint='/api/v1/proposals/'+p['proposal_id']+'/execute'
    login(client, 'approver-1')
    assert client.post(endpoint,json={'actor':approver}).status_code==409
    result=client.post('/api/v1/proposals/'+p['proposal_id']+'/decision',json={
        'actor':approver,'decision':'reject','expected_hash':p['fingerprint']})
    assert result.json()['state']=='REJECTED'
    assert client.post(endpoint,json={'actor':approver}).status_code==409


def test_wrong_role_and_different_team_cannot_approve(client,engineer,approver):
    p=draft(client,engineer)
    q=engineer
    assert approve(client,p,q).status_code==403
    q=dict(approver,user_id='other-approver',team='another_team')
    assert approve(client,p,q).status_code==404
    assert approve(client,p,engineer).status_code==403


def test_tampered_approval_hash_denied(client,engineer,approver):
    p=draft(client,engineer)
    login(client, 'approver-1')
    resp=client.post('/api/v1/proposals/'+p['proposal_id']+'/decision',json={
        'actor':approver,'decision':'approve','expected_hash':'a'*64})
    assert resp.status_code==409


def test_response_loss_reconciliation(client,engineer,approver):
    p=draft(client,engineer)
    assert approve(client,p,approver).status_code==200
    end='/api/v1/proposals/'+p['proposal_id']
    lost=client.post(end+'/execute',json={'actor':approver,'simulate_response_loss':True})
    assert lost.json()=={'state':'UNKNOWN_RECONCILE','receipt_id':None}
    checked=client.post(end+'/reconcile',json={'actor':approver})
    assert checked.json()['state']=='SUCCEEDED'
    twice=client.post(end+'/execute',json={'actor':approver})
    assert twice.json()['receipt_id']==checked.json()['receipt_id']


def test_historical_proposal_is_readonly(client,engineer):
    request=live_request(engineer)
    request['known_as_of']='2026-09-20T12:00:00+09:00'
    request['effective_at']='2026-09-20T12:00:00+09:00'
    result=client.post('/api/v1/proposals',json={'request':request})
    assert result.status_code==422


def test_conflicting_evidence_blocks_proposal(client,engineer):
    request=live_request(engineer)
    request['asset_id']='A-105'
    assert client.post('/api/v1/proposals',json={'request':request}).status_code==422


def test_single_proposal_concurrent_duplicate_executions(tmp_path,engineer,approver):
    from concurrent.futures import ThreadPoolExecutor
    db=tmp_path/'race.sqlite3'
    seed_users(db)
    app=create_app(db)
    with TestClient(app) as c:
        login(c, 'engineer-1')
        p=draft(c,engineer)
        approve(c,p,approver)
        endpoint='/api/v1/proposals/'+p['proposal_id']+'/execute'
        def run_one(_):return c.post(endpoint,json={'actor':approver})
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(run_one,range(20)))
        assert all(r.status_code==200 for r in results)
        assert len({r.json()['receipt_id'] for r in results})==1
        with sqlite3.connect(db) as connection:
            assert connection.execute('SELECT COUNT(*) FROM work_orders').fetchone()[0]==1


def test_evidence_mutation_invalidates_approved_proposal(client,engineer,approver,monkeypatch):
    p=draft(client,engineer)
    assert approve(client,p,approver).status_code==200
    import opspilot_x.api as module
    real_evaluate=module.evaluate
    def altered(request, **kwargs):
        report=real_evaluate(request, **kwargs)
        return report.model_copy(update={'recommended_action':'another_unapproved_action'})
    monkeypatch.setattr(module,'evaluate',altered)
    result=client.post('/api/v1/proposals/'+p['proposal_id']+'/execute',json={'actor':approver})
    assert result.status_code==409
    assert client.get('/api/v1/proposals/'+p['proposal_id']).json()['state']=='EXPIRED'
