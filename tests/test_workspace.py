import asyncio
import json
import sqlite3
from contextlib import closing

import httpx
import pytest

from opspilot_x import auth
from opspilot_x.api import create_app
from opspilot_x.database_backup import backup_database
from opspilot_x.workspace import initialize_workspace, import_workspace_evidence, restore_workspace


def source(evidence_id, tenant="local-ops"):
    return {
        "evidence_id": evidence_id,
        "tenant": tenant,
        "team": "archives",
        "readable_roles": ["engineer", "approver"],
        "asset_id": "ARCHIVE-EDI",
        "claim_key": "first_action",
        "value": "보관 인덱스 해시 비교",
        "authority": "approved_sop",
        "source_id": evidence_id,
        "source_version": "3",
        "valid_from": "2026-01-01T00:00:00Z",
        "recorded_at": "2026-01-01T00:00:00Z",
        "locator": "rule 3",
        "text": "보관 목록에 차이가 나면 먼저 보관 인덱스 해시를 비교한다.",
    }


def write_manifest(path, records):
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return path


def stored_sources(path):
    with closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT evidence_id FROM evidence_documents ORDER BY evidence_id").fetchall()


def test_workspace_creation_is_empty_and_import_is_atomic(tmp_path):
    profile = tmp_path / "workplace"
    db = initialize_workspace(profile)
    create_app(db)
    assert stored_sources(db) == []
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone() == (0,)
    with pytest.raises(FileExistsError):
        initialize_workspace(profile)

    initial = source("ARCHIVE-03")
    manifest = write_manifest(tmp_path / "new-version.json", [initial])
    assert import_workspace_evidence(profile, manifest) == 1
    assert import_workspace_evidence(profile, manifest) == 1
    conflicting = dict(initial, text="다른 문서를 승인된 기록으로 남긴다.")
    manifest = write_manifest(manifest, [source("ARCHIVE-04"), conflicting])
    with pytest.raises(ValueError, match="immutable"):
        import_workspace_evidence(profile, manifest)
    assert stored_sources(db) == [("ARCHIVE-03",)]


def test_workspace_import_rejects_sources_the_reader_cannot_open(tmp_path):
    profile = tmp_path / "workplace"
    db = initialize_workspace(profile)
    large_text = "a" * (4 * 1024 * 1024)
    for bad_source in (source("s" * 121), dict(source("large"), text=large_text)):
        manifest = write_manifest(tmp_path / "invalid.json", [source("valid"), bad_source])
        with pytest.raises(ValueError, match="position 2"):
            import_workspace_evidence(profile, manifest)
    assert stored_sources(db) == []


def test_restore_makes_a_separate_workspace_and_quarantines_accounts(tmp_path):
    profile = tmp_path / "live"
    db = initialize_workspace(profile)
    auth.create_user(db, username="old-reviewer", password="synthetic-only-password",
                     tenant="local-ops", team="archives", role="approver")
    manifest = write_manifest(tmp_path / "sources.json", [source("ARCHIVE-03")])
    import_workspace_evidence(profile, manifest)
    create_app(db)
    session = auth.login(db, "old-reviewer", "synthetic-only-password", "127.0.0.1")
    assert session is not None
    snapshot = tmp_path / "backup.sqlite3"
    backup_database(db, snapshot)
    restored = restore_workspace(snapshot, tmp_path / "recovered")
    create_app(restored)
    assert stored_sources(restored) == stored_sources(db) == [("ARCHIVE-03",)]
    assert auth.session(restored, session[0]) is None
    assert auth.login(restored, "old-reviewer", "synthetic-only-password", "127.0.0.1") is None
    assert auth.session(db, session[0]) is not None
    with pytest.raises(FileExistsError):
        restore_workspace(snapshot, profile)

    demo = tmp_path / "demo.sqlite3"
    create_app(demo)
    other_snapshot = tmp_path / "demo-backup.sqlite3"
    backup_database(demo, other_snapshot)
    with pytest.raises(ValueError, match="managed OpsPilot"):
        restore_workspace(other_snapshot, tmp_path / "unpublished")
    assert not (tmp_path / "unpublished").exists()


def test_workspace_catalog_and_original_require_current_scope(tmp_path):
    profile = tmp_path / "workplace"
    db = initialize_workspace(profile)
    password = "synthetic-only-passphrase"
    auth.create_user(db, username="author", password=password, tenant="local-ops",
                     team="archives", role="engineer")
    manifest = write_manifest(tmp_path / "sources.json", [
        source("ARCHIVE-03"),
        source("PARTNER-03", tenant="other-org"),
        dict(source("ARCHIVE-04"), recorded_at="2026-06-01T00:00:00Z"),
    ])
    import_workspace_evidence(profile, manifest)
    app = create_app(db)

    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health")).json()["mode"] == "local-workspace"
            reply = await client.post("/api/v1/auth/login", json={"username": "author", "password": password})
            reply.raise_for_status()
            client.headers["X-CSRF-Token"] = reply.json()["csrf_token"]
            catalog = (await client.get("/api/v1/demo/scenarios")).json()
            assert catalog == {
                "assets": ["ARCHIVE-EDI"], "claims_by_asset": {"ARCHIVE-EDI": ["first_action"]},
                "managed_workspace": True, "scenarios": [],
            }
            cutoff = "2026-05-01T00:00:00Z"
            response = await client.post("/api/v1/analysis", json={
                "asset_id": "ARCHIVE-EDI", "claim_key": "first_action",
                "effective_at": cutoff, "known_as_of": cutoff,
            })
            response.raise_for_status()
            citation, = response.json()["citations"]
            assert citation["evidence_id"] == "ARCHIVE-03"
            source_path = "/api/v1/evidence/source"
            for hidden in ("PARTNER-03", "ARCHIVE-04"):
                response = await client.get(source_path, params={"evidence_id": hidden, "known_as_of": cutoff})
                assert response.status_code == 404
            original = await client.get(source_path, params={"evidence_id": citation["evidence_id"], "known_as_of": cutoff})
            assert original.json() == {**citation, "text": source("ARCHIVE-03")["text"]}
            with auth.connection(db) as connection:
                connection.execute("DELETE FROM evidence_acl WHERE evidence_id='ARCHIVE-03' AND role='engineer'")
            assert (await client.get(source_path, params={"evidence_id": "ARCHIVE-03"})).status_code == 404

    asyncio.run(check())
