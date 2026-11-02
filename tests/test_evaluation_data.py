import hashlib
import json

import pytest

from opspilot_x.evaluation_data import load_dataset, score_predictions


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def bundle(tmp_path):
    text = 'Approved pressure sensor inspection instruction for pump alpha.'
    source_path = tmp_path / 'source.txt'
    source_path.write_text(text, encoding='utf-8')
    source = {
        'source_id': 's1', 'source_group_id': 'g1', 'document_revision_family': 'r1',
        'split': 'dev', 'path': 'source.txt',
        'sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(),
        'source_ref': 'synthetic://test/alpha', 'license': 'LicenseRef-Project-Synthetic',
        'synthetic': True, 'tenant': 'demo', 'team': 'team_a',
        'readable_roles': ['engineer'], 'valid_from': '2026-01-01T00:00:00Z',
        'valid_to': None, 'recorded_at': '2026-01-02T00:00:00Z',
    }
    case = {
        'case_id': 'c1', 'question': 'Which inspection is supported?',
        'actor_scope': {'user_id': 'reviewer', 'tenant': 'demo', 'team': 'team_a', 'role': 'engineer'},
        'effective_at': '2026-02-01T00:00:00Z', 'known_as_of': '2026-02-01T00:00:00Z',
        'source_ids': ['s1'], 'gold_evidence_ids': ['s1'], 'expected_state': 'SUPPORTED',
        'permitted_action': 'inspect_sensor', 'gold_reason': 'The approved instruction supports this action.',
        'annotator_id': 'author', 'review_status': 'author_only',
    }
    (tmp_path / 'dev.jsonl').write_text(json.dumps(case) + '\n', encoding='utf-8')
    manifest = {
        'schema_version': 1, 'dataset_id': 'test-contract', 'track': 'T2',
        'purpose': 'contract_only', 'label_review': 'author_only',
        'sources': [source],
        'splits': {'dev': {'path': 'dev.jsonl', 'case_ids': ['c1'],
                           'sha256': hashlib.sha256((tmp_path / 'dev.jsonl').read_bytes()).hexdigest()}},
    }
    path = tmp_path / 'manifest.json'
    write_json(path, manifest)
    return path, manifest, case


def rewrite_cases(path, manifest, cases):
    labels = path.parent / 'dev.jsonl'
    labels.write_text(''.join(json.dumps(c) + '\n' for c in cases), encoding='utf-8')
    manifest['splits']['dev']['sha256'] = hashlib.sha256(labels.read_bytes()).hexdigest()
    manifest['splits']['dev']['case_ids'] = [c['case_id'] for c in cases]
    write_json(path, manifest)


def test_valid_source_and_gold_scoring(tmp_path):
    path, _, _ = bundle(tmp_path)
    dataset = load_dataset(path)
    outcomes = score_predictions(dataset, [
        {'case_id': 'c1', 'action': 'inspect_sensor', 'evidence_ids': ['s1'], 'confidence': 0.9}])
    assert outcomes[0].eligible and outcomes[0].proposed and outcomes[0].correct
    assert outcomes[0].source_group_id == 'g1'
    assert dataset.purpose == 'contract_only'


def test_source_tampering_and_path_escape_rejected(tmp_path):
    path, manifest, _ = bundle(tmp_path)
    (tmp_path / 'source.txt').write_text('tampered', encoding='utf-8')
    with pytest.raises(ValueError, match='SHA256'):
        load_dataset(path)
    manifest['sources'][0]['path'] = '../outside.txt'
    write_json(path, manifest)
    with pytest.raises(ValueError, match='inside'):
        load_dataset(path)


def test_t0_cannot_be_promoted_and_research_requires_review(tmp_path):
    path, manifest, _ = bundle(tmp_path)
    manifest['track'] = 'T0'
    write_json(path, manifest)
    with pytest.raises(ValueError, match='T2'):
        load_dataset(path)
    manifest['track'] = 'T2'
    manifest['purpose'] = 'research'
    write_json(path, manifest)
    with pytest.raises(ValueError, match='independent'):
        load_dataset(path)


