from contextlib import closing
from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi.testclient import TestClient

from conftest import PASSWORD, login, seed_users
from opspilot_x import api, auth
from opspilot_x.api import create_app
from test_draft_handover_acceptance import current_request


PROPOSALS = '/api/v1/proposals'
DRAFT = '/api/v1/draft-intent'


def test_review_due_is_bound_to_recovered_draft_and_existing_retry(tmp_path):
    path = tmp_path / 'draft.sqlite3'
    seed_users(path)
    with TestClient(create_app(path)) as client:
        login(client, 'engineer-1')
        request = current_request()
        due = '2026-12-01T22:30:00+09:00'
        attempt = client.post(DRAFT, json={'request': request, 'review_due_at': due}).json()['attempt']
        assert attempt['review_due_at'] == '2026-12-01T13:30:00.000000Z'
        assert 'review_due_at' not in attempt['request']
        assert client.get(DRAFT).json() == {'attempt': attempt}
        headers = {'Idempotency-Key': attempt['key']}
        body = {'request': attempt['request'], 'review_due_at': due}
        assert client.post(PROPOSALS, json={'request': attempt['request']}, headers=headers).status_code == 409
        created = client.post(PROPOSALS, json=body, headers=headers)
        assert created.status_code == 201, created.text
        replay = client.post(PROPOSALS, json={**body, 'review_due_at': '2026-12-01T13:30:00Z'}, headers=headers)
        assert replay.status_code == 201 and replay.json() == created.json()
        assert client.post(PROPOSALS, json={**body, 'review_due_at': '2026-12-01T13:31:00Z'}, headers=headers).status_code == 409
        for invalid in ('2026-12-01T13:30:00', '2026-12-01T13:30:00+24:00', 1796131800):
            assert client.post(PROPOSALS, json={**body, 'review_due_at': invalid}).status_code == 422
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('SELECT review_due_at FROM proposals').fetchall() == [('2026-12-01T13:30:00.000000Z',)]


def test_queue_date_boundary_and_access_with_migrated_legacy_rows(tmp_path, monkeypatch):
    path = tmp_path / 'queue.sqlite3'
    seed_users(path)
    auth.create_user(path, username='reviewer-2', password=PASSWORD, user_id='reviewer-2',
                     tenant='demo', team='team_a', role='approver')
    app = create_app(path)
    instant = datetime.now(timezone.utc)

    class FrozenTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)

    with TestClient(app) as client:
        login(client, 'engineer-1')
        request = current_request()
        request['effective_at'] = request['known_as_of'] = (instant - timedelta(seconds=2)).isoformat()
        legacy = client.post(PROPOSALS, json={'request': request},
                             headers={'Idempotency-Key': 'legacy-queue'}).json()
    # Start again from the original table layout with an existing proposal and request.
    with closing(sqlite3.connect(path)) as db, db:
        if 'review_due_at' in {row[1] for row in db.execute('PRAGMA table_info(proposals)')}:
            db.execute('ALTER TABLE proposals DROP COLUMN review_due_at')
    create_app(path)
    reopened = create_app(path)
    monkeypatch.setattr(api, 'datetime', FrozenTime)
    with TestClient(reopened) as client:
        login(client, 'engineer-1')
        assert client.post(PROPOSALS, json={'request': request}, headers={'Idempotency-Key': 'legacy-queue'}).json() == legacy

        def add(due):
            response = client.post(PROPOSALS, json={'request': request, 'review_due_at': due.isoformat()})
            assert response.status_code == 201, response.text
            return response.json()['proposal_id']

        overdue = add(instant - timedelta(seconds=1))
        exact = add(instant)
        future = add(instant + timedelta(seconds=1))
        completed = add(instant - timedelta(seconds=5))
        other = add(instant - timedelta(seconds=7))
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('UPDATE proposals SET state=? WHERE id=?', ('REJECTED', completed))
            db.execute('UPDATE proposals SET team=? WHERE id=?', ('other_team', other))
            assert [row[1] for row in db.execute('PRAGMA table_info(proposals)')].count('review_due_at') == 1
        login(client, 'reviewer-2')
        old = client.get(PROPOSALS).json()
        assert set(old) == {'items'}
        assert all('review_due_at' not in item for item in old['items'])
        queue = client.get(PROPOSALS, params={'review_queue': 'overdue'}).json()
        assert queue['as_of'] == instant.isoformat(timespec='microseconds').replace('+00:00', 'Z')
        assert [item['proposal_id'] for item in queue['items']] == [overdue]
        assert queue['items'][0]['review_due_at'] == (instant - timedelta(seconds=1)).isoformat(timespec='microseconds').replace('+00:00', 'Z')
        unscheduled = client.get(PROPOSALS, params={'review_queue': 'unscheduled'}).json()
        assert [item['proposal_id'] for item in unscheduled['items']] == [legacy['proposal_id']]
        assert unscheduled['items'][0]['review_due_at'] is None
        assert {item['proposal_id'] for item in old['items']} >= {exact, future, completed}
        assert client.get(PROPOSALS + '?review_queue=overdue&review_queue=unscheduled').status_code == 422

        with closing(sqlite3.connect(path)) as db, db:
            db.execute("DELETE FROM evidence_acl WHERE role='approver'")
        assert client.get(PROPOSALS, params={'review_queue': 'overdue'}).json()['items'] == []
        assert client.get(PROPOSALS, params={'review_queue': 'unscheduled'}).json()['items'] == []
        restricted = client.get(PROPOSALS + '/' + overdue).json()
        assert 'review_due_at' not in restricted and 'asset_id' not in restricted
