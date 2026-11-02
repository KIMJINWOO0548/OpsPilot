"""Initial deterministic EIE slice; NOT an NLI model or a validated innovation.

Security invariant: authorization happens before any business filtering, scoring,
reasoning or response construction. The local fixture store is a demo, not a DB RLS layer.
"""
from __future__ import annotations

import json
import hashlib
from importlib.resources import files

from .schema import Actor, Analysis, AnalyzeRequest, Citation, Evidence


def load_seed() -> list[Evidence]:
    p = files("opspilot_x").joinpath("fixtures/evidence.json")
    result = [Evidence.model_validate(row) for row in json.loads(p.read_text(encoding="utf8"))]
    for e in result:
        expected = hashlib.sha256(e.text.encode("utf8")).hexdigest()
        if e.checksum != expected:
            raise ValueError("Evidence source integrity check failed")
    return result


def authorized(evidence: Evidence, actor: Actor) -> bool:
    return (
        evidence.tenant == actor.tenant
        and evidence.team == actor.team
        and actor.role in evidence.readable_roles
    )


def effective_at(evidence: Evidence, timestamp) -> bool:
    return evidence.valid_from <= timestamp and (
        evidence.valid_to is None or timestamp < evidence.valid_to
    )


def evaluate(request: AnalyzeRequest, seed: list[Evidence] | None = None) -> Analysis:
    seed = load_seed() if seed is None else seed
    # Do NOT report unauthorized candidates, IDs, counts, reasons or debug detail.
    permitted = [e for e in seed if authorized(e, request.actor)]
    related = [
        e for e in permitted if e.asset_id == request.asset_id and e.claim_key == request.claim_key
    ]
    known = [e for e in related if e.recorded_at <= request.known_as_of]
    current = [e for e in known if effective_at(e, request.effective_at)]

    if not current:
        stale = bool(known) and all(e.valid_from <= request.effective_at for e in known)
        return Analysis(
            state="STALE" if stale else "INSUFFICIENT",
            recommended_action=None,
            reason="No currently valid authorized evidence" if stale else "No sufficient authorized evidence",
            citations=[], effective_at=request.effective_at, known_as_of=request.known_as_of,
        )

    # A later acknowledged record can supersede a known predecessor. Only within the
    # authorized + available + temporally valid set, never based on inaccessible data.
    overridden = {old for e in current for old in e.supersedes}
    current = [e for e in current if e.evidence_id not in overridden]
    # Approved SOP rules, not incident notes, can authorize a proposed maintenance action.
    authoritative = [e for e in current if e.authority == "approved_sop"]
    if not authoritative:
        return Analysis(
            state="INSUFFICIENT", recommended_action=None,
            reason="No valid authoritative instruction",
            citations=[], effective_at=request.effective_at, known_as_of=request.known_as_of,
        )
    actions = {e.value for e in authoritative}
    citations = [
        Citation(evidence_id=e.evidence_id, source_id=e.source_id,
                 source_version=e.source_version, locator=e.locator, checksum=e.checksum)
        for e in sorted(authoritative, key=lambda x: x.evidence_id)
    ]
    if len(actions) != 1:
        return Analysis(
            state="CONFLICT", recommended_action=None,
            reason="Conflicting authorized instructions with no unambiguous precedence",
            citations=citations, effective_at=request.effective_at,
            known_as_of=request.known_as_of,
        )
    return Analysis(
        state="SUPPORTED", recommended_action=next(iter(actions)),
        reason="One consistent authorized current instruction; approval still required",
        citations=citations, effective_at=request.effective_at,
        known_as_of=request.known_as_of,
    )