def test_cross_split_near_duplicate_with_distinct_hashes_rejected(tmp_path):
    path, manifest, _ = bundle(tmp_path)
    text = 'one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'
    (tmp_path / 'source.txt').write_text(text, encoding='utf-8')
    manifest['sources'][0]['sha256'] = hashlib.sha256((tmp_path / 'source.txt').read_bytes()).hexdigest()
    (tmp_path / 'holdout.txt').write_text(text + ' twentyone', encoding='utf-8')
    source = dict(manifest['sources'][0], source_id='s2', source_group_id='g2',
                  document_revision_family='r2', split='holdout', path='holdout.txt',
                  sha256=hashlib.sha256((tmp_path / 'holdout.txt').read_bytes()).hexdigest())
    manifest['sources'].append(source)
    manifest['splits']['holdout'] = {'path': 'unopened.jsonl', 'sha256': '0' * 64, 'case_ids': ['held']}
    write_json(path, manifest)
    with pytest.raises(ValueError, match='near-duplicate'):
        load_dataset(path)


def test_dev_does_not_open_holdout_labels_and_holdout_requires_opt_in(tmp_path):
    path, manifest, _ = bundle(tmp_path)
    manifest['splits']['holdout'] = {'path': 'does-not-exist.jsonl', 'sha256': '0' * 64, 'case_ids': ['held']}
    write_json(path, manifest)
    assert len(load_dataset(path).cases) == 1
    with pytest.raises(ValueError, match='holdout'):
        load_dataset(path, split='holdout')


@pytest.mark.parametrize('change', [
    {'valid_to': '2025-01-01T00:00:00Z'}, {'recorded_at': '2026-01-02'},
])
def test_invalid_source_time_contract_rejected(tmp_path, change):
    path, manifest, _ = bundle(tmp_path)
    manifest['sources'][0].update(change)
    write_json(path, manifest)
    with pytest.raises(ValueError):
        load_dataset(path)


@pytest.mark.parametrize('field,value', [('team', 'secret_team'), ('recorded_at', '2026-03-01T00:00:00Z')])
def test_inaccessible_or_future_gold_cannot_be_scored_as_supported(tmp_path, field, value):
    path, manifest, _ = bundle(tmp_path)
    manifest['sources'][0][field] = value
    write_json(path, manifest)
    with pytest.raises(ValueError, match='gold'):
        load_dataset(path)


def test_predictions_require_complete_ids_and_evidence_support(tmp_path):
    path, _, _ = bundle(tmp_path)
    data = load_dataset(path)
    with pytest.raises(ValueError, match='case'):
        score_predictions(data, [])
    row = {'case_id': 'c1', 'action': 'inspect_sensor', 'evidence_ids': [], 'confidence': 0.8}
    assert not score_predictions(data, [row])[0].correct
    row['evidence_ids'] = ['hallucinated']
    assert not score_predictions(data, [row])[0].correct


def test_abstain_does_not_erase_unauthorized_citation(tmp_path):
    path, manifest, case = bundle(tmp_path)
    source = dict(manifest['sources'][0], source_id='hidden', team='secret_team')
    manifest['sources'].append(source)
    case['source_ids'].append('hidden')
    rewrite_cases(path, manifest, [case])
    result = score_predictions(load_dataset(path), [
        {'case_id': 'c1', 'action': None, 'evidence_ids': ['hidden'], 'confidence': 0.0}])[0]
    assert result.leaked and not result.proposed and not result.correct


def test_malformed_labels_fail_with_line_number(tmp_path):
    path, manifest, _ = bundle(tmp_path)
    labels = tmp_path / 'dev.jsonl'
    labels.write_text('\n{bad json}\n', encoding='utf-8')
    manifest['splits']['dev']['sha256'] = hashlib.sha256(labels.read_bytes()).hexdigest()
    write_json(path, manifest)
    with pytest.raises(ValueError, match='line 2'):
        load_dataset(path)


@pytest.mark.parametrize('entry', [None, [], {}, {'path': 1, 'sha256': '0' * 64}])
def test_malformed_snapshot_reference_has_controlled_error(tmp_path, entry):
    path, manifest, _ = bundle(tmp_path)
    manifest['splits']['dev'] = entry
    write_json(path, manifest)
    with pytest.raises(ValueError, match='snapshot'):
        load_dataset(path)


def test_case_ids_must_be_unique_across_split_metadata_without_opening_labels(tmp_path):
    path, manifest, _ = bundle(tmp_path)
    manifest['splits']['dev']['case_ids'] = ['c1']
    manifest['splits']['holdout'] = {'path': 'unopened.jsonl', 'sha256': '0' * 64, 'case_ids': ['c1']}
    write_json(path, manifest)
    with pytest.raises(ValueError, match='case IDs'):
        load_dataset(path)
