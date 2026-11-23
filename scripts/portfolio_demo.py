"""Generate the 90-second OpsPilot demo pack from a fresh synthetic database."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import tempfile
import time

from httpx import ASGITransport, AsyncClient

from opspilot_x.auth import create_user
from opspilot_x.hybrid import HybridRag
from opspilot_x.local_models import LocalModels

AUTHOR = "demo-author"
REVIEWER = "demo-reviewer"
PREFIX = "/api/v1"


def analyze_input(asset_id, effective_at, known_as_of=None):
    return {
        "asset_id": asset_id, "claim_key": "inspection_priority",
        "effective_at": effective_at, "known_as_of": known_as_of or effective_at,
    }


async def login(client, username, password):
    reply = await client.post(f"{PREFIX}/auth/login", json={"username": username, "password": password})
    reply.raise_for_status()
    identity = reply.json()
    assert identity["user_id"] == username
    client.headers["X-CSRF-Token"] = identity["csrf_token"]
    return identity


def asgi_client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def storage_snapshot(database):
    with closing(sqlite3.connect(database)) as db:
        orders, = db.execute("SELECT COUNT(*) FROM work_orders").fetchone()
        reports, = db.execute("SELECT COUNT(*) FROM proposal_reports").fetchone()
        work = db.execute("SELECT receipt_id, sha256, document FROM proposal_reports").fetchone()
        return orders, reports, work


async def run_demo(database, models):
    # The API module initializes its default app at import time.
    os.environ["OPSPILOT_DB"] = str(database)
    from opspilot_x.api import create_app

    started = time.perf_counter()
    calls = {"embeddings": 0, "chat": 0}

    def embed(texts):
        calls["embeddings"] += 1
        return models.embed(texts)

    def generate(query, sources):
        calls["chat"] += 1
        return models.generate(query, sources)

    hybrid = HybridRag(embed, generate)
    app = create_app(database, hybrid=hybrid)
    password = secrets.token_urlsafe(24)
    for person, role in ((AUTHOR, "engineer"), (REVIEWER, "approver")):
        create_user(database, username=person, password=password, tenant="demo", team="team_a", role=role)
    now = datetime.now(timezone.utc).isoformat()
    past = "2026-09-15T12:00:00+09:00"
    current = analyze_input("A-103", now)
    phases = {}
    async with asgi_client(app) as author, asgi_client(app) as reviewer:
        assert (await login(author, AUTHOR, password))["role"] == "engineer"
        reviewer_identity = await login(reviewer, REVIEWER, password)
        for label, request, expected_action, expected_source in (
            ("historical", analyze_input("A-103", past), "replace_filter", "SOP-A103-v1"),
            ("current", current, "sensor_diagnostic_first", "SOP-A103-v2"),
            ("conflict", analyze_input("A-105", now), None, None),
            ("restricted", analyze_input("SECRET-1", now), None, None),
        ):
            before = calls.copy()
            phase_start = time.perf_counter()
            reply = await author.post(f"{PREFIX}/analysis/hybrid", json={
                **request, "query": f"What should we do first for {request['asset_id']}?",
            })
            reply.raise_for_status()
            result = reply.json()
            consumed = {key: calls[key] - value for key, value in before.items()}
            if expected_action:
                assert consumed == {"embeddings": 1, "chat": 1}
                assert result["model_status"] == "DRAFT_READY", (label, result)
                assert result["draft"]["action"] == expected_action
                assert [citation["evidence_id"] for citation in result["draft"]["citations"]] == [expected_source]
            else:
                assert consumed == {"embeddings": 0, "chat": 0}
                assert result["model_status"] == "POLICY_BLOCKED"
                assert result["draft"] is None
                assert result["analysis"]["state"] == ("CONFLICT" if label == "conflict" else "INSUFFICIENT")
                if label == "restricted":
                    assert result["analysis"]["citations"] == [] and "SOP-SECRET" not in reply.text
            phases[label] = {"model_calls": consumed, "seconds": round(time.perf_counter() - phase_start, 3), **result}

        comparison = await author.post(f"{PREFIX}/analysis/compare", json={
            "asset_id": "A-104", "claim_key": "inspection_priority",
            "effective_at": "2026-10-02T12:00:00+09:00",
            "before_known_as_of": "2026-10-04T12:00:00+09:00",
            "after_known_as_of": "2026-10-06T12:00:00+09:00",
        })
        comparison.raise_for_status()
        observed = comparison.json()
        assert observed["before"]["recommended_action"] == "manual_inspection"
        assert observed["after"]["recommended_action"] == "sensor_diagnostic_first"
        assert observed["before"]["effective_at"] == observed["after"]["effective_at"]
        phases["same_effective_date_comparison"] = observed

        rejected = await author.post(f"{PREFIX}/proposals", json={"request": analyze_input("A-105", now)})
        assert rejected.status_code == 422 and "CONFLICT" in rejected.text, rejected.text
        created = await author.post(f"{PREFIX}/proposals", json={"request": current}, headers={
            "Idempotency-Key": "portfolio-demo-a103",
        })
        created.raise_for_status()
        proposal = created.json()
        assert proposal["state"] == "PENDING_APPROVAL"
        assert proposal["citations"][0]["checksum"] == phases["current"]["draft"]["citations"][0]["checksum"]
        proposal_url = f"{PREFIX}/proposals/{proposal['proposal_id']}"
        decision = {"decision": "approve", "expected_hash": proposal["fingerprint"], "expected_version": 0}
        reviewer_actor = {key: reviewer_identity[key] for key in ("user_id", "tenant", "team", "role")}
        denial = await author.post(f"{proposal_url}/decision", json={**decision, "actor": reviewer_actor})
        assert denial.status_code == 403 and "separation of duty" in denial.text
        premature = await reviewer.post(f"{proposal_url}/execute", json={"output": "pdf"})
        assert premature.status_code == 409 and storage_snapshot(database) == (0, 0, None)
        phases["proposal_before_approval"] = {
            "state": proposal["state"], "conflict_proposal_status": rejected.status_code,
            "self_approval_status": denial.status_code, "unapproved_pdf_status": premature.status_code,
            "reports_before_approval": 0,
        }

        approved = await reviewer.post(f"{proposal_url}/decision", json=decision)
        approved.raise_for_status()
        assert approved.json()["state"] == "APPROVED"
        phases["independent_approval"] = {
            "state": approved.json()["state"], "reviewer": REVIEWER, "author": AUTHOR,
            "approved_fingerprint": proposal["fingerprint"], "approved_citations": proposal["citations"],
        }
        lost = await reviewer.post(f"{proposal_url}/execute", json={"output": "pdf", "simulate_response_loss": True})
        lost.raise_for_status()
        assert lost.json() == {"state": "UNKNOWN_RECONCILE", "receipt_id": None}
        unavailable = await reviewer.get(f"{proposal_url}/report")
        assert unavailable.status_code == 409
        orders, reports, work = storage_snapshot(database)
        assert (orders, reports) == (1, 1)
        receipt_id, digest, document = work
        assert hashlib.sha256(document).hexdigest() == digest
        phases["response_loss"] = {
            **lost.json(), "hidden_report_status": unavailable.status_code,
            "committed_receipts": orders, "committed_reports": reports,
        }

    restart = create_app(database, hybrid=hybrid)
    async with asgi_client(restart) as reviewer:
        await login(reviewer, REVIEWER, password)
        pending = await reviewer.get(proposal_url)
        pending.raise_for_status()
        assert pending.json()["state"] == "UNKNOWN_RECONCILE"
        recovered = await reviewer.post(f"{proposal_url}/reconcile", json={"output": "pdf"})
        recovered.raise_for_status()
        assert recovered.json() == {"state": "SUCCEEDED", "receipt_id": receipt_id}
        retry = await reviewer.post(f"{proposal_url}/execute", json={"output": "pdf"})
        retry.raise_for_status()
        assert retry.json() == recovered.json()
        settled = await reviewer.get(proposal_url)
        settled.raise_for_status()
        assert settled.json()["report_available"]
        exported = await reviewer.get(f"{proposal_url}/report")
        exported.raise_for_status()
        assert exported.headers["Content-Type"] == "application/pdf"
        assert exported.headers["ETag"] == f'"{digest}"'
        assert exported.content == document and document.startswith(b"%PDF-")
        assert storage_snapshot(database) == (1, 1, work)
        phases["restart_and_recovery"] = {
            "before_reconcile": pending.json()["state"], **recovered.json(),
            "execution_retry_same_receipt": True, "report_available": settled.json()["report_available"],
            "receipt_rows": 1, "report_rows": 1, "sha256": digest, "bytes": len(document),
            "etag": exported.headers["ETag"], "same_committed_bytes": True,
        }
    return phases, document, round(time.perf_counter() - started, 3)


def inspect_pdf(scratch_pdf):
    executable = shutil.which("pdfinfo")
    if executable is None:
        return {"parser": "pdfinfo", "status": "UNAVAILABLE"}
    process = subprocess.run(
        [executable, str(scratch_pdf)], check=True, capture_output=True, text=True,
        encoding="utf8", errors="replace", timeout=15,
    )
    rows = dict(line.split(":", maxsplit=1) for line in process.stdout.splitlines() if ":" in line)
    pages = int(rows["Pages"].strip())
    if pages < 1:
        raise ValueError("Independent PDF parser found no pages")
    return {"parser": "pdfinfo", "status": "PASSED", "pages": pages, "version": rows["PDF version"].strip()}


def readme(data):
    phases = data["phases"]
    recovery = phases["restart_and_recovery"]
    return f"""# OpsPilot-X · 90초 합성 시연

