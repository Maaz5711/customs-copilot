"""A3: SRO 297(I)/2023 (sales tax 25% on listed imported goods) as amended by SRO 370(I)/2024 and SRO 1525(I)/2026.

Source pages are scans with embedded OCR. The code lists were first read from the OCR text, then every serial was
compared with the page image by Claude (see CORRECTIONS: where the printed image differs from the OCR text).
Codes are stored as printed in the SRO, with validator flags (code_not_in_tariff, code_format); nothing is fixed silently.
Usage: python -m src.ingest.a3_sro297
"""
import csv
import json
import re
from pathlib import Path

import pymupdf

RAW = Path("data/raw")
OUT = Path("data/processed")
SRC297 = "2023382232741774SRO-297-OF-2023.pdf"
SRC370 = "202438103312693AMENDMENTINSRO297OF2023,DATED08.03.2023.pdf"  # is actually SRO 370(I)/2024 (scan)
SRC1525 = "20269141794445366SRO1525.pdf"

# Where the image (what is printed) differs from the embedded OCR text. Found by reading each page image.
# key: (serial, ocr_token) -> printed token
CORRECTIONS = {
    (2, "04.90"): "1704.9010",   # OCR text has "1704.90W" (W for 10); the regex only sees "04.90"
}
# Codes the OCR text missed entirely but the image shows (serial -> codes), see vision_notes
ADD_FROM_IMAGE = {2: ["1704.9010"]}

SERIAL_TITLES = {}


def ocr_blocks():
    d = pymupdf.open(RAW / SRC297)
    pages = [p.get_text() for p in d]
    txt = ""
    for i, t in enumerate(pages, 1):
        txt += f"\n@@PAGE{i}\n" + t
    i1 = txt.index("Table-1"); i2 = txt.index("Table-II", i1)
    body = txt[i1:i2]
    pos, cur = [], 0
    for n in range(1, 37):
        m = re.search(rf"\n\s*{n}\s*\n", body[cur:])
        pos.append((n, cur + m.start(), cur + m.end()))
        cur = cur + m.end()
    pos.append((99, len(body), len(body)))
    out = {}
    for (n, s, e), (_, s2, _) in zip(pos, pos[1:]):
        seg = body[e:s2]
        page = 1 + body[:s].count("@@PAGE") + int(txt[:i1].count("@@PAGE") - 1) if False else None
        out[n] = seg
    return txt, body, out


if __name__ == "__main__":
    txt, body, blocks = ocr_blocks()
    for n, seg in blocks.items():
        toks = re.findall(r"\d{4}[.,]\d{4}|\d{4}\.[\dA-Za-z]{4}|\d{8}|\d{2}\.\d{2}", seg)
        print(n, len(toks))
