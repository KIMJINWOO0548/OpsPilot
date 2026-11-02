"""Run an executable local E2E smoke test: python scripts/smoke_demo.py."""
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from pathlib import Path
from fastapi.testclient import TestClient
from opspilot_x.api import create_app
from opspilot_x.auth import create_user
import secrets

engineer={"user_id":"demo-engineer","role":"engineer","team":"team_a","tenant":"demo"}
approver={"user_id":"demo-approver","role":"approver","team":"team_a","tenant":"demo"}
now=datetime.now(timezone.utc).isoformat()
req={"actor":engineer,"asset_id":"A-103","claim_key":"inspection_priority",
     "effective_at":now,"known_as_of":now}

with TemporaryDirectory() as tmp:
    path = Path(tmp) / 'demo.sqlite3'
    password = secrets.token_urlsafe(24)
    for actor in (engineer, approver):
        create_user(path, username=actor['user_id'], password=password, **actor)
    with TestClient(create_app(path)) as client:
        def login(actor):
            response = client.post('/api/v1/auth/login', json={'username':actor['user_id'], 'password':password})
            assert response.status_code == 200, response.text
            client.headers['X-CSRF-Token'] = response.json()['csrf_token']
        login(engineer)
        analysis=client.post('/api/v1/analysis',json=req)
        assert analysis.status_code==200 and analysis.json()['state']=='SUPPORTED',analysis.text
        prop=client.post('/api/v1/proposals',json={'request':req}).json()
        login(approver)
        decision=client.post('/api/v1/proposals/'+prop['proposal_id']+'/decision',
                             json={'actor':approver,'decision':'approve','expected_hash':prop['fingerprint']})
        assert decision.status_code==200,decision.text
        lost=client.post('/api/v1/proposals/'+prop['proposal_id']+'/execute',
                         json={'actor':approver,'simulate_response_loss':True})
        assert lost.json()['state']=='UNKNOWN_RECONCILE',lost.text
        recovered=client.post('/api/v1/proposals/'+prop['proposal_id']+'/reconcile',json={'actor':approver})
        assert recovered.json()['state']=='SUCCEEDED',recovered.text
        print('LOCAL E2E PASS: analysis → proposal → approval → response loss → reconciliation')
        print('receipt:',recovered.json()['receipt_id'])
        print('CAUTION: local synthetic smoke test only; not a benchmark or proof of production safety')
