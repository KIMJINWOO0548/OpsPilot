"""A draft POST's response is discarded, then the real desktop API process restarts."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from http.client import HTTPConnection
import json
from pathlib import Path
import queue
import secrets
import sqlite3
import subprocess
import sys
from threading import Thread
from time import monotonic, sleep
from urllib.parse import urlsplit

import pytest

from conftest import PASSWORD
from opspilot_x.auth import create_user


@contextmanager
def desktop_backend(data, web):
    src = str(Path(__file__).resolve().parents[1] / "src")
    launcher = ("import sys; sys.path.insert(0, " + repr(src) + "); "
                "from opspilot_x.desktop_runtime import main; raise SystemExit(main())")
    token = secrets.token_hex(32)
    command = [sys.executable, "-I", "-u", "-c", launcher, "--data-dir", str(data), "--web-dir", str(web)]
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, encoding="utf-8") as process:
        events = queue.Queue()
        try:
            Thread(target=lambda: events.put(process.stdout.readline()), daemon=True).start()
            process.stdin.write(json.dumps({"token": token}) + "\n")
            process.stdin.flush()
            line = events.get(timeout=20)
            assert line, process.stderr.read()
            event = json.loads(line)
            assert event["event"] == "ready" and event["token"] == token
            target = urlsplit(event["origin"])
            assert target.hostname == "127.0.0.1"
            yield target.port, {"X-OpsPilot-Desktop-Token": token}
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        assert process.returncode == 0


def send(conn, verb, path, headers, body=None):
    conn.request(verb, path, body=None if body is None else json.dumps(body),
                 headers={"Content-Type": "application/json", **headers})
    response = conn.getresponse()
    data = json.loads(response.read())
    return response, data


def sign_in(conn, headers):
    response, user = send(conn, "POST", "/api/v1/auth/login", headers,
                         {"username": "restart-engineer", "password": PASSWORD})
    assert response.status == 200
    return {**headers, "Cookie": response.getheader("Set-Cookie").split(";", 1)[0],
            "X-CSRF-Token": user["csrf_token"]}


@pytest.mark.parametrize("review_due_at", [None, "2026-12-01T13:30:00.000000Z"])
def test_discarded_response_and_real_desktop_process_restart(tmp_path, review_due_at):
    data, web = tmp_path / "data", tmp_path / "web" / "dist"
    data.mkdir()
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("test", encoding="utf-8")
    db_path = data / "opspilot.sqlite3"
    create_user(db_path, username="restart-engineer", password=PASSWORD,
                tenant="demo", team="team_a", role="engineer")
    at = datetime.now(timezone.utc).isoformat()
    draft_input = {"asset_id": "A-103", "effective_at": at, "known_as_of": at}
    with desktop_backend(data, web) as (port, desktop_headers):
        with closing(HTTPConnection("127.0.0.1", port, timeout=8)) as conn:
            headers = sign_in(conn, desktop_headers)
            body = {"request": draft_input}
            if review_due_at is not None:
                body["review_due_at"] = review_due_at
            staged, result = send(conn, "POST", "/api/v1/draft-intent", headers, body)
            assert staged.status == 200
            attempt = result["attempt"]
            assert attempt.get("review_due_at") == review_due_at
            body["request"] = attempt["request"]
            conn.request("POST", "/api/v1/proposals", json.dumps(body),
                         {**headers, "Content-Type": "application/json", "Idempotency-Key": attempt["key"]})
            # Observe the commit without calling getresponse() on this connection.
            deadline = monotonic() + 8
            with closing(sqlite3.connect(db_path)) as db:
                while (stored := db.execute("SELECT id FROM proposals").fetchone()) is None:
                    assert monotonic() < deadline, "The first draft did not commit"
                    sleep(0.02)
    with desktop_backend(data, web) as (port, desktop_headers):
        with closing(HTTPConnection("127.0.0.1", port, timeout=8)) as conn:
            headers = sign_in(conn, desktop_headers)
            fetched, result = send(conn, "GET", "/api/v1/draft-intent", headers)
            assert fetched.status == 200 and result == {"attempt": attempt}
            retry, draft = send(conn, "POST", "/api/v1/proposals",
                                {**headers, "Idempotency-Key": attempt["key"]},
                                body)
            assert retry.status == 201 and draft["proposal_id"] == stored[0]
            assert draft["action"] == "sensor_diagnostic_first"
            assert [c["evidence_id"] for c in draft["citations"]] == ["SOP-A103-v2"]
    with closing(sqlite3.connect(db_path)) as db:
        assert db.execute("SELECT id FROM proposals").fetchall() == [stored]
        assert db.execute("SELECT review_due_at FROM proposals").fetchall() == [(review_due_at,)]
        assert db.execute("SELECT kind FROM audit").fetchall() == [("CREATED",)]
        assert db.execute("SELECT COUNT(*) FROM work_orders").fetchone() == (0,)
