import asyncio
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
