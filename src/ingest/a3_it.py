"""A3 (income tax): import-stage advance tax, section 148 ITO 2001, FY2025-26 and FY2026-27.

Run:  PYTHONIOENCODING=utf-8 .venv/Scripts/python src/ingest/a3_it.py

Outputs (data/processed/):
  a3_it_twelfth_schedule.csv/.json   A: Twelfth Schedule entries (class of goods: Part I / II / III)
  a3_it_s148_rates.csv/.json         B: First Schedule Part II table (rates of advance tax at import)
  a3_it_s148_special_rules.csv/.json C: section 148 text + Second Schedule clauses touching s.148
  a3_it_failures.csv                 every row with a validator flag
  spotcheck_a3_it.csv                sheet for the owner (>= 10 % of rows, all B and C rows)

No rate, code or date is written from memory: every value is parsed from the PDFs in data/raw and
every quoted text is checked against the PDF text layer (quote check). Page numbers are 1-based PDF
page indexes. Vision (page image) checks are recorded in a3_it_vision_log.json (written by hand
after looking at the images) and read back here.
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a3_it_clauses as CL  # noqa: E402
import a3_it_twelfth as TW  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
IMG = PROC / "page_images"

FY25, FY26 = "FY2025-26", "FY2026-27"
OPEN_END = "9999-12-31"
PDF = {
    FY26: "2026724177725705IncomeTaxOrdinanace2001.pdf",  # amended up to 30.06.2026
    FY25: "2025881983148210Income-Tax-Ordinance,-2001-Amended-upto-31.07.2025.pdf",
    "MID": "2026226162211364IncomeTaxOrdinance2001-Amended-20.02.2026.pdf",
}
SRO_FILES = {
    "SRO1216": "2025791374222561SRO1216-2025.pdf",
    "SRO1833": "2025923149161117Sro1833IncomeTax.pdf",
    "SRO455": "202635143564166SRO455.pdf",
    "SRO663": "2026423042643455SRO663.pdf",
}
FIN_ACT_2026 = "20266291261044366FinanceAct2026.pdf"
SCOPE_START = "2025-07-01"

COMMON = [
    "rule_id", "tax", "schedule_or_section", "s_no", "description", "code_raw", "code_norm", "match_level",
    "except_codes", "unparsed_except_text", "rule_group", "rate_kind", "rate_pct", "rate_specific_amount",
    "rate_specific_unit", "rate_raw", "condition_text", "charged_on", "valid_from", "valid_to", "date_basis",
    "snapshot", "footnote", "source_file", "page", "clause", "status", "issues", "extraction_method",
]
EXTRA_A = ["twelfth_part", "snapshot_pages"]
EXTRA_B = ["importer_category", "importer_status", "class_of_goods", "twelfth_part", "snapshot_pages"]
EXTRA_C = ["clause_part", "in_scope", "codes_in_clause", "snapshot_pages"]

TARIFF = {}


def load_tariff():
    for fy, f in ((FY25, "tariff_2025_26.json"), (FY26, "tariff_2026_27.json")):
        d = json.loads((PROC / f).read_text(encoding="utf-8"))
        TARIFF[fy] = {
            "codes": {r["code"].replace(".", "") for r in d["rows"]},
            "headings": {h["heading"].replace(".", "") for h in d["headings"]},
        }
        # a 4-digit heading is also valid if any 8-digit code starts with it
        for c in TARIFF[fy]["codes"]:
            TARIFF[fy]["headings"].add(c[:4])


def tariff_has(fy, norm):
    t = TARIFF[fy]
    if len(norm) == 8:
        return norm in t["codes"]
    if len(norm) == 4:
        return norm in t["headings"]
    return None


# ---------------------------------------------------------------- pdf text helpers
_DOCS, _TXT = {}, {}


def doc(key):
    if key not in _DOCS:
        _DOCS[key] = pymupdf.open(str(RAW / (PDF.get(key) or key)))
    return _DOCS[key]


def squash(s):
    s = re.sub(r"\d{1,2}\s*\[|\]", "", s)
    s = re.sub(r"[‘’“”\"'`―–—‑]", "", s)
    s = s.replace("‐", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def page_squash(key, pn):
    k = (key, pn)
    if k not in _TXT:
        _TXT[k] = squash(doc(key)[pn - 1].get_text())
    return _TXT[k]


def locate(key, fragment, pages=None):
    """pages (1-based) where the fragment occurs (after squashing both)."""
    frag = squash(fragment)
    rng = pages or range(1, len(doc(key)) + 1)
    return [p for p in rng if frag in page_squash(key, p)]


def tidy(s):
    return re.sub(r"\s+", " ", s).strip()


def img_rel(key, page):
    stem = Path(PDF.get(key) or key).stem
    return f"data/processed/page_images/{stem}/p{page:03d}.png"


def render(key, page):
    stem = Path(PDF.get(key) or key).stem
    out = IMG / stem
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"p{page:03d}.png"
    if not f.exists():
        doc(key)[page - 1].get_pixmap(dpi=110).save(str(f))
    return f


# ---------------------------------------------------------------- vision log (hand written)
def load_vision():
    f = PROC / "a3_it_vision_log.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"viewed": {}, "mismatches": []}


VISION = load_vision()


def vision_viewed(key, page):
    return page in VISION["viewed"].get(key, [])


# ---------------------------------------------------------------- row factory
def mk(extra, **kw):
    r = {c: "" for c in COMMON + extra}
    r.update({"tax": "IT", "except_codes": "[]", "unparsed_except_text": 0, "status": "accepted",
              "issues": "", "valid_to": OPEN_END})
    r.update(kw)
    return r


def add_issue(row, msg):
    row["issues"] = (row["issues"] + "; " if row["issues"] else "") + msg
    row["status"] = "needs_review"


def date_both():
    return dict(valid_from=SCOPE_START, valid_to=OPEN_END, date_basis="snapshot", snapshot="both")


# ================================================================= A: Twelfth Schedule
CODE_TOKEN = re.compile(r"\d{4}\.\d{4}|\d{2}\.\d{2}|\d{8}")


def parse_code_cell(cell):
    m = re.search(r"\(\s*except\b(.*)$", cell, re.I)
    main = cell[:m.start()] if m else cell
    except_text = m.group(0) if m else ""
    exc = [t.replace(".", "") for t in CODE_TOKEN.findall(m.group(1))] if m else []
    toks = CODE_TOKEN.findall(main)
    return toks, exc, except_text.strip().rstrip(")").strip() if m else "", bool(m)


def build_twelfth():
    rows, report = [], {}
    snaps = {}
    for fy in (FY26, FY25):
        d, start, end, entries, omitted, notes_by_page = TW.parse_schedule(RAW / PDF[fy])
        ents = TW.finish_entries(entries)
        snaps[fy] = dict(doc=d, start=start, end=end, entries=ents, omitted=omitted, notes=notes_by_page)
    # entry keys
    def keyed(fy):
        out, prefix = [], ""
        for e in snaps[fy]["entries"]:
            if e.get("orphan"):
                prefix = e["description"]
                e["group_prefix"] = prefix
                continue
            if prefix and e["description"].startswith("("):
                e["description_full"] = f"{prefix} {e['description']}"
            else:
                prefix = ""
                e["description_full"] = e["description"]
            toks, exc, exc_text, has_exc = parse_code_cell(e["code_cell"])
            if e["part"] == "III":
                toks = []
            e["toks"], e["exc"], e["exc_text"], e["has_exc"] = toks, exc, exc_text, has_exc
            e["key"] = (e["part"], re.sub(r"\s+", " ", e["code_cell"]).lower(), e["description_full"])
            out.append(e)
        return out
    ents = {fy: keyed(fy) for fy in (FY26, FY25)}
    k25 = {e["key"]: e for e in ents[FY25]}
    k26 = {e["key"]: e for e in ents[FY26]}
    report["entries"] = {fy: len(ents[fy]) for fy in ents}
    report["pages"] = {fy: (snaps[fy]["start"], snaps[fy]["end"]) for fy in snaps}
    report["omitted_placeholders"] = {fy: len(snaps[fy]["omitted"]) for fy in snaps}
    report["only_in_FY2025-26"] = [k for k in k25 if k not in k26]
    report["only_in_FY2026-27"] = [k for k in k26 if k not in k25]
    seq = defaultdict(int)
    seen_ids = Counter()

    def footnote_text(fy, e):
        notes = snaps[fy]["notes"]
        out = []
        for (p, n) in e.get("foot_nos", []):
            t = notes.get(p, {}).get(n)
            if t and t not in out:
                out.append(t)
        return " | ".join(out)

    order = [(FY26, e) for e in ents[FY26]] + [(FY25, e) for e in ents[FY25] if e["key"] not in k26]
    for fy, e in order:
        both = e["key"] in k25 and e["key"] in k26
        e26, e25 = k26.get(e["key"]), k25.get(e["key"])
        part = e["part"]
        seq[part] += 1
        sn = f"{part}-{seq[part]:03d}"
        fnote = re.sub(r"(\s*\.\.)+\s*$", "", footnote_text(fy, e)).strip()
        toks = e["toks"] or [""]
        for t in toks:
            norm = t.replace(".", "")
            if e["part"] == "III":
                ml, norm = "all", ""
            elif len(norm) == 8:
                ml = "code8"
            elif len(norm) == 4:
                ml = "heading4"
            else:
                ml = "unmapped"
            rid_base = f"IT-12TH-P{ {'I': 1, 'II': 2, 'III': 3}[part] }-{norm or 'ALL'}"
            seen_ids[rid_base] += 1
            row = mk(EXTRA_A,
                     rule_id=f"{rid_base}-{'both' if both else ('26' if fy == FY26 else '25')}"
                             + (f"-{seen_ids[rid_base]}" if seen_ids[rid_base] > 1 else ""),
                     schedule_or_section=f"Twelfth Schedule Part {part}", s_no=sn,
                     description=e["description_full"], code_raw=re.sub(r"\s+", " ", e["code_cell"]).strip(),
                     code_norm=norm, match_level=ml,
                     except_codes=json.dumps(e["exc"]), unparsed_except_text=int(e["has_exc"] and not e["exc"]),
                     rule_group=f"IT-12TH-P{ {'I': 1, 'II': 2, 'III': 3}[part] }",
                     rate_kind="conditional", rate_raw=f"class: Part {part}",
                     condition_text=e["exc_text"], footnote=fnote,
                     source_file=PDF[FY26 if (both or fy == FY26) else FY25],
                     page=(e26 or e)["page"] if (both or fy == FY26) else e["page"],
                     clause=f"Twelfth Schedule Part {part}, PCT entry '{re.sub(chr(10), ' ', e['code_cell'])}'",
                     extraction_method="pymupdf rule-line table rows + page image check",
                     twelfth_part=part, **({} if not both else date_both()))
            if both:
                row["snapshot_pages"] = f"{FY25}: p.{e25['page']}; {FY26}: p.{e26['page']}"
            elif fy == FY26:
                row.update(valid_from="2026-07-01", valid_to=OPEN_END, snapshot=FY26,
                           date_basis="snapshot (row present only in the FY2026-27 file)",
                           snapshot_pages=f"{FY26}: p.{e['page']}")
            else:
                row.update(valid_from=SCOPE_START, valid_to="2026-06-30", snapshot=FY25,
                           date_basis="snapshot (row present only in the FY2025-26 file)",
                           snapshot_pages=f"{FY25}: p.{e['page']}")
            if "Finance Act, 2026" in fnote and fy == FY26 and not both:
                row.update(valid_from="2026-07-01", valid_to=OPEN_END, snapshot=FY26,
                           date_basis=("footnote on the page says inserted by Finance Act, 2026 (no other date) -> "
                                       "Finance Act 2026 s.1(2) default 1 Jul 2026; Finance Act 2026 s.5(48), p.56"))
            if ml == "all":
                row["description"] = e["description_full"]
                row["code_raw"] = "Respective headings"
                row["condition_text"] = "Residual class: goods not specifically mentioned in Part I or II (a lookup must test Part I and Part II first)"
            rows.append(row)
    # V4: independent count of code tokens printed in the code column (all body lines x0<135)
    rec = {}
    for fy in (FY26, FY25):
        n_ind = 0
        for pn in range(snaps[fy]["start"], snaps[fy]["end"] + 1):
            body, foot = TW.page_lines(snaps[fy]["doc"][pn - 1])
            for l in body:
                if 50 < l["y0"] < 600 and l["x0"] < TW.CODE_X_MAX:
                    n_ind += len(CODE_TOKEN.findall(l["text"]))
        n_par = sum(len(e["toks"]) + len(e["exc"]) for e in ents[fy])
        rec[fy] = {"independent_code_tokens_in_code_column": n_ind, "parsed_code_plus_except_tokens": n_par, "difference": n_ind - n_par}
    report["reconcile_v4"] = rec
    # V2: order check (printed order should be ascending inside each part)
    anomalies = []
    last = {}
    for e in ents[FY26]:
        if e["toks"]:
            cur = e["toks"][0].replace(".", "")[:4]
            if e["part"] in last and cur < last[e["part"]][0]:
                anomalies.append(f"Part {e['part']} p.{e['page']}: {e['toks'][0]} printed after {last[e['part']][1]}")
            last[e["part"]] = (cur, e["toks"][0])
    report["order_anomalies"] = anomalies
    report["snaps"] = {fy: {"start": s["start"], "end": s["end"]} for fy, s in snaps.items()}
    report["_snaps"] = snaps
    return rows, report


def validate_twelfth(rows, report):
    flags = Counter()
    # V1: tariff + code format
    for r in rows:
        fys = [FY25, FY26] if r["snapshot"] == "both" else [r["snapshot"]]
        codes = []
        if r["match_level"] in ("code8", "heading4"):
            codes.append((r["code_norm"], "code"))
        for x in json.loads(r["except_codes"]):
            codes.append((x, "except"))
        for norm, kind in codes:
            miss = [fy for fy in fys if tariff_has(fy, norm) is False]
            if miss:
                tag = "code_not_in_tariff" if kind == "code" else "except_code_not_in_tariff"
                add_issue(r, f"{tag}: {norm} missing in tariff {','.join(miss)}")
                flags[tag] += 1
        raw = r["code_raw"]
        if r["match_level"] in ("code8", "heading4") and not re.search(r"\d{4}\.\d{4}|\d{2}\.\d{2}", raw):
            add_issue(r, "code_format: printed without the dot (" + raw + ")")
            flags["code_format"] += 1
        if r["unparsed_except_text"]:
            add_issue(r, "unparsed_except_text")
            flags["unparsed_except"] += 1
        # footnote names a code that differs from the printed code by one character
        if "code_not_in_tariff" in r["issues"] and r["footnote"]:
            fcodes = [c for c in re.findall(r"\d{4}\.\d{4}", r["footnote"]) if c.replace(".", "") != r["code_norm"]]
            for fc in fcodes:
                a, b = fc.replace(".", ""), r["code_norm"]
                if len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1 and not any(x["code_norm"] == a for x in rows):
                    add_issue(r, f"source_inconsistency: the page footnote names {fc} (one character different) - table or footnote has a typo")
                    flags["footnote_code_mismatch"] += 1
    # V2: duplicates and cross-part overlap, order
    seen = defaultdict(list)
    for r in rows:
        if r["match_level"] in ("code8", "heading4") and r["snapshot"] in ("both", FY26):
            seen[r["code_norm"]].append(r)
    for code, rs in seen.items():
        parts = {x["twelfth_part"] for x in rs}
        if len(rs) > 1:
            for x in rs:
                add_issue(x, f"duplicate_or_overlap: {code} listed {len(rs)} times in the source (parts {sorted(parts)}; "
                             f"different descriptions; the page footnote also lists the code twice)")
            flags["duplicate_or_overlap"] += len(rs)
    # heading/code overlap: 8-digit code inside a listed 4-digit heading of another part
    heads = {(r["twelfth_part"], r["code_norm"]): r for r in rows
             if r["match_level"] == "heading4" and r["snapshot"] in ("both", FY26)}
    for r in rows:
        if r["match_level"] == "code8" and r["snapshot"] in ("both", FY26):
            for (p, h), hr in heads.items():
                if r["code_norm"].startswith(h) and not any(
                        r["code_norm"].startswith(x) for x in json.loads(hr["except_codes"])):
                    add_issue(r, f"overlap_with_heading: inside heading {h} of Part {p}")
                    flags["overlap_with_heading"] += 1
    return flags


# ================================================================= B: rate table
B_BASE = "import value as increased by customs-duty, sales tax and federal excise duty"


def parse_mobile_table(key, page):
    """parse the 6-row mobile phone table (CBU / CKD columns) from the text layer lines."""
    lines = [l.strip() for l in doc(key)[page - 1].get_text().split("\n")]
    i = max(j for j, l in enumerate(lines) if l == "(4)")
    out, cur = [], None
    for l in lines[i + 1:]:
        if not l:
            continue
        if re.match(r"^\d{1,2}\s*\[\s*\]|^\d\[\s+\]", l) or l.startswith("3[") and "]" in l and len(l) < 12:
            break
        c = re.sub(r"\d\s*\[|\]", "", l).strip()
        if re.fullmatch(r"\d", c) and (cur is None or len(cur["vals"]) == 2):
            cur = {"sno": int(c), "desc": [], "vals": [], "raw": []}
            out.append(cur)
            continue
        if cur is None:
            continue
        if re.fullmatch(r"[\d,]+", c):
            cur["vals"].append(c)
            cur["raw"].append(l)
        elif len(cur["vals"]) == 0:
            cur["desc"].append(c)
    return [{"sno": o["sno"], "desc": tidy(" ".join(o["desc"])), "cbu": o["vals"][0], "ckd": o["vals"][1],
             "cbu_raw_line": o["raw"][0]} for o in out if len(o["vals"]) == 2]


def build_rates():
    rows = []
    # (page numbers found by locating the printed text in each file)
    def pg(key, frag):
        p = locate(key, frag)
        return p[0] if p else None

    OPW = {FY26: range(551, 553), FY25: range(534, 536)}   # operative table pages (images checked)
    items = [
        # (rid, s_no, category, class, twelfth_part, pct, rate text, [quote fragments], condition fragment, footnote)
        ("S1", "1", "persons (any importer)", "goods classified in Part I of the Twelfth Schedule", "I", 1.0,
         "1% of the import value as increased by customs-duty, sales tax and federal excise duty",
         ["Persons importing goods classified in Part I of the Twelfth Schedule",
          "1% of the import value as increased by customs-duty, sales tax and federal excise duty"],
         "Persons importing goods classified in Part I of the Twelfth Schedule", ""),
        ("S2", "2", "persons (any importer)", "goods classified in Part II of the Twelfth Schedule", "II", 2.0,
         "2% of the import value as increased by customs-duty, sales tax and federal excise duty",
         ["Persons importing goods classified in Part II of the Twelfth Schedule",
          "2% of the import value as increased by customs-duty, sales tax and federal excise duty"],
         "Persons importing goods classified in Part II of the Twelfth Schedule", ""),
        ("S2C", "2", "commercial importer", "goods classified in Part II of the Twelfth Schedule", "II", 3.5,
         "and 3.5% of the import value as increased by customs duty, sales tax and federal excise duty in case of commercial importer",
         ["and 3.5% of the", "import value as increased by customs duty, sales tax and federal excise duty in case of commercial importer"],
         "Persons importing goods classified in Part II of the Twelfth Schedule", "The expression added by the Finance Act, 2022."),
        ("S3", "3", "persons (any importer)", "goods classified in Part III of the Twelfth Schedule", "III", 5.5,
         "5.5% of the import value as increased by customs-duty, sales tax and federal excise duty",
         ["Persons importing goods classified in Part III of the Twelfth Schedule",
          "5.5% of the import value as increased by customs-duty, sales tax and federal excise duty"],
         "Persons importing goods classified in Part III of the Twelfth Schedule", ""),
        ("S3C", "3", "commercial importer", "goods classified in Part III of the Twelfth Schedule", "III", 6.0,
         "and 6% of the import value as increased by customs duty, sales tax and federal excise duty in case of a commercial importer",
         ["and 6% of the import value as increased by customs duty, sales tax and federal excise duty in case of a commercial importer"],
         "Persons importing goods classified in Part III of the Twelfth Schedule", "The expression added by the Finance Act, 2023."),
    ]
    for rid, sno, cat, cls, tp, pct, rate_raw, frags, cond_frag, fnote in items:
        pages = {}
        for fy in (FY26, FY25):
            ps = []
            for fr in frags:
                p = locate(fy, fr, pages=OPW[fy] if rid != "S3C" and rid != "S3" else range(min(OPW[fy]), max(OPW[fy]) + 2))
                ps.append(p[0] if p else None)
            pages[fy] = ps
        ok = {fy: all(pages[fy]) for fy in pages}
        row = mk(EXTRA_B, rule_id=f"IT-S148-RATE-{rid}-both", schedule_or_section="First Schedule Part II (rates of advance tax, s.148)",
                 s_no=sno, description=f"Rate of advance tax at import: {cat}; {cls}", code_raw=f"Twelfth Schedule Part {tp}",
                 code_norm="", match_level="all", rule_group=f"IT-S148-RATE-P{ {'I':1,'II':2,'III':3}[tp] }",
                 rate_kind="percent", rate_pct=pct, rate_raw=rate_raw, condition_text=cond_frag,
                 charged_on=B_BASE, source_file=PDF[FY26], page=next((p for p in pages[FY26] if p), ""),
                 clause=f"First Schedule Part II, S.No {sno}, column (3)" + (" (commercial importer part)" if rid.endswith("C") else ""),
                 footnote=fnote, extraction_method="text layer + page image check", importer_category=cat,
                 importer_status="", class_of_goods=cls, twelfth_part=tp,
                 snapshot_pages=f"{FY25}: p.{','.join(str(x) for x in sorted(set(p for p in pages[FY25] if p)))}; {FY26}: p.{','.join(str(x) for x in sorted(set(p for p in pages[FY26] if p)))}",
                 **date_both())
        for fy in pages:
            if not ok[fy]:
                add_issue(row, f"quote_check_failed_{fy}: {[f[:30] for f, p in zip(frags, pages[fy]) if not p]}")
        rows.append(row)
    # provisos
    prov = [
        ("PA", "a", "manufacturers covered under SRO 1125(I)/2011 (as it stood on 28 June 2019)",
         "items covered under the rescinded SRO 1125(I)/2011", 1.0,
         "in the case of manufacturers covered under rescinded Notification No. S.R.O 1125(I)/2011 dated the 31st December, 2011 as it stood on the 28th June, 2019 on import of items covered under the aforementioned S.R.O shall be 1%",
         ""),
        ("PB", "b", "persons importing finished pharmaceutical products not manufactured otherwise in Pakistan (certified by DRAP)",
         "finished pharmaceutical products not manufactured otherwise in Pakistan", 4.0,
         "in case of persons importing finished pharmaceutical products that are not manufactured otherwise in Pakistan, as certified by the Drug Regulatory Authority of Pakistan shall be 4%",
         ""),
        ("PC", "c", "importers of CKD kits of electric vehicles",
         "CKD kits of electric vehicles for small cars or SUVs with 50 kwh battery or below and LCVs with 150 kwh battery or below", 1.0,
         "in case of importers of CKD kits of electric vehicles for small cars or SUVs with 50 kwh battery or below and LCVs with 150 kwh battery or below shall be one percent",
         "Colon substituted and new clause (c) added by the Finance Act, 2021. Earlier this substitution and addition were made through Tax Laws (Amendment) Ordinance, 2021."),
    ]
    for rid, letter, cat, cls, pct, frag, fnote in prov:
        pages = {fy: locate(fy, frag, pages=range(551, 554) if fy == FY26 else range(534, 537)) for fy in (FY26, FY25)}
        row = mk(EXTRA_B, rule_id=f"IT-S148-RATE-{rid}-both",
                 schedule_or_section="First Schedule Part II (rates of advance tax, s.148)", s_no=f"proviso ({letter})",
                 description=f"Proviso ({letter}) to the rate table: {cat}", code_raw="", code_norm="", match_level="unmapped",
                 rule_group="IT-S148-RATE-PROVISO", rate_kind="percent", rate_pct=pct,
                 rate_raw=f"shall be {int(pct)}%" if pct != 1.0 or letter != "c" else "shall be one percent",
                 condition_text="Provided that the rate specified in column (3), " + frag, charged_on="",
                 source_file=PDF[FY26], page=(pages[FY26] or [""])[0],
                 clause=f"First Schedule Part II, proviso to table, clause ({letter})", footnote=fnote,
                 extraction_method="text layer + page image check", importer_category=cat, importer_status="",
                 class_of_goods=cls, twelfth_part="",
                 snapshot_pages=f"{FY25}: p.{(pages[FY25] or ['?'])[0]}; {FY26}: p.{(pages[FY26] or ['?'])[0]}", **date_both())
        row["match_level"] = "unmapped"
        add_issue(row, "scope_text_only: proviso overrides column (3) rate for the described importers/goods; "
                       "it carries no PCT code (SRO 1125(I)/2011 item list is not in data/raw)" if letter == "a" else
                  "scope_text_only: proviso overrides column (3) rate for the described importers/goods; no PCT code printed")
        if not pages[FY26] or not pages[FY25]:
            add_issue(row, "quote_check_failed")
        rows.append(row)
    # mobile phone table
    mob = {fy: parse_mobile_table(fy, 553 if fy == FY26 else 536) for fy in (FY26, FY25)}
    base_by_sno = {m["sno"]: m for m in mob[FY26]}
    for m26 in mob[FY26]:
        m25 = next(x for x in mob[FY25] if x["sno"] == m26["sno"])
        for cond, pcode, field in (("CBU", "8517.1219", "cbu"), ("CKD/SKD", "8517.1211", "ckd")):
            v26 = int(m26[field].replace(",", ""))
            v25 = int(m25[field].replace(",", ""))
            variants = [(FY25, v25, m25), (FY26, v26, m26)] if v25 != v26 else [("both", v26, m26)]
            for snap, val, mm in variants:
                row = mk(EXTRA_B,
                         rule_id=f"IT-S148-MOB-{m26['sno']}-{cond.split('/')[0]}-{'25' if snap == FY25 else '26' if snap == FY26 else 'both'}",
                         schedule_or_section="First Schedule Part II (rates of advance tax, s.148), mobile phone table",
                         s_no=str(m26["sno"]),
                         description=f"Mobile phone, {cond} condition (PCT {pcode}); C&F value (US dollar): {m26['desc']}",
                         code_raw=pcode, code_norm=pcode.replace(".", ""), match_level="code8",
                         rule_group="IT-S148-MOBILE", rate_kind="specific", rate_specific_amount=val,
                         rate_specific_unit="Rs (per mobile phone; unit not printed, header says 'Tax (in Rs.)')",
                         rate_raw=m26[field] if snap != FY25 else m25[field],
                         condition_text=("Provided further that the rate of tax on value of import of mobile phone by any person shall be as set out "
                                         f"in the following table: C & F Value of mobile phone (in US Dollar): {m26['desc']}; Tax (in Rs.) in {cond} condition"),
                         charged_on="import of mobile phone, by C&F value in US dollars (table)",
                         source_file=PDF[FY26] if snap != FY25 else PDF[FY25],
                         page=553 if snap != FY25 else 536, clause=f"First Schedule Part II, mobile phone table, S.No {m26['sno']}, column {'(3)' if cond == 'CBU' else '(4)'}",
                         footnote=("The figure '930' substituted by the Finance Act, 2026." if (m26["sno"] == 3 and field == "cbu" and snap == FY26) else ""),
                         extraction_method="text layer + page image check", importer_category="any person", importer_status="",
                         class_of_goods=f"mobile phones in {cond} condition", twelfth_part="",
                         snapshot_pages=f"{FY25}: p.536; {FY26}: p.553")
                if snap == "both":
                    row.update(date_both())
                elif snap == FY25:
                    row.update(valid_from=SCOPE_START, valid_to="2026-06-30", snapshot=FY25,
                               date_basis="FY2025-26 file prints 930; replaced from 1 Jul 2026 (see next row)")
                else:
                    row.update(valid_from="2026-07-01", valid_to=OPEN_END, snapshot=FY26,
                               date_basis=("footnote 1 on p.553: figure '930' substituted by the Finance Act, 2026; Finance Act 2026 s.5(44)(aa) p.55 "
                                           "(in Part II, second proviso table, S.No 3, column (3), for 930 substitute 100); default effective 1 Jul 2026 (s.1(2))"))
                rows.append(row)
    return rows, mob


def validate_rates(rows):
    flags = Counter()
    for r in rows:
        if r["rate_kind"] == "percent":
            p = float(r["rate_pct"])
            if not (0 <= p <= 100):
                add_issue(r, "rate_out_of_range")
            elif p > 40:
                add_issue(r, "rate_unusual_gt_40")
            if p != round(p, 1):
                add_issue(r, "one_decimal_rule")
        if r["match_level"] == "code8":
            fys = [FY25, FY26] if r["snapshot"] == "both" else [r["snapshot"]]
            for fy in fys:
                if tariff_has(fy, r["code_norm"]) is False:
                    note = ""
                    if r["code_norm"] in ("85171219", "85171211"):
                        note = " (legacy PCT code; the tariff has 8517.1100, 8517.1310/1390 smart phones and 8517.1411-1490 other mobile phones: a code mapping decision is needed before the lookup)"
                    add_issue(r, f"code_not_in_tariff: {r['code_norm']} missing in tariff {fy}{note}")
                    flags["code_not_in_tariff"] += 1
        # specific amounts: confirm printed raw text equals the amount
        if r["rate_kind"] == "specific":
            if str(r["rate_raw"]).replace(",", "") != str(r["rate_specific_amount"]):
                add_issue(r, "specific_amount_mismatch_with_raw")
    return flags


# ================================================================= C: s.148 text + Second Schedule clauses
S148_ITEMS = [
    # (id, label, fragments, meaning, rate_kind, rate_raw, charged_on, footnote_hint)
    ("1", "s.148(1)", [
        "The Collector of Customs shall collect advance tax from every importer of goods on the value of the goods at the rate specified in Part II of the First Schedule",
        "in respect of goods classified in Parts I to III of the Twelfth Schedule"],
     "Advance tax is collected at import by the Collector of Customs from EVERY importer (no filer / non-filer or active-taxpayer-list test in the text), at the Part II First Schedule rate for the Twelfth Schedule class of the goods.",
     "conditional", "rate per First Schedule Part II by Twelfth Schedule class", "value of the goods (see s.148(9))",
     "Footnote 2: expression inserted through Finance Act 2020 dated 30 Jun 2020. Footnote 1 on the preceding sub-section 147(8) mentions the active taxpayers' list but belongs to section 147, not 148."),
    ("1-P1", "s.148(1) first proviso", [
        "Provided that the Board may, by a notification in the official Gazette, add in the Twelfth Schedule any entry thereto or omit any entry therefrom or amend any entry therein"],
     "Board can add, omit or amend Twelfth Schedule entries by notification (a notification can move a code between classes).", "conditional", "", "", "Footnote 3: colon and provisos added through Finance Act 2020"),
    ("1-P2", "s.148(1) second proviso", [
        "Provided further that in case of goods classified under Part III of the Twelfth Schedule which are used both as raw material and finished goods, the Board may, by notification in the official Gazette, specify that goods imported by a person or class of persons as raw material for its own use shall be treated as classified under Part II of the Twelfth Schedule, subject to such conditions and procedure as may be prescribed"],
     "Board may by notification treat Part III goods imported as raw material for own use as Part II (2% class) goods.", "conditional", "", "", "Footnote 3: Finance Act 2020"),
    ("1-P3", "s.148(1) third proviso (Digital Presence Proceeds Tax)", [
        "Provided also that the Collector of Customs, shall not collect tax under this section, where the recipient of goods is also liable under the Digital Presence Proceeds tax, Act, 2025 and same has been collected by the payment intermediary as defined in section 153."],
     "No s.148 collection where the recipient is also liable under the Digital Presence Proceeds Tax Act 2025 and that tax was collected by the payment intermediary (s.153).", "exempt", "tax not collected", "",
     "Footnote 4: Full stop substituted and a new proviso inserted by the Finance Act, 2025."),
    ("2A", "s.148(2A)", [
        "Notwithstanding omission of sub-section (2), any notification issued under the said sub-section and for the time being in force, shall continue to remain in force, unless amended or rescinded by the Board through notification in the official Gazette."],
     "Old exemption notifications issued under the omitted sub-section (2) stay in force until amended or rescinded (SRO 663(I)/2026 cites this sub-section (2A) when rescinding SRO 455(I)/2026).", "conditional", "", "", "Footnote 3 Inserted by Finance Act 2015; footnote 4 'amended or' inserted by Finance Act 2018"),
    ("5", "s.148(5)", [
        "Advance tax shall be collected in the same manner and at the same time as the customs-duty payable in respect of the import or, if the goods are exempt from customs-duty, at the time customs-duty would be payable if the goods were dutiable."],
     "Time and manner of collection: with customs duty, or when duty would have been payable if goods are duty-exempt.", "conditional", "", "", ""),
    ("6", "s.148(6)", [
        "Subject to sub-section (6A), the provisions of the Customs Act, 1969 (IV of 1969), in so far as relevant, shall apply to the collection of tax under this section."],
     "Customs Act 1969 applies to the collection (recovery, assessment procedure).", "conditional", "", "", "Footnote 1: word 'The' substituted by Finance Act 2024"),
    ("6A", "s.148(6A)", [
        "The Board may, by notification in the official Gazette, determine the minimum value of goods for the purpose of collection of advance tax under this section."],
     "Board can notify a minimum value of goods; tax is then charged on at least that value (see s.148(9)(c)). The notified values are not in data/raw.", "conditional", "", "minimum value notified by the Board (not in data/raw)", "Sub-section (6A) inserted by the Finance Act, 2024"),
    ("7", "s.148(7)", [
        "The tax required to be collected under this section shall be minimum tax on the income of the importer arising from the imports subject to sub-section (1) and this sub-section shall not apply in the case of import of goods on which tax is required to be collected under this section by an industrial undertaking for its own use."],
     "The tax collected is a MINIMUM tax (not final) on the importer's income from these imports; the minimum-tax treatment does not apply to an industrial undertaking importing for its own use.", "conditional", "minimum tax", "income of the importer arising from imports",
     "Footnotes: sub-section (7) substituted by Finance Act 2006; 'a final' replaced by 'minimum' via Finance Act 2019; 'industrial undertaking' words inserted Finance Act 2020"),
    ("7A", "s.148(7A)", [
        "Notwithstanding anything contained in sub-section (7), the tax required to be collected under this section shall be minimum tax on the income every person arising from imports of following goods",
        "(i) edible oil; (ii) packaging material; (iii) paper and paper board; or (iv) plastics:",
        "Provided that the Board with the approval of Minister in-charge may, by a notification in the official Gazette, add any entry thereto or omit any entry therefrom or amend any entry therein this sub-section."],
     "For edible oil, packaging material, paper and paper board, plastics the tax collected is a minimum tax for EVERY person (including an industrial undertaking importing for own use, which sub-section (7) excludes).", "conditional", "minimum tax", "income of every person arising from imports of the listed goods", "Sub-section (7A) inserted by the Finance Act, 2022"),
    ("9-COLL", "s.148(9) 'Collector of Customs'", [
        "Collector of Customs means the person appointed as Collector of Customs under section 3 of the Customs Act, 1969 (IV of 1969), and includes a Deputy Collector of Customs, an Additional Collector of Customs, or an officer of customs appointed as such under the aforesaid section"],
     "Definition of the collecting officer.", "conditional", "", "", ""),
    ("9-VAL-a", "s.148(9) 'value of goods' (a): Third Schedule retail-price goods", [
        "Value of goods means",
        "(a) in case of goods chargeable to tax at retail price under the Third Schedule of the Sales Tax Act, 1990, the retail price of such goods increased by sales tax payable in respect of the import and taxable supply of the goods;"],
     "For Third Schedule (retail-price) goods the tax base is the retail price plus sales tax payable on import and on the taxable supply.", "conditional", "", "retail price of the goods increased by sales tax payable in respect of the import and taxable supply",
     "Footnote 4 (p.332): the expressions substituted by Finance Act 2020; the pre-2020 text based the value on customs value + duty + FED + sales tax"),
    ("9-VAL-b", "s.148(9) 'value of goods' (b): all other goods", [
        "(b) in case of goods other than those specified in clauses (a) and (c); the value of the goods as determined under the Customs Act, 1969 (IV of 1969), as if the goods were subject to ad valorem duty increased by the custom-duty, federal excise duty and sales tax, if any, payable in respect of the import of the goods"],
     "Normal base: customs value (as if ad valorem) + customs duty + federal excise duty + sales tax payable on import. Customs duty is therefore in the base of s.148 tax (cascade: CD/RD/ACD first, then ST, then IT).", "conditional", "", "customs value increased by customs-duty, federal excise duty and sales tax",
     "Footnote 1: words 'all other goods' substituted by Finance Act 2024"),
    ("9-VAL-c", "s.148(9) 'value of goods' (c): notified minimum value", [
        "(c) minimum value as notified by the Board under subsection (6A) as if such goods were subject to ad valorem duty as increased by the custom-duty, federal excise duty and sales tax, payable in respect of the import of the goods."],
     "Where the Board has notified a minimum value, that value (plus customs duty, FED and sales tax) is the base.", "conditional", "", "notified minimum value increased by customs-duty, federal excise duty and sales tax", "Clause (c) added by the Finance Act, 2024"),
]

# Second Schedule clause metadata. dates: (valid_from, valid_to, basis) or None -> snapshot convention
CLAUSE_META = {
    "9AA": dict(kind="percent", pct=0.25, raw="0.25%", desc="Reduced rate of 0.25% under s.148 on import of white sugar, 25 Aug 2020 to 15 Nov 2020 (expired)",
                dates=("2020-08-25", "2020-11-15", "stated in clause: 25th day of August, 2020 to the 15th day of November, 2020")),
    "9AB": dict(kind="percent", pct=0.25, raw="0.25%", desc="Reduced rate of 0.25% under s.148 on commercial import of white sugar, 26 Jan 2021 till 30 Jun 2021 (expired)",
                dates=("2021-01-26", "2021-06-30", "stated in clause: from the 26th day of January 2021 till the 30th day of June, 2021")),
    "4": dict(kind="conditional", raw="tax under section 148 shall not exceed the amount specified in Notification No. S.R.O. 577(I)/2005, dated 6 June 2005",
              desc="Cap on s.148 tax for old and used automotive vehicles: not more than the amount in SRO 577(I)/2005 (that SRO is not in data/raw)", issue="cap_amount_in_SRO_577(I)/2005_not_in_data_raw"),
    "12B": dict(kind="exempt", desc="s.148 does not apply to import of listed COVID-19 testing/medical goods (Table), 20 Mar 2020 to 31 Dec 2021 (expired)",
                dates=("2020-03-20", "2021-12-31", "stated in clause: commencing from 20th day of March, 2020 and ending on 31st day of December, 2021")),
    "12BA": dict(kind="exempt", desc="s.148 does not apply to import of 30 million face masks received as humanitarian assistance (HANES Brands) for Lahore Division; one-off, no date printed", issue="no_end_date_printed_one_off_consignment"),
    "12C": dict(kind="exempt", desc="s.148 does not apply to persons importing pulses, 7 Apr 2020 to 30 Sep 2020 (expired)",
                dates=("2020-04-07", "2020-09-30", "stated in clause: commencing from the 7th day of April, 2020 and ending on 30th September, 2020")),
    "12D": dict(kind="exempt", desc="s.148 does not apply to import of finished drug Remdesivir 100 mg injection from 22 Jun 2020 until the date notified by the Board",
                dates=("2020-06-22", OPEN_END, "stated start 22 Jun 2020; end 'date as may be notified by the Board' - no notification in data/raw"), issue="end_date_depends_on_Board_notification_not_in_data_raw"),
    "12E": dict(kind="exempt", desc="s.148 does not apply to import of medicines for life-threatening rare diseases not manufactured in Pakistan, subject to Board approval and NHSRC recommendation (personal use)"),
    "12H": dict(kind="exempt", desc="s.148 does not apply to import of oxygen gas, oxygen cylinders and cryogenic tanks for three months from 23 Jun 2020 (expired)",
                dates=("2020-06-23", "2020-09-22", "stated: period of three months starting from the 23rd of June, 2020 (end date computed)"), issue="end_date_computed_from_three_months"),
    "12I": dict(kind="exempt", desc="s.148 does not apply to import of 83 X Micron sprayers for anti-locust operation by NDMA (one-off, no date printed)", issue="no_end_date_printed_one_off_consignment"),
    "12K": dict(kind="exempt", desc="s.148 does not apply to import of cryogenic tanks for oxygen by manufacturers of oxygen for three months from 25 Dec 2020 (expired)",
                dates=("2020-12-25", "2021-03-24", "stated: three months starting from the 25th day of December, 2020 (end date computed)"), issue="end_date_computed_from_three_months"),
    "12L": dict(kind="exempt", desc="s.148 and s.153 do not apply to import and subsequent supply of 500,000 MT white sugar imported by the Trading Corporation of Pakistan (no date printed)", issue="no_end_date_printed_quantity_limited"),
    "12M": dict(kind="exempt", desc="s.148 does not apply to import of oxygen, oxygen cylinders, cryogenic tanks, concentrators etc. for 180 days from 14 May 2021 (expired)",
                dates=("2021-05-14", "2021-11-09", "stated: period of one hundred and eighty days starting from the 14th day of May, 2021 (end date computed)"), issue="end_date_computed_from_180_days"),
    "12N": dict(kind="exempt", desc="s.148 does not apply to import into Border Sustenance Markets (Iran / Afghanistan border) of the goods in Table-I, subject to conditions (supply only inside the markets, bank guarantee, proof of premises)"),
    "12O": dict(kind="exempt", desc="s.148 does not apply to import of drones donated by the Ministry of Agriculture and Rural Affairs, China, through sea route (no date printed)", issue="no_end_date_printed_one_off_consignment"),
    "12P": dict(kind="exempt", desc="s.148 does not apply to import of machinery and equipment listed in S.No 32 of Part-I of the Fifth Schedule to the Customs Act, 1969, on the same conditions"),
    "16": dict(kind="exempt", desc="Sections 113, 148, 151, 153, 155 and 156 do not apply to institutions of the Agha Khan Development Network (Pakistan)"),
    "47A": dict(kind="conditional", xref=True, desc="Cross reference: s.153 does not apply to payments for supply of goods imported by the same person on which s.148 tax has been paid (not an exemption from s.148 itself)"),
    "47C": dict(kind="conditional", xref=True, desc="Cross reference: s.154(1) does not apply to an exporter of cooking oil/ghee to Afghanistan from whom s.148 tax was collected on import of edible oil (not an exemption from s.148 itself)"),
    "56": dict(kind="exempt", desc="s.148 (withholding tax on imports) does not apply to a long list: Chapter 86 and 99 goods except 9918, listed petroleum products imported by OMCs and refineries, Federal/Provincial/Local Governments, foreign government-owned companies, exporters' inputs, goods for relief, CBU motor vehicles up to 1000cc, printed books, newspapers, etc. (sub-clauses (i) to (xx) and table (xviii)); see condition_text"),
    "60": dict(kind="exempt", desc="s.148 and s.153 do not apply to cypher devices verified by Cabinet Division (NTISB)"),
    "60A": dict(kind="exempt", desc="s.148 does not apply to plant, machinery, equipment, dumpers and special purpose vehicles imported by CSCEC and CCCC for Sukkur-Multan Motorway and KKH Phase-II (CPEC)"),
    "60AA": dict(kind="exempt", desc="s.148 does not apply to construction materials or goods up to Rs 10,898.000 million imported by CSCEC for Sukkur-Multan Motorway (CPEC)"),
    "60B": dict(kind="exempt", desc="s.148 does not apply to 35 armoured and security vehicles imported by or for the Ministry of Foreign Affairs (conditions apply)"),
    "60C": dict(kind="exempt", desc="s.148 does not apply to equipment for Rail Based Mass Transit Projects in Lahore, Karachi, Peshawar and Quetta under CPEC"),
    "60D": dict(kind="exempt", desc="s.148 does not apply to fire fighting equipment imported by industrial undertakings in special economic zones"),
    "60DA": dict(kind="exempt", desc="s.148 does not apply to import of capital equipment (as defined in the Special Technology Zones Authority Act, 2021) by zone developers (10 years from development agreement), zone enterprises (10 years from licence) and the Authority", issue="period_runs_from_agreement_or_licence_date_not_in_data_raw"),
    "60E": dict(kind="exempt", desc="s.148 does not apply to mobile phones brought in personal baggage under the Baggage Rules, 2006"),
    "70": dict(kind="exempt", desc="s.148 does not apply to goods imported by contractors and sub-contractors for the HUB Power Company Limited power project"),
    "77": dict(kind="exempt", desc="Sections 148 and 153 do not apply to import and supply of items with dedicated use of renewable energy (solar, wind: lamps, LEDs, wind turbines, PV modules and components)"),
    "91": dict(kind="exempt", desc="s.148 does not apply to listed agricultural machinery and equipment (tillage, seeding, irrigation, harvesting, post-harvest) with their PCT codes (tables)"),
    "92": dict(kind="exempt", desc="s.148 does not apply to aircraft (wet or dry lease), maintenance kits, spare parts, MRO tools, greenfield airport tools, aviation simulators"),
    "98": dict(kind="exempt", desc="s.148 does not apply to import of ships and floating crafts purchased or bare-boat chartered by a Pakistani entity flying the Pakistani flag, up to the year 2030; ships imported for demolition (ship breaking) remain chargeable",
               dates=(SCOPE_START, "2030-12-31", "clause says 'available up to the year 2030' (read as 31 Dec 2030)"), issue="date_interpretation: 'up to the year 2030' read as 31 Dec 2030"),
    "99": dict(kind="exempt", desc="s.148 does not apply to import or acquisition of aircraft on wet or dry lease by Pakistan International Airlines Corporation w.e.f. 19 Mar 2015",
               dates=("2015-03-19", OPEN_END, "stated in clause: with effect from 19th March, 2015 (earlier than the data scope)")),
    "123": dict(kind="exempt", desc="s.148 does not apply to goods imported for flood relief operations (NDMA/PDMA certified) for three months from 1 Dec 2022 (expired)",
                dates=("2022-12-01", "2023-02-28", "stated: three months from the 1st day of December, 2022 (end date computed)"), issue="end_date_computed_from_three_months"),
    "124": dict(kind="exempt", desc="s.148 does not apply to tomato (0702.0000) and onion (0703.1000) imported till 31 Dec 2022 (expired)",
                dates=(None, "2022-12-31", "stated in clause: imported till the 31st day of December, 2022")),
}


def extract_codes(text):
    cs = set()
    for m in re.finditer(r"(?<![\d.])(\d{4}\.\d{4}|\d{8})(?![\d])", text):
        cs.add(m.group(1).replace(".", ""))
    return sorted(cs)


def build_special():
    rows = []
    # ---- section 148 text
    for rid, label, frags, meaning, kind, rate_raw, charged, fnote in S148_ITEMS:
        pg = {}
        for fy in (FY26, FY25):
            ps = []
            for f in frags:
                p = locate(fy, f, pages=range(300, 345))
                ps.append(p[0] if p else None)
            pg[fy] = ps
        ok26, ok25 = all(pg[FY26]), all(pg[FY25])
        row = mk(EXTRA_C, rule_id=f"IT-S148-SUB-{rid}-both", schedule_or_section="s.148", s_no=label.split(" ")[0],
                 description=meaning, code_raw="", code_norm="", match_level="all", rule_group="IT-S148-SECTION",
                 rate_kind=kind, rate_raw=rate_raw, condition_text=" ".join(frags), charged_on=charged,
                 source_file=PDF[FY26], page=next((p for p in pg[FY26] if p), ""), footnote=fnote,
                 clause=f"Income Tax Ordinance 2001, {label}", extraction_method="text layer quote-check + page image check",
                 clause_part="", in_scope=1, codes_in_clause="[]",
                 snapshot_pages=f"{FY25}: p.{','.join(str(p) for p in sorted(set(x for x in pg[FY25] if x)))}; {FY26}: p.{','.join(str(p) for p in sorted(set(x for x in pg[FY26] if x)))}",
                 **date_both())
        if rid == "1-P3":
            row.update(date_basis="FA2025-convention (footnote 4 p.329: proviso inserted by the Finance Act, 2025; both snapshot files contain it)")
            add_issue(row, "not_verified_in_Finance_Act_2025: the Finance Bill 2025 text has no amendment of s.148; the Act 2025 (scan) was not searched page by page")
        if not ok26:
            add_issue(row, "quote_check_failed_FY2026-27: " + str([f[:40] for f, p in zip(frags, pg[FY26]) if not p]))
        if not ok25:
            add_issue(row, "quote_check_failed_FY2025-26: " + str([f[:40] for f, p in zip(frags, pg[FY25]) if not p]))
        rows.append(row)
    # ---- s.53A (Finance Act 2026) general power to reduce withholding minimum taxes
    frag_a = ("The Federal Government may reduce the rate of any of the withholding taxes in the nature of minimum tax as given in First Schedule of this Ordinance, "
              "other than minimum tax chargeable under section 113 of this Ordinance, by one")
    frag_b = ("percent on the basis of economic viability in cases of persons or class of persons, "
              "subject to such restrictions and limitations as the Federal Government may specify.")
    frag = frag_a + " " + frag_b
    pa, pb = locate(FY26, frag_a), locate(FY26, frag_b)
    p26 = pa if (pa and pb) else []
    p25 = locate(FY25, frag_a)
    row = mk(EXTRA_C, rule_id="IT-S53A-XREF-26", schedule_or_section="s.53A", s_no="s.53A(1)",
             description=("Federal Government may reduce a withholding tax 'in the nature of minimum tax' in the First Schedule by one percentage point for persons or classes of persons "
                          "on 'economic viability' grounds. s.148(7) calls the s.148 tax a minimum tax, so this may reach s.148 rates, but the text does not name s.148."),
             match_level="all", rule_group="IT-S148-XREF", rate_kind="conditional", rate_raw="reduction of up to 1 percentage point by notification (none in data/raw)",
             condition_text=frag, source_file=PDF[FY26], page=(p26 or [""])[0], valid_from="2026-07-01", valid_to=OPEN_END,
             date_basis="inserted by the Finance Act, 2026 (s.5(8), Act p.33); default effective 1 Jul 2026 (s.1(2)); absent from the FY2025-26 file",
             snapshot=FY26, footnote="5[53A ...] Section 53A inserted by the Finance Act, 2026.", clause="Income Tax Ordinance 2001, section 53A (inserted by Finance Act 2026 s.5(8))",
             extraction_method="text layer quote-check", clause_part="", in_scope=1, codes_in_clause="[]", snapshot_pages=f"{FY26}: p.{(p26 or ['?'])[0]}")
    add_issue(row, "applicability_to_s148_not_stated: section names 'withholding taxes in the nature of minimum tax' in the First Schedule generally; no notification under it is in data/raw")
    if p25:
        add_issue(row, "unexpected: s.53A text found in FY2025-26 file")
    if not p26:
        add_issue(row, "quote_check_failed_FY2026-27")
    rows.append(row)

    # ---- Second Schedule clauses
    cl = {}
    for fy in (FY26, FY25):
        a, b = CL.second_schedule_range(RAW / PDF[fy])
        cl[fy] = {}
        for c in CL.body_clauses(RAW / PDF[fy], a, b):
            if "148" in c["text"]:
                cl[fy][c["no"]] = c
    cstat = {"clauses_FY2026-27": len(cl[FY26]), "clauses_FY2025-26": len(cl[FY25]),
             "only_FY2026-27": sorted(set(cl[FY26]) - set(cl[FY25])), "only_FY2025-26": sorted(set(cl[FY25]) - set(cl[FY26])),
             "text_differs": sorted(k for k in set(cl[FY26]) & set(cl[FY25]) if cl[FY26][k]["text"] != cl[FY25][k]["text"]),
             "text_order_differs_same_words": sorted(k for k in set(cl[FY26]) & set(cl[FY25]) if cl[FY26][k]["text"] != cl[FY25][k]["text"] and sorted(re.sub(r"[^a-z0-9]", "", cl[FY26][k]["text"].lower())) == sorted(re.sub(r"[^a-z0-9]", "", cl[FY25][k]["text"].lower())))}
    missing_meta = [k for k in cl[FY26] if k not in CLAUSE_META and k != "9AD"]
    cstat["clauses_without_meta"] = missing_meta
    for no in sorted(cl[FY26], key=lambda x: (int(re.match(r"\d+", x).group()), x)):
        if no == "9AD":
            continue
        c26, c25 = cl[FY26][no], cl[FY25].get(no)
        meta = CLAUSE_META.get(no, dict(kind="exempt", desc="(no meta) s.148 mention"))
        same_words = c25 is not None and sorted(re.sub(r"[^a-z0-9]", "", c25["text"].lower())) == sorted(re.sub(r"[^a-z0-9]", "", c26["text"].lower()))
        both = c25 is not None and (c25["text"] == c26["text"] or same_words)
        stated = meta.get("dates")
        row = mk(EXTRA_C, rule_id=f"IT-2ND-P{c26['part']}-{no}-{'both' if both else '26'}",
                 schedule_or_section=f"Second Schedule Part {c26['part']}", s_no=f"({no})",
                 description=meta["desc"], code_raw="", code_norm="", match_level="all" if False else "unmapped",
                 rule_group="IT-S148-XREF" if meta.get("xref") else "IT-S148-EXEMPT" if meta["kind"] == "exempt" else "IT-S148-REDUCED",
                 rate_kind=meta["kind"], rate_pct=meta.get("pct", ""), rate_raw=meta.get("raw", "section 148 shall not apply" if meta["kind"] == "exempt" else ""),
                 condition_text=c26["text"], charged_on="", source_file=PDF[FY26], page=c26["pages"][0],
                 clause=f"Income Tax Ordinance 2001, Second Schedule Part {c26['part']}, clause ({no})"
                        + (f" (continues on p.{c26['pages'][-1]})" if len(c26["pages"]) > 1 else ""),
                 footnote="", extraction_method="pymupdf body text (above footnote rule) + page image check", clause_part=c26["part"],
                 codes_in_clause=json.dumps(extract_codes(c26["text"])),
                 snapshot_pages=f"{FY25}: p.{c25['pages'][0] if c25 else '?'}; {FY26}: p.{c26['pages'][0]}")
        if stated:
            vf, vt, basis = stated
            row.update(valid_from=vf or SCOPE_START, valid_to=vt, date_basis=basis, snapshot="both" if both else FY26)
            if vf is None:
                row["valid_from"] = vt
                row["date_basis"] += "; no start date printed: valid_from set equal to valid_to"
                add_issue(row, "start_date_not_printed")
        else:
            row.update(date_both() if both else dict(valid_from="2026-07-01", valid_to=OPEN_END, date_basis="snapshot", snapshot=FY26))
        row["in_scope"] = int(row["valid_to"] >= SCOPE_START)
        if meta.get("issue"):
            add_issue(row, meta["issue"])
        if not both:
            add_issue(row, "text_differs_or_missing_in_FY2025-26_file")
        if not row["in_scope"]:
            row["date_basis"] += "; EXPIRED before the data scope (kept for history, in_scope=0)"
        if no == "12N":
            row["condition_text"] = c26["text"]
        rows.append(row)

    # ---- clause (9AD) sugar chain (only in the 30.06.2026 file; plus SROs in data/raw)
    c = cl[FY26]["9AD"]
    base_text = c["text"]
    fn_pg = 649
    foot = ("Footnotes on p.649 of the 30.06.2026 file: 1 Clause (9AD) added by S.R.O.1216(I)/2025 dated 08.07.2025. "
            "2 The word 'September' substituted with the word 'November' by S.R.O. 1833(I)/2025 dated 22.09.2025. "
            "3 The expression '30th day of November, 2025' substituted by S.R.O. 455(I)/2026 dated 05.03.2026. "
            "4 The S.R.O. 455(I)/2026 dated 05.03.2026 rescinded through S.R.O. 663(I)/2026 dated 22.04.2026.")
    chain = [
        ("A", "2025-07-08", "2025-09-21", "SRO 1216(I)/2025 dated 08.07.2025 (clause added; cut-off date for imports 30 September 2025)",
         "9AD as first notified: 0.25% on commercial import of white crystalline sugar up to 500,000 MT, cut-off 30 Sep 2025",
         "cut-off date for import of sugar ... shall be the 30th day of September, 2025", SRO_FILES["SRO1216"], 1,
         "valid_to=day before SRO 1833 took effect; 'on or before 30 Sep 2025' was the import cut-off at the time"),
        ("B", "2025-09-22", "2025-11-30", "SRO 1833(I)/2025 dated 22.09.2025 ('September' replaced by 'November'; day taken as 30th from the quote in SRO 455(I)/2026: 'expression 30th day of November, 2025')",
         "9AD after SRO 1833: cut-off moved to 30 Nov 2025", "cut-off date ... the 30th day of November, 2025", SRO_FILES["SRO1833"], 1,
         "the 30th is inferred from SRO 455(I)/2026 which quotes '30th day of November, 2025'; SRO 1833 itself only says November"),
        ("C", "2026-03-05", "2026-04-21", "SRO 455(I)/2026 dated 05.03.2026 (cut-off changed to 28 February 2026); rescinded by SRO 663(I)/2026 dated 22.04.2026 'with immediate effect'",
         "9AD after SRO 455: cut-off 28 Feb 2026 (a date BEFORE the SRO was issued)", "cut-off date ... the 28th day of February, 2026", SRO_FILES["SRO455"], 1,
         "valid range = issue date of SRO 455 to day before SRO 663; whether it reached back to imports of 1 Dec 2025 - 28 Feb 2026 is not stated"),
        ("D", "2026-04-22", OPEN_END, "SRO 663(I)/2026 dated 22.04.2026 rescinded SRO 455(I)/2026 'with immediate effect' (cites s.148(2A) of the Ordinance)",
         "After SRO 663: the 28 Feb 2026 change is rescinded, so the 30 Nov 2025 cut-off (SRO 1833) applies; no new imports qualify for 0.25%", "(rescission; no cut-off text)", SRO_FILES["SRO663"], 1,
         "the consolidated 30.06.2026 text still prints '28th day of February, 2026' (p.649) with footnote 4 saying SRO 455 was rescinded"),
    ]
    mcut = re.search(r"shall be the .*$", base_text)
    head = base_text[:mcut.start()] + "shall be the "
    cut_text = {"A": "30th day of September, 2025.", "B": "30th day of November, 2025.", "C": "28th day of February, 2026."}
    for tag, vf, vt, basis, desc, cond, srcf, srcp, note in chain:
        row = mk(EXTRA_C, rule_id=f"IT-2ND-P2-9AD-{tag}", schedule_or_section="Second Schedule Part II", s_no="(9AD)",
                 description=desc, code_raw="", code_norm="", match_level="unmapped", rule_group="IT-S148-REDUCED",
                 rate_kind="percent" if tag != "D" else "conditional", rate_pct=0.25 if tag != "D" else "",
                 rate_raw="0.25% of the value of commercial import" if tag != "D" else "reverts to the 30 Nov 2025 cut-off (see issues)",
                 condition_text=(head + cut_text[tag] if tag != "D" else "S.R.O. 663(I)/2026 ... to rescind ... (i) S.R.O. No. 455(I)/2026 dated the 5th March, 2026; and (ii) S.R.O. No. 527(I)/2026 dated the 19th March, 2026."),
                 charged_on="value of commercial import of white crystalline sugar, up to 500,000 MT in aggregate",
                 valid_from=vf, valid_to=vt, date_basis=basis, snapshot=FY25,
                 footnote=foot, source_file=PDF[FY26], page=fn_pg,
                 clause="Income Tax Ordinance 2001, Second Schedule Part II, clause (9AD) with footnotes 1-4; amending SRO: " + srcf,
                 extraction_method="text layer (ITO p.649) + SRO page images (SRO files are scans, read by eye)", clause_part="II",
                 in_scope=1, codes_in_clause="[]", snapshot_pages=f"{FY26}: p.649 (clause absent from the FY2025-26 file of 31.07.2025 and the 20.02.2026 file)")
        if tag == "D":
            row["snapshot"] = "both"
        add_issue(row, "ambiguity: " + note)
        if tag == "C":
            add_issue(row, "ambiguity: consolidated text prints 28 Feb 2026 but footnote 4 says SRO 455 was rescinded by SRO 663 (22.04.2026); net cut-off is probably 30 Nov 2025 (SRO 1833) - confirm with FBR/owner")
        rows.append(row)
    return rows, cstat


def validate_special(rows):
    flags = Counter()
    for r in rows:
        if r["tax"] != "IT":
            continue
        if r["valid_to"] < r["valid_from"]:
            add_issue(r, "date_order")
        codes = json.loads(r["codes_in_clause"] or "[]") if r["codes_in_clause"] else []
        if r["in_scope"] and codes:
            miss = [c for c in codes if tariff_has(FY26, c) is False and len(c) == 8]
            if miss:
                add_issue(r, f"codes_in_clause_not_in_tariff_FY2026-27: {len(miss)} of {len(codes)} (first: {','.join(miss[:6])})")
                flags["clause_codes_missing"] += 1
    return flags


# ================================================================= output
def write_outputs(name, rows, extra, meta):
    cols = COMMON + extra
    for r in rows:
        for c in cols:
            r.setdefault(c, "")
    with open(PROC / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r[c] for c in cols})
    meta = dict(meta)
    meta["row_count"] = len(rows)
    meta["status_counts"] = dict(Counter(r["status"] for r in rows))
    (PROC / f"{name}.json").write_text(json.dumps({"meta": meta, "rows": [{c: r[c] for c in cols} for r in rows]},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")


def apply_vision(rows, key_by_fy):
    """mark rows whose page was viewed; record mismatches from the hand-written log."""
    mm = defaultdict(list)
    for m in VISION["mismatches"]:
        mm[(m["file"], m["page"])].append(m)
    n_view = 0
    for r in rows:
        fy = FY25 if r["source_file"] == PDF[FY25] else FY26
        pg = r["page"]
        if pg == "":
            continue
        if vision_viewed(fy, int(pg)):
            n_view += 1
            r["extraction_method"] = r["extraction_method"].replace("page image check", "page image CHECKED")
            for m in mm.get((fy, int(pg)), []):
                if m.get("match") and m["match"] not in (r["code_raw"], r["s_no"], r["rule_id"]):
                    continue
                add_issue(r, "vision_mismatch: " + m["note"])
    return n_view


def main():
    PROC.mkdir(exist_ok=True)
    load_tariff()
    meta_common = {"method": "pymupdf text/geometry from the PDFs in data/raw; every quoted text checked against the page text layer; "
                             "page images checked by eye (see a3_it_vision_log.json)",
                   "files": {k: v for k, v in PDF.items()},
                   "snapshots": {FY25: "ITO amended up to 31.07.2025 (includes Finance Act 2025)", FY26: "ITO amended up to 30.06.2026 (includes Finance Act 2026)"}}
    # ---- A
    A, repA = build_twelfth()
    flagsA = validate_twelfth(A, repA)
    # ---- B
    B, mob = build_rates()
    flagsB = validate_rates(B)
    # ---- C
    C, cstat = build_special()
    flagsC = validate_special(C)
    for rows in (A, B, C):
        for r in rows:
            r["rate_pct"] = r["rate_pct"]
    nvA = apply_vision(A, None)
    nvB = apply_vision(B, None)
    nvC = apply_vision(C, None)
    decision = ("First Schedule Part II: the OPERATIVE table is the 3-row table printed in the page body (S.No 1 = Twelfth Schedule Part I 1%, "
                "S.No 2 = Part II 2% and 3.5% for commercial importers, S.No 3 = Part III 5.5% and 6% for commercial importers) followed by provisos (a)-(c) "
                "and the mobile phone table with CBU / CKD-SKD columns. The table with S.No 1 (i)-(vii), 2 pulses 2%, 3 commercial importers 3%, 3A coal 4%, "
                "4 ship breakers 4.5%, 5/6 5.5%, 7 6%, plastic raw material provisos (1.75% / 4.5%) and the US-dollar mobile table with only one tax column, is printed "
                "in FOOTNOTE type (small font, below the rule, inside footnote 3 'Table substituted through Finance Act, 2020 ... substituted table read as follows') and is the "
                "SUPERSEDED table. Evidence: page images p.550-553 of the 30.06.2026 file and p.534-536 of the 31.07.2025 file (heading 'PART II ... [3 ' footnote marker on the table title, the old table sits below the footnote rule).")
    metaA = dict(meta_common, purpose="Twelfth Schedule entries: class of goods for s.148 (Part I -> 1% class, Part II -> 2% class, Part III -> residual)",
                 validators={"flags": dict(flagsA)}, report={k: v for k, v in repA.items() if not k.startswith("_")})
    metaB = dict(meta_common, purpose="First Schedule Part II rates of advance tax at import (s.148)", operative_table_decision=decision,
                 validators={"flags": dict(flagsB)}, mobile_table_parsed={k: v for k, v in mob.items()})
    metaC = dict(meta_common, purpose="s.148 operative text and Second Schedule clauses exempting/reducing s.148 tax", validators={"flags": dict(flagsC)}, report=cstat,
                 note="in_scope=0 rows expired before 1 Jul 2025 and are kept for history only")
    write_outputs("a3_it_twelfth_schedule", A, EXTRA_A, metaA)
    write_outputs("a3_it_s148_rates", B, EXTRA_B, metaB)
    write_outputs("a3_it_s148_special_rules", C, EXTRA_C, metaC)
    # ---- failures + spotcheck
    allrows = [("A", r) for r in A] + [("B", r) for r in B] + [("C", r) for r in C]
    with open(PROC / "a3_it_failures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "page_image", "s_no", "code_raw", "rate_raw", "issues"])
        for tag, r in allrows:
            if r["issues"]:
                key = FY25 if r["source_file"] == PDF[FY25] else FY26
                w.writerow([r["page"], img_rel(key, int(r["page"])) if r["page"] != "" else "", r["s_no"], r["code_raw"], r["rate_raw"], r["issues"]])
    sc = []
    import random
    rnd = random.Random(20260713)
    must = [(t, r) for t, r in allrows if t in ("B", "C")]
    Arows = [r for t, r in allrows if t == "A"]
    chosen = {id(r) for r in Arows if ("xcept" in r["code_raw"]) or r["code_norm"] == "15200000" or r["issues"]}
    byp = defaultdict(list)
    for r in Arows:
        byp[(r["twelfth_part"], r["page"])].append(r)
    for k, lst in byp.items():  # at least 2 per page
        for r in rnd.sample(lst, min(2, len(lst))):
            chosen.add(id(r))
    need = int(len(Arows) * 0.10) + 1
    pool = [r for r in Arows if id(r) not in chosen]
    rnd.shuffle(pool)
    while len(chosen) < max(need, int(len(Arows) * 0.15)) and pool:
        chosen.add(id(pool.pop()))
    sel = [(t, r) for t, r in allrows if (t == "A" and id(r) in chosen)] + must
    with open(PROC / "spotcheck_a3_it.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "page_image", "s_no", "pct_code", "rate", "correct? (Y/N)", "true_value_if_N"])
        for t, r in sel:
            key = FY25 if r["source_file"] == PDF[FY25] else FY26
            pg = int(r["page"]) if r["page"] != "" else ""
            if pg != "":
                render(key, pg)
            rate = r["rate_raw"] if t != "A" else f"{r['rate_raw']} | {r['description'][:70]}"
            if t == "B":
                rate = f"{r['rate_raw']} | {r['importer_category']} | {r['snapshot']}"
            w.writerow([pg, img_rel(key, pg) if pg != "" else "", r["s_no"], r["code_raw"] or r["clause"][:50], rate, "", ""])
    print("A rows", len(A), "B rows", len(B), "C rows", len(C))
    print("flags A", dict(flagsA), "B", dict(flagsB), "C", dict(flagsC))
    print("rows with issues", sum(1 for _, r in allrows if r["issues"]), "spotcheck rows", len(sel),
          "A share", round(len([1 for t, r in sel if t == "A"]) / len(Arows), 3))
    print("vision-marked rows", nvA, nvB, nvC)
    print("C stats", cstat)
    print({k: v for k, v in repA.items() if not k.startswith("_") and k != "only_in_FY2026-27"})


if __name__ == "__main__":
    main()
