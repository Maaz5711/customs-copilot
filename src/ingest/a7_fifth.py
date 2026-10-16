"""A7: Fifth Schedule to the Customs Act 1969 (FY2026-27 text, "Updated 30th June, 2026") -> dated concession rows.

Source: data/raw/2026825118858478FifthSchedule2026-27.pdf (typeset, text layer present but the table cells are scattered
in reading order, so the tables are rebuilt from the ruling lines: src/ingest/pdf_grid.py).
It is the Second Schedule of the Finance Act 2026 (s.3(14): "The Fifth Schedule ... shall be substituted"), so it is the
schedule in force from 1 Jul 2026. The FY2025-26 version (Finance Act 2025) is NOT in this file and not in the two Customs Act
consolidations (they print only the title); see docs/concessions_findings.md.

Outputs (data/processed): a7_fifth_rows.csv/json (every table row incl. headings and omitted rows), a7_fifth_rules.csv/json
(loadable rule rows), a7_fifth_failures.csv (every validator finding, nothing silently fixed), a7_fifth_validation.json,
spotcheck_a7_fifth.csv. Usage: python -m src.ingest.a7_fifth
"""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from src.ingest.pdf_grid import read_block, table_blocks

RAW = Path("data/raw")
PROC = Path("data/processed")
SOURCE = "2026825118858478FifthSchedule2026-27.pdf"
VALID_FROM = "2026-07-01"
VALID_TO = "9999-12-31"

# page 22 and the lower blocks of page 21 are the Annex forms (Annex-A/B), not concession rows
SKIP_PAGES = {22}
ONLY_FIRST_BLOCK = {21}

HEAD_PART = re.compile(r"^Part[- ]\s*([IVX]+)\s*(?:\(\s*([A-C])\s*\))?(?![A-Za-z])")
HEAD_TABLE_ABC = re.compile(r"^Table\s+([A-E])\s*$")
HEAD_TABLE_ROMAN = re.compile(r"^TABLE\s*-\s*([IVX]+)\s*$")
HEAD_TABLE_PLAIN = re.compile(r"^TABLE\s*$", re.I)

CODE8 = re.compile(r"\b(\d{4})\.(\d{4})\b")
CODE6 = re.compile(r"\b(\d{4})\.(\d{2})\b(?!\d)")
CODE4 = re.compile(r"\b(\d{2})\.(\d{2})\b(?!\.?\d)")
MARKER = re.compile(r"^\s*(\(?\d{1,2}[\.\)]|\(?[ivx]{1,5}[\.\)]|\(?[a-zA-Z][\.\)])\s")
HEADER_WORDS = re.compile(r"^(S\.? ?No\.?|Sr\.? ?No\.?|No\.?|\(\d\)|Description( of [a-z ]+)?|PCT [Cc]ode|Customs [Dd]uty.*|CD ?%|Conditions?|Special Condition|Rate of Duty)$")


def heading_events(page):
    """(y, kind, value) for Part / Table headings printed on the page (exact line positions)."""
    ev = []
    for blk in page.get_text("dict")["blocks"]:
        if blk["type"] != 0:
            continue
        for ln in blk["lines"]:
            s = "".join(sp["text"] for sp in ln["spans"]).strip()
            if not s:
                continue
            y = ln["bbox"][1]
            m = HEAD_PART.match(s)
            if m and len(s) < 60:
                part = m.group(1) + (f"({m.group(2)})" if m.group(2) else "")
                ev.append((y, "part", part))
                continue
            m = HEAD_TABLE_ABC.match(s)
            if m:
                ev.append((y, "table", m.group(1)))
                continue
            m = HEAD_TABLE_ROMAN.match(s)
            if m:
                ev.append((y, "table", m.group(1)))
                continue
            if HEAD_TABLE_PLAIN.match(s):
                ev.append((y, "table", "main"))
    return ev


def roles_for(part, table, ncols):
    """Column roles of a ruled table."""
    if part == "IV":
        return ["sno", "pct", "cd", "cond"]
    if part == "V(A)" and table == "II":
        return ["sno", "desc", "desc2", "cd", "cond"]
    if part == "V(A)" and table == "III":
        return ["sno", "desc", "cd", "cond"]
    if ncols == 5:
        return ["sno", "desc", "pct", "cd", "cond"]
    if ncols == 4:
        return ["sno", "desc", "pct", "cd"]
    raise ValueError(f"no role map for part={part} table={table} ncols={ncols}")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ")).strip()


