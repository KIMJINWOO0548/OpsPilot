"""Create one disposable A-103 database and byte-identical copies for the clients."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import sys

root = Path(sys.argv[1]).resolve()
root.mkdir()
seed = root / "opspilot.sqlite3"
os.environ["OPSPILOT_DB"] = str(seed)
from fastapi.testclient import TestClient
from opspilot_x import auth
from opspilot_x.api import create_app
from opspilot_x.eie import load_seed
from opspilot_x.evidence_store import initialize_evidence

pw = secrets.token_urlsafe(24)
for name, role in (("qa-engineer", "engineer"), ("qa-first", "approver"), ("qa-second", "approver")):
    auth.create_user(
        seed, username=name, password=pw, user_id=name,
        tenant="demo", team="team_a", role=role,
    )
original = next(source for source in load_seed() if source.evidence_id == "SOP-A103-v2")
initialize_evidence(seed, [
    original.model_copy(update={
        "evidence_id": f"A103-OTHER-{index:02}",
        "source_id": f"A103-OTHER-{index:02}",
        "claim_key": "synthetic_other_claim",
        "authority": "incident_note",
        "supersedes": [],
    })
    for index in range(30)
])
with TestClient(create_app(seed)) as app:
    login = app.post("/api/v1/auth/login", json={"username": "qa-engineer", "password": pw})
    login.raise_for_status()
    headers = {"x-csrf-token": login.json()["csrf_token"]}
    for _ in range(2):
        stamp = datetime.now(timezone.utc).isoformat()
        result = app.post("/api/v1/proposals", json={"request": {
            "asset_id": "A-103", "claim_key": "inspection_priority",
            "effective_at": stamp, "known_as_of": stamp,
        }}, headers=headers)
        result.raise_for_status()
    app.post("/api/v1/auth/logout", json={}, headers=headers).raise_for_status()
with closing(sqlite3.connect(seed)) as db:
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    rows = db.execute("SELECT id FROM proposals ORDER BY created_at DESC").fetchall()
    assert len(rows) == 2 and db.execute("SELECT count(*) FROM work_orders").fetchone()[0] == 0

digest = hashlib.sha256(seed.read_bytes()).hexdigest()
for label in ("dart-contract", "flutter-ui", "wpf-ui"):
    copy = root / label
    copy.mkdir()
    dst = copy / seed.name
    shutil.copyfile(seed, dst)
    assert hashlib.sha256(dst.read_bytes()).hexdigest() == digest
(root / "credentials.json").write_text(
    json.dumps({"reviewer": "qa-first", "replacement": "qa-second", "author": "qa-engineer", "password": pw}),
    encoding="utf-8",
)
(root / "fixture.json").write_text(
    json.dumps({"fixture_sha256": digest, "requests": [r[0] for r in rows],
                "initial_work_orders": 0, "same_starting_bytes": True}, indent=2),
    encoding="utf-8",
)
print("Fixture ready: 2 actual A-103 proposals and 3 byte-identical isolated copies")
