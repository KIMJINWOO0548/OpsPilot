"""로컬 평가용 지표: 임계값 선택과 출처군 단위 paired 불확실성을 분리한다."""

import math
import random
from dataclasses import dataclass
from typing import Iterable


def _score(value, name):
    if type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number in [0, 1]")


@dataclass(frozen=True)
class Outcome:
    case_id: str
    source_group_id: str
    eligible: bool
    proposed: bool
    correct: bool
    confidence: float
    leaked: bool = False

    def __post_init__(self):
        for name in ("case_id", "source_group_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"{name} must be a nonempty trimmed string")
        for name in ("eligible", "proposed", "correct", "leaked"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be bool")
        _score(self.confidence, "confidence")
        if self.correct and not (self.eligible and self.proposed):
            raise ValueError("correct requires an eligible proposal")


def _rows(outcomes):
    try:
        rows = list(outcomes)
    except TypeError as exc:
        raise ValueError("outcomes must be an iterable of Outcome instances") from exc
    if any(not isinstance(row, Outcome) for row in rows):
        raise ValueError("outcomes must contain Outcome instances")
    if len({row.case_id for row in rows}) != len(rows):
        raise ValueError("duplicate case_id")
    return rows


def _counts(rows, threshold):
    proposals = [row for row in rows if row.proposed and row.confidence >= threshold]
    eligible = sum(row.eligible for row in rows)
    correct = sum(row.correct for row in proposals)
    return {
        "n_cases": len(rows),
        "n_eligible": eligible,
        "n_proposed": len(proposals),
        "n_correct": correct,
        "coverage": sum(row.eligible for row in proposals) / eligible if eligible else None,
        "proposal_rate": len(proposals) / len(rows) if rows else None,
        "unsupported_action_rate": (len(proposals) - correct) / len(proposals)
        if proposals else None,
        "safe_completion": correct / eligible if eligible else None,
        "leak_count": sum(row.leaked for row in rows),
    }


def risk_coverage_curve(outcomes: Iterable[Outcome]) -> list[dict]:
    """동점 confidence를 함께 선택한다. 첫 점은 제안이 없는 상태다."""
    rows = _rows(outcomes)
    curve = [{"threshold": None, "coverage": 0 if any(r.eligible for r in rows) else None,
              "risk": None}]
    for threshold in sorted({row.confidence for row in rows if row.proposed}, reverse=True):
        counts = _counts(rows, threshold)
        curve.append({"threshold": threshold, "coverage": counts["coverage"],
                      "risk": counts["unsupported_action_rate"]})
    return curve


def summarize(outcomes: Iterable[Outcome], threshold: float = 0.0) -> dict:
    """부분 AURC는 관측 가능한 coverage 구간의 오른쪽 계단 면적이다."""
    _score(threshold, "threshold")
    rows = _rows(outcomes)
    result = _counts(rows, threshold)
    curve = risk_coverage_curve(rows)
    result["max_attainable_coverage"] = _counts(rows, 0)["coverage"]
    result["aurc_partial"] = (
        sum((right["coverage"] - left["coverage"]) * right["risk"]
            for left, right in zip(curve, curve[1:]))
        if len(curve) > 1 and result["n_eligible"] else None
    )
    return result


def calibrate_threshold(outcomes: Iterable[Outcome], target_coverage: float = 0.7,
                        *, split: str = "dev") -> dict:
    """dev의 eligibility/proposal/confidence만 사용하며 정오답은 보지 않는다."""
    _score(target_coverage, "target_coverage")
    if split != "dev":
        raise ValueError("threshold calibration requires dev split")
    rows = _rows(outcomes)
    eligible = sum(row.eligible for row in rows)
    result = {"threshold": None, "target_coverage": target_coverage,
              "achieved_coverage": 0 if eligible else None,
              "reached": False, "tie_overrun": None}
    # threshold=1이 confidence=1 동점까지 포함하므로 별도의 abstain sentinel은 선택하지 않는다.
    thresholds = {row.confidence for row in rows if row.eligible and row.proposed}
    for threshold in sorted(thresholds | {1.0}, reverse=True):
        coverage = (sum(row.eligible and row.proposed and row.confidence >= threshold
                        for row in rows) / eligible if eligible else None)
        result["achieved_coverage"] = coverage
        if coverage is not None and coverage >= target_coverage:
            result.update(threshold=threshold, reached=True,
                          tie_overrun=coverage - target_coverage)
            break
    return result


def _percentile(values, fraction):
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def paired_bootstrap(left: Iterable[Outcome], right: Iterable[Outcome],
                     metric: str = "safe_completion", *, iterations: int = 1000,
                     seed: int = 0, threshold: float = 0.0) -> dict:
    """출처군을 복원 추출하고 동일 사례 쌍의 right-left 차이를 계산한다."""
    if metric not in ("coverage", "safe_completion", "unsupported_action_rate"):
        raise ValueError("unsupported bootstrap metric")
    if type(iterations) is not int or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    _score(threshold, "threshold")
    left_rows, right_rows = _rows(left), _rows(right)
    left_by_id = {row.case_id: row for row in left_rows}
    right_by_id = {row.case_id: row for row in right_rows}
    if left_by_id.keys() != right_by_id.keys():
        raise ValueError("paired case IDs must match")
    groups = {}
    for case_id in sorted(left_by_id):
        a, b = left_by_id[case_id], right_by_id[case_id]
        if (a.source_group_id, a.eligible) != (b.source_group_id, b.eligible):
            raise ValueError("paired source groups and eligibility must match")
        groups.setdefault(a.source_group_id, []).append((a, b))

    def difference(pairs):
        a = _counts([pair[0] for pair in pairs], threshold)[metric]
        b = _counts([pair[1] for pair in pairs], threshold)[metric]
        return b - a if a is not None and b is not None else None

    group_ids = sorted(groups)
    observed = difference([pair for group in group_ids for pair in groups[group]])
    generator = random.Random(seed)
    samples = []
    undefined = 0
    for _ in range(iterations):
        pairs = [pair for group in generator.choices(group_ids, k=len(group_ids))
                 for pair in groups[group]] if group_ids else []
        value = difference(pairs)
        if value is None:
            undefined += 1
        else:
            samples.append(value)
    result = {"metric": metric, "difference": observed, "n_clusters": len(groups),
              "iterations": iterations, "seed": seed, "undefined_count": undefined,
              "ci_low": None, "ci_high": None}
    if len(groups) >= 2 and not undefined and observed is not None:
        samples.sort()
        result.update(ci_low=_percentile(samples, 0.025),
                      ci_high=_percentile(samples, 0.975))
    return result
