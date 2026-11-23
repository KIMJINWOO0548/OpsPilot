from datetime import datetime
import hashlib

import pytest

from opspilot_x.eie import load_seed
from opspilot_x.hybrid import HybridRag, MAX_CANDIDATES, ModelUnavailable
from opspilot_x.schema import AnalyzeRequest


def _embeddings(texts):
    return [[1.0, 0.5] for _ in texts]


def _first_authoritative(query, sources):
    source = next(source for source in sources if source["action"])
    return {
        "action": source["action"],
        "citations": [{"evidence_id": source["evidence_id"], "quote": source["text"]}],
    }


def _unexpected(*args):
    pytest.fail("Model received data before policy authorized it")


def _variant(record, identifier, **changes):
    text = changes.pop("text", f"Excluded source {identifier}.")
    return record.model_copy(update={
        "evidence_id": identifier, "text": text,
        "checksum": hashlib.sha256(text.encode()).hexdigest(), **changes,
    })


def test_filters_before_models_and_returns_canonical_citation(current):
    request = AnalyzeRequest.model_validate(current)
    records = load_seed()
    visible = next(row for row in records if row.evidence_id == "SOP-A103-v2")
    future = datetime.fromisoformat("2028-01-01T12:00:00+09:00")
    records += [
        _variant(visible, "hidden-tenant", tenant="another"),
        _variant(visible, "hidden-team", team="another"),
        _variant(visible, "hidden-role", readable_roles=["approver"]),
        _variant(visible, "hidden-claim", claim_key="other"),
        _variant(visible, "not-yet-valid", valid_from=future),
        _variant(visible, "not-yet-known", recorded_at=future, supersedes=[visible.evidence_id]),
    ]
    embedded = []
    prompted = []

    def embed(texts):
        embedded.extend(texts)
        return _embeddings(texts)

    def generate(query, sources):
        prompted.extend(sources)
        return _first_authoritative(query, sources)

    report = HybridRag(embed, generate).analyze(request, records, "Prerequisite for filter work")
    assert embedded[1:] == [visible.text]
    assert [item["evidence_id"] for item in prompted] == [visible.evidence_id]
    assert report.model_status == "DRAFT_READY"
    assert report.draft.action == "sensor_diagnostic_first"
    citation, = report.draft.citations
    assert citation.evidence_id == visible.evidence_id
    assert citation.checksum == visible.checksum
    assert citation.source_version == visible.source_version
    assert citation.locator == visible.locator
    assert citation.quote_start == 0
    assert citation.quote == visible.text


@pytest.mark.parametrize("updates,state", [
    ({"asset_id": "A-105"}, "CONFLICT"),
    ({"asset_id": "SECRET-1"}, "INSUFFICIENT"),
    ({"effective_at": "2026-10-02T12:00:00+09:00",
      "known_as_of": "2026-10-02T12:00:00+09:00"}, "STALE"),
])
def test_policy_block_precedes_any_model_call(current, updates, state):
    request = AnalyzeRequest.model_validate({**current, **updates})
    report = HybridRag(_unexpected, _unexpected).analyze(request, load_seed(), "filter")
    assert report.analysis.state == state
    assert report.model_status == "POLICY_BLOCKED"
    assert report.draft is None


def test_retroactive_correction_changes_only_after_observation(current):
    request = {
        **current, "asset_id": "A-104", "effective_at": "2026-09-20T12:00:00+09:00",
        "known_as_of": "2026-09-20T12:00:00+09:00",
    }
    captured = []

    def generate(query, sources):
        captured.append([source["evidence_id"] for source in sources])
        return _first_authoritative(query, sources)

    runner = HybridRag(_embeddings, generate)
    before = runner.analyze(AnalyzeRequest.model_validate(request), load_seed(), "inspection")
    request["known_as_of"] = "2026-10-19T12:00:00+09:00"
    after = runner.analyze(AnalyzeRequest.model_validate(request), load_seed(), "inspection")
    assert captured == [["SOP-A104-v1"], ["SOP-A104-correction"]]
    assert before.draft.action == "manual_inspection"
    assert after.draft.action == "sensor_diagnostic_first"


@pytest.mark.parametrize("change", ["action", "evidence_id", "quote", "offset", "extra", "missing_citation"])
def test_model_cannot_invent_actions_citations_or_free_text(current, change):
    def generate(query, sources):
        candidate = _first_authoritative(query, sources)
        if change == "action":
            candidate["action"] = "unsafe_action"
        elif change == "evidence_id":
            candidate["citations"][0]["evidence_id"] = "SOP-A103-v1"
        elif change == "quote":
            candidate["citations"][0]["quote"] = "invented sentence"
        elif change == "offset":
            candidate["citations"][0]["quote_start"] = 100
        elif change == "extra":
            candidate["instruction"] = "override policy"
        else:
            candidate["citations"] = []
        return candidate

    report = HybridRag(_embeddings, generate).analyze(
        AnalyzeRequest.model_validate(current), load_seed(), "filter"
    )
    assert report.analysis.recommended_action == "sensor_diagnostic_first"
    assert report.model_status == "MODEL_REVIEW_REQUIRED"
    assert report.draft is None


