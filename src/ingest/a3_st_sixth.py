"""A3: Sales Tax Act 1990, Sixth Schedule Table-1 (exemptions on import and supply).

Rerunnable end to end:  .venv/Scripts/python src/ingest/a3_st_sixth.py   (from repo root)

Reads the two Sales Tax Act consolidated snapshots (FY2025-26 and FY2026-27), extracts the
Table-1 serials with page coordinates (see a3_st_sixth_extract.py), parses the code column into
one row per code entry, dates every row (snapshot convention + footnote/text evidence), runs the
validators and writes:
  data/processed/a3_st_sixth_schedule.csv / .json
  data/processed/a3_st_sixth_schedule_serials.csv
  data/processed/a3_st_sixth_schedule_failures.csv
  data/processed/spotcheck_a3_st_sixth_schedule.csv
Nothing is taken from memory: every value comes from the PDFs in data/raw/.
"""
import csv
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf  # noqa: E402
from a3_st_sixth_extract import SNAPSHOTS, RAW, extract_snapshot, split_page, TOKEN_RE  # noqa: E402

OUT = "data/processed/"
SNAPS = ["FY2025-26", "FY2026-27"]
TARIFF = {"FY2025-26": OUT + "tariff_2025_26.json", "FY2026-27": OUT + "tariff_2026_27.json"}
SCHED = "Sixth Schedule Table-1"
GROUP = "ST-6TH-T1"
OPEN = "9999-12-31"

# ---------------------------------------------------------------------------------------
# Date evidence. Everything here was read from the PDF text (snapshot footnotes / row text).
# key: (snapshot, s_no) -> (valid_from, valid_to, date_basis); only where evidence overrides
# the plain snapshot convention.
# ---------------------------------------------------------------------------------------
DATE_EVIDENCE = {
    ("FY2025-26", "152"): ("2025-07-01", "2026-06-30",
        "text: 'till [30th June, 2026]' (fn 884 expression substituted by Finance Act 2025); identical in both snapshots"),
    ("FY2026-27", "152"): ("2025-07-01", "2026-06-30",
        "text: 'till [30th June, 2026]' (fn 921 expression substituted by Finance Act 2025); identical in both snapshots"),
    ("FY2025-26", "157"): ("2025-07-01", "2026-06-30",
        "text: 'till 30th June, 2026' (FY2025-26 wording; replaced by Finance Act 2026, see FY2026-27 row)"),
    ("FY2026-27", "157"): ("2026-07-01", "2027-06-30",
        "text: 'till 30th June, [2027]' + fn 927 'expression 2027 substituted through Finance Act 2026' (Finance Act 2026 s.1(2) = 1 Jul 2026)"),
    ("FY2025-26", "181"): ("2025-07-01", "2026-06-30",
        "fn 898 'S.No. 181 ... added through Finance Act 2025' (FA2025-convention 1 Jul 2025); superseded 30 Jun 2026 by the FA2026 substitution"),
    ("FY2026-27", "181"): ("2026-07-01", OPEN,
        "fn 936 'Substituted through Finance Act 2026' (Finance Act 2026 s.1(2) = 1 Jul 2026)"),
    ("FY2025-26", "32"): ("2025-07-01", "2026-06-30",
        "snapshot (row replaced by Finance Act 2026, see FY2026-27 row)"),
    ("FY2026-27", "32"): ("2026-07-01", OPEN,
        "fn 832 'Serial number 32 substituted through Finance Act 2026' (Finance Act 2026 s.1(2) = 1 Jul 2026)"),
    ("FY2026-27", "27A"): ("2026-07-01", OPEN,
        "fn 824 'New serial number 27A inserted through Finance Act 2026' (Finance Act 2026 s.1(2) = 1 Jul 2026)"),
    ("FY2026-27", "181A"): ("2027-07-01", OPEN,
        "text: 'This will be effective from the first day of July, 2027' (fn 937 inserted through Finance Act 2026); NOTE starts after FY2026-27"),
}
DATE_EVIDENCE[("FY2026-27", "179")] = ("2025-07-01", OPEN,
    "snapshot; fn 935 '(for personal use only)' omitted through Finance Act 2025 (FA2025-convention 1 Jul 2025)")
