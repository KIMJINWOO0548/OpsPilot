"""Render a frozen, approved evidence record as a dependency-free static PDF."""

from __future__ import annotations

from io import BytesIO
from textwrap import wrap

from .schema import Analysis, AnalyzeRequest

MAX_REPORT_BYTES = 1024 * 1024
_ROWS_PER_PAGE = 43
_LINE_WIDTH = 86


def _pdf_text(text: str) -> str:
    # PDF operators only receive literal strings escaped here.
    return "(" + text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def _plain_ascii(value: str) -> str:
    # The PDF's standard fonts do not include all Unicode glyphs. Preserve
    # every code point without allowing embedded controls to introduce lines.
    return "".join(
        char if " " <= char <= "~" and char != "\\"
        else char.encode("unicode_escape").decode("ascii")
        for char in value
    )


def _page_stream(rows: list[tuple[str, str]], page: int, pages: int) -> bytes:
    operators = [
        "0.08 0.15 0.23 rg",
        "BT /F2 11 Tf 46 748 Td (OpsPilot-X) Tj ET",
        "BT /F2 23 Tf 46 712 Td (Approved evidence report) Tj ET",
        "0.65 0.71 0.76 RG 0.7 w 46 694 m 566 694 l S",
    ]
    for index, (kind, line) in enumerate(rows):
        if not line:
            continue
        y = 671 - index * 14
        font = "/F2 10" if kind == "heading" else "/F1 9.5"
        operators.append(f"BT {font} Tf 46 {y} Td {_pdf_text(line)} Tj ET")
    operators.extend([
        "46 62 m 566 62 l S",
        f"BT /F2 9 Tf 46 43 Td {_pdf_text(f'Approval record  |  Page {page} of {pages}')} Tj ET",
    ])
    return "\n".join(operators).encode("ascii") + b"\n"


def _serialize_pdf(rows: list[tuple[str, str]]) -> bytes:
    pages = [rows[start:start + _ROWS_PER_PAGE] for start in range(0, len(rows), _ROWS_PER_PAGE)]
    kids = " ".join(f"{5 + index * 2} 0 R" for index in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    for index, page in enumerate(pages):
        stream = _page_stream(page, index + 1, len(pages))
        objects.append((
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {6 + index * 2} 0 R >>"
        ).encode("ascii"))
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream")

    with BytesIO() as document:
        document.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for identifier, obj in enumerate(objects, start=1):
            offsets.append(document.tell())
            document.write(f"{identifier} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
            if document.tell() > MAX_REPORT_BYTES:
                raise ValueError("Approved evidence report exceeds the PDF size limit")
        xref = document.tell()
        document.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
        for offset in offsets:
            document.write(f"{offset:010d} 00000 n \n".encode("ascii"))
        document.write((
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii"))
        if document.tell() > MAX_REPORT_BYTES:
            raise ValueError("Approved evidence report exceeds the PDF size limit")
        return document.getvalue()


def render_approved_report(
    *,
    proposal_id: str,
    receipt_id: str,
    approver: str,
    approved_at: str,
    fingerprint: str,
    request: AnalyzeRequest,
    snapshot: Analysis,
) -> bytes:
    if (snapshot.state != "SUPPORTED" or not snapshot.recommended_action or not snapshot.citations
            or snapshot.effective_at != request.effective_at or snapshot.known_as_of != request.known_as_of):
        raise ValueError("An approved, supported and time-matched evidence snapshot is required")

    rows: list[tuple[str, str]] = [("heading", "APPROVAL")]
    chars = 0

    def field(label: str, value: str) -> None:
        nonlocal chars
        chars += len(value)
        if chars > MAX_REPORT_BYTES:
            raise ValueError("Approved evidence report exceeds the PDF size limit")
        prefix = f"{label:<21} "
        rows.extend(("body", line) for line in wrap(
            prefix + _plain_ascii(value),
            width=_LINE_WIDTH,
            subsequent_indent=" " * len(prefix),
            break_on_hyphens=False,
        ))

    field("Proposal", proposal_id)
    field("PDF receipt", receipt_id)
    field("Approved by", approver)
    field("Approved at", approved_at)
    field("Approved action", snapshot.recommended_action)
    field("Approval fingerprint", fingerprint)

    rows.extend([("body", ""), ("heading", "EVIDENCE SCOPE")])
    field("Asset", request.asset_id)
    field("Claim", request.claim_key)
    field("Effective at", snapshot.effective_at.isoformat())
    field("Known as of", snapshot.known_as_of.isoformat())
    field("Determination", snapshot.state)

    rows.extend([("body", ""), ("heading", f"CITED SOURCES ({len(snapshot.citations)})")])
    for citation in snapshot.citations:
        field("Evidence ID", citation.evidence_id)
        field("Source ID", citation.source_id)
        field("Source version", citation.source_version)
        field("Locator", citation.locator)
        field("SHA-256", citation.checksum)
        rows.append(("body", ""))
    rows.pop()
    return _serialize_pdf(rows)
