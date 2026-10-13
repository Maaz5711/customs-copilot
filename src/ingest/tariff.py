"""A1: parse the Pakistan Customs Tariff PDF into heading and code rows.

Layout facts (checked on the FY2026-27 PDF):
- Code and heading numbers start at the left margin (x0 < CODE_X_MAX).
- The description sits between CODE_X_MAX and CD_X_MIN.
- The CD column starts at CD_X_MIN. Plain CDs are horizontal. Specific duties
  (for example "Rs. 117.00/MT") are rotated 90 degrees and wrapped over several
  short lines, so plain text extraction scrambles them. We rebuild them from
  the individual characters (column by column, bottom to top).

Every row keeps source_file and page (hard rule 1). valid_from / valid_to are
set by the loader because they come from the fiscal year, not from the PDF.
"""
import json
import re
from multiprocessing import Pool
from pathlib import Path

import pdfplumber

CODE_X_MAX = 80
CD_X_MIN = 390
LINE_TOL = 2.5

CODE_RE = re.compile(r"^\d{4}\.\d{4}$")
SPECIAL_RE = re.compile(r"^\d{4}$")  # Chapter 99 style 4-digit codes
DELETED_RE = re.compile(r"^\[\d{2}\.\d{2}\]$")  # deleted headings, e.g. [05.03]
HEADING_RE = re.compile(r"^\d{2}\.\d{2}$")
NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _extract_page(args):
    pdf_path, idx = args
    with pdfplumber.open(pdf_path) as pdf:
        pg = pdf.pages[idx]
        horiz = pg.filter(lambda o: o.get("object_type") != "char" or abs(o["matrix"][1]) < 0.1)
        words = [[w["text"], round(w["x0"], 1), round(w["top"], 1)]
                 for w in horiz.extract_words()]
        rot = [[c["text"], round(c["x0"], 1), round(c["top"], 1)]
               for c in pg.chars if abs(c["matrix"][1]) >= 0.1 and c["x0"] >= CD_X_MIN]
    return {"page": idx + 1, "words": words, "rot": rot}


def load_pages(pdf_path: Path, cache: Path) -> list[dict]:
    """Per-page words and rotated chars. pdfplumber is slow, so cache as JSON."""
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
    with Pool(4) as pool:
        pages = pool.map(_extract_page, [(str(pdf_path), i) for i in range(n)])
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(pages), encoding="utf-8")
    return pages


def _group_lines(words):
    """Group words into visual lines by their top coordinate."""
    lines = []
    for w in sorted(words, key=lambda w: (w[2], w[1])):
        if lines and abs(lines[-1][0] - w[2]) <= LINE_TOL:
            lines[-1][1].append(w)
        else:
            lines.append([w[2], [w]])
    return [(top, sorted(ws, key=lambda w: w[1])) for top, ws in lines]


def _rotated_text(chars):
    """Read rotated text: columns left to right, each column bottom to top."""
    cols = {}
    for t, x0, top in chars:
        cols.setdefault(round(x0 / 4), []).append((top, t))
    out = ""
    for key in sorted(cols):
        out += "".join(t for _, t in sorted(cols[key], reverse=True))
    return out


SPECIFIC_RE = re.compile(r"^Rs\.?(\d+(?:\.\d+)?)(?:/|per)(\w+)$", re.I)


def _clean_rate(raw: str):
    """Return (cd_plain, specific, kind).

    plain    -> cd_plain is the percentage (float).
    specific -> specific = {"amount": float, "unit": str}, for example Rs.11700/MT.
                The PDF wraps these cells mid-number ("117" / "00/"), so the amount
                is the digits joined as printed. There is no decimal point in the text
                layer; every specific row goes to the spot-check sheet.
    other    -> raw text kept, nothing guessed.
    """
    s = re.sub(r"\s+", "", raw)
    if NUM_RE.match(s):
        return float(s), None, "plain"
    m = SPECIFIC_RE.match(s)
    if m:
        return None, {"amount": float(m.group(1)), "unit": m.group(2)}, "specific"
    return None, None, "other"


def parse_pages(pages: list[dict], source_file: str):
    """Return (headings, rows, special). `special` are Chapter 99 four-digit codes."""
    headings, rows, special = [], [], []
    cur_heading = None
    for pg in pages:
        page_no = pg["page"]
        lines = _group_lines(pg["words"])
        # band edges: every code/heading line starts a band that ends at the next one
        starts = [i for i, (_, ws) in enumerate(lines)
                  if ws[0][1] < CODE_X_MAX and (CODE_RE.match(ws[0][0]) or HEADING_RE.match(ws[0][0])
                                                or SPECIAL_RE.match(ws[0][0]) or DELETED_RE.match(ws[0][0]))]
        bounds = [lines[i][0] for i in starts] + [float("inf")]
        for n, i in enumerate(starts):
            top, ws = lines[i]
            first = ws[0][0]
            band_end = bounds[n + 1]
            nxt = starts[n + 1] if n + 1 < len(starts) else len(lines)
            desc_words = [w[0] for w in ws[1:] if w[1] < CD_X_MIN]
            cd_words = [w[0] for w in ws[1:] if w[1] >= CD_X_MIN]
            # continuation lines inside this band
            for _, cws in lines[i + 1:nxt]:
                desc_words += [w[0] for w in cws if w[1] < CD_X_MIN]
                cd_words += [w[0] for w in cws if w[1] >= CD_X_MIN]
            rot = [c for c in pg["rot"] if top - LINE_TOL <= c[2] < band_end - LINE_TOL]
            cd_raw = _rotated_text(rot) if rot else " ".join(cd_words)
            desc = " ".join(desc_words).strip()
            if DELETED_RE.match(first):
                continue
            if SPECIAL_RE.match(first):
                special.append({"code": first, "description": desc, "cd_raw": cd_raw,
                                "source_file": source_file, "page": page_no})
                continue
            if HEADING_RE.match(first):
                cur_heading = {"heading": first, "text": desc, "source_file": source_file, "page": page_no}
                headings.append(cur_heading)
                continue
            cd_plain, specific, kind = _clean_rate(cd_raw) if cd_raw else (None, None, "missing")
            # A code's heading is its own first four digits. Some heading lines are
            # not in the PDF text layer (11.03) or are merged into a single-code
            # row (02.05 / 0205.0000), so the code is the authority, not the last
            # heading line seen. Missing headings are added as derived entries.
            code_heading = first[:2] + "." + first[2:4]
            if cur_heading is None or cur_heading["heading"] != code_heading:
                single = first.endswith("0000") and not desc.startswith("-")
                cur_heading = {"heading": code_heading, "text": desc if single else "",
                               "source_file": source_file, "page": page_no,
                               "derived_from_code": True}
                headings.append(cur_heading)
            rows.append({
                "code": first,
                "heading": code_heading,
                "description": desc,
                "cd_raw": cd_raw,
                "cd_plain": cd_plain,
                "cd_specific": specific,
                "cd_kind": kind,
                "rotated": bool(rot),
                "source_file": source_file,
                "page": page_no,
            })
    return headings, rows, special
