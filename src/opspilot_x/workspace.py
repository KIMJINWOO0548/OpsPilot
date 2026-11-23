"""Provision a managed local workspace and import immutable evidence snapshots."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from . import auth
from .database_backup import backup_database, restore_database
from .evidence_store import initialize_evidence
from .schema import Evidence

DATABASE_NAME = "opspilot.sqlite3"
MARKER_NAME = "OPSPILOT-WORKSPACE"
MARKER = b"OpsPilot-X local workspace v1\n"
MAX_IMPORT_BYTES = 16_777_216
MAX_SOURCE_BYTES = 4 * 1024 * 1024
SOURCE_FIELDS = {"evidence_id", "source_id", "source_version", "locator", "checksum", "text"}


def _local_path(path: Path) -> Path:
    absolute = path.absolute()
    if os.name == "nt" and absolute.drive.startswith("\\"):
        raise ValueError("Choose a local workspace folder")
    if absolute != absolute.resolve():
        raise ValueError("Workspace paths must not traverse links")
    return absolute


def _regular_single_link(path: Path) -> bool:
    return path.is_file() and path.resolve() == path and path.stat().st_nlink == 1


def _has_workspace_metadata(path: Path) -> bool:
    with closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)) as connection:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='opspilot_workspace_metadata'"
        ).fetchone():
            return False
        if connection.execute("SELECT version FROM opspilot_workspace_metadata").fetchall() != [(1,)]:
            raise ValueError("Unsupported OpsPilot workspace database version")
    return True


def workspace_database(profile: Path) -> Path:
    profile = _local_path(profile)
    marker = profile / MARKER_NAME
    db = profile / DATABASE_NAME
    if (not _regular_single_link(marker) or marker.stat().st_size != len(MARKER)
            or marker.read_bytes() != MARKER or not _regular_single_link(db)):
        raise ValueError("Choose an initialized OpsPilot workspace")
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = profile / (DATABASE_NAME + suffix)
        if os.path.lexists(sidecar) and not _regular_single_link(sidecar):
            raise ValueError("Workspace database sidecar must be a regular local file")
    if not _has_workspace_metadata(db):
        raise ValueError("Missing OpsPilot workspace database metadata")
    return db


def is_workspace_database(path: str | Path) -> bool:
    path = Path(path)
    if path.name.casefold() != DATABASE_NAME or not os.path.lexists(path.parent / MARKER_NAME):
        if path.is_file() and _has_workspace_metadata(path):
            raise ValueError("Select the initialized OpsPilot workspace folder, or use workspace restore")
        return False
    if path.absolute() != workspace_database(path.parent):
        raise ValueError("Choose the workspace database")
    return True


@contextmanager
def _new_workspace(profile: Path):
    profile = _local_path(profile)
    if os.path.lexists(profile):
        raise FileExistsError("Choose a new directory for the workspace")
    with TemporaryDirectory(prefix=".opspilot-workspace-", dir=profile.parent) as directory:
        staged = Path(directory) / "workspace"
        staged.mkdir()
        db = staged / DATABASE_NAME
        yield db
        (staged / MARKER_NAME).write_bytes(MARKER)
        if os.name == "nt":
            staged.rename(profile)
        else:
            profile.mkdir()
            for name in (DATABASE_NAME, MARKER_NAME):
                (staged / name).rename(profile / name)


def initialize_workspace(profile: Path) -> Path:
    with _new_workspace(profile) as db:
        auth.initialize(db)
        initialize_evidence(db, records=[])
        with auth.connection(db) as connection:
            connection.execute("CREATE TABLE opspilot_workspace_metadata (version INTEGER PRIMARY KEY)")
            connection.execute("INSERT INTO opspilot_workspace_metadata VALUES (1)")
    return workspace_database(profile)


def restore_workspace(backup: Path, profile: Path) -> Path:
    with _new_workspace(profile) as db:
        restore_database(backup, db)
        if not _has_workspace_metadata(db):
            raise ValueError("Choose a backup from a managed OpsPilot workspace")
    return workspace_database(profile)


def import_workspace_evidence(profile: Path, source: Path) -> int:
    db = workspace_database(profile)
    with source.open("rb") as stream:
        raw = stream.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise ValueError("Evidence manifest exceeds 16 MiB")
    rows = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("Evidence manifest must contain an array of source records")
    records = []
    for index, row in enumerate(rows, start=1):
        try:
            if not isinstance(row, dict) or not isinstance(row.get("text"), str) or not row["text"].strip():
                raise ValueError
            item = dict(row)
            item.setdefault("checksum", hashlib.sha256(item["text"].encode()).hexdigest())
            record = Evidence.model_validate(item)
            if (not record.readable_roles or set(record.readable_roles) - {"viewer", "engineer", "approver"}
                    or (record.valid_to is not None and record.valid_to <= record.valid_from)):
                raise ValueError
            if not all(value.strip() for value in (
                record.tenant, record.team, record.asset_id, record.claim_key, record.evidence_id,
                record.source_id, record.source_version, record.locator, record.value,
            )):
                raise ValueError
            if not 1 <= len(record.asset_id) <= 80 or not 1 <= len(record.claim_key) <= 80:
                raise ValueError
            source_payload = json.dumps(
                record.model_dump(include=SOURCE_FIELDS), ensure_ascii=False, separators=(",", ":"),
            ).encode("utf-8")
            if len(record.evidence_id) > 120 or len(source_payload) > MAX_SOURCE_BYTES:
                raise ValueError
            records.append(record)
        except ValueError:
            raise ValueError(f"Invalid evidence record at position {index}") from None
    initialize_evidence(db, records=records)
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("init", help="Create an empty managed workspace")
    account = command.add_parser("user-add", help="Create a scoped account using an interactive password")
    account.add_argument("--username", required=True)
    account.add_argument("--tenant", required=True)
    account.add_argument("--team", required=True)
    account.add_argument("--role", choices=("viewer", "engineer", "approver"), required=True)
    for name in ("user-disable", "revoke-sessions"):
        command.add_parser(name).add_argument("--username", required=True)
    command.add_parser("import").add_argument("manifest", type=Path)
    command.add_parser("backup").add_argument("destination", type=Path)
    command.add_parser("restore").add_argument("backup_file", type=Path)
    options = parser.parse_args()
    try:
        if options.command == "init":
            initialize_workspace(options.profile)
            print("Workspace created.")
        elif options.command == "restore":
            restore_workspace(options.backup_file, options.profile)
            print("Workspace restored with old accounts and sessions disabled.")
        elif options.command == "import":
            count = import_workspace_evidence(options.profile, options.manifest)
            print(f"Validated evidence records: {count}")
        else:
            db = workspace_database(options.profile)
            if options.command == "user-add":
                password = getpass.getpass("Password (12+ characters): ")
                if password != getpass.getpass("Repeat password: "):
                    raise ValueError("Passwords did not match")
                auth.create_user(db, username=options.username, password=password,
                                 tenant=options.tenant, team=options.team, role=options.role)
                print("Workspace account created.")
            elif options.command == "backup":
                backup_database(db, options.destination)
                print("Workspace database backup created.")
            else:
                auth.revoke_sessions(db, options.username, disable=options.command == "user-disable")
                print("Workspace sessions revoked.")
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Workspace operation failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
