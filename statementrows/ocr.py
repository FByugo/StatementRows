"""Reading scanned pages: render the page, run OCR, and hand back the same Line objects the text reader
makes, so every check downstream works unchanged. OCR misreads numbers; the running balance and the
totals are what catch that, row by row.

Optional: needs `rapidocr-onnxruntime`. Without it a scanned statement stays `needs_ocr`."""
from __future__ import annotations

import re

try:
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR
    AVAILABLE = True
except ImportError:  # pragma: no cover - depends on what is installed
    AVAILABLE = False

_ENGINE = None
TARGET_WIDTH_PX = 2600     # enough for 8 to 9 pt statement text; more only costs time


def _engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = RapidOCR()
    return _ENGINE


def fix_ocr_text(t: str) -> str:
    """Repairs OCR makes on statements. None of them changes the value a number was printed with:
    '2.686,759.17' or '4,007.108.14' (separators read at random) -> '2,686,759.17' / '4,007,108.14',
    because the last separator before two digits is always the decimal point;
    '01/01/202407:34:14AM' -> '01/01/2024 07:34:14AM'; 'Rs.513.47' -> 'Rs. 513.47'."""
    def money(m):
        body, dec = m.group(1), m.group(2)
        return re.sub(r"[.,]", ",", body) + "." + dec
    t = re.sub(r"\bRs\.(?=\d)", "Rs. ", t)
    t = re.sub(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{3})+)[.,](\d{2})(?![\d.,])", money, t)
    t = re.sub(r"(\d{4})(\d{1,2}:\d{2})", r"\1 \2", t)
    return t


def ocr_page_lines(pdf_path: str, page_index: int, page_no: int, page_width_pt: float, page_height_pt: float):
    """Lines for one page, in PDF points, built from OCR boxes."""
    from .core import Line   # imported here: core imports this module
    doc = pdfium.PdfDocument(pdf_path)
    try:
        scale = TARGET_WIDTH_PX / page_width_pt
        img = doc[page_index].render(scale=scale).to_numpy()
    finally:
        doc.close()
    result, _ = _engine()(img)
    boxes = []
    for box, text, conf in result or []:
        x0 = min(p[0] for p in box) / scale
        x1 = max(p[0] for p in box) / scale
        y0 = min(p[1] for p in box) / scale
        y1 = max(p[1] for p in box) / scale
        text = fix_ocr_text(text.strip())
        if text:
            boxes.append((x0, x1, y0, y1, text))
    boxes.sort(key=lambda b: ((b[2] + b[3]) / 2, b[0]))
    rows: list[list] = []
    for b in boxes:
        mid, h = (b[2] + b[3]) / 2, b[3] - b[2]
        for row in rows[-3:]:
            r = row[0]
            if abs((r[2] + r[3]) / 2 - mid) < max(2.0, 0.5 * min(h, r[3] - r[2])):
                row.append(b)
                break
        else:
            rows.append([b])
    lines = []
    for row in rows:
        row.sort(key=lambda b: b[0])
        text, xs = [], []
        prev = None
        # an OCR box hugs the letters; the font size that the spacing rules expect is about a quarter more
        size = max(b[3] - b[2] for b in row) * 1.25
        for b in row:
            if prev is not None:
                gap = b[0] - prev[1]
                sep = "  " if gap > size * 1.6 else " "
                text.append(sep)
                xs += [(prev[1], b[0])] * len(sep)
            w = (b[1] - b[0]) / max(1, len(b[4]))
            text.append(b[4])
            xs += [(b[0] + k * w, b[0] + (k + 1) * w) for k in range(len(b[4]))]
            prev = b
        s = "".join(text)
        lines.append(Line(s, xs, min(b[2] for b in row), size, page_no))
    return lines
