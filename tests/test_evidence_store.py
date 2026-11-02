import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import pytest

from opspilot_x.eie import load_seed
from opspilot_x.evidence_store import authorized_evidence, initialize_evidence, search_evidence
from opspilot_x.schema import Actor


def principal(role='engineer', team='team_a', tenant='demo'):
    return Actor(user_id='test-user', role=role, team=team, tenant=tenant)


def test_store_seeds_once_and_returns_scoped_current_sources(tmp_path):
    db = tmp_path / 'evidence.sqlite3'
    initialize_evidence(db)
    initialize_evidence(db)
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM evidence_documents').fetchone()[0] == len(load_seed())
    rows = authorized_evidence(db, principal(), asset_id='A-103')
    assert rows and all(e.asset_id == 'A-103' and e.team == 'team_a' for e in rows)
    assert not authorized_evidence(db, principal(tenant='other'))
    assert not authorized_evidence(db, principal(team='other'))


def test_acl_and_knowledge_cutoff_precede_ranking(tmp_path, monkeypatch):
    from opspilot_x import evidence_store
    db = tmp_path / 'evidence.sqlite3'
    initialize_evidence(db)
    allowed = authorized_evidence(db, principal(), known_as_of=datetime(2026, 9, 20, tzinfo=timezone.utc))
    assert allowed and all(e.recorded_at <= datetime(2026, 9, 20, tzinfo=timezone.utc) for e in allowed)
    assert not any(e.asset_id == 'SECRET-1' for e in allowed)
    seen = []
    tokenize = evidence_store._tokens

    def watched(text):
        seen.append(text)
        return tokenize(text)

    monkeypatch.setattr(evidence_store, '_tokens', watched)
    result = search_evidence(db, principal(), query='SECRET', known_as_of=datetime(2026, 9, 20, tzinfo=timezone.utc))
    assert all(row['evidence_id'] in {e.evidence_id for e in allowed} for row in result)
    forbidden = [e.text for e in load_seed() if e.asset_id == 'SECRET-1' or e.recorded_at > datetime(2026, 9, 20, tzinfo=timezone.utc)]
    assert any(e.text in token_input for e in allowed for token_input in seen)
    assert not any(text in token_input for text in forbidden for token_input in seen)


def test_search_exposes_temporal_status_and_parameterized_scope(tmp_path):
    db = tmp_path / 'evidence.sqlite3'
    initialize_evidence(db)
    rows = search_evidence(db, principal(), asset_id='A-103',
                           effective_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
                           known_as_of=datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert rows and all(row['temporal_status'] in {'VALID', 'STALE', 'NOT_YET_EFFECTIVE', 'SUPERSEDED'} for row in rows)
    assert any(row['source_version'] == '2' and row['temporal_status'] == 'VALID' for row in rows)
    assert search_evidence(db, principal(), asset_id="A-103' OR 1=1 --") == []


def test_seed_mutation_cannot_overwrite_existing_snapshot(tmp_path):
    db = tmp_path / 'evidence.sqlite3'
    records = load_seed()
    initialize_evidence(db, records)
    import hashlib
    changed = records[0].model_copy(update={'text': 'changed', 'checksum': hashlib.sha256(b'changed').hexdigest()})
    with pytest.raises(ValueError, match='immutable'):
        initialize_evidence(db, [changed])
    assert authorized_evidence(db, principal(), asset_id=records[0].asset_id)[0].text != 'changed'


def test_invalid_search_budget_and_naive_clock_rejected(tmp_path):
    db = tmp_path / 'evidence.sqlite3'
    initialize_evidence(db)
    for limit in (0, 101, True):
        with pytest.raises(ValueError):
            search_evidence(db, principal(), limit=limit)
    with pytest.raises(ValueError):
        authorized_evidence(db, principal(), known_as_of=datetime(2026, 1, 1))


def test_unrelated_claim_cannot_supersede_timeline_evidence(tmp_path):
    db = tmp_path / 'evidence.sqlite3'
    original = load_seed()[1]
    unrelated = original.model_copy(update={
        'evidence_id': 'unrelated', 'asset_id': 'OTHER-ASSET',
        'supersedes': [original.evidence_id],
    })
    initialize_evidence(db, [original, unrelated])
    rows = search_evidence(db, principal(), effective_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
                           known_as_of=datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert next(row for row in rows if row['evidence_id'] == original.evidence_id)['temporal_status'] == 'VALID'


def test_search_hides_inaccessible_and_not_yet_known_relations(tmp_path):
    db = tmp_path / 'evidence.sqlite3'
    records = load_seed()
    hidden = next(e for e in records if e.asset_id == 'SECRET-1')
    future = records[1].model_copy(update={'evidence_id': 'future-version',
        'recorded_at': datetime(2027, 1, 1, tzinfo=timezone.utc)})
    visible = records[0].model_copy(update={'supersedes': [hidden.evidence_id, future.evidence_id]})
    initialize_evidence(db, [hidden, future, visible])
    rows = search_evidence(db, principal(), known_as_of=datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert len(rows) == 1
    assert rows[0]['supersedes'] == []