def norm_codes(text: str):
    """Return (digit strings, match levels, respective_headings flag)."""
    codes, levels = [], []
    for m in CODE8.finditer(text):
        codes.append(m.group(1) + m.group(2))
        levels.append("code8")
    t2 = CODE8.sub(" ", text)
    for m in CODE6.finditer(t2):
        codes.append(m.group(1) + m.group(2))
        levels.append("code6")
    t3 = CODE6.sub(" ", t2)
    for m in CODE4.finditer(t3):
        codes.append(m.group(1) + m.group(2))
        levels.append("heading4")
    return codes, levels, bool(re.search(r"respective", text, re.I))


def parse_rate(raw: str):
    """Parse the Customs Duty cell. Returns (kind, pct_list, fraction, note)."""
    t = re.sub(r"[”“\"]+\.?$", "", clean(raw)).strip()
    if not t:
        return "none", [], None, ""
    rep = re.findall(r"\d+(?:\.\d+)?%?", t)
    if len(rep) >= 2 and re.fullmatch(r"(\d+(?:\.\d+)?%?\s+)+\d+(?:\.\d+)?%?", t):
        # stacked rates of several rows read as one cell ("0% 0%"): identical -> one rate, different -> keep as text
        if len(set(rep)) == 1:
            t = rep[0]
        else:
            return "other", [], None, t
    low = t.lower()
    if re.search(r"\d+\s*%\s*of", low) and re.search(r"prevailing|rate of customs|of the rate", low):
        m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*of", low)
        return "fraction_of_first_schedule", [], m.group(1), t
    if re.search(r"\bplus\b|additional", low):
        return "other", [], None, t
    nums = re.findall(r"\d+(?:\.\d+)?", t)
    if nums and not re.sub(r"[0-9\.\s%,]|\band\b|\bor\b|/", "", t, flags=re.I):
        return "percent", nums, None, ""
    if re.fullmatch(r"nil", low):
        return "nil", [], None, t
    return "other", nums if re.match(r"^\d+(?:\.\d+)?\s*%", t) else [], None, t


