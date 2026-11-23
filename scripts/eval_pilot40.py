"""Run the repository's fixed synthetic pilot against two loopback models."""
from __future__ import annotations

import argparse
import asyncio
import collections
import hashlib
import json
import math
import platform
import re
import secrets
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from opspilot_x.api import create_app
from opspilot_x.auth import create_user
from opspilot_x.eie import authorized, effective_at
from opspilot_x.evidence_store import initialize_evidence
from opspilot_x.hybrid import SOURCE_CHARS, TOP_K, HybridRag, ModelUnavailable
from opspilot_x.local_models import LocalModels, draft_generation_parameters
from opspilot_x.schema import Actor, AnalyzeRequest, Evidence

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "pilot40.json"
TENANT, TEAM = "pilot40-synthetic", "platform-operations"
ROLE = "engineer"
ACTOR = Actor(user_id="pilot40-author", tenant=TENANT, team=TEAM, role=ROLE)
VARIANTS = {
    "policy-a": ("a", "1.0"),
    "expiring-a": ("a", "1.1"),
    "upcoming-b": ("b", "2.0"),
    "retro-b": ("b", "2.1"),
    "conflict-b": ("b", "1.0-peer"),
    "foreign-team": ("b", "1.0-private-team"),
    "foreign-tenant": ("b", "1.0-private-tenant"),
    "restricted-role": ("b", "1.0-private-role"),
    "note": ("a", "0.1-diary"),
}


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def at(day):
    return datetime(2026, 10, day, 12, tzinfo=timezone.utc)


def evidence(family, key):
    action_key, version = VARIANTS[key]
    family_id = family["id"]
    approved = key != "note"
    if approved:
        text = f"Approved instruction when {family['symptom']}. {family[f'instruction_{action_key}']}"
    else:
        text = f"Incident timeline: {family['symptom']}. The support team is gathering logs."
    if key in {"foreign-tenant", "foreign-team", "restricted-role"}:
        text += f" Restricted synthetic reference {family_id}-{key}."
    return Evidence(
        evidence_id=f"{family_id}/{key}", asset_id=family_id, claim_key="incident_response",
        tenant="pilot40-unrelated" if key == "foreign-tenant" else TENANT,
        team="unrelated-operations" if key == "foreign-team" else TEAM,
        readable_roles=["approver"] if key == "restricted-role" else [ROLE, "approver"],
        authority="approved_sop" if approved else "incident_note",
        value=family[f"action_{action_key}"] if approved else "observation",
        source_id=f"pilot40/{family_id}" if key not in {"conflict-b", "note"} else f"pilot40/{family_id}/{key}",
        source_version=version, locator="section:response",
        valid_from=at(12 if key == "upcoming-b" else 1),
        valid_to=at(12) if key == "expiring-a" else None,
        recorded_at=at(15 if key == "retro-b" else 1),
        supersedes=[f"{family_id}/policy-a"] if key == "retro-b" else [],
        checksum=hashlib.sha256(text.encode("utf8")).hexdigest(), text=text,
    )


def load_cases():
    data = json.loads(DATASET.read_text(encoding="utf8"))
    families = [family["id"] for family in data["families"]]
    if data["version"] != "pilot40-v1" or len(set(families)) != 10 or len(families) != 10:
        raise ValueError("Unexpected dataset version or duplicate source family")
    cases = []
    for family in data["families"]:
        for name, stratum, effective_day, known_day, source_keys, state, expected in family["cases"]:
            documents = [evidence(family, key) for key in source_keys]
            if len(source_keys) != len(set(source_keys)) or (state == "SUPPORTED") != bool(expected):
                raise ValueError("Invalid expected label or duplicate source")
            gold = documents[source_keys.index(expected)] if expected else None
            cases.append({
                "id": f"{family['id']}/{name}", "family": family["id"], "split": family["split"],
                "stratum": stratum, "query": f"What should we check first when the {family['symptom']}?",
                "request": AnalyzeRequest(
                    actor=ACTOR, asset_id=family["id"], claim_key="incident_response",
                    effective_at=at(effective_day), known_as_of=at(known_day),
                ),
                "documents": documents, "expected_state": state,
                "expected_source": gold.evidence_id if gold else None,
                "expected_action": gold.value if gold else None,
            })
    if len({case["id"] for case in cases}) != 40 or collections.Counter(
        case["split"] for case in cases
    ) != {"development": 24, "holdout": 16}:
        raise ValueError("Exactly 24 development and 16 family-disjoint holdout cases are required")
    return cases


def terms(text):
    return set(re.findall(r"\w+", text.casefold()))


