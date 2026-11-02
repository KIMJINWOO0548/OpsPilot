import math

import pytest

from opspilot_x.evaluation_metrics import (
    Outcome, calibrate_threshold, paired_bootstrap, risk_coverage_curve, summarize,
)


def row(case, group="g1", eligible=True, proposed=True, correct=True, confidence=0.9, leaked=False):
    return Outcome(case, group, eligible, proposed, correct, confidence, leaked)


@pytest.mark.parametrize("field,value", [
    ("case_id", " "), ("case_id", " a"), ("source_group_id", ""),
    ("eligible", 1), ("proposed", 0), ("correct", 1), ("leaked", 0),
    ("confidence", True), ("confidence", math.nan), ("confidence", math.inf),
    ("confidence", -0.1), ("confidence", 1.1), ("confidence", "0.5"),
])
def test_outcome_rejects_invalid_fields(field, value):
    fields = dict(case_id="a", source_group_id="g", eligible=True, proposed=True,
                  correct=True, confidence=0.9, leaked=False)
    fields[field] = value
    with pytest.raises(ValueError):
        Outcome(**fields)


@pytest.mark.parametrize("eligible,proposed", [(False, True), (True, False), (False, False)])
def test_correct_requires_eligible_proposal(eligible, proposed):
    with pytest.raises(ValueError):
        row("a", eligible=eligible, proposed=proposed)


def test_summary_denominators_threshold_and_unerasable_leak():
    rows = [row("a"), row("b", correct=False, confidence=0.5),
            row("c", eligible=False, correct=False, confidence=0.4, leaked=True),
            row("d", proposed=False, correct=False)]
    result = summarize(rows)
    assert [result[k] for k in ("n_cases", "n_eligible", "n_proposed", "n_correct")] == [4, 3, 3, 1]
    assert result["coverage"] == 2 / 3
    assert result["proposal_rate"] == 3 / 4
    assert result["unsupported_action_rate"] == 2 / 3
    assert result["safe_completion"] == 1 / 3
    filtered = summarize(rows, 0.8)
    assert filtered["n_proposed"] == filtered["n_correct"] == 1
    assert filtered["leak_count"] == 1
    assert filtered["max_attainable_coverage"] == 2 / 3


def test_empty_and_all_abstain_do_not_report_success():
    result = summarize([row("a", proposed=False, correct=False)])
    assert result["coverage"] == result["safe_completion"] == 0
    assert result["unsupported_action_rate"] is None
    assert result["aurc_partial"] is None
    empty = summarize([])
    assert empty["coverage"] is empty["safe_completion"] is empty["aurc_partial"] is None


def test_curve_ties_and_right_step_partial_area():
    rows = [row("a"), row("b", correct=False, confidence=0.5),
            row("c", confidence=0.5), row("d", proposed=False, correct=False)]
    curve = risk_coverage_curve(rows)
    assert [p["coverage"] for p in curve] == [0, 0.25, 0.75]
    assert [p["risk"] for p in curve] == [None, 0, 1 / 3]
    assert curve[0]["threshold"] is None
    result = summarize(rows)
    assert result["aurc_partial"] == pytest.approx(1 / 6)
    assert result["max_attainable_coverage"] == 0.75


def test_calibration_uses_dev_confidence_and_records_tie_overrun():
    rows = [row("a"), row("b", confidence=0.5), row("c", confidence=0.5),
            row("d", proposed=False, correct=False)]
    result = calibrate_threshold(rows, 0.6)
    assert result["threshold"] == 0.5
    assert result["achieved_coverage"] == 0.75
    assert result["reached"] is True
    assert result["tie_overrun"] == pytest.approx(0.15)
    flipped = [row(o.case_id, proposed=o.proposed, correct=False, confidence=o.confidence) for o in rows]
    assert calibrate_threshold(flipped, 0.6) == result
    unreachable = calibrate_threshold(rows, 0.9)
    assert unreachable["reached"] is False
    assert unreachable["threshold"] is None
    for split in ("train", "holdout"):
        with pytest.raises(ValueError):
            calibrate_threshold(rows, split=split)


