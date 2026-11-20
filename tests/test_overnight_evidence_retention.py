"""Approval and handoff retain the exact synthetic source versions after restart."""
import hashlib
import json

from fastapi.testclient import TestClient

from conftest import login
from opspilot_x.api import create_app
from opspilot_x.evidence_store import initialize_evidence
from opspilot_x.schema import Evidence
from contextlib import closing
from datetime import datetime, timezone
import sqlite3
from test_draft_handover_acceptance import case as case, decision, handover, new_proposal, rows


def test_approval_handoff_restart_preserves_source_bytes_and_citation_versions(case):
    path, app = case
    with TestClient(app) as client:
        login(client, 'engineer-1')
        endpoint, draft = new_proposal(client)
        citations = draft['citations']
        assert citations
        source_rows = rows(path, 'SELECT evidence_id,payload FROM evidence_documents ORDER BY evidence_id')
        sources = dict(source_rows)
        for citation in citations:
            source = json.loads(sources[citation['evidence_id']])
            assert citation['source_version'] == source['source_version']
            assert citation['checksum'] == hashlib.sha256(source['text'].encode()).hexdigest()
        login(client, 'approver-1')
        assert decision(client, endpoint, draft['fingerprint']).status_code == 200
        approved = client.get(endpoint).json()
        assert approved['citations'] == citations
        login(client, 'engineer-1')
        assert handover(client, endpoint, draft['fingerprint'], 1).status_code == 403
        login(client, 'reviewer-2')
        assert handover(client, endpoint, draft['fingerprint'], 1).status_code == 200
        assert decision(client, endpoint, draft['fingerprint'], 2).status_code == 200

    with TestClient(create_app(path)) as restarted:
        login(restarted, 'reviewer-2')
        recovered = restarted.get(endpoint).json()
        assert recovered['state'] == 'APPROVED'
        assert recovered['review_version'] == 3
        assert recovered['citations'] == citations
        assert recovered['fingerprint'] == approved['fingerprint']
        assert recovered['review_context'] == approved['review_context']
        assert rows(path, 'SELECT evidence_id,payload FROM evidence_documents ORDER BY evidence_id') == source_rows
        assert rows(path, 'SELECT kind FROM audit') == [('CREATED',), ('APPROVED',), ('HANDOVER',), ('APPROVED',)]
        assert rows(path, 'SELECT * FROM work_orders') == []


def test_audit_opens_approved_document_after_revision_but_respects_revoked_acl(case):
    path, app = case
    with TestClient(app) as client:
        login(client, 'engineer-1')
        endpoint, draft = new_proposal(client)
        original = Evidence.model_validate_json(rows(path, 'SELECT payload FROM evidence_documents WHERE evidence_id=?',
                                                     (draft['citations'][0]['evidence_id'],))[0][0])
        login(client, 'approver-1')
        assert decision(client, endpoint, draft['fingerprint']).status_code == 200
        text = original.text + ' Synthetic later revision.'
        revised = original.model_copy(update={'evidence_id': original.evidence_id + '-later',
            'source_version': 'overnight-next', 'text': text, 'checksum': hashlib.sha256(text.encode()).hexdigest(),
            'recorded_at': datetime.now(timezone.utc), 'supersedes': [original.evidence_id]})
        initialize_evidence(path, [revised])
        event = next(x for x in client.get(endpoint + '/audit').json()['items'] if x['kind'] == 'APPROVED')
        document, = event['approved_documents']
        assert document['evidence_id'] == original.evidence_id
        assert document['source_version'] == original.source_version
        assert document['text'] == original.text and document['checksum'] == original.checksum
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("DELETE FROM evidence_acl WHERE evidence_id=? AND role='approver'", (original.evidence_id,))
        response = client.get(endpoint + '/audit')
        assert response.status_code == 200
        assert response.json()['items'] == []
        assert original.evidence_id not in response.text and original.text not in response.text
