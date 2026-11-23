"""Verify authenticated hybrid analysis against both local model servers."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import secrets
import sqlite3
from tempfile import TemporaryDirectory
import time

from fastapi.testclient import TestClient

from opspilot_x.auth import create_user
from opspilot_x.hybrid import HybridRag
from opspilot_x.local_models import LocalModels


def smoke(database: Path, models: LocalModels) -> dict:
    # The API module creates a default app at import time; direct that app to the
    # same synthetic scratch database instead of opening the user's default DB.
    os.environ["OPSPILOT_DB"] = str(database)
    from opspilot_x.api import create_app

    call_counts = {"embeddings": 0, "chat": 0}

    def embed(texts):
        call_counts["embeddings"] += 1
        return models.embed(texts)

    def generate(query, sources):
        call_counts["chat"] += 1
        return models.generate(query, sources)

    app = create_app(database, hybrid=HybridRag(embed, generate))
    password = secrets.token_urlsafe(24)
    create_user(database, username="hybrid-smoke", password=password,
                tenant="demo", team="team_a", role="engineer")
    samples = [
        ("historical", "A-103", "2026-09-15", "SUPPORTED", "replace_filter", "SOP-A103-v1"),
        ("current", "A-103", "2026-11-23", "SUPPORTED", "sensor_diagnostic_first", "SOP-A103-v2"),
        ("conflict", "A-105", "2026-11-23", "CONFLICT", None, None),
        ("out_of_scope", "SECRET-1", "2026-11-23", "INSUFFICIENT", None, None),
    ]
    checked = []
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/login", json={
            "username": "hybrid-smoke", "password": password,
        })
        login.raise_for_status()
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        for label, asset, date, state, action, evidence_id in samples:
            before = call_counts.copy()
            started = time.perf_counter()
            reply = client.post("/api/v1/analysis/hybrid", json={
                "asset_id": asset,
                "effective_at": f"{date}T12:00:00+09:00",
                "known_as_of": f"{date}T12:00:00+09:00",
                "query": f"What should we do first for {asset}?",
            })
            reply.raise_for_status()
            seconds = round(time.perf_counter() - started, 3)
            result = reply.json()
            consumed = {name: value - before[name] for name, value in call_counts.items()}
            assert result["analysis"]["state"] == state, (label, result)
            if action:
                assert consumed == {"embeddings": 1, "chat": 1}, (label, consumed)
                assert result["model_status"] == "DRAFT_READY", (label, result)
                assert result["draft"]["action"] == action, (label, result)
                assert [citation["evidence_id"] for citation in result["draft"]["citations"]] == [evidence_id]
            else:
                assert consumed == {"embeddings": 0, "chat": 0}, (label, consumed)
                assert result["model_status"] == "POLICY_BLOCKED", (label, result)
                assert result["draft"] is None, (label, result)
            if label == "out_of_scope":
                assert result["analysis"]["citations"] == []
                assert "SOP-SECRET" not in reply.text
            checked.append({"scenario": label, "seconds": seconds, "model_calls": consumed, **result})

    with closing(sqlite3.connect(database)) as db:
        proposals, = db.execute("SELECT COUNT(*) FROM proposals").fetchone()
        work_orders, = db.execute("SELECT COUNT(*) FROM work_orders").fetchone()
    assert proposals == work_orders == 0
    return {"scenarios": checked, "work_orders": work_orders, "proposals": proposals}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-port", required=True, type=int)
    parser.add_argument("--chat-port", required=True, type=int)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="opspilot-hybrid-smoke-") as scratch:
        result = smoke(Path(scratch) / "smoke.sqlite3", LocalModels(args.embedding_port, args.chat_port))
    report = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out is not None:
        args.out.write_text(report, encoding="utf-8")
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