def test_bootstrap_is_cluster_paired_deterministic_and_order_independent():
    left = [row("a", "g1", correct=False), row("b", "g1", correct=False), row("c", "g2")]
    right = [row("a", "g1"), row("b", "g1"), row("c", "g2")]
    result = paired_bootstrap(left, right, iterations=100, seed=7)
    assert result["difference"] == pytest.approx(2 / 3)
    assert result["n_clusters"] == 2
    assert result["ci_low"] == 0
    assert result["ci_high"] == 1
    assert paired_bootstrap(left[::-1], right[::-1], iterations=100, seed=7) == result


def test_bootstrap_undefined_replicates_and_single_cluster_have_no_ci():
    left = [row("a", "g1"), row("b", "g2", proposed=False, correct=False)]
    result = paired_bootstrap(left, left, metric="unsupported_action_rate", iterations=100)
    assert result["undefined_count"] > 0
    assert result["ci_low"] is result["ci_high"] is None
    single = paired_bootstrap(left[:1], left[:1])
    assert single["n_clusters"] == 1
    assert single["ci_low"] is None


@pytest.mark.parametrize("right", [
    [row("different")], [row("a", "different")],
    [row("a", eligible=False, correct=False)],
])
def test_bootstrap_rejects_unpaired_cases_groups_and_eligibility(right):
    with pytest.raises(ValueError):
        paired_bootstrap([row("a")], right)


def test_duplicate_ids_and_invalid_parameters_rejected():
    with pytest.raises(ValueError):
        summarize([row("a"), row("a")])
    for value in (True, math.nan, -1, 2):
        with pytest.raises(ValueError):
            summarize([], value)
        with pytest.raises(ValueError):
            calibrate_threshold([], value)
    with pytest.raises(ValueError):
        paired_bootstrap([], [], iterations=0)
    with pytest.raises(ValueError):
        paired_bootstrap([], [], metric="accuracy")


@pytest.mark.parametrize("invalid", [[{}], [None], None])
def test_metrics_reject_non_outcome_inputs(invalid):
    for function in (summarize, risk_coverage_curve, calibrate_threshold):
        with pytest.raises(ValueError):
            function(invalid)
    with pytest.raises(ValueError):
        paired_bootstrap(invalid, [])


@pytest.mark.parametrize("iterations", [True, 1.5, -1, "100"])
def test_bootstrap_rejects_invalid_iteration_types(iterations):
    with pytest.raises(ValueError):
        paired_bootstrap([], [], iterations=iterations)


@pytest.mark.parametrize("seed", [True, 0.5, None, "0"])
def test_bootstrap_rejects_invalid_seed_types(seed):
    with pytest.raises(ValueError):
        paired_bootstrap([], [], seed=seed)


def test_coverage_excludes_ineligible_proposals_but_risk_counts_them():
    rows = [row("allowed", confidence=0.5),
            row("forbidden", eligible=False, correct=False, confidence=0.9)]
    curve = risk_coverage_curve(rows)
    assert [point["coverage"] for point in curve] == [0, 0, 1]
    assert [point["risk"] for point in curve] == [None, 1, 0.5]
    assert summarize(rows)["aurc_partial"] == 0.5
    assert calibrate_threshold(rows, 1)["threshold"] == 0.5


def test_bootstrap_different_case_order_and_threshold_are_paired():
    left = [row("a", "g1", confidence=0.4), row("b", "g2", confidence=0.9)]
    right = [row("b", "g2", confidence=0.9), row("a", "g1", confidence=0.9)]
    result = paired_bootstrap(left, right, metric="coverage", threshold=0.5, iterations=50)
    assert result["difference"] == 0.5
    assert result["undefined_count"] == 0
    assert paired_bootstrap(left[::-1], right, metric="coverage", threshold=0.5,
                            iterations=50) == result


def test_bootstrap_rejects_duplicates_and_bad_threshold():
    with pytest.raises(ValueError):
        paired_bootstrap([row("a"), row("a")], [row("a")])
    with pytest.raises(ValueError):
        paired_bootstrap([], [], threshold=math.nan)


def test_outcome_is_frozen():
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        row("a").correct = False