def build_rows(pdf_path: Path):
    doc = pymupdf.open(pdf_path)
    rows = []
    state = {"part": "I", "table": "main"}
    carry_sno = ""
    for pno in range(2, len(doc) + 1):
        page = doc[pno - 1]
        if pno in SKIP_PAGES:
            continue
        events = sorted(heading_events(page))
        blocks = table_blocks(page)
        if pno in ONLY_FIRST_BLOCK:
            blocks = blocks[:1]
        words = page.get_text("words")
        for bi, blk in enumerate(blocks):
            for y, kind, val in events:
                if y < blk["y0"]:
                    state = {"part": val, "table": "main"} if kind == "part" else {"part": state["part"], "table": val}
            xs = list(blk["xs"])
            if state["part"] == "I" and len(xs) == 7:  # nested numbering column inside Description (p19-21)
                xs = [x for x in xs if not (110 < x < 135)]
            try:
                roles = roles_for(state["part"], state["table"], len(xs) - 1)
            except ValueError as e:
                rows.append({"page": pno, "part": state["part"], "table": state["table"], "row_kind": "unparsed_block",
                             "issues": str(e)})
                continue
            cols = read_block(page, blk["y0"], blk["y1"], xs)
            ci = {r: i for i, r in enumerate(roles)}
            bset = set()
            for r, i in ci.items():
                if r == "cond":
                    continue
                for c in cols[i]:
                    bset.add(round(c.y0, 1))
                    bset.add(round(c.y1, 1))
            mb = []
            for y in sorted(bset):
                if mb and y - mb[-1] < 2.0:
                    continue
                mb.append(y)
            bands = [(mb[k], mb[k + 1]) for k in range(len(mb) - 1) if mb[k + 1] - mb[k] > 3.0]

            def cell_at(role, yc):
                if role not in ci:
                    return None
                for c in cols[ci[role]]:
                    if c.y0 - 0.5 <= yc <= c.y1 + 0.5:
                        return c
                return None

            def text_in(role, ya, yb):
                xa, xb = xs[ci[role]], xs[ci[role] + 1]
                ws = [w for w in words if xa - 1 <= (w[0] + w[2]) / 2 <= xb + 1 and ya - 0.5 <= (w[1] + w[3]) / 2 <= yb + 0.5]
                ws.sort(key=lambda w: (round((w[1] + w[3]) / 2 / 3), w[0]))
                return " ".join(w[4] for w in ws)

            # own words (code column) per band: a band "carries" an item when it prints a code or "Respective headings"
            own_pct = {}
            if "pct" in ci:
                for (ya, yb) in bands:
                    own_pct[(ya, yb)] = clean(text_in("pct", ya, yb))
            carrier = {b: bool(norm_codes(t)[0] or norm_codes(t)[2]) for b, t in own_pct.items()}
            desc_for_band = {}
            issues_for_band = {}
            if "desc" in ci:
                for c in cols[ci["desc"]]:
                    inside = [b for b in bands if b[0] >= c.y0 - 1 and b[1] <= c.y1 + 1]
                    whole = clean(c.text)
                    if len(inside) <= 1:
                        for b in inside:
                            desc_for_band[b] = whole
                        continue
                    car = [b for b in inside if carrier.get(b)]
                    if len(car) <= 1:
                        target = car[0] if car else inside[0]
                        for b in inside:
                            desc_for_band[b] = whole if b == target else ""
                        continue
                    segs = []
                    for line in c.text.split(chr(10)):
                        if MARKER.match(line) or not segs:
                            segs.append(line)
                        else:
                            segs[-1] += " " + line
                    if len(segs) == len(car):
                        for b in inside:
                            desc_for_band[b] = ""
                        for b, sg in zip(car, segs):
                            desc_for_band[b] = clean(sg)
                    else:
                        for b in inside:
                            desc_for_band[b] = whole if b in car else ""
                            if b in car:
                                issues_for_band[b] = "description_shared_by_several_codes"
            first_band = True
            for (ya, yb) in bands:
                yc = (ya + yb) / 2
                rec = {"page": pno, "part": state["part"], "table": state["table"], "block": bi, "y0": round(ya, 1), "y1": round(yb, 1)}
                cs = {r: cell_at(r, yc) for r in ci}
                sno_cell = cs.get("sno")
                sno_txt = clean(sno_cell.text).rstrip(".") if sno_cell else ""
                rec["is_header"] = bool(sno_txt and HEADER_WORDS.match(sno_txt))
                if sno_txt and not rec["is_header"]:
                    carry_sno = sno_txt
                rec["s_no"] = "" if rec["is_header"] else carry_sno
                rec["s_no_printed"] = bool(sno_txt) and not rec["is_header"]
                rec["description"] = desc_for_band.get((ya, yb), "")
                rec["issues"] = issues_for_band.get((ya, yb), "")
                d2 = cs.get("desc2")
                rec["description2"] = clean(d2.text) if d2 else ""
                pcell = cs.get("pct")
                if pcell:
                    nb = sum(1 for b in bands if b[0] >= pcell.y0 - 1 and b[1] <= pcell.y1 + 1)
                    rec["pct_raw"] = clean(pcell.text) if nb <= 1 else own_pct[(ya, yb)]
                else:
                    rec["pct_raw"] = ""
                rc = cs.get("cd")
                rec["rate_raw"] = clean(rc.text) if rc else ""
                if rc:
                    inside = [b for b in bands if b[0] >= rc.y0 - 1 and b[1] <= rc.y1 + 1]
                    if len(inside) > 1:
                        owns = {b: clean(text_in("cd", b[0], b[1])) for b in inside}
                        nonempty = [v for v in owns.values() if v]
                        # one complete rate printed per row inside a tall cell (not one wrapped sentence)
                        if len(nonempty) >= 2 and all(parse_rate(v)[0] in ("percent", "nil") for v in nonempty):
                            mine = owns[(ya, yb)]
                            if mine:
                                rec["rate_raw"] = mine
                            else:
                                earlier = [owns[b] for b in inside if b[0] < ya and owns[b]]
                                rec["rate_raw"] = earlier[-1] if earlier else ""
                                if rec["rate_raw"]:
                                    rec["issues"] = (rec.get("issues", "") + "; " if rec.get("issues") else "") + "rate_taken_from_row_above_in_tall_cell"
                rec["rate_cell"] = f"{pno}:{round(rc.y0, 1)}" if rc else None
                rec["rate_top_open"] = bool(rc and rc.top_open)
                rec["rate_bottom_open"] = bool(rc and rc.bottom_open)
                cc = cs.get("cond")
                rec["cond_raw"] = clean(cc.text) if cc else ""
                rec["cond_cell"] = f"{pno}:{round(cc.y0, 1)}" if cc else None
                rec["cond_top_open"] = bool(cc and cc.top_open)
                rec["cond_bottom_open"] = bool(cc and cc.bottom_open)
                rec["block_first_band"] = first_band
                first_band = False
                rows.append(rec)
        # headings printed below the last table of the page apply to the next page's tables
        last_y = blocks[-1]["y0"] if blocks else -1
        for y, kind, val in events:
            if y >= last_y:
                state = {"part": val, "table": "main"} if kind == "part" else {"part": state["part"], "table": val}
    return rows