감자 PC의 실제 로컬 모델과 인증된 API로 분석·승인·PDF·영수증 복구를 자동 실행했습니다.
자동 실행 {data['automatic_execution_seconds']:.3f}초는 아래 90초 발표 흐름과 별도로 측정했습니다.
시연 데이터는 저장소의 합성 SOP와 실행 시 생성한 계정으로 구성했습니다.

| 시연 시간 | 보여 줄 동작 | 실행에서 확인한 값 |
| --- | --- | --- |
| 00–16초 | A-103의 과거와 현재 근거를 보고 첫 조치를 비교합니다. | SOP-A103 v1은 필터 교체, v2는 센서 진단. 두 응답 모두 원문을 확인한 LLM 초안입니다. |
| 16–31초 | A-104에서 업무일을 고정한 뒤 관측 시점을 이동합니다. A-105에서는 상충하는 SOP를 확인합니다. | 사후 정정의 관측 전후 결과 변경. A-105는 `CONFLICT`, 모델 호출 0회. |
| 31–49초 | A-103의 현재 근거로 요청을 생성합니다. 작성자가 자신의 요청을 승인하려 하면 차단됩니다. | 작성자 승인 HTTP 403. 승인을 받기 전 PDF 0건. |
| 49–64초 | 다른 승인자가 요청의 근거와 버전을 확인하고 승인합니다. PDF 작업에서 응답 유실을 모의합니다. | 서버 기록 `APPROVED` → `UNKNOWN_RECONCILE`, 확인 전 다운로드 HTTP 409. |
| 64–90초 | 백엔드 앱 인스턴스를 다시 만들고 결과를 확인합니다. PDF를 열어 같은 영수증과 해시를 확인합니다. | 영수증 `{recovery['receipt_id']}`. 동일 PDF 바이트, 영수증 1건과 PDF 1건. |

