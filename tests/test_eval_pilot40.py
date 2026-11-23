import asyncio
import hashlib
from collections import Counter

from opspilot_x.eie import evaluate
from scripts.eval_pilot40 import aggregate, load_cases, run_case


def test_fixed_pilot_has_family_disjoint_splits_and_explicit_gold_labels():
    cases = load_cases()
    development = [case for case in cases if case["split"] == "development"]
    holdout = [case for case in cases if case["split"] == "holdout"]
    assert Counter(case["stratum"] for case in development) == {
        "supported": 5, "effective-time": 5, "retroactive": 3,
        "conflict": 3, "acl": 5, "insufficient": 3,
    }
    assert Counter(case["stratum"] for case in holdout) == {
        "supported": 3, "effective-time": 3, "retroactive": 3,
        "conflict": 3, "acl": 3, "insufficient": 1,
    }
    assert {case["family"] for case in development}.isdisjoint(case["family"] for case in holdout)
    assert {doc.checksum for case in development for doc in case["documents"]}.isdisjoint(
        doc.checksum for case in holdout for doc in case["documents"]
    )
    for case in cases:
        result = evaluate(case["request"], case["documents"])
        assert result.state == case["expected_state"], case["id"]
        assert result.recommended_action == case["expected_action"], case["id"]


class SyntheticFirstSourceModel:
    """Deterministic transport substitute for checking only the metrics instrumentation."""

    def embed(self, texts):
        return [[1.0, 1.0] for _ in texts]

    def generate(self, query, sources):
        selected = next(item for item in sources if item["action"])
        return {
            "action": selected["action"],
            "citations": [{"evidence_id": selected["evidence_id"], "quote": selected["text"]}],
        }


def test_reports_acl_exposure_and_valid_answer_with_distinct_denominators(tmp_path):
    cases = {case["id"]: case for case in load_cases()}

    async def exercise():
        model = SyntheticFirstSourceModel()
        row = await run_case(cases["artifact-mirror/another-team"], model, tmp_path / "acl.sqlite")
        blocked = await run_case(cases["batch-broker/two-valid-playbooks"], model, tmp_path / "conflict.sqlite")
        return row, blocked

    row, blocked = asyncio.run(exercise())
    assert row["plain"]["acl_model_exposure"]
    assert row["plain"]["acl_output_leak"]
    assert not row["guarded"]["acl_model_exposure"]
    assert row["guarded"]["correct_grounded_draft"]
    assert blocked["guarded"]["context_ids"] == []
    metrics = aggregate([row, blocked], "guarded")
    assert metrics["unusable_citation"] == {"numerator": 0, "denominator": 1}
    assert metrics["conflict_block"] == {"numerator": 1, "denominator": 1}
    assert metrics["correct_draft_on_eligible"] == {"numerator": 1, "denominator": 1}


def test_embedding_trace_attributes_split_passages_to_the_actual_source(tmp_path):
    cases = {case["id"]: case for case in load_cases()}
    case = cases["artifact-mirror/another-team"]
    shared_passage = "Shared synthetic reference about the mirror maintenance glossary."
    additional_passages = " ".join(
        f"Synthetic operations glossary entry {index} documents a separate maintenance term."
        for index in range(1, 20)
    )
    documents = []
    for document in case["documents"]:
        text = " ".join((document.text, shared_passage, additional_passages))
        documents.append(document.model_copy(update={
            "text": text,
            "checksum": hashlib.sha256(text.encode("utf8")).hexdigest(),
        }))

    class RecordingModel(SyntheticFirstSourceModel):
        def __init__(self):
            self.batches = []

        def embed(self, texts):
            self.batches.append(texts)
            return super().embed(texts)

    model = RecordingModel()
    row = asyncio.run(run_case(
        dict(case, documents=documents), model, tmp_path / "passages.sqlite",
    ))

    assert len(model.batches) > 1
    assert any(shared_passage in batch for batch in model.batches)
    assert row["guarded"]["embedding_ids"] == [case["expected_source"]]
    assert not row["guarded"]["acl_model_exposure"]