for _s in ("182", "183", "184", "185"):
    DATE_EVIDENCE[("FY2026-27", _s)] = ("2026-07-01", OPEN,
        "fn 938 'Serial number(s) 182 to 185 added through Finance Act 2026' (Finance Act 2026 s.1(2) = 1 Jul 2026)")

# Serial-specific notes that make the row needs_review (evidence read from other documents).
SERIAL_NOTES = {
    "156": "date_unverified: Salient-Feature.pdf p.4 says exemption on import of CKD for electric vehicles is extended to 30.06.2027, but S.No 156 carries no date in the Act text (only S.No 157 does)",
    "182": "budget_conflict: Salient-Feature.pdf p.4 lists 'Withdrawal of exemption of sales tax on family planning devices' but the Act text shows S.No 182 Contraceptives (3926.9020, 4014.1000) ADDED by Finance Act 2026",
}

# Vision check log: filled from the manual look at the page images (see run notes).
# entries: (snapshot, page, s_no or '*', result 'ok' or text of disagreement)
VISION_LOG = []
VISION_FILE = OUT + "a3_st_sixth_vision_log.json"


# ---------------------------------------------------------------------------------------
def strip_fn(t):
    t = re.sub(r"\{fn:\d+\}", "", t)
    return re.sub(r"\s+", " ", t).strip()


def is_omitted(s):
    d = strip_fn(s["desc_raw"])
    if re.match(r"^[\[\s]*(\*{3}|\.{2,}|…+|omitted|\[omitted\])", d, re.I):
        return True
    return d.replace("]", "").strip() in ("***", "")


def fn_refs(s):
    return sorted(set(re.findall(r"\{fn:(\d{3,4})\}", s["col1"] + " " + s["desc_raw"] + " " + s["code_raw"])), key=int)


def fn_text(snap_data, s):
    fns = snap_data["footnotes"]
    parts = ["%s: %s" % (r, fns[r]) for r in fn_refs(s) if r in fns]
    return " | ".join(parts)


def norm_tokens(t):
    t = strip_fn(t).lower()
    return Counter(re.findall(r"[a-z]+|\d+(?:\.\d+)*", t))


def same_text(a, b):
    """'same' (token multiset equal: ignores spacing/ordering/punctuation/footnote markers),
    'label_diff' (only list-label characters differ, no digit run touched) or 'changed'."""
    ca, cb = norm_tokens(a), norm_tokens(b)
    if ca == cb:
        return "same", []
    diff = (ca - cb) + (cb - ca)
    toks = sorted(diff)
    import difflib
    sa = re.sub(r"[^A-Za-z0-9]", "", strip_fn(a)).lower()
    sb = re.sub(r"[^A-Za-z0-9]", "", strip_fn(b)).lower()
    sm = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
    segs, ok = [], True
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        segs.append((sa[i1:i2], sb[j1:j2]))
        if (i2 - i1) > 2 or (j2 - j1) > 2:
            ok = False
        # a digit with a neighbouring digit = year / code / amount -> material
        for s_, i1_, i2_ in ((sa, i1, i2), (sb, j1, j2)):
            ctx = s_[max(0, i1_ - 1):i2_ + 1]
            if re.search(r"\d\d", ctx):
                ok = False
    if ok and segs and len(segs) <= 12:
        return "label_diff", ["%s->%s" % (x, y) for x, y in segs]
    return "changed", toks


# ---------------------------------------------------------------------------------------
CODE_RE = re.compile(
    r"(?P<c8>(?<![\d.])\d{4}\.\d{4}(?!\d)(?!\.\d))"
    r"|(?P<h4>(?<![\d.])\d{2}\.\d{2}(?!\d)(?!\.\d))"
    r"|(?P<p4>(?<![\d.])\d{4}(?!\d)(?!\.\d))(?P<sub>\((?:[ivx]+|\d)\))?"
    r"|(?P<ch>chapter\s+(?P<chn>\d{1,2}))"
    r"|(?P<resp>respective\s+head\w*)", re.I)