def finalize(rows):
    """Carry merged cells over page breaks (rate, conditions) and attach the full conditions text.

    A cell with no ruling line at its top continues the open cell at the bottom of the previous page (same Part and Table).
    The mapping is kept per cell, so every row inside a continued cell gets the carried value.
    """
    cond_text, cond_real = {}, {}
    rate_real = {}
    prev_cond_key, prev_cond_open, prev_pt = None, False, None
    prev_rate_text, prev_rate_open = "", False
    for r in rows:
        if r.get("row_kind") == "unparsed_block":
            continue
        pt = (r["part"], r["table"])
        # the block's first band continues the previous page when its serial number is not printed again (a table border
        # is drawn at every page top, so "no ruling line" cannot be used)
        continuing = bool(r["block_first_band"] and prev_pt == pt and not r["s_no_printed"])
        key = r["cond_cell"]
        if key is not None:
            if key not in cond_real:
                cond_real[key] = prev_cond_key if (continuing and prev_cond_key) else key
            real = cond_real[key]
            lst = cond_text.setdefault(real, [])
            if r["cond_raw"] and r["cond_raw"] not in lst:
                lst.append(r["cond_raw"])
            r["cond_key"] = real
            prev_cond_key, prev_cond_open = real, r["cond_bottom_open"]
        else:
            r["cond_key"] = None
        rk = r.get("rate_cell")
        if rk is not None:
            if r["rate_raw"]:
                rate_real[rk] = r["rate_raw"]
            elif rk not in rate_real and continuing and prev_rate_text:
                rate_real[rk] = prev_rate_text
                r["rate_carried_over_page_break"] = True
            if not r["rate_raw"] and rk in rate_real:
                r["rate_raw"] = rate_real[rk]
                r["rate_carried_over_page_break"] = True
        if r["rate_raw"]:
            prev_rate_text = r["rate_raw"]
        prev_rate_open = bool(r.get("rate_bottom_open"))
        prev_pt = pt
    for r in rows:
        if r.get("row_kind") == "unparsed_block":
            continue
        k = r.get("cond_key")
        r["conditions"] = clean(" ".join(cond_text.get(k, []))) if k else ""
    return rows


def classify(r):
    desc, pct, rate = r.get("description", ""), r.get("pct_raw", ""), r.get("rate_raw", "")
    if r.get("is_header") or HEADER_WORDS.match(desc) or HEADER_WORDS.match(pct) or HEADER_WORDS.match(rate):
        if not norm_codes(pct)[0]:
            return "table_header"
    if re.fullmatch(r"\W*(\(?[ivx]+\)\s*)?omitted\W*", desc, re.I) or re.fullmatch(r"\W*omitted\W*", pct, re.I):
        return "omitted"
    codes, _, resp = norm_codes(pct)
    if codes or resp:
        return "item"
    if rate and (desc or pct):
        return "item_without_code"
    if desc:
        return "heading"
    return "empty"


def read_all():
    rows = finalize(build_rows(RAW / SOURCE))
    for r in rows:
        r["row_kind"] = r.get("row_kind") or classify(r)
    return rows


if __name__ == "__main__":
    import sys
    rows = read_all()
    pn = int(sys.argv[1]) if len(sys.argv) > 1 else None
    for r in rows:
        if pn is None or r["page"] == pn:
            print(r["page"], r["part"], r["table"], r.get("s_no"), r["row_kind"], "|", r.get("description", "")[:45], "|", r.get("pct_raw", ""), "|", r.get("rate_raw", ""), "|", (r.get("conditions") or "")[:30])
