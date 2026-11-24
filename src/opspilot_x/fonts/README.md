# Nanum Gothic Regular

The TrueType font is unchanged from Google Fonts commit `06bfe0d62a98375cb09c942fa18e68bd32cff057`. Its SHA-256 is `76f45ef4a6bcff344c837c95a7dcc26e017e38b5846d5ae0cdcb5b86be2e2d31`. See the [pinned upstream files](https://github.com/google/fonts/tree/06bfe0d62a98375cb09c942fa18e68bd32cff057/ofl/nanumgothic) and the [SIL Open Font License](OFL.txt).

`NanumGothic-Regular.map` stores the font's BMP code point, glyph ID, and horizontal advance in PDF units as big-endian unsigned 16-bit triples, ordered by code point. The renderer uses the map and the unchanged font without importing a font parser at runtime. To regenerate the map, run the following from this directory in a development environment with ReportLab available.

```python
from pathlib import Path
from struct import pack

from reportlab.pdfbase.ttfonts import TTFontFile

face = TTFontFile("NanumGothic-Regular.ttf")
metrics = (
    (code, glyph, round(face.charWidths.get(code, face.defaultWidth)))
    for code, glyph in sorted(face.charToGlyph.items())
    if code <= 0xFFFF and glyph
)
Path("NanumGothic-Regular.map").write_bytes(b"".join(pack(">HHH", *row) for row in metrics))
```