def parse_codes(code_raw):
    """-> (entries, leftover_issues). entry = (token_text, code_norm, match_level)."""
    c = strip_fn(code_raw)
    c = re.sub(r"\[\s*[.…]+\s*\]", " ", c)          # [..] / [...] placeholders (omitted words)
    c = c.replace("[", " ").replace("]", " ").replace("”", " ").replace("“", " ").replace('"', " ")
    entries, seen = [], set()
    issues = []
    for m in CODE_RE.finditer(c):
        if m.group("c8"):
            tok, norm, lvl = m.group("c8"), m.group("c8").replace(".", ""), "code8"
        elif m.group("h4"):
            tok, norm, lvl = m.group("h4"), m.group("h4").replace(".", ""), "heading4"
        elif m.group("p4"):
            tok = m.group("p4") + (m.group("sub") or "")
            norm, lvl = m.group("p4"), "heading4"
        elif m.group("ch"):
            tok, norm, lvl = m.group("ch"), m.group("chn").zfill(2), "chapter2"
        else:
            tok, norm, lvl = m.group("resp"), "", "all"
        key = (norm, lvl)
        if key in seen:
            continue
        seen.add(key)
        entries.append((tok, norm, lvl))
    # leftovers: digits not consumed
    rest = CODE_RE.sub(" ", c)
    for m in re.finditer(r"\d[\d.,]*", rest):
        issues.append("code_format: unparsed numeric text %r in code cell" % m.group(0))
    if re.search(r"\d{4},\d{4}|\d[A-Za-z]\d|\d{2}\.\d{2}\.\d{4}", c):
        issues.append("code_format: possible typographic garbage in code cell")
    return entries, issues


def parse_except(desc):
    """except/excluding phrase in the description. -> (codes list, phrase or '')"""
    m = re.search(r"(?i)\b(but excluding|excluding|except(?: for)?|other than)\b(.*)", strip_fn(desc))
    if not m:
        return [], ""
    tail = m.group(2)
    codes = []
    for mm in CODE_RE.finditer(tail):
        if mm.group("c8"):
            codes.append(mm.group("c8").replace(".", ""))
        elif mm.group("h4"):
            codes.append(mm.group("h4").replace(".", ""))
    return codes, (m.group(1) + m.group(2))[:160].replace(";", ",")


def split_condition(desc):
    d = strip_fn(desc)
    m = re.search(r"(?i)(subject to|provided that|provided further|\bprovided\b)", d)
    return d[m.start():] if m else ""



# Serials whose code column is an inner table (item <-> code on the same row). Verified on the page
# images (p169-172 for S.No 133, p180 for S.No 184 in the FY2026-27 file).
PAIR_CFG = {
    "133": dict(header_from_first_band=True),
    "184": dict(header_before_first=True, tail_re=r"^(Excluding|Provided that)"),
}


def _lines(spans):
    """merge spans into visual lines -> [(pg, y0, text)] in page/y order."""
    out = []
    for sp in sorted(spans, key=lambda t: (t["pg"], round(t["y0"] / 3.0), t["x0"])):
        if out and out[-1][0] == sp["pg"] and abs(out[-1][1] - sp["y0"]) <= 3.0:
            out[-1][2].append((sp["x0"], sp["text"], sp.get("sup")))
        else:
            out.append([sp["pg"], sp["y0"], [(sp["x0"], sp["text"], sp.get("sup"))]])
    res = []
    for pg, y0, parts in out:
        parts.sort()
        txt = "".join("" if (sup and re.fullmatch(r"\s*\d{1,4}\s*", t)) else t for _, t, sup in parts)
        txt = re.sub(r"\s+", " ", txt).strip()
        res.append((pg, y0, txt))
    return res


