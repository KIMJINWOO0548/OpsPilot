from datetime import datetime, timezone
import re

import pytest

from opspilot_x.eie import evaluate, load_seed
from opspilot_x.pdf_report import MAX_REPORT_BYTES, render_approved_report
from opspilot_x.schema import AnalyzeRequest


@pytest.fixture
def report_inputs():
    at = datetime(2026, 11, 23, tzinfo=timezone.utc)
    request = AnalyzeRequest(
        actor={"user_id": "engineer-test", "tenant": "demo", "team": "team_a", "role": "engineer"},
        asset_id="A-103",
        effective_at=at,
        known_as_of=at,
    )
    return dict(
        proposal_id="proposal-abc",
        receipt_id="pdf-receipt-abc",
        approver="approver-test",
        approved_at=at.isoformat(),
        fingerprint="a" * 64,
        request=request,
        snapshot=evaluate(request, load_seed()),
    )


def test_report_bytes_capture_approved_record(report_inputs):
    document = render_approved_report(**report_inputs)
    assert document == render_approved_report(**report_inputs)
    assert document.startswith(b"%PDF-1.4")
    assert document.endswith(b"%%EOF\n")
    assert b"/Count 1" in document
    for value in (
        b"proposal-abc", b"pdf-receipt-abc", b"sensor_diagnostic_first", b"approver-test",
        b"SOP-A103-v2#section-2", b"Effective at", b"Known as of", b"Source version",
        report_inputs["snapshot"].citations[0].checksum.encode(),
    ):
        assert value in document
    assert b"SOP-SECRET" not in document
    startxref = int(document.rsplit(b"startxref\n", 1)[1].splitlines()[0])
    assert document[startxref:].startswith(b"xref\n")
    offsets = re.findall(rb"(?m)^([0-9]{10}) 00000 n $", document[startxref:])
    assert len(offsets) == 6
    for object_id, offset in enumerate(offsets, 1):
        assert document[int(offset):].startswith(f"{object_id} 0 obj\n".encode())


def test_report_keeps_more_sources_on_following_pages_and_escapes_strings(report_inputs):
    snapshot = report_inputs["snapshot"]
    reference = snapshot.citations[0]
    citations = [
        reference.model_copy(update={"evidence_id": f"synthetic-source-{index:02}", "locator": r"a(b)\c"})
        for index in range(8)
    ]
    report_inputs["snapshot"] = snapshot.model_copy(update={"citations": citations})
    report_inputs["approver"] = "\ud14c\uc2a4\ud2b8"
    document = render_approved_report(**report_inputs)
    assert b"/Count 2" in document
    assert b"Page 1 of 2" in document and b"Page 2 of 2" in document
    assert b"synthetic-source-07" in document
    assert rb"a\(b\)\\\\c" in document
    assert rb"\\ud14c\\uc2a4\\ud2b8" in document


def test_rejects_unsupported_or_oversized_report(report_inputs):
    snapshot = report_inputs["snapshot"]
    with pytest.raises(ValueError, match="time-matched"):
        render_approved_report(**{
            **report_inputs, "snapshot": snapshot.model_copy(update={"state": "CONFLICT"}),
        })
    with pytest.raises(ValueError, match="size"):
        render_approved_report(**{**report_inputs, "approver": "a" * MAX_REPORT_BYTES})
