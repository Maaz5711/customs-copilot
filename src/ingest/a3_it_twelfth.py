"""A3 income tax, part A: parse the Twelfth Schedule (goods subject to s.148 advance tax).

Layout (checked on page images): two columns. Code column starts at x0 < 135, the
description column at x0 >= 135. The code is vertically centred in its cell, so we
rely on the text-block reading order (code lines first, then description lines)
and on x0 to tell code lines from description lines. Footnotes are the lines in
small type (size <= 7.5) at the bottom of each page that start with a number.

Inserted entries are printed as "1[07.01 ... ]": the number is the page-local
footnote number and "[" ... "]" brackets the inserted entries.
"""
import re
from pathlib import Path

import pymupdf

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"

FILES = {
    "FY2026-27": "2026724177725705IncomeTaxOrdinanace2001.pdf",   # amended up to 30.06.2026
    "FY2025-26": "2025881983148210Income-Tax-Ordinance,-2001-Amended-upto-31.07.2025.pdf",
}

CODE_X_MAX = 135
SKIP_TEXT = {"PCT", "CODE", "DESCRIPTION", "(1)", "(2)", "", "THE TWELFTH SCHEDULE",
             "[See Section148]", "PCT CODE", "[See Section 148]"}
PART_RE = re.compile(r"^\s*PART\s+(III|II|I)\s*$", re.I)
FOOT_START_RE = re.compile(r"^\s*(\d{1,2})\s{1,4}\S")
CODE_START_RE = re.compile(r"^\s*(?:(\d{1,2})\[)?\s*(\d{2}\.\d{2}|\d{4}\.\d{4}|\d{8})(?!\d)")


def find_pages(doc):
    """first page of 'THE TWELFTH SCHEDULE' ... last page with 'Part III' goods."""
    start = end = None
    for i in range(len(doc)):
        t = doc[i].get_text()
        if start is None and "THE TWELFTH SCHEDULE" in t and "SeeSection148" in t.replace(" ", "") and "PCT CODE" in t:
            start = i + 1
        if start and "Goods not specifically mentioned in Part I or II" in t:
            end = i + 1
            break
    return start, end


def page_lines(page):
    """-> (body_lines, footnote_lines); each line = dict(x0,y0,size,text)."""
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            txt = "".join(s["text"] for s in l["spans"]).rstrip()
            lines.append({"x0": l["bbox"][0], "y0": l["bbox"][1],
                          "size": l["spans"][0]["size"], "text": txt})
    foot_i = None
    for i, l in enumerate(lines):
        if (l["size"] <= 7.5 and l["text"].strip() and FOOT_START_RE.match(l["text"]) and l["y0"] > 300
                and not re.match(r"^\s*\d{1,2}\s*\[", l["text"])):
            foot_i = i
            break
    if foot_i is None:
        return lines, []
    return lines[:foot_i], lines[foot_i:]


def parse_footnotes(foot_lines):
    notes, cur = {}, None
    for l in foot_lines:
        m = FOOT_START_RE.match(l["text"]) if l["size"] <= 7.5 else None
        if m:
            cur = int(m.group(1))
            notes[cur] = l["text"].strip()[len(m.group(1)):].strip()
        elif cur is not None and l["text"].strip():
            notes[cur] += " " + l["text"].strip()
    return {k: re.sub(r"\s+", " ", v) for k, v in notes.items()}


def row_boundaries(page):
    """y positions of the horizontal rules of the table (clustered)."""
    ys = []
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] == "re":
                r = it[1]
                if r.height < 1.6 and r.width > 20:
                    ys.append((r.y0 + r.y1) / 2)
            elif it[0] == "l" and abs(it[1].y - it[2].y) < 0.5 and abs(it[1].x - it[2].x) > 20:
                ys.append(it[1].y)
    ys.sort()
    out = []
    for y in ys:
        if not out or y - out[-1] > 1.0:
            out.append(y)
    return out