def pair_entries(s, cfg):
    """code entries with the item text printed on the same inner-table row."""
    toks = []
    for sp in sorted(s["code_geo"], key=lambda t: (t["pg"], t["y0"], t["x0"])):
        if sp.get("sup") and re.fullmatch(r"\s*\d{1,4}\s*", sp["text"]):
            continue
        ents, _ = parse_codes(sp["text"])
        for e in ents:
            toks.append((sp["pg"], sp["y0"], e))
    dl = [l for l in _lines(s["desc_geo"]) if l[2] and not re.fullmatch(r"[\[\]\s.…]*", l[2])]
    bands = [[] for _ in toks]
    header, orphans = [], []
    first_pg = toks[0][0] if toks else None
    for pg, y0, txt in dl:
        idx = -1
        for i, (tp, ty, _e) in enumerate(toks):
            if tp == pg and ty <= y0 + 3.0:
                idx = i
            elif tp > pg:
                break
        if idx >= 0:
            bands[idx].append(txt)
        elif pg == first_pg and cfg.get("header_before_first"):
            header.append(txt)
        else:
            orphans.append((pg, y0, txt))
    items = [" ".join(b) for b in bands]
    head = " ".join(header)
    if cfg.get("header_from_first_band") and items:
        head = items[0]
    tail = ""
    if cfg.get("tail_re") and items:
        last = bands[-1]
        for j, l in enumerate(last):
            if re.match(cfg["tail_re"], l):
                tail = " ".join(last[j:])
                items[-1] = " ".join(last[:j])
                break
    out = []
    prev_item = ""
    for (pg, y0, e), it in zip(toks, items):
        item = it if it else prev_item
        prev_item = item
        if cfg.get("header_from_first_band") and it == head:
            d = head
        else:
            d = " | ".join(x for x in (head, item, tail) if x)
        out.append(dict(tok=e[0], norm=e[1], lvl=e[2], desc=d, extra=[], pg=pg, pos=(pg, round(y0))))
    # blank-code rows inside the inner table
    merged = []
    for pg, y0, txt in orphans:            # consecutive lines of one blank-code row
        if merged and merged[-1][0] == pg and y0 - merged[-1][1] <= 14.5:
            merged[-1] = (pg, y0, merged[-1][2] + " " + txt)
        else:
            merged.append((pg, y0, txt))
    for pg, y0, txt in merged:
        out.append(dict(tok="", norm="", lvl="all", desc=(head + " | " if head else "") + txt,
                        extra=["code_cell_empty: inner-table row has no code printed in the source (page %d)" % pg],
                        pg=pg, pos=(pg, round(y0))))
    # De-duplicate on the printed POSITION as well: S.No 133 prints "Ingredients for pesticides / Respective headings"
    # three times (footnotes 902, 904, 905); keying on text alone dropped two of them (A3 fix, found by the AI second read).
    seen, res = set(), []
    for o in out:
        k = (o["norm"], o["lvl"], o["desc"], o["pos"])
        if k not in seen:
            seen.add(k)
            res.append(o)
    return res


# ---------------------------------------------------------------------------------------
def load_tariff():
    T = {}
    for snap, f in TARIFF.items():
        d = json.load(open(f, encoding="utf-8"))
        codes = {r["code"].replace(".", "") for r in d["rows"]}
        heads = {h["heading"].replace(".", "") for h in d["headings"]}
        special = {str(x["code"]) for x in d.get("special", [])}
        T[snap] = dict(codes=codes, heads=heads, special=special)
    return T


def code_in_tariff(T, snap, norm, lvl):
    t = T[snap]
    if lvl == "code8":
        return norm in t["codes"]
    if lvl == "heading4":
        return norm in t["heads"] or norm in t["special"] or any(c.startswith(norm) for c in t["special"])
    if lvl == "chapter2":
        return any(h.startswith(norm) for h in t["heads"])
    return True