def lexical_sources(query, documents):
    query_terms = terms(query)
    return [
        {"evidence_id": doc.evidence_id, "text": doc.text[:SOURCE_CHARS],
         "action": doc.value if doc.authority == "approved_sop" else ""}
        for doc in sorted(documents, key=lambda doc: (
            -len(query_terms & terms(doc.text[:SOURCE_CHARS])), doc.evidence_id,
        ))[:TOP_K]
    ]


def inspect_result(case, state, draft, context, embedded, duration, *, analysis=None):
    request = case["request"]
    documents = {doc.evidence_id: doc for doc in case["documents"]}
    blocked_ids = {key for key, doc in documents.items() if not authorized(doc, request.actor)}
    invalid_effective = {key for key, doc in documents.items() if not effective_at(doc, request.effective_at)}
    unobserved = {key for key, doc in documents.items() if doc.recorded_at > request.known_as_of}
    applicable = set(documents) - blocked_ids - invalid_effective - unobserved
    superseded = {old for key in applicable for old in documents[key].supersedes}
    action = draft.get("action") or None
    citations = draft.get("citations", [])
    output_sources = {entry["evidence_id"] for entry in citations}
    if analysis:
        output_sources.update(entry["evidence_id"] for entry in analysis["citations"])
    copied_quotes = [entry.get("quote", "") for entry in citations]
    for quote in copied_quotes:
        output_sources.update(key for key in blocked_ids if quote and quote in documents[key].text)
    visible_actions = {doc.value for key, doc in documents.items() if key not in blocked_ids}
    if action and action not in visible_actions:
        output_sources.update(key for key in blocked_ids if documents[key].value == action)
    exact_citation = bool(citations) and all(
        (doc := documents.get(entry["evidence_id"])) is not None
        and entry.get("quote", "").strip()
        and entry["quote"] in doc.text
        and doc.authority == "approved_sop" and action == doc.value
        and doc.evidence_id in applicable - superseded
        for entry in citations
    )
    valid = (
        action is not None and action == case["expected_action"] and exact_citation
        and any(entry["evidence_id"] == case["expected_source"] for entry in citations)
    )
    return {
        "state": state, "action": action, "context_ids": sorted(context), "embedding_ids": sorted(embedded),
        "citation_ids": sorted(output_sources), "exact_admissible_citation": exact_citation,
        "correct_grounded_draft": valid, "elapsed_ms": round(duration * 1000, 2),
        "acl_model_exposure": bool((embedded | context) & blocked_ids),
        "acl_output_leak": bool(output_sources & blocked_ids),
        "effective_error": bool(output_sources & invalid_effective),
        "observation_error": bool(output_sources & unobserved),
        "supersession_error": bool(output_sources & superseded),
        "temporal_model_exposure": bool((embedded | context) & (invalid_effective | unobserved | superseded)),
    }


async def run_case(case, models, path):
    request = case["request"]
    context, embedded = set(), set()

    def generate(query, sources):
        context.update(source["evidence_id"] for source in sources)
        return models.generate(query, sources)

    hybrid = HybridRag(models.embed, generate, observe_embedding=embedded.update)
    app = create_app(path, hybrid=hybrid)
    initialize_evidence(path, case["documents"])
    password = secrets.token_urlsafe(24)
    create_user(path, username="pilot40-author", password=password, **ACTOR.model_dump())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        login = await client.post("/api/v1/auth/login", json={"username": "pilot40-author", "password": password})
        login.raise_for_status()
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        request_json = request.model_dump(mode="json", exclude={"actor"})
        existing = await client.post("/api/v1/analysis", json=request_json)
        existing.raise_for_status()
        started = time.perf_counter()
        response = await client.post("/api/v1/analysis/hybrid", json=dict(request_json, query=case["query"]))
        response.raise_for_status()
        duration = time.perf_counter() - started
    payload = response.json()
    guarded = inspect_result(case, payload["analysis"]["state"], payload["draft"] or {},
                             context, embedded, duration, analysis=payload["analysis"])
    guarded["model_status"] = payload["model_status"]

    started = time.perf_counter()
    candidates = lexical_sources(case["query"], case["documents"])
    try:
        plain_draft = models.generate(case["query"], candidates) if candidates else {}
    except ModelUnavailable:
        plain_draft, status = {}, "MODEL_UNAVAILABLE"
    else:
        status = "DRAFT_RETURNED" if plain_draft.get("action") else "NO_ACTION"
    plain = inspect_result(case, status, plain_draft, {source["evidence_id"] for source in candidates},
                           set(), time.perf_counter() - started)
    return {
        "case_id": case["id"], "source_family": case["family"], "split": case["split"],
        "stratum": case["stratum"], "query": case["query"], "effective_at": request.effective_at.isoformat(),
        "known_as_of": request.known_as_of.isoformat(), "expected_state": case["expected_state"],
        "expected_source": case["expected_source"], "expected_action": case["expected_action"],
        "document_hashes": {doc.evidence_id: doc.checksum for doc in case["documents"]},
        "existing_policy_state": existing.json()["state"], "plain": plain, "guarded": guarded,
    }


