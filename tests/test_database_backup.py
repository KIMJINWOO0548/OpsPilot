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
        db.execute("INSERT INTO proposals VALUES ('p','{}','x','f','u','t','g','pending',NULL,'now')")


def test_backup_and_restore_preserve_app_data(tmp_path):
    source, backup, restored = (tmp_path / name for name in ("source.db", "backup.db", "restored.db"))
    _app_db(source)

    backup_database(source, backup)
    restore_database(backup, restored)

    with sqlite3.connect(backup) as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT username FROM users").fetchone() == ("u",)
        assert db.execute("SELECT id FROM proposals").fetchone() == ("p",)
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
