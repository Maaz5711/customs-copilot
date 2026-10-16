"""Cell-grid reader for ruled tables in PDFs with a text layer (pymupdf).

The Fifth Schedule prints its tables with ruled lines and many merged cells.
pymupdf.find_tables() is unreliable there (merged cells, nested numbering columns),
so we read the ruling lines ourselves: a cell is the space between two horizontal
separators that fully cross a column. Text in a cell = words whose centre lies in it.
"""
from __future__ import annotations

from dataclasses import dataclass

import pymupdf


def _segments(page):
    """Return (vertical, horizontal) segments as (pos, a, b) from drawings (lines and thin rects)."""
    vs, hs = [], []
    for g in page.get_drawings():
        for it in g["items"]:
            if it[0] == "l":
                p, q = it[1], it[2]
                if abs(p.x - q.x) < 1.0 and abs(p.y - q.y) > 3:
                    vs.append((p.x, min(p.y, q.y), max(p.y, q.y)))
                elif abs(p.y - q.y) < 1.0 and abs(p.x - q.x) > 3:
                    hs.append((p.y, min(p.x, q.x), max(p.x, q.x)))
            elif it[0] == "re":
                r = it[1]
                if r.width < 2.0 and r.height > 3:
                    vs.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
                if r.height < 2.0 and r.width > 3:
                    hs.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
    return vs, hs


def table_blocks(page, min_len=8.0, gap=14.0):
    """Group vertical rulings into table blocks. Returns list of dicts {y0,y1,xs}."""
    vs, _ = _segments(page)
    vs = [v for v in vs if v[2] - v[1] >= min_len]
    vs.sort(key=lambda v: v[1])
    blocks = []
    for x, y0, y1 in vs:
        for b in blocks:
            if y0 <= b["y1"] + gap and y1 >= b["y0"] - gap:
                b["y0"], b["y1"] = min(b["y0"], y0), max(b["y1"], y1)
                b["segs"].append((x, y0, y1))
                break
        else:
            blocks.append({"y0": y0, "y1": y1, "segs": [(x, y0, y1)]})
    # merge blocks that grew into each other
    merged = True
    while merged:
        merged = False
        for i in range(len(blocks)):
            for j in range(i + 1, len(blocks)):
                a, b = blocks[i], blocks[j]
                if a["y0"] <= b["y1"] + gap and b["y0"] <= a["y1"] + gap:
                    a["y0"], a["y1"] = min(a["y0"], b["y0"]), max(a["y1"], b["y1"])
                    a["segs"] += b["segs"]
                    del blocks[j]
                    merged = True
                    break
            if merged:
                break
    out = []
    for b in sorted(blocks, key=lambda b: b["y0"]):
        # x clusters weighted by length
        tot = {}
        for x, y0, y1 in b["segs"]:
            k = round(x)
            tot[k] = tot.get(k, 0) + (y1 - y0)
        xs = sorted(k for k, l in tot.items() if l >= 0.5 * (b["y1"] - b["y0"]) or l > 60)
        # merge xs closer than 5pt
        mx = []
        for x in xs:
            if mx and x - mx[-1] < 5:
                continue
            mx.append(x)
        out.append({"y0": b["y0"], "y1": b["y1"], "xs": mx})
    return out


@dataclass
class Cell:
    col: int
    y0: float
    y1: float
    text: str
    top_open: bool = False      # no separator at the top (cell continues from previous page)
    bottom_open: bool = False   # no separator at the bottom (cell continues on next page)


def _words_text(words):
    """Join words into text, lines by y, words by x."""
    if not words:
        return ""
    words = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines, cur, cy = [], [], None
    for w in words:
        yc = (w[1] + w[3]) / 2
        if cy is None or abs(yc - cy) <= 3.2:
            cur.append(w)
            cy = yc if cy is None else (cy + yc) / 2
        else:
            lines.append(cur)
            cur, cy = [w], yc
    lines.append(cur)
    return "\n".join(" ".join(w[4] for w in sorted(l, key=lambda w: w[0])) for l in lines)


def read_block(page, y0, y1, xs, cover=0.5, tol=1.8):
    """Return cells per column for one ruled table block.

    cover: fraction of the right part of the column a horizontal rule must span to count as a
    separator in that column (nested sub-tables rule only part of the description column).
    """
    _, hs = _segments(page)
    words = page.get_text("words")
    cols = []
    for ci in range(len(xs) - 1):
        xa, xb = xs[ci], xs[ci + 1]
        w = xb - xa
        lo = xb - max(12.0, w * cover)  # test the right part of the column
        seps = set()
        for y, a, b in hs:
            if y0 - tol <= y <= y1 + tol and a <= lo + tol and b >= xb - tol:
                seps.add(round(y, 1))
        ys = sorted(seps)
        # merge separators closer than 1.5pt (double rules)
        mys = []
        for y in ys:
            if mys and y - mys[-1] < 1.5:
                continue
            mys.append(y)
        top_open = not mys or mys[0] > y0 + 3
        bot_open = not mys or mys[-1] < y1 - 3
        bounds = ([y0] if top_open else []) + mys + ([y1] if bot_open else [])
        cells = []
        for k in range(len(bounds) - 1):
            ca, cb = bounds[k], bounds[k + 1]
            ws = [wd for wd in words if xa - 1 <= (wd[0] + wd[2]) / 2 <= xb + 1 and ca <= (wd[1] + wd[3]) / 2 <= cb]
            cells.append(Cell(ci, ca, cb, _words_text(ws), top_open and k == 0, bot_open and k == len(bounds) - 2))
        cols.append(cells)
    return cols