def fraction(outcomes, check):
    return {"numerator": sum(bool(check(row)) for row in outcomes), "denominator": len(outcomes)}


def percentile(sorted_values, proportion):
    return sorted_values[max(0, math.ceil(len(sorted_values) * proportion) - 1)] if sorted_values else None


def aggregate(rows, branch):
    acl = [row for row in rows if row["stratum"] == "acl"]
    time_cases = [row for row in rows if row["stratum"] in {"effective-time", "retroactive"}]
    conflict = [row for row in rows if row["expected_state"] == "CONFLICT"]
    supported = [row for row in rows if row["expected_state"] == "SUPPORTED"]
    proposed = [row for row in rows if row[branch]["action"]]
    ms = sorted(row[branch]["elapsed_ms"] for row in rows)
    return {
        "acl_model_exposure": fraction(acl, lambda r: r[branch]["acl_model_exposure"]),
        "acl_output_leak": fraction(acl, lambda r: r[branch]["acl_output_leak"]),
        "wrong_time_used": fraction(time_cases, lambda r: any(
            r[branch][key] for key in ("effective_error", "observation_error", "supersession_error"))),
        "effective_time_error": fraction(time_cases, lambda r: r[branch]["effective_error"]),
        "observation_time_error": fraction(time_cases, lambda r: r[branch]["observation_error"]),
        "superseded_source_error": fraction(time_cases, lambda r: r[branch]["supersession_error"]),
        "unusable_citation": fraction(proposed, lambda r: not r[branch]["exact_admissible_citation"]),
        "conflict_block": fraction(conflict, lambda r: r[branch]["state"] == "CONFLICT" and not r[branch]["action"]),
        "any_draft_on_eligible": fraction(supported, lambda r: r[branch]["action"]),
        "correct_draft_on_eligible": fraction(supported, lambda r: r[branch]["correct_grounded_draft"]),
        "draft_on_blocked": fraction([row for row in rows if row not in supported], lambda r: r[branch]["action"]),
        "correct_policy_state": fraction(rows, lambda r: r[branch]["state"] == r["expected_state"]),
        "elapsed_ms": {"p50": percentile(ms, .50), "p95": percentile(ms, .95)},
    }


LABELS = {
    "acl_model_exposure": "권한 위반 · 모델 전달",
    "acl_output_leak": "권한 위반 · 응답",
    "wrong_time_used": "시점 오류 · 잘못된 버전 사용",
    "effective_time_error": "유효 기간 위반",
    "observation_time_error": "관측 시점 위반",
    "superseded_source_error": "대체된 버전 사용",
    "unusable_citation": "부적격·누락 인용 / 조치가 있는 응답",
    "conflict_block": "충돌 명시 및 초안 차단",
    "any_draft_on_eligible": "적격 사례 중 초안 제시",
    "correct_draft_on_eligible": "적격 사례 중 정답 및 근거 일치",
    "draft_on_blocked": "차단 대상에 조치 제시",
    "correct_policy_state": "기대 정책 상태 일치",
}


