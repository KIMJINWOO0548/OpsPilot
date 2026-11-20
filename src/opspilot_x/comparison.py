"""Read-only differences between two already authorized decision snapshots."""
from __future__ import annotations

from .schema import Analysis, AnalysisComparison, Citation, CitationChanges


def _citation_key(citation: Citation) -> tuple[str, ...]:
    return (citation.evidence_id, citation.source_id, citation.source_version,
            citation.locator, citation.checksum)


def compare_snapshots(before: Analysis, after: Analysis) -> AnalysisComparison:
    previous = {_citation_key(c): c for c in before.citations}
    current = {_citation_key(c): c for c in after.citations}
    changes = CitationChanges(
        state_changed=before.state != after.state,
        action_changed=before.recommended_action != after.recommended_action,
        added_citations=[current[key] for key in sorted(current.keys() - previous.keys())],
        removed_citations=[previous[key] for key in sorted(previous.keys() - current.keys())],
    )
    return AnalysisComparison(
        before=before, after=after,
        changed=bool(changes.state_changed or changes.action_changed
                     or changes.added_citations or changes.removed_citations),
        changes=changes,
    )