def parse_schedule(pdf_path):
    """Row-based parse: rows are the cells between the table's horizontal rules."""
    doc = pymupdf.open(str(pdf_path))
    start, end = find_pages(doc)
    entries, omitted = [], []
    notes_by_page = {}
    part = None
    pending = None   # description prefix of a row split across pages (blank code on first page)
    for pn in range(start, end + 1):
        page = doc[pn - 1]
        body, foot = page_lines(page)
        notes = parse_footnotes(foot)
        notes_by_page[pn] = notes
        foot_y = foot[0]["y0"] - 3 if foot else 600
        bounds = [b for b in row_boundaries(page) if b > 50 and b < foot_y]
        bounds.append(foot_y)
        # lines of the table (after any title/part header lines)
        lines = [l for l in body if l["y0"] > 50 and l["y0"] < foot_y and l["text"].strip() not in ("", "..")]
        # part markers are single lines like "Part II" / "PART I" (centered, not in rows)
        for l in lines:
            m = PART_RE.match(l["text"].strip())
            if m:
                l["part_marker"] = m.group(1).upper()
        rows_on_page = []
        for a, b in zip(bounds[:-1], bounds[1:]):
            cell = [l for l in lines if a - 0.5 <= (l["y0"] + 5) < b + 0.5 and "part_marker" not in l]
            code = [l for l in cell if l["x0"] < CODE_X_MAX]
            desc = [l for l in cell if l["x0"] >= CODE_X_MAX]
            if not code and not desc:
                continue
            rows_on_page.append((a, b, code, desc))
        # part markers in order of y: assign to rows below them
        markers = sorted((l["y0"], l["part_marker"]) for l in lines if "part_marker" in l)
        for idx, (a, b, code, desc) in enumerate(rows_on_page):
            for my, pm in markers:
                if my < a + 1:
                    part = pm
            code_t = " ".join(l["text"].strip() for l in sorted(code, key=lambda l: l["y0"])).strip()
            desc_t = " ".join(l["text"].strip() for l in sorted(desc, key=lambda l: l["y0"])).strip()
            if code_t in ("PCT CODE", "PCT CODE DESCRIPTION", "(1)", "(1) (2)", "PCT", "CODE") or desc_t in ("DESCRIPTION", "(2)"):
                continue
            if code_t.upper().replace(" ", "") in ("PCTCODE",) :
                continue
            mo = re.fullmatch(r"(?:(\d{1,2})\s*)?\[\s*\]", code_t)
            if mo and not desc_t:
                no = int(mo.group(1)) if mo.group(1) else None
                omitted.append({"page": pn, "note_no": no, "note": notes.get(no, "") if no else "", "part": part})
                continue
            if not code_t and desc_t:
                if idx == 0 and entries and entries[-1]["page"] < pn:
                    entries[-1]["desc"].append(desc_t)        # continuation from previous page
                    entries[-1]["pages"].append(pn)
                elif idx == len(rows_on_page) - 1:
                    pending = desc_t                          # continues on next page (code printed there)
                else:
                    entries.append({"part": part, "page": pn, "code_lines": [], "desc": [desc_t],
                                    "notes": notes, "orphan": True})
                continue
            if code_t and not desc_t:
                # code with no description on this page: description is on the next page or empty
                entries.append({"part": part, "page": pn, "code_lines": [code_t], "desc": [],
                                "notes": notes, "pages": [pn]})
                continue
            d = [desc_t]
            if pending:
                d = [pending, desc_t]
                pending = None
            entries.append({"part": part, "page": pn, "code_lines": [code_t], "desc": d,
                            "notes": notes, "pages": [pn]})
    return doc, start, end, entries, omitted, notes_by_page


def finish_entries(entries):
    """Resolve footnote brackets, split code cell into code / except text."""
    open_notes = []  # (page, no) still open
    rows = []
    for e in entries:
        code_cell = " ".join(e["code_lines"]).strip()
        desc = " ".join(e["desc"]).strip()
        m = re.match(r"^(\d{1,2})\s*\[\s*(.*)$", code_cell)
        if m:
            open_notes.append((e["page"], int(m.group(1))))
            code_cell = m.group(2)
        attached = [(p, n) for (p, n) in open_notes]
        # closing bracket at the end of description
        closes = 0
        d2 = desc
        while d2.endswith("]"):
            d2 = d2[:-1].rstrip()
            closes += 1
        # a "]" can close brackets opened on the same entry
        for _ in range(closes):
            if open_notes:
                open_notes.pop()
        e["code_cell"] = code_cell
        e["description"] = re.sub(r"\s+", " ", d2)
        e["foot_nos"] = attached
        rows.append(e)
    return rows
