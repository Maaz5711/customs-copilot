"""A3: Sales Tax Act 1990 - Third, Fifth, Eighth, Ninth and Twelfth Schedules.

Reads the two consolidated Act snapshots (FY2025-26 and FY2026-27) straight from the PDFs
(PyMuPDF, character boxes, so columns come from x positions), builds one row per
(serial x item x code entry), dates the rows by comparing the two snapshots, runs the
validators and writes the CSV/JSON outputs plus the failure and spot-check files.

Run:  PYTHONIOENCODING=utf-8 .venv/Scripts/python src/ingest/a3_st_other.py
Nothing here is typed from memory: every rate / code comes from a parsed PDF cell.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
IMG = OUT / "page_images"

FILES = {
    "FY2025-26": "202586148252375SalesTaxActupdatedupto2025-26.pdf",
    "FY2026-27": "20267171373418951SalesTaxAct1990updatedupto30.06.2026.pdf",
}
# 1-based inclusive PDF page ranges (found by searching the schedule headings).
RANGES = {
    "FY2025-26": {"third": (134, 137), "fifth": (137, 141), "eighth": (205, 216),
                  "ninth": (217, 219), "twelfth": (226, 228)},
    "FY2026-27": {"third": (143, 148), "fifth": (149, 152), "eighth": (205, 214),
                  "ninth": (215, 217), "twelfth": (225, 227)},
}
SNAP_FROM = {"FY2025-26": "2025-07-01", "FY2026-27": "2026-07-01"}
SNAP_TO = {"FY2025-26": "2026-06-30", "FY2026-27": "9999-12-31"}
OPEN = "9999-12-31"
SCOPE_START = "2025-07-01"
TARIFF = {"FY2025-26": OUT / "tariff_2025_26.json", "FY2026-27": OUT / "tariff_2026_27.json"}

COLS = ["rule_id", "tax", "schedule_or_section", "s_no", "description", "code_raw", "code_norm",
        "match_level", "except_codes", "unparsed_except_text", "rule_group", "rate_kind", "rate_pct",
        "rate_specific_amount", "rate_specific_unit", "rate_raw", "condition_text", "charged_on",
        "valid_from", "valid_to", "date_basis", "snapshot", "footnote", "source_file", "page", "clause",
        "status", "issues", "extraction_method"]

log_omitted: list[dict] = []     # omitted serials (report only)
log_serial: list[dict] = []      # serial continuity notes
log_counts: list[dict] = []      # parser vs page-text reconciliation


# --------------------------------------------------------------------------- word extraction
class W:
    __slots__ = ("t", "x0", "x1", "y", "size", "page", "marker")

    def __init__(self, t, x0, x1, y, size, page, marker=False):
        self.t, self.x0, self.x1, self.y, self.size, self.page, self.marker = t, x0, x1, y, size, page, marker

    def key(self):
        return (self.page, round(self.y), self.x0)


def page_words(doc, pno):
    """Return (body_words, footnotes{num:text}) for 1-based page pno."""
    pg = doc[pno - 1]
    raw = pg.get_text("rawdict")
    words: list[W] = []
    foot: list[tuple[float, float, str, float]] = []   # y, x, text, size
    for b in raw["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                size = s["size"]
                cur, cx0, cx1 = "", None, None
                chars = s["chars"]
                for ch in chars + [{"c": " ", "bbox": (0, 0, 0, 0)}]:
                    c = ch["c"]
                    if c.strip() == "":
                        if cur:
                            words.append(W(cur, cx0, cx1, s["origin"][1], size, pno))
                        cur, cx0 = "", None
                    else:
                        if cx0 is None:
                            cx0 = ch["bbox"][0]
                        cx1 = ch["bbox"][2]
                        cur += c
    # footnote zone: first token (x<135, 3-4 digits, small, low on the page) that is followed on (about) the
    # same line by a word starting with a letter
    def fn_start(w, ws_sorted):
        if not (w.x0 < 135 and re.fullmatch(r"\d{3,4}", w.t) and w.y > 420 and w.size < 9):
            return False
        for o in ws_sorted:
            if o is not w and abs(o.y - w.y) <= 4.5 and 0 < o.x0 - w.x0 < 20 and re.match(r"[A-Za-z\"“]", o.t):
                return True
        return False

    wsorted = sorted(words, key=lambda w: (w.y, w.x0))
    zone_y = None
    for w in wsorted:
        if fn_start(w, wsorted):
            zone_y = w.y - 3
            break
    body, fwords = [], []
    for w in words:
        if w.y > 700 or w.y < 55:          # running head / page number
            continue
        if zone_y is not None and w.y >= zone_y:
            fwords.append(w)
        else:
            body.append(w)
    fn: dict[str, str] = {}
    cur, last = None, None
    for w in sorted(fwords, key=lambda w: (w.y, w.x0)):
        if w.x0 < 135 and re.fullmatch(r"\d{3,4}", w.t) and w.size < 9 and (last is None or int(w.t) - last in (1, 2, 3)):
            cur, last = w.t, int(w.t)
            fn[cur] = ""
        elif cur:
            fn[cur] = (fn[cur] + " " + w.t).strip()
    # markers: small tokens: digits (optionally followed by '[') or glued 'digits[serial'
    med = sorted(w.size for w in body)[len(body) // 2] if body else 10
    out = []
    for w in body:
        small = w.size < 0.8 * med
        m = re.fullmatch(r"(\d{1,4})\[(\d{1,3}[A-Z]?\.?)", w.t)
        if m:
            mk = W(m.group(1), w.x0, w.x0, w.y, w.size, pno, True)
            out.append(mk)
            w.t = m.group(2)
            w.x0 += 8
            out.append(w)
            continue
        if (small and re.fullmatch(r"\d{1,4}\[?", w.t)) or (w.x0 < 150 and re.fullmatch(r"\d{3,4}\[?", w.t)):
            w.marker = True
            w.t = re.sub(r"\D", "", w.t)
        elif w.t in ("th", "st", "nd", "rd") and out and w.size < out[-1].size - 0.5:
            out[-1].t += w.t
            continue
        out.append(w)
    return out, fn


def header_cut(ws):
    """Drop everything above and including the column-number row '(1) (2) (3)..' (first such row)."""
    byy = defaultdict(list)
    for w in ws:
        if re.fullmatch(r"\(\d\)", w.t) and w.x0 < 470:
            byy[round(w.y / 3.0)].append(w)
    for k in sorted(byy):
        row = byy[k]
        if len(row) >= 2 and any(w.t == "(1)" for w in row) and any(w.t == "(2)" for w in row):
            ycut = max(w.y for w in row) + 4
            return [w for w in ws if w.y > ycut]
    return ws


STOP: dict = {}


def stream(doc, rng, stop_re=None):
    """All body words in reading order for pages in range plus footnote dict.
    stop_re: stop (exclusive) at the first word matching it."""
    allw, fn = [], {}
    for p in range(rng[0], rng[1] + 1):
        ws, f = page_words(doc, p)
        fn.update(f)
        ws.sort(key=lambda w: (round(w.y / 2.0), w.x0))
        stop = None
        if stop_re:
            for i, w in enumerate(ws):
                if re.search(stop_re, w.t):
                    stop = i
                    break
            if stop is not None:
                STOP[("%d" % rng[0], doc.name)] = p
                ws = ws[:stop]
        ws = header_cut(ws)
        allw += ws
        if stop is not None:
            break
    allw.sort(key=lambda w: (w.page, round(w.y / 2.0), w.x0))
    return allw, fn


def fix_serials(allw, xmax):
    """Re-join serial numbers that the text layer split ('[8' + '1.', '73' + '.', '66' + 'A')."""
    idx = [i for i, w in enumerate(allw) if w.x0 < xmax and not w.marker]
    drop = set()
    prev = 0
    k = 0
    while k < len(idx):
        i = idx[k]
        a = allw[i]
        m = re.fullmatch(r"\[?(\d{1,3})([A-Z]?)", a.t)
        if m and k + 1 < len(idx):
            j = idx[k + 1]
            b = allw[j]
            if b.page == a.page and 0 < b.y - a.y < 24 and b.x0 <= a.x0 + 3:
                mb = re.fullmatch(r"(\d*)\.?", b.t)
                if mb and mb.group(0) == "":
                    mb = None
                mc = re.fullmatch(r"[A-Z]", b.t)
                if mb and not m.group(2) and (int(m.group(1)) <= prev or mb.group(0) == "."):
                    a.t = m.group(1) + mb.group(1) + m.group(2) + "."
                    drop.add(j)
                    k += 1
                elif mc and not m.group(2):
                    a.t = m.group(1) + b.t + "."
                    drop.add(j)
                    k += 1
        mm = re.fullmatch(r"\[?(\d{1,3})[A-Z]?\.?", allw[i].t)
        if mm:
            prev = int(mm.group(1))
        k += 1
    return [w for i, w in enumerate(allw) if i not in drop]


# --------------------------------------------------------------------------- helpers
def clean(s: str) -> str:
    s = s.replace("’", "'")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def strip_br(s: str) -> str:
    s = re.sub(r"[\[\]]", "", s)
    return clean(s)


def join(ws):
    return clean(" ".join(w.t for w in sorted(ws, key=lambda w: (w.page, round(w.y / 2.0), w.x0))))


ITEM_RE = re.compile(r"^\(([ivxIVX]+|[a-z])\)$")
SER_RE = re.compile(r"^\[?(\d{1,3}[A-Z]?)\.?$")


def blocks_by_serial(allw, serial_x_max, stop_re=None):
    """Split the stream into blocks that start at a serial-number token in the serial column."""
    allw = fix_serials(allw, serial_x_max)
    blocks, cur = [], None
    pending_markers = []
    for i, w in enumerate(allw):
        if w.x0 < serial_x_max and not w.marker and SER_RE.match(w.t) and (
                i == 0 or True):
            m = SER_RE.match(w.t)
            sn = m.group(1)
            # a serial token must not be a number inside text; col check suffices, plus leading-digit check
            cur = {"s_no": sn, "words": [], "page": w.page, "y": w.y, "markers": list(pending_markers)}
            pending_markers = []
            blocks.append(cur)
            continue
        if w.marker and w.x0 < serial_x_max + 25:
            # marker just before a serial (same y) or inline marker in the serial column
            nxt = allw[i + 1] if i + 1 < len(allw) else None
            if nxt is not None and nxt.page == w.page and abs(nxt.y - w.y) < 6 and nxt.x0 < serial_x_max and SER_RE.match(nxt.t) and not nxt.marker:
                pending_markers.append(w.t)
                continue
        if cur is None:
            continue
        cur["words"].append(w)
    for b in blocks:
        sc = b["s_no"] + " " + " ".join(w.t for w in b["words"] if w.x0 < serial_x_max and not w.marker)
        m_ = re.search(r"(\d+)\s*(?:to|&|and)\s*(\d+)", sc)
        b["range"] = (int(re.match(r"\d+", b["s_no"]).group(0)), int(m_.group(2))) if m_ else None
    # text-layer quirk: a serial token can sit a few points BELOW the first line of its own row
    # ('(i)' or '***' printed just above the serial). Move such dangling words to the next block.
    sizes = sorted(w.size for w in allw if not w.marker)
    dang_max = 1.2 * (sizes[len(sizes) // 2] if sizes else 10)
    for bi in range(len(blocks) - 1):
        a, bnext = blocks[bi], blocks[bi + 1]
        dang = [w for w in a["words"] if w.page == bnext["page"] and 0 < bnext["y"] - w.y <= dang_max and w.x0 >= serial_x_max
                and not (a["page"] == w.page and abs(w.y - a["y"]) <= 2.5)]
        if dang:
            first = sorted(dang, key=lambda w: (w.y, w.x0))[0]
            only_stars = all(re.fullmatch(r"[\*\]\[\.]+", w.t) for w in dang)
            if ITEM_RE.match(first.t) and first.t in ("(i)", "(a)", "(1)") or only_stars:
                ids = {id(w) for w in dang}
                a["words"] = [w for w in a["words"] if id(w) not in ids]
                bnext["words"] = dang + bnext["words"]
    return blocks


def dedupe(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def footnote_text(nums, fn):
    parts = []
    for n in dedupe(nums):
        if n in fn:
            parts.append(f"[{n}] {fn[n]}")
    return " | ".join(parts)


def is_omitted(desc: str) -> bool:
    d = re.sub(r"[\[\]\*\.\s;,]", "", desc.lower())
    return d == "" or d.startswith("omitted")


# --------------------------------------------------------------------------- code parsing
CODE8 = re.compile(r"\b(\d{4})\.(\d{4})\b")
HEAD4 = re.compile(r"\b(\d{2})\.(\d{2})\b")


def parse_codes(cell: str):
    """Return list of dicts (code_raw, code_norm, match_level, note)."""
    cell = clean(cell)
    s = strip_br(cell)
    out = []
    if not s:
        return [dict(code_raw="", code_norm="", match_level="all", note="no_code_in_cell")]
    # chapters
    for m in re.finditer(r"[Cc]hapter\s+(\d{1,2})", s):
        out.append(dict(code_raw=m.group(0), code_norm=m.group(1).zfill(2), match_level="chapter2", note=""))
    rest = re.sub(r"[Cc]hapter\s+\d{1,2}", " ", s)
    tokens = []
    for m in CODE8.finditer(rest):
        tokens.append((m.start(), m.group(0), m.group(1) + m.group(2), "code8"))
    consumed = [(m.start(), m.end()) for m in CODE8.finditer(rest)]
    for m in HEAD4.finditer(rest):
        if any(a <= m.start() < b for a, b in consumed):
            continue
        tokens.append((m.start(), m.group(0), m.group(1) + m.group(2), "heading4"))
    for _, raw, norm, lvl in sorted(tokens):
        out.append(dict(code_raw=raw, code_norm=norm, match_level=lvl, note=""))
    low = s.lower()
    if "respective" in low:
        if out:
            for o in out:
                o["note"] = "respective_sub_headings"
        else:
            out.append(dict(code_raw=s, code_norm="", match_level="all", note="respective_heading"))
    if not out:
        out.append(dict(code_raw=s, code_norm="", match_level="all", note="no_code_in_cell"))
    return out


# --------------------------------------------------------------------------- rate parsing
def parse_rate(raw: str):
    r = strip_br(raw)
    r = clean(re.sub(r"[”\"];?|\s+and$", "", r)).rstrip(";")
    d = dict(rate_kind="conditional", rate_pct=None, rate_specific_amount=None, rate_specific_unit=None, rate_raw=r, flags=[])
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*%\s*\.?", r)
    if m:
        d.update(rate_kind="percent", rate_pct=float(m.group(1)))
        return d
    m = re.search(r"Rs\.?\s*([\d,]+(?:\.\d+)?)\s*(per\s+[a-zA-Z ]+?)(?:\s+or\b|$)", r)
    pct = re.search(r"(\d+(?:\.\d+)?)\s*%", r)
    # compound / alternative rates cannot be stored as percent or specific (store schema): kept as conditional + rate_raw
    if m and pct:
        d["flags"].append("compound rate: %s%% and Rs %s %s (%s)" % (pct.group(1), m.group(1), m.group(2).strip(),
                          "whichever is higher" if "higher" in r else "in addition" if "along" in r else "see rate_raw"))
    elif m:
        d["flags"].append("specific rate: Rs %s %s inside a conditional rate text" % (m.group(1), m.group(2).strip()))
    return d


# --------------------------------------------------------------------------- generic row maker
def new_row(**kw):
    r = {c: "" for c in COLS}
    r.update(tax="ST", except_codes="[]", unparsed_except_text=0, status="accepted", issues="",
             extraction_method="text_layer(pymupdf chars, x-columns)+vision_check")
    r.update(kw)
    return r


def add_issue(r, txt, note=False):
    txt = txt.replace(";", ",")
    tag = ("note:" if note else "") + txt
    r["issues"] = (r["issues"] + "; " + tag).strip("; ") if r["issues"] else tag
    if not note:
        r["status"] = "needs_review"


# --------------------------------------------------------------------------- THIRD schedule
def parse_third(doc, snap):
    rng = RANGES[snap]["third"]
    allw, fn = stream(doc, rng)
    # stop at FOURTH SCHEDULE / Note
    cut = None
    for i, w in enumerate(allw):
        if w.t == "Note:" and w.x0 < 140:
            cut = i
            break
    for i, w in enumerate(allw):
        if w.t in ("FOURTH", "FIFTH") and (cut is None or i < cut):
            cut = i
            break
    note_txt = ""
    if cut is not None:
        note_w = [w for w in allw[cut:] if not (w.t in ("FOURTH", "FIFTH"))]
        nt = join(note_w)
        mn = re.match(r"Note:(.*?)(The.*)?$", nt)
        note_txt = clean("Note: " + (mn.group(1) if mn else nt)) if nt.startswith("Note") else ""
        allw = allw[:cut]
        while allw and (allw[-1].marker or allw[-1].t in ("The", "[", "]")):
            allw.pop()
    blocks = blocks_by_serial(allw, 165)
    SERIALS[("third", snap)] = [(b["s_no"], b["page"], b.get("range")) for b in blocks]
    rows = []
    src = FILES[snap]
    for b in blocks:
        sn = b["s_no"]
        ws = b["words"]
        desc_w = [w for w in ws if 165 <= w.x0 < 310 and not w.marker]
        head_w = [w for w in ws if w.x0 >= 310 and not w.marker]
        mk = b["markers"] + [w.t for w in ws if w.marker]
        desc, head = strip_br(join(desc_w)), join(head_w)
        desc = clean(re.sub(r"(?<!\S)\*+(?!\S)", " ", desc))
        fnt = footnote_text(mk, fn)
        if is_omitted(desc) and not CODE8.search(head) and not HEAD4.search(head):
            log_omitted.append(dict(schedule="Third", snapshot=snap, s_no=sn, page=b["page"], text=desc, footnote=fnt))
            continue
        # leftover 'omitted' prose inside description (serial 50)
        omitted_note = "omitted with effect" in desc
        entries = parse_codes(head)
        for e in entries:
            r = new_row(schedule_or_section="Third Schedule", condition_text=note_txt, s_no=sn, description=desc, code_raw=e["code_raw"],
                        code_norm=e["code_norm"], match_level=e["match_level"], rule_group="ST-3RD",
                        rate_kind="conditional", rate_raw="retail price basis (s.3(2)(a))",
                        charged_on="retail price (Third Schedule goods, s.3(2)(a))",
                        footnote=fnt, source_file=src, page=b["page"],
                        clause=f"Third Schedule, S.No {sn}, col 3", snapshot=snap)
            if e["note"] == "respective_heading":
                add_issue(r, "respective_heading: scope given by description only (no code in cell)", note=True)
            elif e["note"] == "respective_sub_headings":
                add_issue(r, "respective_sub_headings: cell says 'Respective sub-headings of'; mapped to the named heading", note=True)
            if re.search(r"\bexcept|excluding", desc, re.I):
                add_issue(r, "except_phrase_in_description: " + re.search(r"(except[^.]*|excluding[^.]*)", desc, re.I).group(0)[:120], note=True)
                r["unparsed_except_text"] = 1
            if omitted_note:
                add_issue(r, "serial_text_says_omitted: description says omitted w.e.f. 1 Dec 2021")
            rows.append(r)
    return rows


# --------------------------------------------------------------------------- FIFTH schedule
SERIALS: dict = {}


def fix_ordinal_fn(txt: str) -> str:
    m = re.match(r"^(th|st|nd|rd)\s+(.*)$", txt)
    if not m:
        return txt
    rest = m.group(2)
    rest2 = re.sub(r"\b(\d{1,2})(\s+)(?=(January|February|March|April|May|June|July|August|September|October|November|December))",
                   lambda mm: mm.group(1) + m.group(1) + mm.group(2), rest, count=1)
    return rest2


def parse_fifth(doc, snap):
    rng = RANGES[snap]["fifth"]
    allw, fn = stream(doc, rng)
    fn = {k: fix_ordinal_fn(v) for k, v in fn.items()}
    st = 0
    for i, w in enumerate(allw):
        if w.t.startswith("4]"):
            st = i + 1
            break
    allw = allw[st:]
    blocks = blocks_by_serial(allw, 160)
    SERIALS[("fifth", snap)] = [(b["s_no"], b["page"], b.get("range")) for b in blocks]
    rows = []
    src = FILES[snap]
    for b in blocks:
        sn = b["s_no"]
        if not re.fullmatch(r"\d{1,2}[A-Z]?", sn):
            continue
        ws = [w for w in b["words"] if not w.marker]
        mk = b["markers"] + [w.t for w in b["words"] if w.marker]
        text = strip_br(join(ws))
        text = clean(re.sub(r"^(\*+\s*|\.\s*)+", "", text))
        fnt = footnote_text(mk, fn)
        t = re.sub(r"[\*\.\s]+", " ", text).strip().lower()
        if t in ("", "omitted") or t.startswith("omitted") or text.lower().startswith(("omitted", "***omitted")):
            log_omitted.append(dict(schedule="Fifth", snapshot=snap, s_no=sn, page=b["page"], text=text, footnote=fnt))
            continue
        pieces = [(sn, text, "")]
        if sn == "12":
            m = re.search(r"\((xxiii)\)\s*(.*)$", text)
            if m:
                lead = text[:m.start()].strip()
                k = lead.find(":--")
                lead = lead[:k + 3] if k >= 0 else lead
                tail = re.split(r"\(xxiv\)", m.group(2))[0].strip()
                pieces = [(sn + "(xxiii)", clean(lead + " (xxiii) " + tail), "clause (xxiii)")]
        for (s_no, tx, sub) in pieces:
            codes = []
            for m2 in re.finditer(r"(?:PCT\s*)?heading\s+(\d{4}\.\d{4})", tx):
                codes.append((m2.group(1), "code8"))
            if not codes:
                codes = [("", "unmapped")]
            for (c, lvl) in codes:
                r = new_row(schedule_or_section="Fifth Schedule", s_no=s_no, description=tx,
                            code_raw=c, code_norm=c.replace(".", "") if c else "",
                            match_level=lvl, rule_group="ST-5TH", rate_kind="percent", rate_pct=0.0,
                            rate_raw="zero per cent (s.4(a): goods specified in the Fifth Schedule are charged at the rate of zero per cent)",
                            condition_text=tx, charged_on="", footnote=fnt, source_file=src, page=b["page"],
                            clause=f"Fifth Schedule, S.No {sn}" + (f" {sub}" if sub else "") + "; rate: Sales Tax Act s.4(a)", snapshot=snap)
                if lvl == "unmapped":
                    add_issue(r, "no_code: supply/class based entry (no PCT heading in the text)", note=True)
                    r["code_norm"] = None
                if sn == "12":
                    add_issue(r, "serial 12 lists goods; every clause except (xxiii) is omitted in this snapshot", note=True)
                rows.append(r)
    return rows


# --------------------------------------------------------------------------- EIGHTH schedule
ITEM_RE = re.compile(r"^\(([ivxIVX]+|[a-z])\)$")


E8COLS_SER = {"FY2025-26": 160, "FY2026-27": 168}
E8COLS = {"FY2025-26": (160, 262, 331, 384), "FY2026-27": (168, 268, 340, 388)}


def parse_eighth(doc, snap):
    rng = RANGES[snap]["eighth"]
    c_ser, c_desc, c_head, c_rate = E8COLS[snap]
    allw, fn = stream(doc, rng, stop_re=r"Table\s*-?\s*2")
    blocks = blocks_by_serial(allw, c_ser)
    SERIALS[("eighth", snap)] = [(b["s_no"], b["page"], b.get("range")) for b in blocks]
    rows = []
    src = FILES[snap]
    for b in blocks:
        sn = b["s_no"]
        ws = b["words"]
        mk = b["markers"] + [w.t for w in ws if w.marker]
        fnt = footnote_text(mk, fn)
        body = [w for w in ws if not w.marker]
        desc_w = [w for w in body if c_ser <= w.x0 < c_desc]
        head_w = [w for w in body if c_desc <= w.x0 < c_head]
        rate_w = [w for w in body if c_head <= w.x0 < c_rate]
        cond_w = [w for w in body if w.x0 >= c_rate]
        # omitted serials: description begins with *** / [..........] / omitted
        dtxt = strip_br(join(desc_w))
        first = [w.t for w in sorted(desc_w, key=lambda w: (w.page, round(w.y / 2.0), w.x0))][:3]
        if not dtxt or any(re.search(r"\*\*\*|\.\.\.\.|omitted", t, re.I) for t in first):
            log_omitted.append(dict(schedule="Eighth", snapshot=snap, s_no=sn, page=b["page"], text=join(body), footnote=fnt))
            continue
        # items
        items = [w for w in desc_w if ITEM_RE.match(w.t) and w.x0 < c_ser + 12]
        lead_end = items[0].key() if items else None
        def rng_words(cols, i):
            a = items[i].key()
            z = items[i + 1].key() if i + 1 < len(items) else None
            res = []
            for w in cols:
                k = (w.page, round(w.y), w.x0)
                if k >= (a[0], a[1] - 2, 0) and (z is None or k < (z[0], z[1] - 2, 0)):
                    res.append(w)
            return res
        recs = []
        if not items:
            recs.append(dict(item="", desc=dtxt, head=join(head_w), rate=join(rate_w), cond=join(cond_w)))
        else:
            lead = [w for w in desc_w if (w.page, round(w.y), w.x0) < (items[0].page, round(items[0].y) - 2, 0)]
            leadtxt = strip_br(join(lead))
            nheads = len(CODE8.findall(join(head_w))) + len(HEAD4.findall(join(head_w)))
            per_item_codes = nheads >= len(items)
            for i, it in enumerate(items):
                dw = rng_words(desc_w, i)
                itxt = strip_br(join(dw))
                hw = rng_words(head_w, i) if per_item_codes else head_w
                recs.append(dict(item=it.t.strip("()"), desc=(leadtxt + " " + itxt).strip(), head=join(hw), rate=join(rate_w), cond=join(cond_w), lead=leadtxt))
            if per_item_codes and sn == "73":
                # codes/rates of (a) are printed at the top of the next page; assign in reading order
                hs = [join([w]) for w in sorted(head_w, key=lambda w: (w.page, round(w.y), w.x0))]
                rs = [join([w]) for w in sorted(rate_w, key=lambda w: (w.page, round(w.y), w.x0))]
                if len(hs) == len(items) == len(rs):
                    for i, rec in enumerate(recs):
                        rec["head"], rec["rate"] = hs[i], rs[i]
                        rec["note73"] = True
                else:
                    for rec in recs:
                        rec["bad73"] = True
        for rec in recs:
            desc = strip_br(rec["desc"])
            entries = parse_codes(rec["head"])
            rate = parse_rate(rec["rate"])
            cond = strip_br(rec["cond"])
            for e in entries:
                r = new_row(schedule_or_section="Eighth Schedule Table-1", s_no=sn + (("(" + rec["item"] + ")") if rec["item"] else ""),
                            description=desc, code_raw=e["code_raw"], code_norm=e["code_norm"], match_level=e["match_level"],
                            rule_group="ST-8TH-T1", rate_kind=rate["rate_kind"], rate_pct=rate["rate_pct"],
                            rate_specific_amount=rate["rate_specific_amount"], rate_specific_unit=rate["rate_specific_unit"],
                            rate_raw=rate["rate_raw"], condition_text=cond, footnote=fnt, source_file=src, page=b["page"],
                            clause=f"Eighth Schedule Table-1, S.No {sn}" + (f" item ({rec['item']})" if rec["item"] else "") + ", cols 2-5",
                            snapshot=snap)
                r["_sn_base"] = sn
                if e["note"] in ("respective_heading", "respective_sub_headings"):
                    add_issue(r, e["note"] + ": scope given by description only", note=True)
                for fl in rate["flags"]:
                    add_issue(r, fl + " - store schema has no compound kind, kept as conditional with rate_raw verbatim", note=True)
                if rec.get("bad73"):
                    add_issue(r, "serial 73 rate/code alignment could not be paired by reading order")
                if rec.get("note73"):
                    add_issue(r, "serial 73: one merged cell prints 'codes 87.03 / 87.03' and 'rates 8.5%. / 12.75%' for items (a) and (b); they are paired in printed order (a)=8.5%, (b)=12.75%. The rate column is a single column, not two (checked on the page image)", note=True)
                    r["condition_text"] = clean((r["condition_text"] + " Rate cell prints two values for items (a) and (b) in order: 8.5%. then 12.75%.").strip())
                if sn == "84" and rec["item"] == "i":
                    add_issue(r, "vision_mismatch: on the page image the rate cell next to item (i) is blank and the printed 10% sits in a merged cell beside items (ii)-(vii); text layer assigns 10% to the whole serial 84, so 84(i) is 10% only if the merged cell is meant to cover it")
                rows.append(r)
    return rows


# --------------------------------------------------------------------------- NINTH schedule
def parse_ninth(doc, snap):
    rng = RANGES[snap]["ninth"]
    src = FILES[snap]
    pages = {}
    allfn = {}
    for p in range(rng[0], rng[1] + 1):
        ws, fn = page_words(doc, p)
        pages[p] = ws
        allfn.update(fn)
    rows = []
    # ---- Table-I (SIM cards): reported only (switched off from 1 July 2020 by its proviso)
    for p, ws in pages.items():
        txt = join(ws)
        if "Subscriber Identification" in txt:
            prov = re.search(r"Provided that the provisions of Table-I shall not be applicable from [^.]*\.", txt)
            amt = re.search(r"Rs\.\s*(\d+)", txt)
            log_omitted.append(dict(schedule="Ninth Table-I", snapshot=snap, s_no="1", page=p,
                                    text="SIM cards, sales tax on supply by CMOs Rs. %s; %s" % (amt.group(1) if amt else "?", prov.group(0) if prov else ""),
                                    footnote="Table-I switched off from 1 July 2020 by its proviso; not a rule in FY2025-26 / FY2026-27"))
    # ---- Table-II by columns
    t2page = None
    for p, ws in pages.items():
        if any(w.t == "A." and w.x0 < 175 for w in ws) and any(w.t == "B." and w.x0 < 175 for w in ws):
            t2page = p
            break
    if t2page is None:
        r = new_row(schedule_or_section="Ninth Schedule Table-II", s_no="1", description="Table-II not found", rule_group="ST-9TH-T2",
                    source_file=src, page=rng[0], snapshot=snap, clause="Ninth Schedule Table-II", rate_kind="conditional", match_level="all")
        add_issue(r, "table_not_found")
        return [r]
    ws = pages[t2page]
    A = next(w for w in ws if w.t == "A." and w.x0 < 175)
    B = next(w for w in ws if w.t == "B." and w.x0 < 175)
    L = next((w for w in ws if w.t.startswith("LIABILITY")), None)
    yend = L.y - 4 if L else B.y + 40

    def region(y0, y1):
        return [w for w in ws if y0 - 3 <= w.y < y1 - 3 and not w.marker]
    cols = [("col 3", "CBU phones: sales tax at the time of import or registration (IMEI number by CMOs)", 262, 340),
            ("col 4", "CKD/SKD phones: sales tax on import", 340, 410),
            ("col 5", "locally manufactured phones in CBU condition: sales tax on supply, in addition to tax under column (4)", 410, 700)]
    full_t2 = join([w for w in ws if w.y > 100])
    lead = re.search(r"Cellular mobile phones or satellite phones to be charged on the basis of import value per set, or equivalent value in rupees in case of supply by the manufacturer, at the rate as indicated against each category:--?", full_t2)
    leadtxt = lead.group(0) if lead else "Cellular mobile phones or satellite phones charged on import value per set"
    fkeys = [k for k in allfn if "Table-II" in allfn[k] and "substituted" in allfn[k]]
    for band, (a0, a1) in (("A", (A.y, B.y)), ("B", (B.y, yend))):
        rw = region(a0, a1)
        dtxt = join([w for w in rw if 160 <= w.x0 < 262])
        for colname, colmean, x0, x1 in cols:
            ct = join([w for w in rw if x0 <= w.x0 < x1])
            pm = re.fullmatch(r"(\d+(?:\.\d+)?)%\s*ad valorem", ct)
            r = new_row(schedule_or_section="Ninth Schedule Table-II", s_no="1." + band,
                        description="%s Category %s; %s" % (leadtxt, dtxt, colmean),
                        code_raw="", code_norm=None, match_level="unmapped", rule_group="ST-9TH-T2",
                        rate_kind="percent" if pm else "conditional", rate_pct=float(pm.group(1)) if pm else None,
                        rate_raw=ct, condition_text="Value band (import value per set): %s; applies to: %s" % (dtxt, colmean),
                        charged_on="import value per set (or equivalent value in rupees on supply by the manufacturer)",
                        source_file=src, page=t2page, clause="Ninth Schedule, Table-II, S.No 1, category %s, %s" % (band, colname), snapshot=snap,
                        footnote=footnote_text(fkeys, allfn))
            add_issue(r, "no_code: the Ninth Schedule names mobile phones by description only (PCT heads appear in Twelfth Schedule (2)(iv): 8517.1419, 8517.1430, 8517.1390)", note=True)
            add_issue(r, "rate is ad valorem percent of import value per set, not a rupee-per-set amount", note=True)
            if not pm:
                add_issue(r, "rate_parse: " + ct)
            rows.append(r)
    # ---- clause (vi) instalments (procedure, no rate)
    alltxt = " ".join(join(pages[q]) for q in sorted(pages))
    m = re.search(r"\(vi\)\s*(An individual liable to pay tax on imported mobile phone device.*?financial year in which the import is made\.)", alltxt)
    if m:
        pg = next((q for q in sorted(pages) if "An individual liable" in join(pages[q])), t2page)
        fk = [k for k in allfn if "sub-clause (vi)" in allfn[k]]
        rows.append(new_row(schedule_or_section="Ninth Schedule, Liability/Procedure/Conditions", s_no="(vi)",
                            description=strip_br(m.group(1)), code_raw="", code_norm=None, match_level="unmapped",
                            rule_group="ST-9TH-COND", rate_kind="conditional", rate_raw="instalment payment allowed (no rate)",
                            condition_text=strip_br(m.group(1)), source_file=src, page=pg,
                            clause="Ninth Schedule, Liability/Procedure/Conditions, clause (vi)", snapshot=snap,
                            footnote=footnote_text(fk, allfn)))
    return rows


# --------------------------------------------------------------------------- TWELFTH schedule
def parse_twelfth(doc, snap):
    rng = RANGES[snap]["twelfth"]
    allw, fn = stream(doc, rng)
    fn = {k: fix_ordinal_fn(v) for k, v in fn.items()}
    src = FILES[snap]
    for i, w in enumerate(allw):
        if "THIRTEENTH" in w.t:
            allw = allw[:i]
            break
    i1 = next(i for i, w in enumerate(allw) if w.t == "1." and w.x0 < 175)
    ip = next(i for i, w in enumerate(allw) if w.t == "Procedure")
    trow = allw[i1 + 1:ip]
    d = join([w for w in trow if w.x0 < 320])
    h = join([w for w in trow if 320 <= w.x0 < 388])
    rt = join([w for w in trow if w.x0 >= 388])
    rows = []
    pm = re.fullmatch(r"(\d+(?:\.\d+)?)%\s*ad valorem", rt)
    r = new_row(schedule_or_section="Twelfth Schedule Table", s_no="1", description=d, code_raw=h, code_norm="", match_level="all",
                rule_group="ST-12TH", rate_kind="percent" if pm else "conditional", rate_pct=float(pm.group(1)) if pm else None,
                rate_raw=rt, condition_text="Levied and collected at import stage from importers on all taxable goods chargeable under s.3, in addition to the tax under s.3 (Procedure and conditions (1)); the exclusions in clause (2) apply.",
                charged_on="value of imported goods, ad valorem (s.7A(2); Procedure and conditions (1))", source_file=src,
                page=trow[0].page if trow else rng[0],
                clause="Twelfth Schedule, Table S.No 1, cols 2-4; Procedure and conditions (1)", snapshot=snap, footnote="")
    add_issue(r, "respective_heading: applies to all imported taxable goods; exclusions are separate rows", note=True)
    if not pm:
        add_issue(r, "rate_parse: " + rt)
    rows.append(r)

    body = allw[ip:]

    def tok(w):
        return ("{%s}" % w.t) if w.marker else w.t
    toks = [tok(w) for w in body]
    # character offset of each token in the joined string
    offs_tok, pos = [], 0
    for t in toks:
        offs_tok.append(pos)
        pos += len(t) + 1
    full = clean(" ".join(toks).replace("[", " ").replace("]", " "))
    # superscript markers sort just BEFORE their clause label; move them after it
    full = re.sub(r"((?:\{\d+\}\s*)+)\((i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv)\)", lambda m_: "(%s) %s" % (m_.group(2), m_.group(1).strip()), full)

    def page_at(p):
        pg = body[0].page
        for k, o in enumerate(offs_tok):
            if o <= p:
                pg = body[k].page
            else:
                break
        return pg
    i2 = full.find("(2) The value addition tax under this Schedule shall not be charged on")
    i3 = full.find("(3) The value addition tax paid at import stage")
    seg = full[i2:i3]
    parts = re.split(r"(?<![\w])\((i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv)\)\s+", seg)
    labels, texts = parts[1::2], parts[2::2]
    for lab, t0 in zip(labels, texts):
        k = seg.find("(%s) " % lab)
        pg = page_at(i2 + max(k, 0))
        sp = re.search(r"Provided that", t0)
        main0 = t0[:sp.start()] if sp else t0
        prov0 = t0[sp.start():] if sp else ""
        main = strip_br(re.sub(r"\{\d+\}", "", main0)).strip(" ;,")
        main = clean(re.sub(r"(?<!\S)\*+(?!\S)", " ", main))
        main = re.sub(r"[“”]", "", main).strip(" ;,")
        main = re.sub(r"[\s;]*and$", "", main).strip(" ;,")
        fnn = re.findall(r"\{(\d+)\}", main0)
        entries = []
        exc_codes = []
        mex = re.search(r"\bexcluding\b(.*)$", main)
        if mex:        # codes after 'excluding' are carved OUT of this exclusion (the 3% VAT still applies to them)
            exc_codes = [c.replace(".", "") for c in re.findall(r"\b(\d{4}\.\d{4})\b", mex.group(1))]
            codes_text = main[:mex.start()]
        else:
            codes_text = main
        for c in re.findall(r"\b(\d{4}\.\d{3,4})\b", codes_text):
            if re.fullmatch(r"\d{4}\.\d{4}", c):
                entries.append((c, c.replace(".", ""), "code8"))
            else:
                entries.append((c, c.replace(".", "")[:4], "heading4"))
        chm = re.search(r"Chapters?\s+(\d{1,2})(?:\s+and\s+(\d{1,2}))?", codes_text)
        if chm:
            for g in chm.groups():
                if g:
                    entries.append(("Chapter %s" % g, g.zfill(2), "chapter2"))
        if not entries:
            entries = [("", "", "all")]
        for craw, cn, lvl in entries:
            rr = new_row(schedule_or_section="Twelfth Schedule, Procedure and conditions (2)", s_no="(2)(%s)" % lab, description=main,
                         except_codes=json.dumps(exc_codes),
                         code_raw=craw, code_norm=cn, match_level=lvl, rule_group="ST-12TH-EXCL", rate_kind="exempt",
                         rate_raw="value addition tax under the Table is not charged on these goods/importers", condition_text=main,
                         charged_on="", footnote=footnote_text(fnn, fn), source_file=src, page=pg,
                         clause="Twelfth Schedule, Procedure and conditions (2)(%s)" % lab, snapshot=snap)
            if lvl == "all":
                add_issue(rr, "no_code: exclusion by class of goods/importer; scope given by description only", note=True)
            if lvl == "heading4" and not re.fullmatch(r"\d{4}\.\d{4}", craw):
                add_issue(rr, "code_format: %s has only 7 digits in the source; mapped to the 4-digit heading %s" % (craw, cn))
            rows.append(rr)
        if prov0:
            pm_t = strip_br(re.sub(r"\{\d+\}", "", prov0)).strip(" ;")
            fnn2 = re.findall(r"\{(\d+)\}", main0[-25:])
            pr = new_row(schedule_or_section="Twelfth Schedule, Procedure and conditions (2)(i) proviso", s_no="(2)(i) proviso",
                         description=pm_t, code_raw="", code_norm="", match_level="all", rule_group="ST-12TH-PROV", rate_kind="percent",
                         rate_pct=3.0, rate_raw="3% value addition tax of imports on an ad valorem basis, along with default surcharge",
                         condition_text=pm_t, charged_on="value of imports where the imported goods are supplied in the same state (same packing, repacked or in bulk)",
                         footnote=footnote_text(fnn2, fn), source_file=src, page=pg,
                         clause="Twelfth Schedule, Procedure and conditions (2)(i), proviso", snapshot=snap)
            add_issue(pr, "no_code: applies to the manufacturer's imports of raw materials/intermediary goods supplied in the same state; scope given by description only", note=True)
            rows.append(pr)
    m6 = re.search(r"\(6\)\s*(?:\{\d+\}\s*)?The rate of minimum value addition tax shall be (\d+)% in the case of import of coal, (.*?\.)", full)
    if m6:
        p6 = full.find("(6)")
        fk = re.findall(r"\{(\d+)\}", full[max(p6 - 30, 0): p6 + 12])
        rr = new_row(schedule_or_section="Twelfth Schedule, Procedure and conditions (6)", s_no="(6)",
                     description="Import of coal exclusively and directly supplied to Independent Power Producers",
                     code_raw="", code_norm="", match_level="all", rule_group="ST-12TH-COAL", rate_kind="percent",
                     rate_pct=float(m6.group(1)), rate_raw="%s%% (rate of minimum value addition tax on imported coal)" % m6.group(1),
                     condition_text=clean("The rate of minimum value addition tax shall be %s%% in the case of import of coal, %s" % (m6.group(1), m6.group(2))),
                     charged_on="value of imported coal (ad valorem)", footnote=footnote_text(fk, fn), source_file=src,
                     page=page_at(p6), clause="Twelfth Schedule, Procedure and conditions (6)", snapshot=snap)
        add_issue(rr, "no_code: coal named by description (no PCT heading in the clause)", note=True)
        rows.append(rr)
    return rows


# --------------------------------------------------------------------------- dating / merging
MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])}


def norm_sig(r):
    def n(x):
        return re.sub(r"[^a-z0-9%\.]", "", (x or "").lower())
    cond = "" if r["schedule_or_section"].startswith("Third") else r["condition_text"]   # Third: schedule-level Note only
    return (n(r["description"]), n(r["rate_raw"]), n(cond), n(r["code_raw"]))


def row_key(r):
    k = [r["schedule_or_section"], r["s_no"], r["code_norm"] or n_(r["code_raw"])]
    if r.get("_fy_variant"):
        k.append(r["_fy_variant"])
    return tuple(k)


def n_(x):
    return re.sub(r"[^a-z0-9]", "", (x or "").lower())


def stated_till(r):
    for fld in ("description", "condition_text"):
        m = re.search(r"till\s*(\d+)\s*(?:th|st|nd|rd)?\s*(\w+),?\s*(\d{4})", r[fld] or "", re.I)
        if m and m.group(2).lower() in MONTHS:
            return "%04d-%02d-%02d" % (int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))), m.group(0)
    return None, None


def fy_expand(rows):
    """Serial 89 style: rate printed per financial year '10% (for 2025-26)...'. Split into one row per FY."""
    out = []
    for r in rows:
        if r["schedule_or_section"].startswith("Eighth") and r["s_no"].startswith("89"):
            parts = re.findall(r"(\d+(?:\.\d+)?)%\s*\(for\s*(\d{4})-\s*(\d{2})\)", r["rate_raw"])
            if parts:
                for pc, y1, y2 in parts:
                    nr = dict(r)
                    nr["rate_pct"], nr["rate_kind"] = float(pc), "percent"
                    nr["rate_raw"] = f"{pc}% (for {y1}-{y2})"
                    nr["_fy_variant"] = f"{y1}-{y2}"
                    nr["_stated_from"] = f"{int(y1)}-07-01"
                    nr["_stated_to"] = f"{int(y1) + 1}-06-30"
                    nr["_stated_txt"] = f"rate column: '{pc}% (for {y1}-{y2})'"
                    out.append(nr)
                continue
        out.append(r)
    return out


def merge_snapshots(r25, r26):
    r25, r26 = fy_expand(r25), fy_expand(r26)
    d25 = defaultdict(list)
    d26 = defaultdict(list)
    for r in r25:
        d25[row_key(r)].append(r)
    for r in r26:
        d26[row_key(r)].append(r)
    keys = list(dict.fromkeys([row_key(r) for r in r25] + [row_key(r) for r in r26]))
    merged, changes = [], []
    for k in keys:
        a, b = d25.get(k, []), d26.get(k, [])
        for x in (a if not b else []):
            merged.append(date_single(x, "FY2025-26", only=True))
            changes.append(dict(kind="removed_in_FY2026-27", key=k, old=x, new=None))
        for y in (b if not a else []):
            merged.append(date_single(y, "FY2026-27", only=True))
            changes.append(dict(kind="added_in_FY2026-27", key=k, old=None, new=y))
        if a and b:
            # pair in order
            for i in range(max(len(a), len(b))):
                x = a[i] if i < len(a) else None
                y = b[i] if i < len(b) else None
                if x and y and norm_sig(x) == norm_sig(y):
                    nr = dict(y)
                    nr["snapshot"] = "both"
                    nr["footnote"] = y["footnote"] if y["footnote"] else x["footnote"]
                    nr = apply_dates(nr, both=True)
                    merged.append(nr)
                else:
                    if x:
                        merged.append(date_single(x, "FY2025-26", only=(y is None), changed=y is not None))
                    if y:
                        merged.append(date_single(y, "FY2026-27", only=(x is None), changed=x is not None))
                    if x and y:
                        changes.append(dict(kind="changed", key=k, old=x, new=y))
                    elif x:
                        changes.append(dict(kind="removed_in_FY2026-27", key=k, old=x, new=None))
                    else:
                        changes.append(dict(kind="added_in_FY2026-27", key=k, old=None, new=y))
    return merged, changes


def date_single(r, snap, only=False, changed=False):
    nr = dict(r)
    nr["snapshot"] = snap
    nr = apply_dates(nr, both=False, only=only, changed=changed)
    return nr


def apply_dates(r, both, only=False, changed=False):
    snap = r["snapshot"]
    if both:
        vf, vt, basis = SCOPE_START, OPEN, "snapshot: text identical in FY2025-26 and FY2026-27 snapshots (rule may be older than 2025-07-01)"
        if re.search(r"(inserted|added|substituted|new serial)[^|]*Finance Act,? 2025", r.get("footnote", ""), re.I):
            basis = "FA2025-convention: footnote says added/inserted/substituted by Finance Act 2025 (in force 2025-07-01 unless stated); " + basis
    elif snap == "FY2025-26":
        vf, vt = SCOPE_START, "2026-06-30"
        basis = "snapshot: present only in FY2025-26 snapshot" if only else "snapshot: text differs in FY2026-27 snapshot (changed)"
    else:
        vf, vt = "2026-07-01", OPEN
        basis = "snapshot: present only in FY2026-27 snapshot" if only else "snapshot: text differs from FY2025-26 snapshot (changed)"
        fn = r.get("footnote", "")
        if re.search(r"(inserted|added|substituted|new serial)[^|]*Finance Act,? 2026", fn, re.I):
            basis = "footnote says inserted/added/substituted by Finance Act 2026 -> in force 2026-07-01 (Finance Act 2026 s.1(2)); " + basis
        elif re.search(r"Finance Act,? 2025", fn, re.I) and snap == "FY2026-27":
            basis += "; footnote cites Finance Act 2025"
    if r.get("_stated_from"):
        vf = max(vf, r["_stated_from"]) if r["_stated_from"] > vf else vf
        vt = min(vt, r["_stated_to"]) if r["_stated_to"] < vt else vt
        basis = r["_stated_txt"] + " ; " + basis
        if r["_stated_from"] < vf:
            pass
    till, ttxt = stated_till(r)
    if till:
        if till < vt:
            vt = till
        basis = f"stated sunset in row text: '{ttxt}' ; " + basis
    if vt < vf:
        r["_expired"] = vt
    r["valid_from"], r["valid_to"], r["date_basis"] = vf, vt, basis
    if r.get("_table1_dead"):
        r["valid_from"], r["valid_to"] = SCOPE_START, SCOPE_START
        r["valid_to"] = SCOPE_START
        r["date_basis"] = "Table-I proviso: not applicable from 1 July 2020 onwards, i.e. no tax in scope; row kept with a zero-length valid range for completeness"
        r["status"] = "needs_review"
        add_issue(r, "table_I_switched_off_by_proviso: store loader should not treat this row as an active rule")
    return r


# --------------------------------------------------------------------------- validators
def load_tariffs():
    t = {}
    for snap, p in TARIFF.items():
        j = json.load(open(p, encoding="utf-8"))
        t[snap] = (set(x["code"] for x in j["rows"]), set(x["heading"] for x in j["headings"]))
    return t


def validate(rows, tariffs):
    for r in rows:
        snaps = ["FY2025-26", "FY2026-27"] if r["snapshot"] == "both" else [r["snapshot"]]
        cn, lvl = r["code_norm"], r["match_level"]
        raw = r["code_raw"]
        if lvl == "code8":
            ok = [cn[:4] + "." + cn[4:] in tariffs[s][0] for s in snaps]
            if not all(ok):
                add_issue(r, "code_not_in_tariff: " + raw + " (" + ",".join(s for s, o in zip(snaps, ok) if not o) + ")")
        elif lvl == "heading4":
            ok = [(cn[:2] + "." + cn[2:] in tariffs[s][1]) or any(c.startswith(cn[:2] + cn[2:] ) or c.replace(".", "").startswith(cn) for c in tariffs[s][0]) for s in snaps]
            if not all(ok):
                add_issue(r, "code_not_in_tariff: heading " + raw + " (" + ",".join(s for s, o in zip(snaps, ok) if not o) + ")")
        elif lvl == "chapter2":
            if not any(h.startswith(cn + ".") for h in tariffs[snaps[0]][1]):
                add_issue(r, "code_not_in_tariff: chapter " + raw)
        if raw and lvl in ("code8", "heading4") and "code_format" not in r["issues"] and not (re.fullmatch(r"\d{4}\.\d{4}", raw) or re.fullmatch(r"\d{2}\.\d{2}", raw)):
            add_issue(r, "code_format: " + raw)
        if r["rate_kind"] == "percent":
            p = r["rate_pct"]
            if p is None or p < 0 or p > 100:
                add_issue(r, "rate_out_of_range")
            elif p > 40:
                add_issue(r, "rate_unusual(>40)")
        if re.search(r"[A-Za-z]\d|\d[A-Za-z]", raw or "") and lvl != "all":
            add_issue(r, "code_format: letters mixed with digits in " + raw)
        if r["valid_to"] < r["valid_from"]:
            add_issue(r, "dates_inverted")
    return rows


def independent_serials(doc, rng, xmax, last_page=None):
    """Second, simpler reader: serial-looking tokens in the serial column straight from PyMuPDF words."""
    out = defaultdict(set)
    for p in range(rng[0], (last_page or rng[1]) + 1):
        for (x0, y0, x1, y1, wd, *_r) in doc[p - 1].get_text("words"):
            wd2 = re.sub(r"^\d{3,4}\[", "", wd)
            if x0 < xmax + 20 and 60 < y0 < 620 and re.fullmatch(r"\[?\d{1,2}[A-Z]?\.?\]?", wd2) and not re.fullmatch(r"\d{3,4}", wd):
                out[p].add(re.sub(r"[^\dA-Z]", "", wd2))
    return out


def reconcile(docs):
    rep = []
    xm = {"third": {"FY2025-26": 165, "FY2026-27": 165}, "fifth": {"FY2025-26": 160, "FY2026-27": 160}, "eighth": E8COLS_SER}
    for (sched, snap), lst in SERIALS.items():
        nums = [x[0] for x in lst]
        ints = []
        for sn, pg, rg in lst:
            ints.append(int(re.match(r"\d+", sn).group(0)))
        covered = set()
        for sn, pg, rg in lst:
            if rg:
                covered.update(range(rg[0], rg[1] + 1))
        gaps = [n for n in range(min(ints), max(ints) + 1) if n not in set(ints) and n not in covered]
        explained = sorted(n for n in covered if n not in set(ints))
        dups = sorted(set(x for x in nums if nums.count(x) > 1))
        # independent count
        rng = RANGES[snap][sched]
        last = None
        if sched == "eighth":
            for k, v in STOP.items():
                if k[1] == docs[snap].name:
                    last = v - 1
        xmax = xm[sched][snap] if isinstance(xm[sched], dict) else xm[sched]
        ind = independent_serials(docs[snap], rng, xmax if sched != "eighth" else E8COLS[snap][0], last)
        ind_all = set().union(*ind.values()) if ind else set()
        mine = set(re.sub(r"[^\dA-Z]", "", x) for x in nums)
        if last:
            mine = set(re.sub(r"[^\dA-Z]", "", sn) for sn, pg, rg in lst if pg <= last)
        only_parser = sorted(mine - ind_all, key=lambda x: (len(x), x))
        only_indep = sorted(ind_all - mine, key=lambda x: (len(x), x))
        rep.append(dict(schedule=sched, snapshot=snap, parser_serials=len(nums), independent_serials=len(ind_all), gaps=gaps,
                        gap_explained_by_ranges=explained, duplicates=dups, only_in_parser=only_parser, only_in_independent=only_indep))
    return rep


def serial_checks(sched, snap, blocks_sn):
    nums = []
    for sn in blocks_sn:
        m = re.match(r"(\d+)", sn)
        if m:
            nums.append(int(m.group(1)))
    gaps = [n for n in range(min(nums), max(nums) + 1) if n not in set(nums)] if nums else []
    dup = sorted(set(n for n in nums if nums.count(n) > 1))
    log_serial.append(dict(schedule=sched, snapshot=snap, n_serial_tokens=len(blocks_sn), gaps=gaps, duplicates=dup))


# --------------------------------------------------------------------------- vision-check support
def render_pages(snap, pages):
    stem = Path(FILES[snap]).stem
    d = IMG / stem
    d.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(RAW / FILES[snap])
    out = {}
    for p in sorted(set(pages)):
        f = d / f"p{p:03d}.png"
        if not f.exists():
            doc[p - 1].get_pixmap(dpi=110).save(f)
        out[p] = f
    return out


# --------------------------------------------------------------------------- main
def run():
    OUT.mkdir(parents=True, exist_ok=True)
    docs = {s: pymupdf.open(RAW / f) for s, f in FILES.items()}
    parsers = {"third": parse_third, "fifth": parse_fifth, "eighth": parse_eighth, "ninth": parse_ninth, "twelfth": parse_twelfth}
    tariffs = load_tariffs()
    results, all_changes = {}, {}
    for sched, fn in parsers.items():
        per = {}
        for snap in FILES:
            per[snap] = fn(docs[snap], snap)
        merged, changes = merge_snapshots(per["FY2025-26"], per["FY2026-27"])
        validate(merged, tariffs)
        results[sched] = merged
        all_changes[sched] = (changes, {s: len(per[s]) for s in per})
    return results, all_changes, docs


def finish(results, all_changes, docs):
    seq = defaultdict(int)
    final = {}
    for sched, rows in results.items():
        keep = []
        for r in rows:
            if r.get("_expired"):
                log_omitted.append(dict(schedule=sched.capitalize(), snapshot=r["snapshot"], s_no=r["s_no"], page=r["page"],
                                        text=r["description"][:160], footnote="expired before scope start: valid_to %s < 2025-07-01 (stated sunset)" % r["_expired"]))
            else:
                keep.append(r)
        rows[:] = keep
        for r in rows:
            if r["except_codes"] == "[]" and re.search(r"\b(except|excluding)\b", r["description"], re.I):
                mfe = re.search(r"\b(?:except|excluding)\b[^.]*?heading\s+(\d{2})\.(\d{2})", r["description"], re.I)
                if mfe:
                    r["except_codes"] = json.dumps([mfe.group(1) + mfe.group(2)])
                    r["unparsed_except_text"] = 0
                else:
                    r["unparsed_except_text"] = 1
            base = f"A3-ST-{sched.upper()}-{r['s_no'].replace(' ', '')}-{r['code_norm'] or 'ALL'}-{r['snapshot'].replace('FY', '')}"
            seq[base] += 1
            r["rule_id"] = base + (f"-{seq[base]}" if seq[base] > 1 else "")
            for k in [k for k in r if k.startswith("_")]:
                del r[k]
        final[sched] = rows
    return final


def write_outputs(final, all_changes):
    files = []
    for sched, rows in final.items():
        name = f"a3_st_{sched}_schedule"
        with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in COLS})
        meta = dict(schedule=sched, rows=len(rows), by_snapshot={s: sum(1 for r in rows if r["snapshot"] == s) for s in ("FY2025-26", "FY2026-27", "both")},
                    needs_review=sum(1 for r in rows if r["status"] == "needs_review"), method="PyMuPDF character boxes; columns by x position; dated by comparing the FY2025-26 and FY2026-27 Act snapshots; see src/ingest/a3_st_other.py",
                    files=FILES)
        json.dump({"meta": meta, "rows": [{c: r.get(c, "") for c in COLS} for r in rows]}, open(OUT / f"{name}.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        files.append(name)
    return files


def pct_sample(rows_all, vision_pages, imgs):
    pass


def store_check(final):
    """Insert every row into an in-memory copy of the sales_tax_rules table to prove it satisfies the store CHECKs."""
    import sqlite3
    sys.path.insert(0, str(ROOT))
    from src.store import schema
    con = sqlite3.connect(":memory:")
    con.executescript(schema.DDL)
    bad = []
    for sched, rows in final.items():
        for r in rows:
            try:
                con.execute(
                    "INSERT INTO sales_tax_rules (instrument, clause, tax_kind, charged_on, condition_text, code_norm, match_level, except_codes,"
                    " unparsed_except_text, rule_group, rate_kind, rate_pct, rate_specific_amount, rate_specific_unit, rate_raw, status,"
                    " valid_from, valid_to, source_file, page) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("Sales Tax Act 1990, " + r["schedule_or_section"], r["clause"], "sales_tax", r["charged_on"], r["condition_text"],
                     r["code_norm"], r["match_level"], r["except_codes"], r["unparsed_except_text"], r["rule_group"], r["rate_kind"],
                     r["rate_pct"] if r["rate_pct"] != "" else None, r["rate_specific_amount"] if r["rate_specific_amount"] != "" else None,
                     r["rate_specific_unit"] if r["rate_specific_unit"] != "" else None, r["rate_raw"], r["status"],
                     r["valid_from"], r["valid_to"], r["source_file"], r["page"]))
            except Exception as e:  # noqa
                bad.append((sched, r["s_no"], r["code_raw"], str(e)[:120]))
    return bad


def main():
    results, all_changes, docs = run()
    docs_by = docs
    final = finish(results, all_changes, docs)
    files = write_outputs(final, all_changes)
    bad = store_check(final)
    if bad:
        print("STORE CHECK FAILURES:", len(bad))
        for b in bad[:20]:
            print(" ", b)
    else:
        print("store check: all rows satisfy sales_tax_rules CHECKs")
    # image paths + failures + spot check
    allrows = [(s, r) for s, rows in final.items() for r in rows]
    pages_needed = defaultdict(set)
    for s, r in allrows:
        snap = "FY2026-27" if r["snapshot"] in ("FY2026-27", "both") else "FY2025-26"
        pages_needed[snap].add(r["page"])
    for snap in FILES:                      # render every page of every schedule range (page images for the owner)
        for rg in RANGES[snap].values():
            pages_needed[snap].update(range(rg[0], rg[1] + 1))
    imgpath = {}
    for snap, pgs in pages_needed.items():
        for p, f in render_pages(snap, pgs).items():
            imgpath[(snap, p)] = f

    def img_for(r):
        snap = "FY2026-27" if r["snapshot"] in ("FY2026-27", "both") else "FY2025-26"
        return str(imgpath[(snap, r["page"])].relative_to(ROOT)).replace("\\", "/")

    def serious(r):
        return any(not i.strip().startswith("note:") for i in r["issues"].split(";") if i.strip())

    with open(OUT / "a3_st_other_schedules_failures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "page_image", "s_no", "code_raw", "rate_raw", "issues"])
        for s, r in allrows:
            if r["issues"]:
                w.writerow([r["page"], img_for(r), f"{s}:{r['snapshot']}:{r['s_no']}", r["code_raw"], r["rate_raw"], r["issues"]])
    # spot check
    chosen = []
    seen = set()
    def pick(s, r):
        k = r["rule_id"]
        if k not in seen:
            seen.add(k)
            chosen.append((s, r))
    for s, r in allrows:
        if serious(r):
            pick(s, r)
        if s == "eighth" and re.search(r"vehicle|motorcycle|rickshaw|bus|truck|EV|hybrid|tractor|Electric", r["description"], re.I):
            pick(s, r)
        if s == "ninth":
            pick(s, r)
        if s in ("twelfth", "fifth"):
            pick(s, r)
        if s == "eighth" and (r["rate_kind"] != "percent" or r["condition_text"]):
            pick(s, r)
    # stratified fill to >=10% of all rows, per schedule
    for s, rows in final.items():
        need = max(1, -(-len(rows) // 10))
        have = sum(1 for ss, r in chosen if ss == s)
        if have < need:
            rest = [r for r in rows if r["rule_id"] not in seen]
            step = max(1, len(rest) // max(1, (need - have)))
            for r in rest[::step][: need - have]:
                pick(s, r)
    chosen.sort(key=lambda sr: (sr[0], sr[1]["page"], sr[1]["rule_id"]))
    with open(OUT / "spotcheck_a3_st_other_schedules.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "page_image", "s_no", "pct_code", "rate", "correct? (Y/N)", "true_value_if_N"])
        for s, r in chosen:
            w.writerow([r["page"], img_for(r), f"{s}:{r['snapshot']}:{r['s_no']}", r["code_raw"], r["rate_raw"], "", ""])
    # report data
    rep = dict(omitted=log_omitted, serial=reconcile(docs), counts=log_counts,
               changes={s: [dict(kind=c["kind"], key=list(c["key"]),
                                  old=(c["old"] or {}).get("rate_raw", "") + " | " + (c["old"] or {}).get("condition_text", "")[:100] + " | " + (c["old"] or {}).get("description", "")[:60],
                                  new=(c["new"] or {}).get("rate_raw", "") + " | " + (c["new"] or {}).get("condition_text", "")[:100] + " | " + (c["new"] or {}).get("description", "")[:60],
                                  foot=((c["new"] or c["old"]) or {}).get("footnote", "")[:200]) for c in v[0]] for s, v in all_changes.items()},
               per_snapshot_rows={s: v[1] for s, v in all_changes.items()},
               totals={s: len(r) for s, r in final.items()}, spotcheck=len(chosen), total_rows=len(allrows))
    rep_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None   # optional: where to dump the diff/validator report data
    if rep_path:
        json.dump(rep, open(rep_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps({"totals": rep["totals"], "spotcheck": rep["spotcheck"], "total_rows": rep["total_rows"], "per_snapshot": rep["per_snapshot_rows"]}, indent=1))


if __name__ == "__main__":
    main()