def markdown(report):
    generation = report["generation_parameters"]
    lines = [
        "# OpsPilot-X · 합성 40건 비교 결과", "",
        "겹치지 않는 10개 IT 문서군에서 개발 24건과 홀드아웃 16건을 한 번씩 실행했다. "
        "동일한 Qwen 생성 모델, 구조 제약, 상위 4개 근거, 응답 한도로 비교했다. "
        "단순 RAG는 고정 합성 파일에서 단어 겹침으로 검색하며 권한·두 시점·충돌 검사를 적용하지 않는다.", "",
        "모델 전달은 실제 임베딩 배치와 생성 입력에 담긴 근거 ID를 기록한다. "
        "시점 오류는 응답에 실린 유효 기간 위반, 관측 전 버전, 대체된 버전의 합집합이다. "
        "서로 다른 지표의 분자는 겹칠 수 있다. 인용 지표는 실제 조치가 반환된 응답만 분모에 넣고, "
        "정답률과 초안 제시율은 모든 적격 사례를 분모에 넣는다. "
        "같은 생성기가 인용 1개를 제약하므로 인용 지표는 원문과 해당 조치를 뒷받침하는 자료의 일치가 중심이다.", "",
        "고정 합성 예비 실험이다. 성능 벤치마크와 운영 안전성을 일반화할 수 없다. "
        "케이스당 후보가 4개 이하이므로 BM25와 임베딩의 독립적인 품질 개선은 이 실험에서 측정하지 않았다.", "",
    ]
    for subset, title in [("all", "전체 40건"), ("development", "개발 24건"), ("holdout", "홀드아웃 16건")]:
        stats = report["metrics"][subset]
        lines += [f"## {title}", "", "| 지표 | 단순 RAG | OpsPilot |", "| --- | ---: | ---: |"]
        for key, label in LABELS.items():
            if key == "correct_policy_state":
                continue
            left, right = (stats[k][key] for k in ("plain", "guarded"))
            lines.append(f"| {label} | {left['numerator']}/{left['denominator']} | "
                         f"{right['numerator']}/{right['denominator']} |")
        values = [stats[k]["elapsed_ms"] for k in ("plain", "guarded")]
        lines += [f"| P50 / P95 지연 (ms) | {values[0]['p50']} / {values[0]['p95']} | "
                  f"{values[1]['p50']} / {values[1]['p95']} |", ""]
    lines += [
        "## 재현 조건", "",
        f"- 데이터셋 SHA-256: `{report['dataset_sha256']}`",
        f"- 소스 기준 커밋: `{report['base_commit']}`. 실행 파일별 소스 해시는 JSON에 기록했다.",
        "- 환경: " + report["platform"],
        "- 모델: llama.cpp b12649, Qwen2.5-0.5B-Instruct Q4_K_M, Qwen3-Embedding-0.6B Q8_0. "
        "모델·런타임 해시는 JSON에 기록했다.",
        f"- 생성 계약: temperature {generation['temperature']}, seed {generation['seed']}, "
        f"최대 {generation['max_tokens']} 토큰. 실제 토큰 수는 집계하지 않았다.",
        "- 호출 비용: 로컬 CPU에서 유료 API 호출 0회.",
        "- 기존 결정적 판정과 실제 하이브리드 판정은 JSON의 각 사례에 함께 기록했다.",
        "",
    ]
    return "\n".join(lines)


async def run_pilot(cases, models):
    rows = []
    with tempfile.TemporaryDirectory(prefix="opspilot-pilot40-") as scratch:
        for index, case in enumerate(cases, 1):
            row = await run_case(case, models, Path(scratch) / f"case-{index}.sqlite3")
            rows.append(row)
            print(f"{index}/40 {row['case_id']}: {row['plain']['state']} / {row['guarded']['model_status']}", flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--embedding-port", type=int, required=True)
    parser.add_argument("--chat-port", type=int, required=True)
    args = parser.parse_args()
    assets = [
        "llama-b12649-bin-win-cpu-x64.zip", "qwen2.5-0.5b-instruct-q4_k_m.gguf", "Qwen3-Embedding-0.6B-Q8_0.gguf",
    ]
    model_hashes = {asset: digest(args.runtime / asset) for asset in assets}
    cases = load_cases()
    models = LocalModels(args.embedding_port, args.chat_port)
    rows = asyncio.run(run_pilot(cases, models))
    report = {
        "dataset": DATASET.name, "dataset_sha256": digest(DATASET), "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        ).strip(),
        "code_sha256": {path: digest(ROOT / path) for path in (
            "scripts/eval_pilot40.py", "src/opspilot_x/api.py", "src/opspilot_x/eie.py",
            "src/opspilot_x/hybrid.py", "src/opspilot_x/local_models.py",
        )},
        "platform": f"{platform.platform()} / {platform.processor()}",
        "model_hashes": model_hashes, "paid_api_calls": 0, "decoded_token_counts_measured": False,
        "generation_parameters": draft_generation_parameters(),
        "case_count": len(rows), "case_results": rows, "metrics": {},
    }
    for subset in ("all", "development", "holdout"):
        members = [row for row in rows if subset == "all" or row["split"] == subset]
        report["metrics"][subset] = {branch: aggregate(members, branch) for branch in ("plain", "guarded")}
    violations = [row["case_id"] for row in rows if (
        row["expected_state"] != row["guarded"]["state"]
        or row["expected_state"] != row["existing_policy_state"]
        or row["guarded"]["acl_model_exposure"]
        or row["guarded"]["acl_output_leak"]
        or row["guarded"]["temporal_model_exposure"]
        or any(row["guarded"][key] for key in ("effective_error", "observation_error", "supersession_error"))
        or (row["guarded"]["action"] and not row["guarded"]["correct_grounded_draft"])
    )]
    transport_failures = [row["case_id"] for row in rows if (
        row["guarded"]["model_status"] == "MODEL_UNAVAILABLE" or row["plain"]["state"] == "MODEL_UNAVAILABLE"
    )]
    report["guarded_invariant_violations"] = violations
    report["transport_failures"] = transport_failures
    args.output.mkdir(parents=True, exist_ok=True)
    json_path = args.output / "pilot40-results.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    (args.output / "pilot40-results.ko.md").write_text(markdown(report), encoding="utf8")
    print(f"cases={len(rows)} violations={len(violations)} transport_failures={len(transport_failures)}")
    if violations or transport_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
