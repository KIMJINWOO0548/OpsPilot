"""Immutable local evidence snapshots with SQL authorization before lexical ranking."""
from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .eie import effective_at as is_effective, load_seed
from .schema import Actor, Evidence


def _clock(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def initialize_evidence(path: str | Path, records: list[Evidence] | None = None) -> None:
    records = load_seed() if records is None else records
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS evidence_documents (
                evidence_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, team TEXT NOT NULL,
                asset_id TEXT NOT NULL, recorded_at TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence_acl (
                evidence_id TEXT NOT NULL REFERENCES evidence_documents(evidence_id),
                role TEXT NOT NULL, PRIMARY KEY (evidence_id, role)
            );
            CREATE INDEX IF NOT EXISTS evidence_scope
                ON evidence_documents(tenant, team, asset_id, recorded_at);
        """)
        for evidence in records:
            if hashlib.sha256(evidence.text.encode("utf8")).hexdigest() != evidence.checksum:
                raise ValueError("Evidence source integrity check failed")
            payload = evidence.model_dump_json()
            previous = db.execute("SELECT payload FROM evidence_documents WHERE evidence_id=?",
                                  (evidence.evidence_id,)).fetchone()
            if previous:
                if previous[0] != payload:
                    raise ValueError("Evidence snapshot is immutable; use a new evidence_id")
                continue
            db.execute("INSERT INTO evidence_documents VALUES (?, ?, ?, ?, ?, ?)",
                       (evidence.evidence_id, evidence.tenant, evidence.team, evidence.asset_id,
                        _clock(evidence.recorded_at), payload))
            db.executemany("INSERT INTO evidence_acl VALUES (?, ?)",
                           [(evidence.evidence_id, role) for role in set(evidence.readable_roles)])


def authorized_evidence(path: str | Path, actor: Actor, asset_id: str | None = None,
                        known_as_of: datetime | None = None) -> list[Evidence]:
    clauses = ["d.tenant=?", "d.team=?", "a.role=?"]
    parameters = [actor.tenant, actor.team, actor.role]
    if asset_id is not None:
        clauses.append("d.asset_id=?")
        parameters.append(asset_id)
    if known_as_of is not None:
        clauses.append("d.recorded_at<=?")
        parameters.append(_clock(known_as_of))
    # All interpolated clauses are constants; caller data is always bound.
    query = ("SELECT d.payload FROM evidence_documents d JOIN evidence_acl a "
             "ON a.evidence_id=d.evidence_id WHERE " + " AND ".join(clauses)
             + " ORDER BY d.evidence_id")
    with closing(sqlite3.connect(path)) as db:
        return [Evidence.model_validate_json(row[0]) for row in db.execute(query, parameters)]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def search_evidence(path: str | Path, actor: Actor, *, asset_id: str | None = None,
                    query: str = "", effective_at: datetime | None = None,
                    known_as_of: datetime | None = None, limit: int = 30) -> list[dict]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if len(query) > 1000:
        raise ValueError("query exceeds 1000 characters")
    effective_at = effective_at or datetime.now(timezone.utc)
    _clock(effective_at)
    known_as_of = known_as_of or datetime.now(timezone.utc)
    permitted = authorized_evidence(path, actor, asset_id, known_as_of)
    visible_relations = {(e.asset_id, e.claim_key, e.evidence_id) for e in permitted}
    current = [e for e in permitted if is_effective(e, effective_at)]
    superseded = {(e.asset_id, e.claim_key, old) for e in current for old in e.supersedes}
    terms = _tokens(query)
    results = []
    for evidence in permitted:
        score = len(terms & _tokens(" ".join((evidence.text, evidence.source_id,
                                             evidence.asset_id, evidence.value)))) if terms else 0
        if terms and not score:
            continue
        if (evidence.asset_id, evidence.claim_key, evidence.evidence_id) in superseded:
            status = "SUPERSEDED"
        elif evidence.valid_from > effective_at:
            status = "NOT_YET_EFFECTIVE"
        elif not is_effective(evidence, effective_at):
            status = "STALE"
        else:
            status = "VALID"
        row = evidence.model_dump(mode="json", exclude={"tenant", "team", "readable_roles"})
        row["supersedes"] = [old for old in evidence.supersedes
                             if (evidence.asset_id, evidence.claim_key, old) in visible_relations]
        row.update(score=score, temporal_status=status)
        results.append(row)
    return sorted(results, key=lambda row: (-row["score"], row["evidence_id"]))[:limit]
