"""Validated local SQLite backups and fresh-destination restores."""
import os
import sqlite3
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_TABLES = frozenset({
    "users", "sessions", "evidence_documents", "evidence_acl",
    "proposals", "work_orders", "audit",
})


def _paths(source, destination):
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or destination.is_symlink():
        raise ValueError("Symlink paths are not supported")
    if not source.exists() or not source.is_file():
        raise FileNotFoundError("Source database must be an existing regular file")
    if not destination.parent.is_dir():
        raise FileNotFoundError("Destination directory must already exist")
    source = source.resolve(strict=True)
    destination = destination.parent.resolve(strict=True) / destination.name
    if source == destination:
        raise ValueError("Source and destination must be different files")
    if os.path.lexists(destination):
        raise ValueError("Destination already exists")
    return source, destination


def _validate(path):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        result = db.execute("PRAGMA integrity_check").fetchall()
        if result != [("ok",)]:
            raise ValueError("Database integrity check failed")
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        missing = REQUIRED_TABLES - tables
        if missing:
            raise ValueError("Database is missing required application tables")


def _copy_database(source, destination, *, clear_sessions):
    source, destination = _paths(source, destination)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp",
                                    dir=destination.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(temp)) as dst:
                src.backup(dst)
                if clear_sessions:
                    with dst:
                        columns = {row[1] for row in dst.execute('PRAGMA table_info(users)')}
                        if not {'disabled', 'session_version'} <= columns:
                            raise ValueError('Restore requires account quarantine columns; legacy backup refused')
                        dst.execute("DELETE FROM sessions")
                        dst.execute('UPDATE users SET disabled=1, session_version=session_version+1')
                        # The snapshot cannot prove that a later execution or revocation never happened.
                        for proposal_id, state in dst.execute(
                            "SELECT id,state FROM proposals WHERE state IN ('PENDING_APPROVAL','APPROVED')"
                        ).fetchall():
                            restored_state = 'EXPIRED' if state == 'PENDING_APPROVAL' else 'UNKNOWN_RECONCILE'
                            dst.execute('UPDATE proposals SET state=? WHERE id=?',
                                        (restored_state, proposal_id))
                            dst.execute('INSERT INTO audit VALUES (?,?,?,?,?)',
                                        (str(uuid.uuid4()), proposal_id, 'RESTORE_QUARANTINED',
                                         'system', datetime.now(timezone.utc).isoformat()))
        _validate(temp)
        if os.name == "nt":
            # Windows rename atomically refuses an existing destination.
            os.rename(temp, destination)
        else:
            # POSIX rename can overwrite a raced destination, so retain link.
            os.link(temp, destination)
        return {"source": str(source), "destination": str(destination),
                "tables_validated": len(REQUIRED_TABLES)}
    finally:
        temp.unlink(missing_ok=True)


def backup_database(source, destination):
    """Create a validated snapshot while preserving every database row."""
    return _copy_database(source, destination, clear_sessions=False)


def restore_database(source, destination):
    """Restore to a new file with users disabled and executable proposals quarantined."""
    return _copy_database(source, destination, clear_sessions=True)
