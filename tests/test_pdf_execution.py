import asyncio
import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import httpx

from conftest import PASSWORD, seed_users
from opspilot_x.api import create_app


async def sign_in(client, user):
    result = await client.post("/api/v1/auth/login", json={"username": user, "password": PASSWORD})
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]


def test_pdf_approval_loss_restart_integrity_and_no_duplicate(tmp_path):
    async def exercise():
        path = tmp_path / "reports.sqlite3"
        seed_users(path)
        transport = httpx.ASGITransport(app=create_app(path))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await sign_in(client, "engineer-1")
            stamp = datetime.now(timezone.utc).isoformat()
            proposed = await client.post("/api/v1/proposals", json={"request": {
                "asset_id": "A-103", "effective_at": stamp, "known_as_of": stamp,
            }})
            assert proposed.status_code == 201, proposed.text
            proposal = proposed.json()
            route = "/api/v1/proposals/" + proposal["proposal_id"]
            execute = {"output": "pdf", "simulate_response_loss": True}
            assert (await client.post(route + "/execute", json=execute)).status_code == 403
            await sign_in(client, "approver-1")
            assert (await client.post(route + "/execute", json=execute)).status_code == 409
            decision = await client.post(route + "/decision", json={
                "decision": "approve", "expected_hash": proposal["fingerprint"],
            })
            assert decision.status_code == 200, decision.text
            first, second = await asyncio.gather(
                client.post(route + "/execute", json=execute),
                client.post(route + "/execute", json=execute),
            )
            for reply in (first, second):
                assert reply.json() == {"state": "UNKNOWN_RECONCILE", "receipt_id": None}
            assert (await client.get(route + "/report")).status_code == 409
        with closing(sqlite3.connect(path)) as db:
            receipt_id, original = db.execute("SELECT receipt_id, document FROM proposal_reports").fetchone()
            assert db.execute("SELECT count(*) FROM work_orders").fetchone() == (1,)

        restarted = httpx.ASGITransport(app=create_app(path))
        async with httpx.AsyncClient(transport=restarted, base_url="http://test") as client:
            await sign_in(client, "approver-1")
            recovered = await client.post(route + "/reconcile", json={})
            assert recovered.json() == {"state": "SUCCEEDED", "receipt_id": receipt_id}
            assert (await client.post(route + "/execute", json={})).status_code == 409
            assert (await client.get(route)).json()["report_available"]
            await sign_in(client, "engineer-1")
            saved = await client.get(route + "/report")
            assert saved.status_code == 200 and saved.headers["content-type"] == "application/pdf"
            assert saved.content == original and original.startswith(b"%PDF-")
            assert saved.headers["etag"] == '"' + hashlib.sha256(original).hexdigest() + '"'
            await sign_in(client, "other-tenant")
            assert (await client.get(route + "/report")).status_code == 404
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("UPDATE proposal_reports SET document=?", (original[:20],))
            await sign_in(client, "approver-1")
            assert (await client.get(route + "/report")).status_code == 409
            failed = await client.post(route + "/reconcile", json={})
            assert failed.json() == {"state": "UNKNOWN_RECONCILE", "receipt_id": None}
            reply = await client.post(route + "/execute", json=execute)
            assert reply.json() == failed.json()
        with closing(sqlite3.connect(path)) as db:
            assert db.execute("SELECT count(*) FROM work_orders").fetchone() == (1,)
            assert db.execute("SELECT document FROM proposal_reports").fetchone() == (original[:20],)
            assert db.execute("SELECT count(*) FROM audit WHERE kind='PDF_CREATED'").fetchone() == (1,)

    asyncio.run(exercise())
