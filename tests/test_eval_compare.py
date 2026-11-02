import hashlib
import json
import subprocess
import sys

import pytest

from test_evaluation_data import bundle, write_json


def experiment(tmp_path):
    dataset_path, _, _ = bundle(tmp_path)
    predictions = [{'case_id': 'c1', 'action': 'inspect_sensor',
                    'evidence_ids': ['s1'], 'confidence': 0.9}]
    prediction_path = tmp_path / 'predictions.jsonl'
    prediction_path.write_text(json.dumps(predictions[0]) + '\n', encoding='utf-8')
    conditions = {'provider': 'none', 'temperature': 0.0,
                  'model_id': 'none-fixture', 'model_revision': 'none',
                  'prompt_sha256': None, 'retrieval_k': 3, 'context_budget_tokens': 512,
                  'hardware': 'local-fixture-no-inference'}
    run = {'schema_version': 1, 'experiment_id': 'test-contract', 'split': 'dev',
           'dataset': {'path': dataset_path.name,
                       'sha256': hashlib.sha256(dataset_path.read_bytes()).hexdigest()},
           'dataset_commit': None, 'code_commit': None, 'seed': 7,
           'target_coverage': 0.7, 'spend_limit_usd': 0.0, 'bootstrap_iterations': 100,
           'baselines': {name: {
               'predictions': {'path': prediction_path.name,
                               'sha256': hashlib.sha256(prediction_path.read_bytes()).hexdigest()},
               'conditions': dict(conditions), 'implementation_status': 'fixture',
               'wall_seconds': 0.0, 'usd_cost_total': 0.0,
           } for name in ('B0', 'B2')}}
    path = tmp_path / 'experiment.json'
    write_json(path, run)
    return path, run


def cli(path, *args):
    return subprocess.run([sys.executable, '-X', 'utf8', 'scripts/eval_compare.py', str(path), *args],
                          capture_output=True, text=True, encoding='utf-8')


def test_dev_cli_writes_calibration_and_explicit_contract_report(tmp_path):
    path, _ = experiment(tmp_path)
    output = tmp_path / 'report.json'
    calibration = tmp_path / 'calibration.json'
    result = cli(path, '--output', str(output), '--calibration-out', str(calibration))
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['result_type'] == 'CONTRACT_CHECK_NOT_BENCHMARK'
    assert report['research_performance_claim_allowed'] is False
    assert report['missing_baselines'] == ['B1', 'B3', 'B4']
    assert report['baselines']['B0']['metrics']['coverage'] == 1
    assert report['paired']['B0->B2']['safe_completion']['ci_low'] is None
    assert json.loads(calibration.read_text())['split'] == 'dev'


def test_different_budgets_and_holdout_calibration_rejected(tmp_path):
    path, run = experiment(tmp_path)
    run['baselines']['B2']['conditions']['context_budget_tokens'] = 1024
    write_json(path, run)
    result = cli(path)
    assert result.returncode != 0 and 'conditions' in result.stderr
    assert 'Traceback' not in result.stderr
    run['baselines']['B2']['conditions']['context_budget_tokens'] = 512
    run['split'] = 'holdout'
    write_json(path, run)
    result = cli(path, '--calibration-out', str(tmp_path / 'invalid.json'))
    assert result.returncode != 0 and 'holdout' in result.stderr


