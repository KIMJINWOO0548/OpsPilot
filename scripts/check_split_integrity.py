"""Fail if independent train/dev/holdout sets share source families or source hashes.

Usage: python scripts/check_split_integrity.py evaluation/datasets/t2_manifest.jsonl
T0 smoke is deliberately exempt; it is NOT a research dataset.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from opspilot_x.split_integrity import check


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('manifest',type=Path)
    args=parser.parse_args()
    try:
        rows = []
        for line_number, line in enumerate(args.manifest.read_text(encoding='utf8').splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f'ERROR: {args.manifest}: line {line_number}: invalid JSON ({exc.msg})', file=sys.stderr)
                return 1
    except (OSError, UnicodeError) as exc:
        print(f'ERROR: {args.manifest}: {exc}', file=sys.stderr)
        return 1
    problems=check(rows)
    for problem in problems: print('ERROR:',problem)
    if problems: return 1
    print('PASS:',len(rows),'cases; source families, revision families and hashes are split-disjoint')
    return 0

if __name__=='__main__': raise SystemExit(main())
