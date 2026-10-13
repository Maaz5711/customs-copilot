"""A3 income tax, part C helper: pull the operative (body-text) clauses of the Second
Schedule that mention section 148, separating them from footnotes.

Footnotes start below a short horizontal rule (x0 = 72, width = 144 pt). The text
that sits below that rule (including quoted text of omitted clauses that
overflows from the previous page) is footnote text and is NOT operative.
Placeholders like "5[  ]" mark omitted clauses; they end the current clause.
"""
import re
from pathlib import Path

import pymupdf

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"

START = re.compile(r"^(?:\d{1,2}\s*\[)*\s*\(?(\d{1,3}[A-Z]{0,3})\)\s")
PLACEHOLDER = re.compile(r"^\s*(\d{1,2}\s*\[\s*\]\s*)+$")
MARK_RE = re.compile(r"\d{1,2}\s*\[|\]")
PART_HDR = re.compile(r"Second Schedule\s*[–-]\s*Part[\s-]*(IV|III|II|I)(?![A-Za-z])")


def footnote_rule_y(page):
    best = None
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] != "re":
                continue
            r = it[1]
            if r.height < 1.6 and 142 < r.width < 146 and r.x0 < 80 and r.y0 > 60:
                best = r.y0 if best is None else min(best, r.y0)
    return best


def split_page(page):
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).rstrip()
            lines.append((l["bbox"][0], l["bbox"][1], t))
    ry = footnote_rule_y(page)
    body = [l for l in lines if ry is None or l[1] < ry]
    foot = [l for l in lines if not (ry is None or l[1] < ry)]
    return body, foot, ry


def part_of_page(page):
    for l in page.get_text().split("\n")[:3]:
        m = PART_HDR.search(l)
        if m:
            return m.group(1)
    return ""


def body_clauses(pdf_path, first, last):
    """Return list of clause dicts (no, page, pages, part, text) for body text only."""
    doc = pymupdf.open(str(pdf_path))
    out, cur = [], None
    for pn in range(first, last + 1):
        page = doc[pn - 1]
        part = part_of_page(page)
        body, foot, ry = split_page(page)
        for x, y, t in body:
            if y < 50 or y > 600:
                continue
            t = t.strip()
            if not t or t == "..":
                continue
            if PLACEHOLDER.match(t) or t.startswith("THE THIRD SCHEDULE"):
                cur = None
                continue
            m = START.match(t)
            if m and x < 100:
                cur = {"no": m.group(1), "page": pn, "pages": [pn], "part": part, "lines": [t]}
                out.append(cur)
            elif cur is not None:
                cur["lines"].append(t)
                if pn not in cur["pages"]:
                    cur["pages"].append(pn)
    for c in out:
        raw = re.sub(r"\s+", " ", " ".join(c["lines"])).strip()
        # a following clause printed on the same text line: cut it off
        m = re.search(r"(?<=\])\s+\d{1,2}\s*\[\s*\(\d+[A-Z]*\)", raw)
        if m:
            raw = raw[:m.start()].strip()
        c["raw_text"] = raw
        c["text"] = clean_markers(c["raw_text"])
    return out


def clean_markers(s):
    """Remove the editorial footnote markers 'n[' and ']' of the consolidated text."""
    s = MARK_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def second_schedule_range(pdf_path):
    """first/last page whose running header says 'Second Schedule'."""
    doc = pymupdf.open(str(pdf_path))
    first = last = None
    for i in range(len(doc)):
        head = " ".join(doc[i].get_text().split("\n")[:2])
        if re.search(r"Second\s+Schedule", head):
            first = first or i + 1
            last = i + 1
    return first, last
