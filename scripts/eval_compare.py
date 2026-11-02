"""Score immutable prediction files; no model invocation or benchmark claim."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
from dataclasses import replace
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from opspilot_x.evaluation_data import checked_bytes, load_dataset, read_jsonl, score_predictions
from opspilot_x.evaluation_metrics import (
    calibrate_threshold, paired_bootstrap, risk_coverage_curve, summarize,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Artifact(StrictModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r'^[a-fA-F0-9]{64}$')


class Conditions(StrictModel):
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    temperature: float = Field(ge=0, le=2, allow_inf_nan=False)
    prompt_sha256: str | None = Field(pattern=r'^[a-fA-F0-9]{64}$')
    retrieval_k: int = Field(gt=0)
    context_budget_tokens: int = Field(gt=0)
    hardware: str = Field(min_length=1)


class Baseline(StrictModel):
    predictions: Artifact
    conditions: Conditions
    implementation_status: Literal['fixture', 'implemented']
    wall_seconds: float = Field(ge=0, allow_inf_nan=False)
    usd_cost_total: float = Field(ge=0, allow_inf_nan=False)


class Experiment(StrictModel):
    schema_version: Literal[1]
    experiment_id: str = Field(min_length=1)
    split: Literal['dev', 'holdout']
    dataset: Artifact
    dataset_commit: str | None
    code_commit: str | None
    seed: int
    target_coverage: float = Field(gt=0, le=1, allow_inf_nan=False)
    spend_limit_usd: float = Field(ge=0, allow_inf_nan=False)
    bootstrap_iterations: int = Field(ge=1, le=100000)
    baselines: dict[Literal['B0', 'B1', 'B2', 'B3', 'B4'], Baseline]
    calibration: Artifact | None = None


class CalibrationChoice(StrictModel):
    threshold: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    target_coverage: float = Field(gt=0, le=1, allow_inf_nan=False)
    achieved_coverage: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    reached: bool
    tie_overrun: float | None = Field(ge=0, le=1, allow_inf_nan=False)


class Calibration(StrictModel):
    schema_version: Literal[1]
    split: Literal['dev']
    dataset_manifest_sha256: str
    conditions_sha256: str
    scorer_sha256: dict[str, str]
    target_coverage: float = Field(gt=0, le=1, allow_inf_nan=False)
    baselines: dict[str, CalibrationChoice]


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def compare(path: Path, *, allow_holdout=False):
    raw = path.read_bytes()
    run = Experiment.model_validate_json(raw)
    if len(run.baselines) < 2:
        raise ValueError('at least two baseline prediction files are required')
    if sum(b.usd_cost_total for b in run.baselines.values()) > run.spend_limit_usd:
        raise ValueError('submitted costs exceed spend_limit_usd')
    conditions = [b.conditions.model_dump() for b in run.baselines.values()]
    if any(c != conditions[0] for c in conditions[1:]):
        raise ValueError('baseline conditions must match: model, prompt, top-k, budget, hardware')
    if run.split == 'holdout' and not allow_holdout:
        raise ValueError('holdout requires explicit final-evaluation opt-in')
    dataset_bytes = checked_bytes(path.parent, run.dataset.model_dump())
    dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()
    dataset_metadata = json.loads(dataset_bytes)
    if not isinstance(dataset_metadata, dict):
        raise ValueError('dataset manifest must be an object')
    if dataset_metadata.get('purpose') == 'research' and any(
            value is None or re.fullmatch(r'[a-fA-F0-9]{40}|[a-fA-F0-9]{64}', value) is None
            for value in (run.code_commit, run.dataset_commit)):
        raise ValueError('research runs require pinned code_commit and dataset_commit')
    names = sorted(run.baselines)
    conditions_hash = hashlib.sha256(json.dumps(conditions[0], sort_keys=True).encode()).hexdigest()
    root = Path(__file__).resolve().parents[1]
    scorer_hashes = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in (
        'scripts/eval_compare.py', 'src/opspilot_x/evaluation_data.py',
        'src/opspilot_x/evaluation_metrics.py', 'src/opspilot_x/split_integrity.py')}
    calibration = {'schema_version': 1, 'split': 'dev',
                   'dataset_manifest_sha256': dataset_hash,
                   'conditions_sha256': conditions_hash, 'scorer_sha256': scorer_hashes,
                   'target_coverage': run.target_coverage, 'baselines': {}}
    if run.split == 'holdout':
        if run.calibration is None:
            raise ValueError('holdout requires a dev calibration artifact')
        calibration = Calibration.model_validate_json(
            checked_bytes(path.parent, run.calibration.model_dump())).model_dump()
        if (calibration.get('split') != 'dev'
                or calibration.get('dataset_manifest_sha256') != dataset_hash
                or calibration.get('conditions_sha256') != conditions_hash
                or calibration.get('scorer_sha256') != scorer_hashes
                or calibration.get('target_coverage') != run.target_coverage
                or set(calibration.get('baselines', {})) != set(names)):
            raise ValueError('holdout calibration does not match dataset, conditions or baselines')
        for name, choice in calibration['baselines'].items():
            if (not choice['reached'] or choice['threshold'] is None
                    or choice['target_coverage'] != run.target_coverage
                    or choice['achieved_coverage'] is None
                    or choice['achieved_coverage'] < run.target_coverage):
                raise ValueError(f'{name}: valid reached dev calibration required before holdout access')
    dataset = load_dataset(path.parent / run.dataset.path, run.split, allow_holdout=allow_holdout)
    results, filtered = {}, {}
    for name in names:
        baseline = run.baselines[name]
        predictions = read_jsonl(checked_bytes(path.parent, baseline.predictions.model_dump()))
        outcomes = score_predictions(dataset, predictions)
        if run.split == 'dev':
            choice = calibrate_threshold(outcomes, run.target_coverage, split='dev')
            calibration['baselines'][name] = choice
        else:
            choice = calibration['baselines'][name]
        threshold = choice['threshold'] if choice['reached'] else 0.0
        metrics = summarize(outcomes, threshold)
        filtered[name] = [replace(o, proposed=o.proposed and o.confidence >= threshold,
                                  correct=o.correct and o.confidence >= threshold) for o in outcomes]
        results[name] = {'implementation_status': baseline.implementation_status,
                         'calibration': choice, 'metrics': metrics,
                         'risk_coverage_curve': risk_coverage_curve(outcomes),
                         'submitted_wall_seconds': baseline.wall_seconds,
                         'submitted_usd_cost_total': baseline.usd_cost_total,
                         'predictions_sha256': baseline.predictions.sha256}
    paired = {}
    for left, right in combinations(names, 2):
        a, b = results[left], results[right]
        matched = (a['calibration']['reached'] and b['calibration']['reached']
                   and a['metrics']['coverage'] is not None
                   and a['metrics']['coverage'] >= run.target_coverage
                   and a['metrics']['coverage'] == b['metrics']['coverage'])
        entry = {'risk_comparable_at_matched_coverage': matched}
        for metric in ('coverage', 'safe_completion', 'unsupported_action_rate'):
            entry[metric] = (paired_bootstrap(filtered[left], filtered[right], metric=metric,
                                             iterations=run.bootstrap_iterations, seed=run.seed)
                             if metric != 'unsupported_action_rate' or matched else None)
        paired[f'{left}->{right}'] = entry
    report = {
        'schema_version': 1,
        'result_type': ('CONTRACT_CHECK_NOT_BENCHMARK' if dataset.purpose == 'contract_only'
                        else 'OFFLINE_EVALUATION_REQUIRES_INDEPENDENT_REVIEW'),
        'research_performance_claim_allowed': False,
        'warning': 'Input prediction files were scored; no models or external benchmarks were run.',
        'experiment_id': run.experiment_id, 'split': run.split,
        'experiment_sha256': hashlib.sha256(raw).hexdigest(),
        'dataset_manifest_sha256': dataset.manifest_sha256,
        'dataset_commit': run.dataset_commit, 'code_commit': run.code_commit,
        'scorer_sha256': scorer_hashes, 'spend_limit_usd': run.spend_limit_usd,
        'conditions': conditions[0], 'seed': run.seed,
        'executed_at_utc': datetime.now(timezone.utc).isoformat(),
        'scorer_environment': {'python': platform.python_version(), 'platform': platform.platform()},
        'missing_baselines': [f'B{i}' for i in range(5) if f'B{i}' not in names],
        'baselines': results, 'paired': paired,
    }
    return report, calibration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--calibration-out', type=Path)
    parser.add_argument('--allow-holdout', action='store_true')
    args = parser.parse_args()
    try:
        targets = [p.resolve() for p in (args.output, args.calibration_out) if p]
        if len(set(targets)) != len(targets) or any(p.exists() for p in targets):
            raise ValueError('output path already exists or output paths overlap')
        if args.calibration_out:
            doc = json.loads(args.experiment.read_bytes())
            if doc.get('split') != 'dev':
                raise ValueError('holdout cannot write calibration; calibrate only on dev')
        report, calibration = compare(args.experiment.resolve(), allow_holdout=args.allow_holdout)
        if args.calibration_out:
            write_new(args.calibration_out, calibration)
        if args.output:
            write_new(args.output, report)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
