import sqlite3

import pytest

from opspilot_x.api import create_app
from opspilot_x.database_backup import backup_database, restore_database
from scripts.backup_db import main


def _app_db(path):
    create_app(path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO users (username,user_id,tenant,team,role,salt,password_hash) "
                   "VALUES ('u','u','t','g','engineer','salt','hash')")
        db.execute("INSERT INTO sessions VALUES ('token-hash','u','csrf',9999999999)")
        db.execute("INSERT INTO proposals (id,request_json,action,fingerprint,owner_user,tenant,team,state,decided_by,created_at,review_due_at)"
                   " VALUES ('p','{}','x','f','u','t','g','pending',NULL,'now','2026-12-01T13:30:00.000000Z')")


def test_backup_and_restore_preserve_app_data(tmp_path):
    source, backup, restored = (tmp_path / name for name in ("source.db", "backup.db", "restored.db"))
    _app_db(source)

    backup_database(source, backup)
    restore_database(backup, restored)

    with sqlite3.connect(backup) as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT username FROM users").fetchone() == ("u",)
        assert db.execute("SELECT id,review_due_at FROM proposals").fetchone() == ("p", "2026-12-01T13:30:00.000000Z")
        assert db.execute("SELECT count(*) FROM evidence_documents").fetchone()[0] > 0
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0


def test_rejects_same_or_existing_destination_without_changing_it(tmp_path):
    source, destination = tmp_path / "source.db", tmp_path / "existing.db"
    _app_db(source)
    destination.write_bytes(b"keep")

    with pytest.raises(ValueError):
        backup_database(source, source)
    with pytest.raises(ValueError):
        backup_database(source, destination)
    assert destination.read_bytes() == b"keep"


@pytest.mark.parametrize("kind", ["missing", "corrupt", "nonapp"])
def test_rejects_invalid_source_and_cleans_temporary_files(tmp_path, kind):
    source, destination = tmp_path / "source.db", tmp_path / "backup.db"
    if kind == "corrupt":
        source.write_bytes(b"not sqlite")
    elif kind == "nonapp":
        with sqlite3.connect(source) as db:
            db.execute("CREATE TABLE unrelated (value TEXT)")

    with pytest.raises((ValueError, sqlite3.Error, FileNotFoundError)):
        backup_database(source, destination)
    assert not destination.exists()
    assert list(tmp_path.glob(".backup.db.*.tmp")) == []


def test_validation_failure_does_not_publish_or_leave_temp(tmp_path):
    source, destination = tmp_path / "source.db", tmp_path / "backup.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE users (username TEXT)")

    with pytest.raises(ValueError):
        backup_database(source, destination)
    assert not destination.exists()
    assert list(tmp_path.glob(".backup.db.*.tmp")) == []


def test_restore_requires_new_destination(tmp_path):
    source, destination = tmp_path / "source.db", tmp_path / "destination.db"
    _app_db(source)
    destination.write_bytes(b"keep")

    with pytest.raises(ValueError):
        restore_database(source, destination)
    assert destination.read_bytes() == b"keep"


def test_cli_backup_and_restore(tmp_path, capsys):
    source, backup, restored = (tmp_path / name for name in ("source.db", "backup.db", "restored.db"))
    _app_db(source)

    assert main(["backup", "--source", str(source), "--destination", str(backup)]) == 0
    assert main(["restore", "--source", str(backup), "--destination", str(restored)]) == 0
    assert "complete" in capsys.readouterr().out


def test_publication_race_never_overwrites_destination(tmp_path, monkeypatch):
    import opspilot_x.database_backup as module
    source, destination = tmp_path / "source.db", tmp_path / "backup.db"
    _app_db(source)
    validate = module._validate

    def raced_validate(path):
        validate(path)
        destination.write_bytes(b"concurrent-owner")

    monkeypatch.setattr(module, "_validate", raced_validate)
    with pytest.raises(FileExistsError):
        backup_database(source, destination)
    assert destination.read_bytes() == b"concurrent-owner"
    assert list(tmp_path.glob(".backup.db.*.tmp")) == []


@pytest.mark.parametrize('state,expected', [('PENDING_APPROVAL', 'EXPIRED'), ('APPROVED', 'UNKNOWN_RECONCILE'), ('UNKNOWN_RECONCILE', 'UNKNOWN_RECONCILE'), ('SUCCEEDED', 'SUCCEEDED'), ('REJECTED', 'REJECTED'), ('EXPIRED', 'EXPIRED')])
def test_restore_quarantines_old_snapshot_preserving_history(tmp_path, state, expected):
    source, backup, restored = (tmp_path / name for name in ('source.db', 'backup.db', 'restored.db'))
    _app_db(source)
    with sqlite3.connect(source) as db:
        db.execute('UPDATE proposals SET state=?, decided_by=?', (state, 'reviewer'))
        db.execute("INSERT INTO audit VALUES ('a','p','CREATED','u','before')")
        db.execute("INSERT INTO work_orders VALUES ('key','p','receipt','x','before')")
    backup_database(source, backup)
    snapshot = backup.read_bytes()
    with sqlite3.connect(source) as db:
        db.execute('UPDATE users SET disabled=1, session_version=4')
        db.execute("UPDATE proposals SET state='REJECTED'")
    restore_database(backup, restored)
    assert backup.read_bytes() == snapshot
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT disabled,session_version FROM users').fetchone() == (1, 1)
        assert db.execute('SELECT count(*) FROM sessions').fetchone() == (0,)
        assert db.execute('SELECT state,decided_by FROM proposals').fetchone() == (expected, 'reviewer')
        assert db.execute('SELECT * FROM work_orders').fetchone() == ('key', 'p', 'receipt', 'x', 'before')
        assert db.execute("SELECT * FROM audit WHERE event_id='a'").fetchone() == ('a', 'p', 'CREATED', 'u', 'before')
        events = db.execute("SELECT proposal_id,actor FROM audit WHERE kind='RESTORE_QUARANTINED'").fetchall()
        assert events == ([('p', 'system')] if state != expected else [])


def test_restore_audit_failure_never_publishes(tmp_path):
    source, restored = tmp_path / 'source.db', tmp_path / 'restored.db'
    _app_db(source)
    with sqlite3.connect(source) as db:
        db.execute("UPDATE proposals SET state='APPROVED'")
        db.execute("CREATE TRIGGER fail_restore BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END")
    snapshot = source.read_bytes()
    with pytest.raises(sqlite3.IntegrityError, match='audit unavailable'):
        restore_database(source, restored)
    assert not restored.exists()
    assert list(tmp_path.glob('.restored.db.*.tmp')) == []
    assert source.read_bytes() == snapshot


def test_restore_refuses_legacy_accounts_without_quarantine_columns(tmp_path):
    source, restored = tmp_path / 'source.db', tmp_path / 'restored.db'
    _app_db(source)
    with sqlite3.connect(source) as db:
        db.execute('ALTER TABLE users DROP COLUMN disabled')
        db.execute('ALTER TABLE users DROP COLUMN session_version')
    with pytest.raises(ValueError, match='account quarantine'):
        restore_database(source, restored)
    assert not restored.exists()
    assert list(tmp_path.glob('.restored.db.*.tmp')) == []


def test_restore_cli_reports_quarantine(tmp_path, capsys):
    source, restored = tmp_path / 'source.db', tmp_path / 'restored.db'
    _app_db(source)
    assert main(['restore', '--source', str(source), '--destination', str(restored)]) == 0
    output = capsys.readouterr().out
    assert 'disabled' in output and 'quarantined' in output