# ---------------------------------------------------------------------------------------
def build():
    T = load_tariff()
    data = {s: extract_snapshot(s) for s in SNAPS}
    # per-snapshot serial maps (key -> serial dict); a serial number printed twice is kept as list
    maps = {}
    serial_rows = []
    validator = dict(gaps={}, dups={}, omitted={}, count_mismatch=[])
    for snap in SNAPS:
        d = data[snap]
        m = {}
        for s in d["serials"]:
            m.setdefault(s["s_no"], []).append(s)
        maps[snap] = m
        # serial continuity
        nums = sorted({int(re.match(r"\d+", k).group(0)) for k in m})
        validator["gaps"][snap] = [n for n in range(1, nums[-1] + 1) if str(n) not in m and not any(re.match(r"%d[A-Z]" % n, k) for k in m)]
        validator["dups"][snap] = [k for k, v in m.items() if len(v) > 1]
        validator["omitted"][snap] = [s["s_no"] for s in d["serials"] if is_omitted(s)]
        # validator 4: per-page serial markers parsed by pymupdf spans vs an independent count with pdfplumber
        # (different engine): words in the S.No column that look like serial numbers.
        import pdfplumber
        with pdfplumber.open(RAW + SNAPSHOTS[snap]["file"]) as pl:
            for pn in range(d["first"], d["last"] + 1):
                parsed = sum(1 for s in d["serials"] if s["first_page"] == pn)
                info = d["pages"][pn]
                page = pl.pages[pn - 1]
                n = 0
                prev_bare = False
                for w in page.extract_words(extra_attrs=["size"]):
                    if w["x0"] >= 182 or w["top"] < info["hb"] - 1 or w["top"] > info["ft"] - 1 or w["top"] > 715:
                        continue
                    if w["size"] < info["dom"] * 0.75 and not re.match(r"^\d{1,4}\[", w["text"]):
                        continue                                  # superscript footnote reference
                    core = re.sub(r"^\d{1,4}(?=\[)", "", w["text"])
                    if re.fullmatch(r"\[?\d{1,3}[A-Z]{0,2}\.?\]?", core):
                        n += 1
                    elif re.fullmatch(r"\[?\d{3}\d{1,3}[A-Z]{0,2}\.?\]?", core):
                        n += 1                                    # footnote number glued to serial number
                validator.setdefault("page_counts", {}).setdefault(snap, {})[pn] = (parsed, n)
    # ---- build rows
    rows = []
    for snap in SNAPS:
        d = data[snap]
        for s in d["serials"]:
            omitted = is_omitted(s)
            serial_rows.append(dict(
                snapshot=snap, s_no=s["s_no"], omitted=int(omitted),
                raw_description=strip_fn(s["desc_raw"]), raw_code_cell=strip_fn(s["code_raw"]),
                raw_conditions=split_condition(s["desc_raw"]),
                pages="%d-%d" % (min(s["pages"]), max(s["pages"])) if len(s["pages"]) > 1 else str(s["pages"][0]),
                footnote=fn_text(d, s), source_file=SNAPSHOTS[snap]["file"]))
    # identity between snapshots
    plan = []   # (s_no, snap_list, serial_by_snap, relation, difftoks)
    allkeys = []
    for snap in SNAPS:
        for s in data[snap]["serials"]:
            if s["s_no"] not in allkeys:
                allkeys.append(s["s_no"])
    def keyorder(k):
        m = re.match(r"(\d+)([A-Z]*)", k)
        return (int(m.group(1)), m.group(2))
    allkeys.sort(key=keyorder)
    for k in allkeys:
        a = next((x for x in maps["FY2025-26"].get(k, []) if not is_omitted(x)), None)
        b = next((x for x in maps["FY2026-27"].get(k, []) if not is_omitted(x)), None)
        if a is None and b is None:
            continue
        if a and b:
            r1, t1 = same_text(a["desc_raw"], b["desc_raw"])
            r2, t2 = same_text(a["code_raw"], b["code_raw"])
            if r1 == "same" and r2 == "same":
                plan.append((k, ["both"], dict(a=a, b=b), "same", []))
            elif "changed" not in (r1, r2):
                plan.append((k, ["both"], dict(a=a, b=b), "label_diff", t1 + t2))
            else:
                plan.append((k, ["FY2025-26", "FY2026-27"], dict(a=a, b=b), "changed", t1 + t2))
        elif a:
            plan.append((k, ["FY2025-26"], dict(a=a, b=None), "only25", []))
        else:
            plan.append((k, ["FY2026-27"], dict(a=None, b=b), "only26", []))
    changes = []
    for k, snaps, ser, rel, toks in plan:
        for sn in snaps:
            if sn == "both":
                s_src, snap_for_src = ser["b"], "FY2026-27"      # latest wording/page as the row's source
                snap_label = "both"
                alt = ser["a"]
            else:
                s_src = ser["a"] if sn == "FY2025-26" else ser["b"]
                snap_for_src = sn
                snap_label = sn
                alt = None
            sd = data[snap_for_src]
            # dating
            if sn == "both":
                ev = DATE_EVIDENCE.get(("FY2026-27", k))
                vf, vt, basis = ev if ev else ("2025-07-01", OPEN, "snapshot")
            else:
                ev = DATE_EVIDENCE.get((sn, k))
                if ev:
                    vf, vt, basis = ev
                elif sn == "FY2025-26":
                    vf, vt, basis = "2025-07-01", "2026-06-30", "snapshot"
                else:
                    vf, vt, basis = "2026-07-01", OPEN, "snapshot"
            if rel == "label_diff":
                basis += "; snapshots differ only in sub-label tokens %s" % toks
            desc = strip_fn(s_src["desc_raw"])
            code_raw = strip_fn(s_src["code_raw"])
            entries0, cissues = parse_codes(s_src["code_raw"])
            ents = [dict(tok=e[0], norm=e[1], lvl=e[2], desc=desc, extra=[]) for e in entries0]
            if k in PAIR_CFG:
                pe = pair_entries(s_src, PAIR_CFG[k])
                a_ = {(e["norm"], e["lvl"]) for e in pe if e["norm"]}
                b_ = {(e[1], e[2]) for e in entries0 if e[1]}
                if a_ != b_:
                    cissues = cissues + ["pairing_mismatch: inner-table pairing differs from flat parse in %d codes" % len(a_ ^ b_)]
                else:
                    ents = pe
            exc_codes, exc_phrase = parse_except(s_src["desc_raw"])
            sn_issues = list(cissues)
            if SERIAL_NOTES.get(k) and (sn in ("both", "FY2026-27")):
                sn_issues.append(SERIAL_NOTES[k])
            if rel == "label_diff":
                sn_issues.append("snapshot_text_diff: sub-labels differ between snapshots %s (text-layer ordering/labels)" % toks)
            if exc_phrase and not exc_codes:
                sn_issues.append("except_not_code_expressible: %r" % exc_phrase)
            # code text printed inside the description cell too (seen on the page image for S.No 175)
            for e in ents:
                if e["lvl"] != "all" and re.search(r"(?<![\d.])" + re.escape(e["tok"]) + r"(?![\d.])", desc) and len(code_raw) < 60:
                    sn_issues.append("source_typo: code text %r is also printed inside the description cell in the PDF (confirmed on page image)" % e["tok"])
                    break
            mixed = bool(any(e["lvl"] == "all" and e["tok"] for e in ents) and len(ents) > 1)
            if not ents:
                ents = [dict(tok="", norm="", lvl="all", desc=desc, extra=[])]
                sn_issues.append("code_cell_empty: scope taken from description only")
            pages = s_src["pages"]
            src_file = SNAPSHOTS[snap_for_src]["file"]
            fnt = fn_text(sd, s_src)
            if alt is not None:
                fnt_alt = fn_text(data["FY2025-26"], alt)
                if fnt_alt and fnt_alt != fnt:
                    fnt = fnt + " || FY2025-26 snapshot: " + fnt_alt
                elif fnt_alt:
                    fnt = "FY2026-27: " + fnt + " || FY2025-26: " + fnt_alt
            cond = split_condition(s_src["desc_raw"])
            ver = {"both": "b", "FY2025-26": "25", "FY2026-27": "26"}[sn]
            for i, ent in enumerate(ents, 1):
                tok, norm, lvl = ent["tok"], ent["norm"], ent["lvl"]
                issues = list(sn_issues) + list(ent["extra"])
                if lvl == "all" and mixed and tok:
                    issues.append("respective_headings_mixed_with_codes: this 'all' row stands for the goods named in its description, not for every good")
                # tariff check (FY2025-26 tariff file has no chapter 99: its PDF text ends at 9706.9000)
                if lvl != "all":
                    miss = []
                    chk = ["FY2025-26", "FY2026-27"] if sn == "both" else [sn]
                    for cs in chk:
                        if lvl == "heading4" and norm.startswith("99") and cs == "FY2025-26":
                            continue
                        if not code_in_tariff(T, cs, norm, lvl):
                            miss.append(cs)
                    if miss:
                        issues.append("code_not_in_tariff: %s absent from tariff %s" % (tok or norm, "+".join(miss)))
                row = dict(
                    rule_id="%s-%s-%s-%s-%s" % (GROUP, k, ver, norm or "ALL", i),
                    tax="ST", schedule_or_section=SCHED, s_no=k, description=ent["desc"],
                    code_raw=tok if tok else ("" if ent["extra"] else code_raw), code_norm=norm, match_level=lvl,
                    except_codes=json.dumps(exc_codes), unparsed_except_text=int(bool(exc_phrase and not exc_codes)),
                    rule_group=GROUP, rate_kind="exempt", rate_pct="", rate_specific_amount="", rate_specific_unit="",
                    rate_raw="Exempt (Sixth Schedule Table-1; 'See section 13(1)')",
                    condition_text=cond, charged_on="",
                    valid_from=vf, valid_to=vt, date_basis=basis, snapshot=snap_label, footnote=fnt,
                    source_file=src_file, page=ent.get("pg", pages[0]),
                    clause="Sixth Schedule, Table-1, S.No %s, col 3 (entry %d of %d)%s" % (
                        k, i, len(ents),
                        "; FY2025-26 file %s p.%d" % (SNAPSHOTS['FY2025-26']['file'], alt["pages"][0]) if alt is not None else ""),
                    status="accepted", issues="", extraction_method="text_layer(coordinate columns)+vision_check")
                row["_issues"] = issues
                row["_pages"] = pages
                row["_full_code_cell"] = code_raw
                rows.append(row)
            changes.append((k, sn, rel, toks))
    return data, maps, rows, serial_rows, validator, plan, T


