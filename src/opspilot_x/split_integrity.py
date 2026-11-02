"""Shared source-family split validation."""
from collections import defaultdict
import re


def check(rows: list[dict]) -> list[str]:
    errors = []
    if not isinstance(rows, list) or not rows:
        return ['manifest must contain a non-empty list of rows']
    seen_case_ids = set()
    scopes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f'row {i}: expected an object')
            continue
        case_id = row.get('case_id')
        split = row.get('split')
        valid_case_id = isinstance(case_id, str) and bool(case_id) and case_id == case_id.strip()
        valid_split = isinstance(split, str) and split in {'train', 'dev', 'holdout'}
        if not valid_case_id:
            errors.append(f'row {i}: case_id must be a non-blank string without surrounding whitespace')
        elif case_id in seen_case_ids:
            errors.append(f'duplicate case_id: {case_id}')
        else:
            seen_case_ids.add(case_id)
        if not valid_split:
            errors.append(f'row {i}: split must be train, dev or holdout')
        for key in ('source_group_id', 'document_revision_family', 'source_hash'):
            value = row.get(key)
            if not isinstance(value, str) or not value or value != value.strip():
                errors.append(f'row {i}: {key} must be a non-blank string without surrounding whitespace')
            elif key == 'source_hash' and re.fullmatch(r'[0-9a-fA-F]{64}', value) is None:
                errors.append(f'row {i}: source_hash must be a SHA256 hex digest')
            elif valid_split:
                scopes[(key, value.lower() if key == 'source_hash' else value)].add(split)
    for (kind, value), splits in sorted(scopes.items()):
        if len(splits) > 1:
            errors.append(f'{kind}={value} crosses splits: {sorted(splits)}')
    return errors

