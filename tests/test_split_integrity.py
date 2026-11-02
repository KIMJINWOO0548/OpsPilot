import hashlib
import json
import subprocess
import sys

from scripts.check_split_integrity import check


def item(case_id,split,source):
    return {'case_id':case_id,'split':split,'source_group_id':source,
            'document_revision_family':'rev-'+source,
            'source_hash':hashlib.sha256(source.encode()).hexdigest()}


def test_cross_split_document_family_caught():
    assert any('crosses splits' in error for error in check([
        item('a','train','s1'),item('b','holdout','s1')]))


def test_each_source_key_is_checked_independently():
    for key in ('source_group_id', 'document_revision_family', 'source_hash'):
        train = item('a', 'train', 's1')
        holdout = item('b', 'holdout', 's2')
        for other in ('source_group_id', 'document_revision_family', 'source_hash'):
            if other != key:
                train[other] = f'train-{other}'
                holdout[other] = f'holdout-{other}'
        if key == 'source_hash':
            train[key] = hashlib.sha256(b'same').hexdigest()
            holdout[key] = train[key]
        else:
            train[key] = holdout[key] = 'same-family'
        assert any(f'{key}=' in error and 'crosses splits' in error
                   for error in check([train, holdout]))


def test_disjoint_families_pass():
    assert not check([item('a','train','s1'),item('b','holdout','s2')])


def test_duplicate_ids_or_missing_source_fail():
    assert check([item('a','dev','s1'),item('a','dev','s2')])
    broken=item('b','holdout','s3')
    broken['source_hash']=''
    assert check([broken])


def test_invalid_rows_and_identifiers_fail_closed():
    assert check([])
    errors = check([None, {'case_id':' ', 'split':'train', 'source_group_id':'s',
                          'document_revision_family':'r', 'source_hash':'0' * 64},
                    item('valid', 'training', 's2')])
    assert any('row 1' in error for error in errors)
    assert any('case_id' in error for error in errors)
    assert any('split' in error for error in errors)


def test_identifiers_must_be_nonblank_strings_and_hashes_sha256():
    broken = item('a', 'train', 's1')
    broken['source_group_id'] = 3
    assert any('source_group_id' in error for error in check([broken]))
    broken = item('b', 'dev', 's2')
    broken['source_hash'] = 'g' * 64
    assert any('source_hash' in error for error in check([broken]))


def test_hash_case_is_normalized_when_checking_cross_split_leakage():
    train = item('a', 'train', 's1')
    holdout = item('b', 'holdout', 's2')
    holdout['source_hash'] = train['source_hash'].upper()
    assert any('source_hash' in error and 'crosses splits' in error
               for error in check([train, holdout]))


def test_surrounding_identifier_whitespace_cannot_bypass_split_checks():
    for key in ('case_id', 'source_group_id', 'document_revision_family'):
        train = item('a', 'train', 's1')
        holdout = item('b', 'holdout', 's2')
        holdout[key] = ' ' + train[key] + ' '
        assert check([train, holdout]), key


def test_cli_reports_malformed_json_without_traceback_or_pass(tmp_path):
    manifest = tmp_path / 'bad.jsonl'
    manifest.write_text('{bad json}\n', encoding='utf-8')
    result = subprocess.run(
        [sys.executable, '-X', 'utf8', 'scripts/check_split_integrity.py', str(manifest)],
        capture_output=True, text=True, encoding='utf-8')
    assert result.returncode != 0
    assert 'bad.jsonl' in result.stderr
    assert 'line 1' in result.stderr
    assert 'Traceback' not in result.stderr
    assert 'PASS' not in result.stdout


def test_cli_accepts_disjoint_train_dev_holdout_manifest(tmp_path):
    manifest = tmp_path / 'valid.jsonl'
    manifest.write_text('\n'.join(json.dumps(item(str(i), split, f's{i}'))
                                   for i, split in enumerate(('train', 'dev', 'holdout'))),
                        encoding='utf-8')
    result = subprocess.run(
        [sys.executable, '-X', 'utf8', 'scripts/check_split_integrity.py', str(manifest)],
        capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0
    assert result.stdout.startswith('PASS: 3 cases')
    assert not result.stderr
