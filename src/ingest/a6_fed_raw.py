"""A6: coordinate-based reading of the First Schedule tables of the Federal Excise Act 2005 (typeset PDFs, text layer).

Step 1 (this file): turn each table page into S.No rows with four columns (S.No, description, heading, rate) plus the
page footnotes. Interpretation of the rate text is in a6_fed.py. Nothing is typed in by hand here.
"""
import json
import re
from pathlib import Path

import pymupdf

RAW = Path("data/raw")
PROC = Path("data/processed")
FILES = {
    "2026": RAW / "20267171373633512FEDAct2005updatedupto30-06-2026.pdf",
    "2025": RAW / "202588138517680FEDAct,2005withindexupdatedupto30-06-2025.pdf",
}
# printed table page ranges (PDF page index == printed page number in both files; checked)
TABLE_PAGES = {
    "2026": {"I": (70, 79), "IA": (80, 80), "II": (81, 85), "III": (86, 86)},
    "2025": {"I": (72, 82), "II": (83, 87), "III": (88, 88)},
}
SNO_RE = re.compile(r"^(?:\d+\[)?(\d{1,3}[A-Za-z]?)(?:[.*\]]|\*\*\*)*$")


def _col(x0):
    if x0 < 188:
        return 0
    if x0 < 328:
        return 1
    if x0 < 410:
        return 2
    return 3


def page_rows(page):
    """Return (rows, footnotes) for one table page. rows: list of dict(s_no, cols=[[(y,text)...]*4])."""
    words = page.get_text("words")
    # footnote separator: thin black filled rect (height < 1.5, width ~ 144) starting at x ~ 126
    sep = None
    for d in page.get_drawings():
        r = d["rect"]
        if d.get("fill") == (0.0, 0.0, 0.0) and r.height < 1.5 and 100 < r.width < 200 and r.y0 > 300:
            sep = r.y0 if sep is None else max(sep, r.y0)
    body_limit = sep if sep else 690
    body = [w for w in words if 118 < w[1] < body_limit and w[1] < 680]
    foot = [w for w in words if sep and w[1] > sep and w[1] < 680]
    return body, foot


def footnotes(foot):
    lines = {}
    for w in sorted(foot, key=lambda w: (round(w[1]), w[0])):
        lines.setdefault(round(w[1] / 3), []).append(w)
    out, cur = {}, None
    for k in sorted(lines):
        txt = " ".join(w[4] for w in sorted(lines[k], key=lambda w: w[0]))
        m = re.match(r"^(\d{1,2})\s+(.*)$", txt)
        if m and (cur is None or int(m.group(1)) == cur + 1 or int(m.group(1)) == 1):
            cur = int(m.group(1))
            out[cur] = m.group(2)
        elif cur is not None:
            out[cur] += " " + txt
    return out


def read_table(year, table):
    d = pymupdf.open(FILES[year])
    a, b = TABLE_PAGES[year][table]
    rows = []
    for pno in range(a, b + 1):
        page = d[pno - 1]
        body, foot = page_rows(page)
        fn = footnotes(foot)
        # skip header words
        body = [w for w in body if not re.match(r"^(S\.?|No\.?|Description|of|Goods|Heading/|sub-heading|Number|Rate|Duty|Col\.\(\d\)|\(\d\)|Heading/sub-|Services\]|\[Services\]|Description)$", w[4]) or w[1] > 175]
        body.sort(key=lambda w: (w[1], w[0]))
        rows.append({"page": pno, "words": [(round(w[0], 1), round(w[1], 1), w[4]) for w in body], "footnotes": fn})
    return rows


if __name__ == "__main__":
    import sys
    year, table = sys.argv[1], sys.argv[2]
    for pg in read_table(year, table):
        print("=== page", pg["page"])
        cols = [[], [], [], []]
        for x, y, t in pg["words"]:
            cols[_col(x)].append((y, x, t))
        for c in range(4):
            lines = {}
            for y, x, t in sorted(cols[c]):
                lines.setdefault(round(y / 5), []).append(t)
            print(f"--- col{c}")
            for k in sorted(lines):
                print(f"  y{k*5}: " + " ".join(lines[k]))
        print("--- footnotes", json.dumps(pg["footnotes"], ensure_ascii=False)[:1500])


def segment(pg):
    """Split a page into rows at S.No anchors in column 0. Returns list of dicts."""
    words = pg["words"]
    anchors = []
    for x, y, t in words:
        if _col(x) == 0 and SNO_RE.match(t):
            anchors.append((y, t))
    rows = []
    # words above first anchor belong to previous page's last row (continuation)
    bounds = [a[0] for a in anchors] + [10_000]
    first = bounds[0] if anchors else 10_000
    cont = [w for w in words if w[1] < first - 2]
    if cont:
        rows.append({"anchor": None, "words": cont})
    for i, (y, t) in enumerate(anchors):
        ws = [w for w in words if y - 2 <= w[1] < bounds[i + 1] - 2]
        rows.append({"anchor": t, "words": ws})
    return rows


def row_cols(row):
    cols = [[], [], [], []]
    for x, y, t in sorted(row["words"], key=lambda w: (round(w[1] / 4), w[0])):
        cols[_col(x)].append((y, x, t))
    return cols
