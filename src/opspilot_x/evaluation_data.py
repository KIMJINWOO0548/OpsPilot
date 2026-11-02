"""Validate local evaluation snapshots before reading labels or scoring predictions."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .evaluation_metrics import Outcome
from .schema import Actor, Status
from .split_integrity import check


class Source(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source_id: str
    source_group_id: str
    document_revision_family: str
    split: Literal['train', 'dev', 'holdout']
    path: str
    sha256: str
    source_ref: str
    license: str
    synthetic: bool
    tenant: str
    team: str
    readable_roles: list[Literal['viewer', 'engineer', 'approver']]
    valid_from: datetime
    valid_to: datetime | None
    recorded_at: datetime

    @field_validator('valid_from', 'valid_to', 'recorded_at', mode='before')
    @classmethod
    def timestamp(cls, value):
        if value is None:
            return value
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('timestamps must include a timezone')
        return value

    @model_validator(mode='after')
    def integrity(self):
        for key, value in self.model_dump().items():
            if isinstance(value, str) and (not value or value != value.strip()):
                raise ValueError(f'{key} must be a nonempty trimmed string')
        if re.fullmatch(r'[0-9a-fA-F]{64}', self.sha256) is None:
            raise ValueError('source SHA256 must be 64 hex characters')
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError('valid_to must be after valid_from')
        if not self.readable_roles:
            raise ValueError('readable_roles must not be empty')
        return self


class Case(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    case_id: str
    question: str
    actor_scope: Actor
    effective_at: datetime
    known_as_of: datetime
    source_ids: list[str]
    gold_evidence_ids: list[str]
    expected_state: Status
    permitted_action: str | None
    gold_reason: str
    annotator_id: str
    review_status: Literal['author_only', 'independent']

    @field_validator('effective_at', 'known_as_of', mode='before')
    @classmethod
    def timestamp(cls, value):
        return Source.timestamp(value)

    @model_validator(mode='after')
    def integrity(self):
        for key in ('case_id', 'question', 'gold_reason', 'annotator_id'):
            value = getattr(self, key)
            if not value or value != value.strip():
                raise ValueError(f'{key} must be a nonempty trimmed string')
        if not self.source_ids or len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError('source_ids must be nonempty and unique')
        if len(set(self.gold_evidence_ids)) != len(self.gold_evidence_ids):
            raise ValueError('gold_evidence_ids must be unique')
        if not set(self.gold_evidence_ids) <= set(self.source_ids):
            raise ValueError('gold evidence must belong to case sources')
        if self.expected_state == 'SUPPORTED':
            if not self.permitted_action or not self.gold_evidence_ids:
                raise ValueError('SUPPORTED requires permitted action and gold evidence')
        elif self.permitted_action is not None:
            raise ValueError('non-SUPPORTED cases cannot permit actions')
        if self.permitted_action is not None and self.permitted_action != self.permitted_action.strip():
            raise ValueError('permitted_action must be trimmed')
        if self.expected_state == 'CONFLICT' and len(self.gold_evidence_ids) < 2:
            raise ValueError('CONFLICT requires at least two gold evidence sources')
        return self


@dataclass
class Dataset:
    dataset_id: str
    manifest_sha256: str
    split: str
    purpose: str
    sources: dict[str, Source]
    cases: list[Case]


def snapshot_path(root: Path, entry: dict) -> Path:
    if (not isinstance(entry, dict) or not isinstance(entry.get('path'), str)
            or not entry['path'] or not isinstance(entry.get('sha256'), str)
            or re.fullmatch(r'[a-fA-F0-9]{64}', entry['sha256']) is None):
        raise ValueError('snapshot reference requires a path and SHA256')
    path = (root / entry['path']).resolve()
    if Path(entry['path']).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError('snapshot paths must stay inside the manifest directory')
    return path


def checked_bytes(root: Path, entry: dict) -> bytes:
    """Resolve before opening so traversal and symlinks cannot escape the snapshot."""
    path = snapshot_path(root, entry)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f'cannot read snapshot {entry["path"]}: {exc}') from exc
    digest = entry.get('sha256')
    if not isinstance(digest, str) or hashlib.sha256(data).hexdigest() != digest.lower():
        raise ValueError(f'SHA256 mismatch: {entry["path"]}')
    return data


def read_jsonl(data: bytes) -> list[dict]:
    rows = []
    try:
        for number, line in enumerate(data.decode('utf-8').splitlines(), 1):
            if line.strip():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f'invalid JSON at line {number}') from exc
                if not isinstance(row, dict):
                    raise ValueError(f'expected object at line {number}')
                rows.append(row)
    except UnicodeError as exc:
        raise ValueError('snapshot must be UTF-8') from exc
    return rows


def authorized(source: Source, case: Case) -> bool:
    actor = case.actor_scope
    return (source.tenant == actor.tenant and source.team == actor.team
            and actor.role in source.readable_roles)


def available(source: Source, case: Case) -> bool:
    return (authorized(source, case) and source.recorded_at <= case.known_as_of
            and source.valid_from <= case.effective_at
            and (source.valid_to is None or case.effective_at < source.valid_to))


def load_dataset(manifest: str | Path, split: str = 'dev', *, allow_holdout=False) -> Dataset:
    if split not in ('train', 'dev', 'holdout'):
        raise ValueError('invalid split')
    if split == 'holdout' and not allow_holdout:
        raise ValueError('holdout labels require explicit final-evaluation opt-in')
    path = Path(manifest).resolve()
    try:
        raw = path.read_bytes()
        doc = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'cannot read manifest: {exc}') from exc
    if not isinstance(doc, dict) or doc.get('schema_version') != 1 or doc.get('track') != 'T2':
        raise ValueError('schema_version 1 and track T2 are required; T0 is not research data')
    if doc.get('purpose') not in ('contract_only', 'research'):
        raise ValueError('purpose must be contract_only or research')
    if doc['purpose'] == 'research' and doc.get('label_review') != 'independent':
        raise ValueError('research requires independent label review')
    if not isinstance(doc.get('dataset_id'), str) or not doc['dataset_id'].strip():
        raise ValueError('dataset_id is required')
    if not isinstance(doc.get('sources'), list) or not doc['sources']:
        raise ValueError('sources must not be empty')
    sources = {}
    texts = []
    for record in doc['sources']:
        source = Source.model_validate(record)
        if source.source_id in sources:
            raise ValueError('duplicate source_id')
        if doc['purpose'] == 'research' and (source.synthetic or not source.source_ref.startswith('https://')
                                           or source.license.startswith(('UNVERIFIED', 'LicenseRef-'))):
            raise ValueError('research sources require verified public provenance and license')
        data = checked_bytes(path.parent, source.model_dump())
        try:
            normalized = ' '.join(unicodedata.normalize('NFKC', data.decode('utf-8')).casefold().split())
        except UnicodeError as exc:
            raise ValueError('source text must be UTF-8') from exc
        if not normalized:
            raise ValueError('source text must not be empty')
        tokens = re.findall(r'\w+', normalized)
        shingles = {tuple(tokens[i:i + 5]) for i in range(len(tokens) - 4)}
        texts.append((source, normalized, shingles))
        sources[source.source_id] = source
    problems = check([{'case_id': s.source_id, 'split': s.split,
                       'source_group_id': s.source_group_id,
                       'document_revision_family': s.document_revision_family,
                       'source_hash': s.sha256} for s in sources.values()])
    if problems:
        raise ValueError('; '.join(problems))
    # shortcut: pairwise 5-token shingles suit G1 samples; use indexed candidates before large corpora.
    for i, (a, text_a, grams_a) in enumerate(texts):
        for b, text_b, grams_b in texts[i + 1:]:
            if a.split == b.split:
                continue
            overlap = len(grams_a & grams_b) / len(grams_a | grams_b) if grams_a and grams_b else 0
            if text_a == text_b or overlap >= 0.8:
                raise ValueError(f'cross-split near-duplicate: {a.source_id}, {b.source_id}')
    splits = doc.get('splits')
    if not isinstance(splits, dict) or split not in splits:
        raise ValueError(f'missing split: {split}')
    all_ids, label_paths = set(), set()
    for name, entry in splits.items():
        label_path = snapshot_path(path.parent, entry)
        ids = entry.get('case_ids')
        if (name not in ('train', 'dev', 'holdout') or not isinstance(ids, list) or not ids
                or any(not isinstance(value, str) or not value or value != value.strip() for value in ids)
                or len(set(ids)) != len(ids) or all_ids.intersection(ids)):
            raise ValueError('split case IDs must be nonempty, unique and disjoint')
        if label_path in label_paths:
            raise ValueError('split label snapshots must use separate paths')
        all_ids.update(ids)
        label_paths.add(label_path)
    cases = [Case.model_validate(row) for row in read_jsonl(checked_bytes(path.parent, splits[split]))]
    if not cases or len({case.case_id for case in cases}) != len(cases):
        raise ValueError('cases must be nonempty with unique case IDs')
    if {c.case_id for c in cases} != set(splits[split]['case_ids']):
        raise ValueError('label case IDs do not match split metadata')
    for case in cases:
        if any(s not in sources or sources[s].split != split for s in case.source_ids):
            raise ValueError(f'{case.case_id}: case sources must belong to its split')
        if len({sources[s].source_group_id for s in case.source_ids}) != 1:
            raise ValueError('case source families must share one bootstrap group')
        if doc['purpose'] == 'research' and case.review_status != 'independent':
            raise ValueError('research requires independent case review')
        for sid in case.gold_evidence_ids:
            source = sources[sid]
            if not authorized(source, case) or source.recorded_at > case.known_as_of:
                raise ValueError(f'{case.case_id}: gold evidence is unauthorized or unknown as of query')
            if case.expected_state in ('SUPPORTED', 'CONFLICT') and not available(source, case):
                raise ValueError(f'{case.case_id}: gold evidence is outside valid time')
    return Dataset(doc['dataset_id'], hashlib.sha256(raw).hexdigest(), split,
                   doc['purpose'], sources, cases)


class Prediction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    case_id: str
    action: str | None
    evidence_ids: list[str]
    confidence: float

    @model_validator(mode='after')
    def integrity(self):
        if self.action is not None and (not self.action or self.action != self.action.strip()):
            raise ValueError('action must be null or a nonempty trimmed string')
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError('duplicate prediction evidence ID')
        return self


def score_predictions(dataset: Dataset, rows: list[dict]) -> list[Outcome]:
    predictions = [Prediction.model_validate(row) for row in rows]
    by_id = {p.case_id: p for p in predictions}
    if len(by_id) != len(predictions) or by_id.keys() != {c.case_id for c in dataset.cases}:
        raise ValueError('prediction case IDs must match the complete selected split exactly')
    outcomes = []
    for case in dataset.cases:
        p = by_id[case.case_id]
        cited = set(p.evidence_ids)
        valid = {sid for sid in case.source_ids if available(dataset.sources[sid], case)}
        leaked = any(sid in dataset.sources and not authorized(dataset.sources[sid], case) for sid in cited)
        proposed = p.action is not None
        eligible = case.permitted_action is not None
        correct = (eligible and proposed and p.action == case.permitted_action
                   and set(case.gold_evidence_ids) <= cited and cited <= valid)
        outcomes.append(Outcome(case.case_id, dataset.sources[case.source_ids[0]].source_group_id,
                                eligible, proposed, correct, p.confidence, leaked))
    return outcomes