- [생성된 승인 PDF](opspilot-approved-report.pdf)
- [자동 실행 데이터](portfolio-demo.json)
- PDF SHA-256 `{recovery['sha256']}`
- 독립 PDF 파서 `{data['pdf_parser']['status']}`
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="A new output directory")
    parser.add_argument("--embedding-port", required=True, type=int)
    parser.add_argument("--chat-port", required=True, type=int)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output directory already exists; select a fresh path")
    models = LocalModels(args.embedding_port, args.chat_port)
    with tempfile.TemporaryDirectory(prefix="opspilot-portfolio-demo-") as tmp:
        scratch = Path(tmp)
        phases, document, seconds = asyncio.run(run_demo(scratch / "demo.sqlite3", models))
        staged_pdf = scratch / "report.pdf"
        staged_pdf.write_bytes(document)
        checked = inspect_pdf(staged_pdf)
    data = {"scenario": "synthetic A-103/A-104/A-105", "presentation_seconds": 90,
            "automatic_execution_seconds": seconds, "pdf_parser": checked, "phases": phases}
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / "opspilot-approved-report.pdf").open("xb") as handle:
        handle.write(document)
    with (args.output / "portfolio-demo.json").open("x", encoding="utf8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    with (args.output / "README.ko.md").open("x", encoding="utf8") as handle:
        handle.write(readme(data))
    print(f"PASS synthetic 90-second demo pack, automated {seconds:.3f}s, PDF parser {checked['status']}")


if __name__ == "__main__":
    main()