def table2_info(data):
    """Page range and S.No count of Table-2 (not extracted)."""
    out = {}
    for snap in SNAPS:
        doc = pymupdf.open(RAW + SNAPSHOTS[snap]["file"])
        first = data[snap]["t2"]
        # Table-2 ends where the notes/Table-3 text starts: first page after t2 whose body starts with
        # 'Notes' style paragraph '3. For the purposes' / 'For the purpose of Table-3' / 'Table-3'
        last = first
        for pn in range(first, first + 8):
            tx = doc[pn - 1].get_text()
            if re.search(r"S\. ?No\s*\n?\s*Description\s*\n?\s*PCT heading", tx):
                last = pn - 1
                break
            last = pn
        sers = []
        for pn in range(first, last + 1):
            sp = split_page(doc[pn - 1], pn)
            for s in sp["body"]:
                if s["x0"] < 182 and not s["sup"]:
                    t = re.sub(r"(\d)\s+([A-Z])\b", r"\1\2", s["text"])
                    for mm in TOKEN_RE.finditer(t):
                        sers.append(mm.group(1))
        out[snap] = dict(first=first, last=last, count=len(sers), tokens=sers)
    return out


def write_outputs(data, maps, rows, serial_rows, validator, plan, T):
    os.makedirs(OUT, exist_ok=True)
    vlog = []
    if os.path.exists(VISION_FILE):
        vlog = json.load(open(VISION_FILE, encoding="utf-8"))
    viewed = {(v["snapshot"], v["page"]) for v in vlog}
    mism = [v for v in vlog if not v["result"].startswith("ok")]
    file2snap = {SNAPSHOTS[x]["file"]: x for x in SNAPS}
    # attach vision mismatches
    for r in rows:
        for v in mism:
            if v["s_no"] in ("*", r["s_no"]) and v["page"] in r["_pages"] and \
                    (r["snapshot"] in ("both", v["snapshot"])) and \
                    (v.get("code") in (None, "", r["code_norm"], r["code_raw"])):
                r["_issues"].append("vision_mismatch: " + v["result"])
    for r in rows:
        r["issues"] = "; ".join(dict.fromkeys(r["_issues"]))
        r["status"] = "needs_review" if r["issues"] else "accepted"
    cols = ["rule_id", "tax", "schedule_or_section", "s_no", "description", "code_raw", "code_norm", "match_level",
            "except_codes", "unparsed_except_text", "rule_group", "rate_kind", "rate_pct", "rate_specific_amount",
            "rate_specific_unit", "rate_raw", "condition_text", "charged_on", "valid_from", "valid_to", "date_basis",
            "snapshot", "footnote", "source_file", "page", "clause", "status", "issues", "extraction_method"]
    for r in rows:
        assert r["valid_to"] >= r["valid_from"], r["rule_id"]
    with open(OUT + "a3_st_sixth_schedule.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    t2 = table2_info(data)
    ids = [r["rule_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate rule_id"
    per_snap = {}
    for snap in SNAPS:
        per_snap[snap] = sum(1 for r in rows if r["snapshot"] in (snap, "both"))
    meta = dict(
        table="Sales Tax Act 1990, Sixth Schedule Table-1 (Imports or Supplies)",
        scope="FY2025-26 and FY2026-27 snapshots only",
        method="pymupdf span coordinates (3 columns: S.No / description / heading nos), footnotes from page footer, "
               "dated by snapshot diff + footnote/text evidence; page images compared by eye (vision check)",
        snapshots={s: dict(file=SNAPSHOTS[s]["file"], table1_pages="%d-%d" % (data[s]["first"], data[s]["last"]),
                           serial_lines=len(data[s]["serials"]), omitted=len(validator["omitted"][s]),
                           live_serials=len(data[s]["serials"]) - len(validator["omitted"][s])) for s in SNAPS},
        rows_total=len(rows), rows_visible_in_snapshot=per_snap,
        rows_needs_review=sum(1 for r in rows if r["status"] == "needs_review"),
        table2_not_extracted={s: dict(pages="%d-%d" % (t2[s]["first"], t2[s]["last"]), serial_tokens_seen=t2[s]["count"],
                                      max_serial_no=max(int(re.match(r"\d+", t).group(0)) for t in t2[s]["tokens"] if int(re.match(r"\d+", t).group(0)) <= 70),
                                      note="approximate: counts S.No-like tokens in column 1 incl. numbered notes on the last page; not extracted")
                              for s in SNAPS},
        vision=dict(pages_viewed=len(viewed), mismatches=len(mism),
                    rows_on_viewed_pages=sum(1 for r in rows if (file2snap[r["source_file"]], r["page"]) in viewed),
                    log_file=VISION_FILE),
        note_no_conditions_column="Table-1 has no conditions column (cols: S.No, Description, Heading Nos). Conditions are printed inside the description; condition_text = description from 'subject to'/'provided' onward.")
    pub = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    with open(OUT + "a3_st_sixth_schedule.json", "w", encoding="utf-8") as f:
        json.dump(dict(meta=meta, rows=pub), f, ensure_ascii=False, indent=1)
    # serials csv
    scols = ["snapshot", "s_no", "omitted", "raw_description", "raw_code_cell", "raw_conditions", "pages", "footnote", "source_file"]
    with open(OUT + "a3_st_sixth_schedule_serials.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=scols)
        w.writeheader()
        w.writerows(serial_rows)
    # page image path
    def pimg(r):
        f = r["source_file"][:-4]
        return "data/processed/page_images/%s/p%03d.png" % (f, r["page"])
    # failures
    with open(OUT + "a3_st_sixth_schedule_failures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "page_image", "s_no", "code_raw", "rate_raw", "issues"])
        for r in rows:
            if r["issues"]:
                w.writerow([r["page"], pimg(r), r["s_no"], r["code_raw"], r["rate_raw"], r["issues"]])
    # spot check: all flagged rows + stratified >=10% (every 6th row by page order), plus long/except/special rows
    sp = {}
    for r in rows:
        if r["issues"] or r["unparsed_except_text"] or r["match_level"] == "all" and len(r["description"]) > 600:
            sp[r["rule_id"]] = r
    ordered = sorted(rows, key=lambda r: (r["source_file"], r["page"], r["rule_id"]))
    for i, r in enumerate(ordered):
        if i % 5 == 0:
            sp[r["rule_id"]] = r
    with open(OUT + "spotcheck_a3_st_sixth_schedule.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "page_image", "s_no", "pct_code", "rate", "correct? (Y/N)", "true_value_if_N"])
        for r in sorted(sp.values(), key=lambda r: (r["source_file"], r["page"], r["rule_id"])):
            w.writerow([r["page"], pimg(r), r["s_no"], r["code_raw"], r["rate_raw"], "", ""])
    return meta, t2, len(sp)


def main():
    data, maps, rows, serial_rows, validator, plan, T = build()
    meta, t2, nsp = write_outputs(data, maps, rows, serial_rows, validator, plan, T)
    print(json.dumps(meta, indent=1)[:3000])
    print("spot-check rows:", nsp)
    print("gaps", validator["gaps"], "dups", validator["dups"])
    bad = {s: {p: v for p, v in validator["page_counts"][s].items() if v[0] != v[1]} for s in SNAPS}
    print("page marker count (parsed, independent) mismatches:", bad)
    rel = Counter(p[3] for p in plan)
    print("relations", rel)
    for p in plan:
        if p[3] != "same":
            print("  ", p[0], p[3], p[4])


if __name__ == "__main__":
    main()