def test_all_abstain_cannot_meet_target_coverage(tmp_path):
    path, run = experiment(tmp_path)
    pred = tmp_path / 'abstain.jsonl'
    pred.write_text(json.dumps({'case_id': 'c1', 'action': None,
                               'evidence_ids': [], 'confidence': 0.0}) + '\n')
    run['baselines']['B2']['predictions'] = {
        'path': pred.name, 'sha256': hashlib.sha256(pred.read_bytes()).hexdigest()}
    write_json(path, run)
    result = cli(path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    b2 = report['baselines']['B2']
    assert not b2['calibration']['reached']
    assert b2['metrics']['coverage'] == 0
    assert b2['metrics']['unsupported_action_rate'] is None
    assert not report['paired']['B0->B2']['risk_comparable_at_matched_coverage']


def test_report_cannot_overwrite_input(tmp_path):
    path, _ = experiment(tmp_path)
    original = path.read_bytes()
    result = cli(path, '--output', str(path))
    assert result.returncode != 0
    assert 'exists' in result.stderr
    assert path.read_bytes() == original


def test_holdout_uses_frozen_dev_threshold_and_refuses_changed_conditions(tmp_path):
    path, run = experiment(tmp_path)
    manifest_path = tmp_path / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    holdout_source = tmp_path / 'held-source.txt'
    holdout_source.write_text('Unrelated optical monitoring requirements for vessel omega.', encoding='utf-8')
    manifest['sources'].append(dict(manifest['sources'][0], source_id='h1', source_group_id='hgroup',
                                    document_revision_family='hrev', split='holdout',
                                    path=holdout_source.name,
                                    sha256=hashlib.sha256(holdout_source.read_bytes()).hexdigest()))
    case = json.loads((tmp_path / 'dev.jsonl').read_text(encoding='utf-8'))
    case.update(case_id='held-case', source_ids=['h1'], gold_evidence_ids=['h1'])
    second_case = dict(case, case_id='held-case-2')
    held_labels = tmp_path / 'holdout.jsonl'
    held_labels.write_text(json.dumps(case) + '\n' + json.dumps(second_case) + '\n', encoding='utf-8')
    manifest['splits']['holdout'] = {'path': held_labels.name, 'case_ids': ['held-case', 'held-case-2'],
                                    'sha256': hashlib.sha256(held_labels.read_bytes()).hexdigest()}
    write_json(manifest_path, manifest)
    run['dataset']['sha256'] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    write_json(path, run)
    calibration_path = tmp_path / 'dev-calibration.json'
    result = cli(path, '--calibration-out', str(calibration_path))
    assert result.returncode == 0, result.stderr
    held_pred = tmp_path / 'held-predictions.jsonl'
    held_pred.write_text(json.dumps({'case_id': 'held-case', 'action': 'inspect_sensor',
                                    'evidence_ids': ['h1'], 'confidence': 0.1}) + '\n'
                        + json.dumps({'case_id': 'held-case-2', 'action': 'inspect_sensor',
                                      'evidence_ids': ['h1'], 'confidence': 0.9}) + '\n')
    run['split'] = 'holdout'
    run['calibration'] = {'path': calibration_path.name,
                          'sha256': hashlib.sha256(calibration_path.read_bytes()).hexdigest()}
    for b in run['baselines'].values():
        b['predictions'] = {'path': held_pred.name, 'sha256': hashlib.sha256(held_pred.read_bytes()).hexdigest()}
    write_json(path, run)
    assert cli(path).returncode != 0
    result = cli(path, '--allow-holdout')
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['baselines']['B0']['calibration']['threshold'] == 0.9
    assert report['baselines']['B0']['metrics']['coverage'] == 0.5
    assert not report['paired']['B0->B2']['risk_comparable_at_matched_coverage']
    for b in run['baselines'].values():
        b['conditions']['retrieval_k'] = 4
    write_json(path, run)
    result = cli(path, '--allow-holdout')
    assert result.returncode != 0 and 'calibration' in result.stderr


def test_submitted_cost_cannot_exceed_declared_budget(tmp_path):
    path, run = experiment(tmp_path)
    run['baselines']['B2']['usd_cost_total'] = 0.01
    write_json(path, run)
    result = cli(path)
    assert result.returncode != 0 and 'spend_limit' in result.stderr


@pytest.mark.parametrize('invalid', [
    {'reached': False}, {'threshold': float('nan')},
    {'threshold': -0.1}, {'target_coverage': 0.6},
])
def test_invalid_calibration_is_rejected_before_holdout_loader(tmp_path, monkeypatch, invalid):
    from scripts import eval_compare
    path, run = experiment(tmp_path)
    _, calibration = eval_compare.compare(path)
    calibration['baselines']['B0'].update(invalid)
    calibration_path = tmp_path / 'invalid-calibration.json'
    write_json(calibration_path, calibration)
    run['split'] = 'holdout'
    run['calibration'] = {'path': calibration_path.name,
                          'sha256': hashlib.sha256(calibration_path.read_bytes()).hexdigest()}
    write_json(path, run)

    def forbidden_loader(*args, **kwargs):
        raise AssertionError('holdout loader was called before validation')

    monkeypatch.setattr(eval_compare, 'load_dataset', forbidden_loader)
    with pytest.raises(ValueError):
        eval_compare.compare(path, allow_holdout=True)


def test_research_commits_required_before_label_loader(tmp_path, monkeypatch):
    from scripts import eval_compare
    path, run = experiment(tmp_path)
    manifest_path = tmp_path / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest.update(purpose='research', label_review='independent')
    write_json(manifest_path, manifest)
    run['dataset']['sha256'] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    write_json(path, run)

    def forbidden_loader(*args, **kwargs):
        raise AssertionError('labels opened without research metadata')

    monkeypatch.setattr(eval_compare, 'load_dataset', forbidden_loader)
    with pytest.raises(ValueError, match='commit'):
        eval_compare.compare(path)
