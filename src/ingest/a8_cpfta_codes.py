"""A8: second reading of the PCT code of lines whose code the first OCR pass could not read (or read out of order).

For each such line a thin strip around the Sr.No/code columns is cut out of the straightened page at 300 dpi and read again by
the recognition model alone (no layout detection). The new reading is accepted only if it is exactly eight digits, rises in order
between the neighbouring codes, and (for information) is a line of the FY2025-26 or FY2026-27 tariff. Every re-read is logged,
accepted or not (data/processed/a8_cpfta_code_reread.csv).
Usage: python -m src.ingest.a8_cpfta_codes   (reads data/processed/a8_cpfta_rows.csv, writes the log + a8_cpfta_code_fixes.json)
"""
from __future__ import annotations

import csv
import glob
import json
import re
from pathlib import Path

import cv2
import pymupdf

from src.ingest.a8_cpfta_ocr import deskew, render
from src.ingest.a8_cpfta import clean_digits

PROC = Path("data/processed")
PDF = glob.glob("data/raw/cpfta/*.pdf")[0]
DPI2 = 300


_CACHE = {}


def strip_for(doc, page, y200, skew):
    if _CACHE.get("page") != page:
        _CACHE.clear()
        _CACHE["page"], _CACHE["img"] = page, deskew(render(doc, page, DPI2), skew)
    img = _CACHE["img"]
    k = DPI2 / 200.0
    y0, y1 = int((y200 - 16) * k), int((y200 + 16) * k)
    x0, x1 = int(230 * k), int(420 * k)
    crop = img[max(0, y0):y1, x0:x1]
    return cv2.copyMakeBorder(crop, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=(255, 255, 255))


def read_strip(ocr, crop):
    res, _ = ocr(crop)
    return [t for _b, t, _c in (res or [])]


def candidates_from(texts):
    """Eight-character tokens of the strip -> (exact codes, patterns with one unreadable character as '?')."""
    from src.ingest.a8_cpfta import CHAR_DIGIT

    exact, fuzzy = [], []
    for t in texts:
        t = re.sub(r"\s+", "", t)
        if len(t) < 8:
            continue
        u = t[-8:] if len(t) > 8 else t
        mapped = "".join(ch.translate(CHAR_DIGIT) if not ch.isdigit() else ch for ch in u)
        bad = [i for i, ch in enumerate(mapped) if not ch.isdigit()]
        if not bad:
            exact.append(mapped)
        elif len(bad) == 1:
            fuzzy.append(mapped[:bad[0]] + "?" + mapped[bad[0] + 1:])
    return exact, fuzzy


def tariff_codes_all():
    out = set()
    for f in ("tariff_2026_27.csv", "tariff_2025_26.csv"):
        out |= {r["code"].replace(".", "") for r in csv.DictReader(open(PROC / f, encoding="utf-8"))}
    return out


def main(rows):
    """rows: list of dicts with page, y, sr_no, code (maybe None), prev_code, next_code. Returns (fixes, log)."""
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    doc = pymupdf.open(PDF)
    tariff = tariff_codes_all()
    fixes, log, skews = {}, [], {}
    for r in sorted(rows, key=lambda r: (r["page"], r["y"])):
        pg = r["page"]
        if pg not in skews:
            skews[pg] = json.loads((PROC / "cpfta_ocr" / f"p{pg:03d}.json").read_text(encoding="utf-8"))["skew_deg"]
        texts = read_strip(ocr, strip_for(doc, pg, r["y"], skews[pg]))
        exact, fuzzy = candidates_from(texts)
        lo, hi = r.get("prev_code") or "00000000", r.get("next_code") or "99999999"
        ok = [c for c in exact if lo < c < hi]
        how = "second_reading_eight_digits" if ok else ""
        new = ok[0] if ok else None
        if new is None and fuzzy:
            cands = sorted({p.replace("?", str(d)) for p in fuzzy for d in range(10)})
            cands = [c for c in cands if lo < c < hi and c in tariff]
            if len(cands) == 1:
                new, how = cands[0], "second_reading_one_character_inferred_between_neighbours_and_in_tariff"
        log.append(dict(sr_no=r["sr_no"], page=pg, old_code=r.get("code") or "", reread_text=" | ".join(texts), accepted_code=new or "", how=how,
                        why_not=("" if new else "no eight-digit reading between the neighbouring codes")))
        if new:
            fixes[r["sr_no"]] = new
    return fixes, log