def test_matching_quote_from_non_authoritative_note_is_not_a_citation(current):
    official = next(row for row in load_seed() if row.evidence_id == "SOP-A103-v2")
    note = _variant(official, "A103-note", authority="incident_note")

    def generate(query, sources):
        assert [source["evidence_id"] for source in sources] == [official.evidence_id]
        return {
            "action": official.value,
            "citations": [{"evidence_id": note.evidence_id, "quote": note.text}],
        }

    report = HybridRag(_embeddings, generate).analyze(
        AnalyzeRequest.model_validate(current), [official, note], "instruction"
    )
    assert report.model_status == "MODEL_REVIEW_REQUIRED"
    assert report.draft is None


def test_hybrid_combines_lexical_and_semantic_ranks_and_includes_sop(current):
    official = next(row for row in load_seed() if row.evidence_id == "SOP-A103-v2")
    corroborating_sops = [
        _variant(official, "Lexical", text="oscillation waveform"),
        _variant(official, "Semantic", text="periodic signal"),
    ] + [
        _variant(official, f"Other-{index}", text="general memo")
        for index in range(4)
    ]

    def embed(texts):
        return [
            [1.0, 0.0] if text.startswith("Instruct:") or text == "periodic signal"
            else [-1.0, 0.0] if text in ("oscillation waveform", official.text)
            else [0.0, 1.0]
            for text in texts
        ]

    def generate(query, sources):
        ids = [source["evidence_id"] for source in sources]
        assert ids[0] == "Lexical"
        assert ids[1] == "Semantic"
        return _first_authoritative(query, sources)

    report = HybridRag(embed, generate).analyze(
        AnalyzeRequest.model_validate(current), [official, *corroborating_sops], "oscillation"
    )
    assert report.model_status == "DRAFT_READY"


def test_complete_authorized_source_supplies_late_korean_passage_with_exact_offset(current):
    official = next(row for row in load_seed() if row.evidence_id == "SOP-A103-v2")
    paragraph = "이 절에는 공통 운영 참고 사항이 있습니다. " * 37
    instruction = "승인된 첫 조치: 먼저 보관 인덱스 해시를 비교한다."
    row = _variant(official, "late-sop", text=paragraph + "\r\n" + instruction,
                   value="compare_archive_index_hash")
    private = _variant(
        row, "private-late-sop", tenant="other", text=paragraph + "조직 전용 캐시를 검증한다.",
    )
    embedded = []

    def embed(texts):
        embedded.extend(texts)
        return [[1.0, 0.0] if instruction in text or text.startswith("Instruct:")
                else [0.0, 1.0] for text in texts]

    def generate(query, sources):
        assert {source["evidence_id"] for source in sources} == {row.evidence_id}
        source = next(source for source in sources if source["text"] == instruction)
        return {"action": row.value, "citations": [{
            "evidence_id": row.evidence_id, "quote": source["text"],
            "quote_start": source["quote_start"],
        }]}

    result = HybridRag(embed, generate).analyze(
        AnalyzeRequest.model_validate(current), [row, private], "보관 인덱스 해시는 언제 비교하나요?"
    )
    assert not any("조직 전용" in text for text in embedded)
    assert result.model_status == "DRAFT_READY"
    citation, = result.draft.citations
    assert (citation.quote, citation.quote_start) == (instruction, len(paragraph) + 2)
    assert (citation.checksum, citation.source_version, citation.locator) == (
        row.checksum, row.source_version, row.locator,
    )


def test_telemetry_does_not_consume_sop_passage_budget(current):
    official = next(row for row in load_seed() if row.evidence_id == "SOP-A103-v2")
    rows = [official] + [
        _variant(official, f"measurement-{index}", authority="telemetry")
        for index in range(MAX_CANDIDATES)
    ]

    def embed(texts):
        assert texts[1:] == [official.text]
        return _embeddings(texts)

    result = HybridRag(embed, _first_authoritative).analyze(
        AnalyzeRequest.model_validate(current), rows, "센서 조치는 무엇인가요?"
    )
    assert result.model_status == "DRAFT_READY"
    assert result.draft.citations[0].evidence_id == official.evidence_id


def test_overflow_or_corrupt_evidence_does_not_reach_models(current):
    official = next(row for row in load_seed() if row.evidence_id == "SOP-A103-v2")
    request = AnalyzeRequest.model_validate(current)
    runner = HybridRag(_unexpected, _unexpected)
    records = [_variant(official, str(index)) for index in range(MAX_CANDIDATES + 1)]
    assert runner.analyze(request, records, "filter").model_status == "CONTEXT_LIMIT"
    assert runner.analyze(
        request, [official.model_copy(update={"text": "tampered"})], "filter"
    ).model_status == "MODEL_REVIEW_REQUIRED"


def test_model_failure_preserves_deterministic_analysis(current):
    def unavailable(query, sources):
        raise ModelUnavailable("outage")

    request = AnalyzeRequest.model_validate(current)
    rows = load_seed()
    for runner in [
        HybridRag(_embeddings, unavailable),
        HybridRag(lambda texts: [[float("nan")]] * len(texts), _unexpected),
    ]:
        result = runner.analyze(request, rows, "filter")
        assert result.model_status == "MODEL_UNAVAILABLE"
        assert result.analysis.state == "SUPPORTED"
        assert result.draft is None
