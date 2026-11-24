"""Render a frozen, approved evidence record as a dependency-free static PDF."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from io import BytesIO
from struct import iter_unpack, pack
from textwrap import wrap
from unicodedata import normalize
from zlib import compress

from .schema import Analysis, AnalyzeRequest

MAX_REPORT_BYTES = 1024 * 1024
_ROWS_PER_PAGE = 43
_LINE_WIDTH = 86
_FIELD_COLUMNS = 22
_BODY_SIZE = 9.5
_VALUE_X = 46 + _FIELD_COLUMNS * _BODY_SIZE * 0.6  # Courier's 600-unit advance


def _pdf_text(text: str) -> str:
    # PDF operators only receive literal strings escaped here.
    return "(" + text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


@lru_cache(maxsize=1)
def _font_metrics() -> dict[str, tuple[int, int]]:
    font_map = files("opspilot_x").joinpath("fonts", "NanumGothic-Regular.map").read_bytes()
    return {chr(code): (glyph, width) for code, glyph, width in iter_unpack(">HHH", font_map)}


def _display_value(value: str) -> str:
    # NFC allows decomposed Hangul to use the same glyphs as composed Hangul.
    # Unsupported characters and controls retain a readable code-point escape.
    value = normalize("NFC", value)
    metrics = _font_metrics() if not value.isascii() else {}
    return "".join(
        char if " " <= char <= "~" or (char.isprintable() and char in metrics)
        else char.encode("unicode_escape").decode("ascii")
        for char in value
    )


def _page_stream(rows: list[tuple[str, str]], page: int, pages: int,
                 cids: dict[str, int]) -> bytes:
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
        if kind == "unicode":
            label, value = line[:_FIELD_COLUMNS].rstrip(), line[_FIELD_COLUMNS:]
            if label:
                operators.append(f"BT /F1 9.5 Tf 46 {y} Td {_pdf_text(label)} Tj ET")
            encoded = "".join(f"{cids[char]:04X}" for char in value)
            operators.append(f"BT /F3 9.5 Tf {_VALUE_X:g} {y} Td <{encoded}> Tj ET")
            continue
        font = "/F2 10" if kind == "heading" else "/F1 9.5"
        operators.append(f"BT {font} Tf 46 {y} Td {_pdf_text(line)} Tj ET")
    operators.extend([
        "46 62 m 566 62 l S",
        f"BT /F2 9 Tf 46 43 Td {_pdf_text(f'Approval record  |  Page {page} of {pages}')} Tj ET",
    ])
    return "\n".join(operators).encode("ascii") + b"\n"


def _stream(data: bytes, properties: str = "") -> bytes:
    separator = b"" if data.endswith(b"\n") else b"\n"
    return (f"<< /Length {len(data)}{properties} >>\nstream\n".encode("ascii")
            + data + separator + b"endstream")


@lru_cache(maxsize=1)
def _embedded_font() -> bytes:
    font = files("opspilot_x").joinpath("fonts", "NanumGothic-Regular.ttf").read_bytes()
    return _stream(compress(font, level=9), f" /Filter /FlateDecode /Length1 {len(font)}")


def _unicode_cmap(cids: dict[str, int]) -> bytes:
    lines = [
        "/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        "/CMapName /OpsPilotUnicode def", "/CMapType 2 def",
        "1 begincodespacerange", "<0000> <FFFF>", "endcodespacerange",
    ]
    pairs = [f"<{cid:04X}> <{ord(char):04X}>" for char, cid in cids.items()]
    for start in range(0, len(pairs), 100):
        block = pairs[start:start + 100]
        lines.extend([f"{len(block)} beginbfchar", *block, "endbfchar"])
    lines.extend(["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"])
    return "\n".join(lines).encode("ascii") + b"\n"


def _unicode_font_objects(cids: dict[str, int]) -> list[bytes]:
    metrics = _font_metrics()
    widths = " ".join(str(metrics[char][1]) for char in cids)
    glyphs = b"\x00\x00" + b"".join(pack(">H", metrics[char][0]) for char in cids)
    return [
        b"<< /Type /Font /Subtype /Type0 /BaseFont /NanumGothic "
        b"/Encoding /Identity-H /DescendantFonts [6 0 R] /ToUnicode 9 0 R >>",
        (f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /NanumGothic /FontDescriptor 7 0 R "
         f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
         f"/W [1 [{widths}]] /CIDToGIDMap 10 0 R >>").encode("ascii"),
        b"<< /Type /FontDescriptor /FontName /NanumGothic /Flags 4 "
        b"/FontBBox [-14 -198 1005 844] /ItalicAngle 0 /Ascent 856 /Descent -144 "
        b"/CapHeight 743 /StemV 80 /FontFile2 8 0 R >>",
        _embedded_font(),
        _stream(_unicode_cmap(cids)),
        _stream(glyphs),
    ]


def _serialize_pdf(rows: list[tuple[str, str]]) -> bytes:
    pages = [rows[start:start + _ROWS_PER_PAGE] for start in range(0, len(rows), _ROWS_PER_PAGE)]
    chars = sorted({char for kind, line in rows if kind == "unicode" for char in line[_FIELD_COLUMNS:]})
    cids = {char: index for index, char in enumerate(chars, start=1)}
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # Page references are written after the optional font objects.
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    resources = "/F1 3 0 R /F2 4 0 R"
    if cids:
        objects.extend(_unicode_font_objects(cids))
        resources += " /F3 5 0 R"
    first_page = len(objects) + 1
    kids = " ".join(f"{first_page + index * 2} 0 R" for index in range(len(pages)))
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii")
    for index, page in enumerate(pages):
        stream = _page_stream(page, index + 1, len(pages), cids)
        objects.append((
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << {resources} >> >> "
            f"/Contents {first_page + index * 2 + 1} 0 R >>"
        ).encode("ascii"))
        objects.append(
            _stream(compress(stream), " /Filter /FlateDecode") if cids else _stream(stream)
        )

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
        prefix = f"{label:<{_FIELD_COLUMNS}}"
        value = _display_value(value)
        if not value.isascii():
            metrics = _font_metrics()
            max_width = max(metrics[char][1] for char in value)
            columns = int((566 - _VALUE_X) * 1000 / (_BODY_SIZE * max_width))
            for index, line in enumerate(wrap(value, width=columns, break_on_hyphens=False)):
                rows.append(("unicode", (" " * _FIELD_COLUMNS if index else prefix) + line))
            return
        rows.extend(("body", line) for line in wrap(
            prefix + value,
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
