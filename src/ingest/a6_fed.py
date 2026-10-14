"""A6: Federal Excise Act 2005, First Schedule Table I / Table IA (and Third Schedule Table-I exemptions) -> dated FED rule rows.

Sources (data/raw, typeset PDFs with a text layer; red text = the amendment of the latest Finance Act):
  FY2026-27  20267171373633512FEDAct2005updatedupto30-06-2026.pdf   ("as amended up to 30th June, 2026", Finance Act 2026 in red)
  FY2025-26  202588138517680FEDAct,2005withindexupdatedupto30-06-2025.pdf (Finance Act 2025 in red)
Finance Act 2026 (pp.72-75) and Finance Act 2025 (scan, pp.116-118) are used as second sources for the changes.

What this does: parse codes and rates from the printed text (a6_fed_spec.py) with code, run the validators, diff the two
years, write data/processed/a6_fed_rules.{csv,json}, a6_fed_failures.csv (every validator finding, nothing silently fixed),
a6_fed_validation.json and the spot-check sheet. Usage: python -m src.ingest.a6_fed
"""
from __future__ import annotations

import csv
import json
import re
from decimal import Decimal
from pathlib import Path

import pymupdf

from src.ingest import a6_fed_spec as S
from src.ingest import a6_fed_third as T3
from src.ingest.a6_fed_raw import FILES, TABLE_PAGES, _col, page_rows, row_cols, segment, read_table

PROC = Path("data/processed")
RAW = Path("data/raw")

ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
        "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
NUMWORDS = set(ONES) | set(TENS) | {"hundred", "thousand", "and", "million", "lakh"}


def words_to_number(tokens: list[str]) -> Decimal | None:
    """'three hundred and ninety' -> 390; 'one thousand and two hundred' -> 1200; 'five thousand and fifty' -> 5050."""
    total, cur, seen = 0, 0, False
    for t in tokens:
        t = t.lower()
        if t == "and":
            continue
        if t in ONES:
            cur += ONES[t]; seen = True
        elif t in TENS:
            cur += TENS[t]; seen = True
        elif t == "hundred":
            cur = (cur or 1) * 100; seen = True
        elif t == "thousand":
            total += (cur or 1) * 1000; cur = 0; seen = True
        else:
            return None
    return Decimal(total + cur) if seen else None


def _num_at(tokens: list[str], i: int, direction: int) -> tuple[Decimal | None, int]:
    """Read a number (digits or number words) starting at token i going forward (+1) or backward (-1). Returns (value, steps)."""
    j, got = i, []
    while 0 <= j < len(tokens):
        t = tokens[j].lower()
        if re.fullmatch(r"\d+(?:\.\d+)?", t):
            if not got:
                return Decimal(t), 1
            break
        if t in NUMWORDS and not (t == "and" and not got):
            got.append(t)
            j += direction
        else:
            break
    if direction < 0:
        got.reverse()
    while got and got[0] == "and":
        got.pop(0)
    while got and got[-1] == "and":
        got.pop()
    return words_to_number(got), len(got)


UNIT_MAP = [
    (r"^kilogram$|^kg$", "kg"), (r"^thousand cigarettes$", "1000 cigarettes"), (r"^hundred cubic meters$", "100 m3"),
    (r"^million british thermal unit.*mmbtu", "MMBTu"), (r"^hundred metric tonne$", "100 MT"),
    (r"^liter$", "liter"), (r"^fan$", "fan"), (r"^doc$", "DOC"),
]


def norm_unit(u: str) -> str | None:
    u = re.sub(r"\s+", " ", u.strip().strip(".").lower())
    for pat, name in UNIT_MAP:
        if re.search(pat, u):
            return name
    return None


def tokens_of(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]+|\d+(?:\.\d+)?|%", text)


def parse_codes(heading: str) -> list[tuple[str, str]]:
    out = []
    for m in re.finditer(r"\d{4}\.\d{4}", heading):
        out.append((m.group(0).replace(".", ""), "code8"))
    rest = re.sub(r"\d{4}\.\d{4}", " ", heading)
    for m in re.finditer(r"(?<![\d.])(\d{2})\.(\d{2})(?![\d.])", rest):
        out.append((m.group(1) + m.group(2), "heading4"))
    if not out:
        out = [("", "unmapped")]
    return out


def parse_rate(text: str) -> dict:
    """Printed rate text -> structure. Every number comes from the printed words or digits."""
    raw = text
    t = text.replace("%", " % ")
    eff = None
    m = re.search(r"with effect from the (\d+)\w* day of (\w+), (\d{4})", t, re.I)
    if m:
        eff = m.group(0)
        t = t[:m.start()]
    low = re.sub(r"\s+", " ", t.lower().replace("per cent", "percent"))
    toks = re.findall(r"[a-z]+(?:-[a-z]+)?|\d+(?:\.\d+)?|%|\(|\)", low.replace("-", " "))
    res: dict = {"raw": raw, "effective_note": eff, "pct": None, "basis": None, "amount": None, "unit": None,
                 "ref_sno": None, "compound": None, "errors": []}
    # percent part
    pct = None
    for i, tk in enumerate(toks):
        if tk in ("%", "percent"):
            v, n = _num_at(toks, i - 1, -1)
            if v is not None:
                pct = v
                tail = " ".join(toks[i + 1:i + 5])
                res["basis"] = "retail_price" if tail.startswith("of retail price") else (
                    "ad_valorem" if tail.startswith("ad") else None)
                break
    # rupee part
    amount = None
    for i, tk in enumerate(toks):
        if tk in ("rupees", "rs"):
            v, n = _num_at(toks, i + 1, +1)
            if v is None:
                v, n = _num_at(toks, i - 1, -1)
            if v is not None:
                amount = v
                # "and eighteen paisa"
                k = i + 1
                while k < len(toks) and (toks[k] in NUMWORDS or re.fullmatch(r"\d+(?:\.\d+)?", toks[k])):
                    k += 1
                if k < len(toks) and toks[k] == "paisa" or "paisa" in toks:
                    pj = toks.index("paisa")
                    pv, pn = _num_at(toks, pj - 1, -1)
                    if pv is not None:
                        amount += pv / Decimal(100)
                m2 = re.search(r"\bper (?!cent)(.+?)(?: or | whichever|$)", " ".join(toks[i:]))
                if m2:
                    res["unit"] = norm_unit(m2.group(1))
                    if res["unit"] is None:
                        res["errors"].append("unit_not_recognised:" + m2.group(1))
                break
    # reference to another serial
    m = re.search(r"prescribed against s\.? ?no\.? ?(\d+)", text, re.I)
    if m:
        res["ref_sno"] = m.group(1)
    if "whichever is higher" in low:
        res["compound"] = "higher_of"
    res["pct"], res["amount"] = pct, amount
    if pct is not None and amount is not None:
        res["kind"] = "compound"
    elif pct is not None and res["ref_sno"]:
        res["kind"] = "compound"
    elif pct is not None:
        res["kind"] = "percent"
    elif amount is not None:
        res["kind"] = "specific"
    else:
        res["kind"] = None
        res["errors"].append("no_rate_found")
    if res["kind"] == "percent" and res["basis"] is None and pct != 0:
        res["errors"].append("percent_basis_not_found")
    if res["kind"] == "percent" and res["basis"] is None and pct == 0:
        res["basis"] = "ad_valorem"   # printed '0%' with no basis words; a zero rate is zero on any basis (flagged below)
        res["basis_inferred"] = True
    return res


def parse_band(sub_desc: str) -> dict:
    """cylinder capacity (cc) and USD value bands from the sub-clause text. All numbers from the printed words/digits."""
    b: dict = {}
    s = sub_desc.lower().replace("-", " ")
    s = re.sub(r"(\d)cc", r"\1 cc", s)
    if "cylinder capacity" in s:
        m = re.search(r"up to (\d+) cc", s)
        if m:
            b["cc_le"] = int(m.group(1))
        m = re.search(r"(?:from )?(\d+) cc to (\d+) cc", s)
        if m:
            b["cc_ge"], b["cc_le"] = int(m.group(1)), int(m.group(2))
        m = re.search(r"(\d+) cc and above", s)
        if m:
            b["cc_ge"] = int(m.group(1))
        m = re.search(r"exceeding (\d+) cc", s)
        if m:
            if "but not exceeding" in s:
                pass
            else:
                b["cc_gt"] = int(m.group(1))
        m = re.search(r"not exceeding (\d+) cc", s)
        if m:
            b["cc_le"] = int(m.group(1))
    if "usd" in s:
        toks = re.findall(r"[a-z]+|\d+", s)
        idx = [i for i, t in enumerate(toks) if t == "usd"]
        vals = []
        for i in idx:
            v, n = _num_at(toks, i + 1, +1)
            vals.append(v)
        if s.startswith("not exceeding") and vals:
            b["usd_le"] = int(vals[0])
        elif s.startswith("exceeding"):
            if vals:
                b["usd_gt"] = int(vals[0])
            if len(vals) > 1 and vals[1] is not None:
                b["usd_le"] = int(vals[1])
    return b


# ---------------------------------------------------------------------------------------------------- tariff lookups

_TARIFF = {}


def tariff_sets(fy: str):
    key = "tariff_2026_27" if fy == "FY2026-27" else "tariff_2025_26"
    if key not in _TARIFF:
        d = json.loads((PROC / f"{key}.json").read_text(encoding="utf-8"))
        codes = {r["code"].replace(".", "") for r in d["rows"]}
        heads = {h["heading"].replace(".", "") for h in d["headings"]} | {c["code"].replace(".", "") for c in d.get("special", [])
                                                                       if len(c["code"].replace(".", "")) == 4}
        _TARIFF[key] = (codes, heads)
    return _TARIFF[key]


# ---------------------------------------------------------------------------------------------------- page text helpers

_DOCS = {}


def doc(year: str):
    if year not in _DOCS:
        _DOCS[year] = pymupdf.open(FILES[year])
    return _DOCS[year]


def page_tokens(year: str, pages: list[int]) -> set[str]:
    out: set[str] = set()
    for p in pages:
        if 1 <= p <= len(doc(year)):
            for w in doc(year)[p - 1].get_text("words"):
                out.update(t.lower() for t in tokens_of(w[4]))
    return out


def red_rows(year: str, table: str, sno_anchors: dict[int, list[tuple[float, str]]]) -> dict[str, list[int]]:
    """Serial numbers whose body cells contain red text (the latest Finance Act's amendments). Returns {serial: [pages]}."""
    out: dict[str, list[int]] = {}
    d = doc(year)
    a, b = TABLE_PAGES[year][table]
    last = None
    for pn in range(a, b + 1):
        page = d[pn - 1]
        words = page.get_text("words")
        body, _foot = page_rows(page)
        body_ids = {(round(w[0], 1), round(w[1], 1), w[4]) for w in body}
        red = []
        for blk in page.get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                for sp in ln["spans"]:
                    if sp["color"] == 0xFF0000 and sp["text"].strip():
                        red.append((sp["bbox"][1], sp["text"].strip()))
        anchors = sno_anchors.get(pn, [])
        for y, txt in red:
            if y < 118 or y > 680:
                continue
            # footnote region is below the separator; skip red text lines in the footnote area
            if not any(abs(y - w[1]) < 6 for w in body):
                continue
            cur = last
            for ay, a_sno in anchors:
                if ay <= y + 2:
                    cur = a_sno
            # a row's text can start a little above its serial (vertically centred serial cell): prefer an anchor just below
            below = [(ay - y, a_sno) for ay, a_sno in anchors if 0 < ay - y <= 22]
            if below:
                cur = min(below)[1]
            if cur:
                out.setdefault(cur, [])
                if pn not in out[cur]:
                    out[cur].append(pn)
        if anchors:
            last = anchors[-1][1]
    return out


def norm_sno(tok: str) -> str | None:
    m = re.match(r"^(?:\d+\[)?\(?(\d{1,3}[A-Za-z]?)\)?(?:[.*\]\[]|\*\*\*)*$", tok)
    return m.group(1).lower() if m else None


def anchors_by_page(year: str, table: str) -> dict[int, list[tuple[float, str]]]:
    res: dict[int, list[tuple[float, str]]] = {}
    for pg in read_table(year, table):
        lst = []
        for x, y, t in pg["words"]:
            if _col(x) == 0 or (x < 215 and table != "IA"):
                n = norm_sno(t)
                if n and x < 215:
                    lst.append((y, n))
        lst.sort()
        res[pg["page"]] = lst
    return res


# ---------------------------------------------------------------------------------------------------- build rows

def build_year(year: str):
    meta = S.YEARS[year]
    fy = meta["fy"]
    spec = (S.rows_2026() if year == "2026" else S.rows_2025()) + T3.third_rows(year)
    rows, fails = [], []
    tcodes, theads = tariff_sets(fy)

    def fail(check, r, detail, sev="error"):
        fails.append(dict(check=check, fy=fy, table=("Third-I" if r.get("tbl") == "3T1" else r.get("tbl", "")), s_no=r.get("sno", ""), sub=r.get("sub", ""),
                          page=r.get("page", ""), severity=sev, detail=detail))

    amended = {k: v for k, v in S.CHANGES_2026.items()} if year == "2026" else {}
    for item in spec:
        tbl, sno, sub, page = item["tbl"], item["sno"], item["sub"], item["page"]
        # V1: every printed word of the item is on the cited page (or the next / previous page: rows split across pages)
        ptoks = page_tokens(year, list(range(page - 1, page + 2 + item.get("span", 0))))
        want = set(t.lower() for t in tokens_of(" ".join([item["desc"], item["sub_desc"], item["heading"],
                                                          "" if tbl == "3T1" else item["rate"]])))
        missing = sorted(w for w in want if w not in ptoks)
        if missing:
            fail("text_on_page", item, "words not found on pages %d-%d: %s" % (page - 1, page + 1, missing))
        if tbl == "3T1":
            rate = {"raw": item["rate"], "effective_note": None, "pct": None, "basis": None, "amount": None, "unit": None,
                    "ref_sno": None, "compound": None, "errors": [], "kind": "exempt"}
        else:
            rate = parse_rate(item["rate"])
        for e in rate["errors"]:
            fail("rate_parse", item, e)
        band = parse_band(item["sub_desc"]) if item["sub_desc"] else {}
        if item["sub_desc"] and not band:
            fail("band_parse", item, "no cc/USD band found in: " + item["sub_desc"])
        codes = parse_codes(item["heading"])
        schedule = "Third" if tbl == "3T1" else "First"
        group = {"I": "FED-T1", "IA": "FED-T1A", "III": "FED-T3", "3T1": "FED-3RD-SCHEDULE"}[tbl]
        has_except = 1 if re.search(r"\b(excluding|except|other than)\b", item["desc"], re.I) else 0
        cond = []
        if sno == "8":
            cond.append("excludes locally produced cigarettes (those are S.No 9, 10, 12)")
        if sno == "65":
            cond.append("duty not charged on white spirit and solvent oil bought only for in-house consumption by a Form-L licence "
                        "holder importer and recipient, if the goods made are exempt or taxable under the Sales Tax Act with both "
                        "supplier and manufacturer on the Board's digital invoice system; quota approved by the Board or by the "
                        "Directorate General of Input Output Coefficient Organization (proviso printed under S.No 65, "
                        "page %d)" % (78 if year == "2026" else page))
        if sno in ("55", "55B"):
            cond.append("electric vehicles (4 wheelers) are within this serial only until the 30th day of June, %s"
                        % ("2027" if year == "2026" else "2026"))
        if sno == "55A":
            cond.append("value as determined under section 25 of the Customs Act, 1969, in USD per vehicle; CBU only")
        if sno == "55D":
            cond.append("excludes vehicles booked on or before 30 June 2020; subject to the restriction or conditions specified by the Board")
        if sno in ("60", "61"):
            cond.append("printed with effect from the 1st day of January, 2024")
        if tbl == "IA":
            cond.append("Special Excise Duty in addition to the duty under section 3(1) (section 3(3B)); the Board may prescribe time, "
                        "mechanism, procedure, mode and manner of collection (proviso to s.3(3B))")
        if tbl == "3T1":
            cond.append(item["desc"])
        for k, (code_norm, level) in enumerate(codes):
            r = dict(
                fy=fy, schedule=schedule, table_no=("Third-I" if tbl == "3T1" else tbl), s_no=sno, sub=sub, description=item["desc"], sub_desc=item["sub_desc"],
                heading_raw=item["heading"], code_norm=code_norm if level != "unmapped" else "", match_level=level,
                except_codes="[]", unparsed_except_text=has_except, rule_group=group, applies_to=item["applies"],
                rate_kind=rate["kind"], rate_basis=rate["basis"], rate_pct=None if rate["pct"] is None else float(rate["pct"]),
                rate_specific_amount=None if rate["amount"] is None else float(rate["amount"]),
                rate_specific_unit=rate["unit"], rate_ref_s_no=rate["ref_sno"], compound_rule=rate["compound"],
                cc_ge=band.get("cc_ge"), cc_gt=band.get("cc_gt"), cc_le=band.get("cc_le"),
                usd_gt=band.get("usd_gt"), usd_le=band.get("usd_le"),
                condition_text="; ".join(cond) or None, effective_note=rate["effective_note"],
                amended_by=(amended[(tbl, sno)][0] if (tbl, sno) in amended else None),
                rate_raw=item["rate"], issues="", status="accepted", valid_from=meta["valid_from"], valid_to=meta["valid_to"],
                source_file=meta["file"], page=page,
            )
            r["row_id"] = f"fed{year}:{tbl}:{sno}{sub}:{code_norm or 'unmapped'}"
            if tbl == "3T1":
                r["applies_to"] = "import_and_local" if re.search(r"import", item["desc"], re.I) else "unclear"
                r["issues"] += "conditional exemption: every condition in the description must be met, the tools never apply it by themselves;"
                if sno == "1":
                    r["issues"] += "heading column prints '5.07' and '15010' (typographical in the Act): not mapped;"
                if "unmapped" == level:
                    pass
            if rate.get("basis_inferred"):
                r["issues"] += "rate_basis_not_printed_for_0_percent;"
            if level == "unmapped":
                r["code_norm"] = None
            # V2: codes exist in the tariff of the fiscal year
            if level == "code8" and code_norm not in tcodes:
                kids = sorted(c for c in tcodes if c.startswith(code_norm[:6]))
                if code_norm.endswith("00") and kids:
                    r["match_level"], r["code_norm"] = "code6", code_norm[:6]
                    r["issues"] += (f"printed as {item['heading']}; the {fy} tariff has no such 8-digit code but has {kids}; stored as "
                                    f"the 6-digit prefix {code_norm[:6]} (inference);")
                    r["status"] = "needs_review"
                    fail("code_in_tariff", item, f"{code_norm} not an 8-digit tariff code; mapped to 6-digit prefix {code_norm[:6]} "
                         f"(children {kids})", sev="warning")
                else:
                    fail("code_in_tariff", item, f"{code_norm} is not an 8-digit code of the {fy} tariff")
                    r["issues"] += "code_not_in_tariff;"
                    r["status"] = "needs_review"
            if level == "heading4" and code_norm.startswith("99") and fy == "FY2025-26":
                fail("code_in_tariff", item, f"Chapter 99 heading {code_norm}: the FY2025-26 tariff parse (A1) has no Chapter 99 list; not checked",
                     sev="info")
            elif level == "heading4" and code_norm not in theads:
                fail("code_in_tariff", item, f"heading {code_norm} not in the {fy} tariff")
                r["issues"] += "heading_not_in_tariff;"
                r["status"] = "needs_review"
            rows.append(r)
    return rows, fails


def expected_serials(rows, year):
    live = sorted({r["s_no"].lower() for r in rows if r["table_no"] == "I"})
    return live


def validate(year, rows, fails):
    fy = S.YEARS[year]["fy"]
    report = {"fy": fy}

    def fail(check, detail, sev="error", **kw):
        fails.append(dict(check=check, fy=fy, table=kw.get("table", "I"), s_no=kw.get("s_no", ""), sub="", page=kw.get("page", ""),
                          severity=sev, detail=detail))

    # V3 rate ranges and V4 one-decimal/step check
    for r in rows:
        k = r["rate_kind"]
        if k in ("percent", "compound") and r["rate_pct"] is not None:
            p = r["rate_pct"]
            if not (0 <= p <= 100):
                fail("rate_range", f"pct {p} outside 0..100", s_no=r["s_no"], table=r["table_no"], page=r["page"])
            if (p * 2) != int(p * 2):
                fail("rate_step", f"pct {p} is not a multiple of 0.5 (possible dropped or added decimal point)", s_no=r["s_no"],
                     table=r["table_no"], page=r["page"])
            digits = re.findall(r"(\d+(?:\.\d+)?)\s*%", r["rate_raw"])
            if digits and float(digits[0]) != p:
                fail("rate_digits_vs_words", f"printed digits {digits[0]} differ from parsed {p}", s_no=r["s_no"], table=r["table_no"],
                     page=r["page"])
        if r["rate_specific_amount"] is not None and not (0 < r["rate_specific_amount"] <= 1_000_000):
            fail("rate_range", f"amount {r['rate_specific_amount']} outside 0..1,000,000", s_no=r["s_no"], table=r["table_no"], page=r["page"])
    # V5 serial continuity for Table I: live + omitted cover 1..max
    live = {r["s_no"].lower() for r in rows if r["table_no"] == "I"}
    omitted = set(S.OMITTED_I[year])
    nums = {int(re.match(r"\d+", s).group(0)) for s in live | omitted}
    top = max(nums)
    gaps = [n for n in range(1, top + 1) if n not in nums]
    overlap = sorted(live & omitted)
    report["serial_top"] = top
    report["serial_gaps"] = gaps
    report["serial_overlap_live_omitted"] = overlap
    if gaps:
        fail("serial_continuity", f"serial numbers with neither a live row nor an omitted marker: {gaps}")
    if overlap:
        fail("serial_continuity", f"serials both live and omitted: {overlap}")
    # V6 serial anchors found by coordinates vs the spec
    anch = anchors_by_page(year, "I")
    found = {s for lst in anch.values() for _y, s in lst}
    live_n = {s for s in live}
    only_spec = sorted(live_n - found)
    only_pdf = sorted(s for s in found - live_n if s not in {o.lower() for o in omitted} and not re.fullmatch(r"\d+", s) is None and True)
    only_pdf = sorted(s for s in (found - live_n) if s not in {o.lower() for o in omitted})
    report["anchor_serials_found_by_coordinates"] = len(found)
    report["live_serials_not_found_by_coordinates"] = only_spec
    report["coordinate_serials_not_in_spec_or_omitted"] = only_pdf
    for s in only_spec:
        fail("anchor_vs_spec", f"serial {s} is in the spec but no serial anchor was found at that position by coordinates")
    for s in only_pdf:
        fail("anchor_vs_spec", f"coordinate anchor '{s}' is neither a spec serial nor a listed omitted serial", sev="warning")
    # V6b Table IA / III have their own printed serials: check by words on page (done in V1)
    # cc / USD band continuity for vehicle serials
    by = {}
    for r in rows:
        if r["sub"] and (r["cc_ge"] is not None or r["cc_gt"] is not None or r["cc_le"] is not None):
            by.setdefault((r["table_no"], r["s_no"], r["code_norm"]), []).append(r)
    for (tbl, sno, code), lst in by.items():
        pts = sorted(((r["cc_ge"] if r["cc_ge"] is not None else (r["cc_gt"] + 1 if r["cc_gt"] is not None else 0)),
                      (r["cc_le"] if r["cc_le"] is not None else 10 ** 9), r["sub"]) for r in lst)
        for (lo1, hi1, s1), (lo2, hi2, s2) in zip(pts, pts[1:]):
            if lo2 != hi1 + 1:
                fail("band_continuity", f"S.No {sno}{s1}->{s2}: cc bands leave a gap or overlap (upper {hi1}, next lower {lo2})"
                     f"; a 3001 cc engine, for example, is in no band" if lo2 > hi1 + 1 else
                     f"S.No {sno}: bands overlap", sev="warning", s_no=sno, table=tbl)
                break
    return report


def second_source_check(rows, rows25, fails):
    """Finance Act 2026 (text layer, pp.72-75) is a second source for the rows it inserts or substitutes. For a changed row only
    the words that are new compared with FY2025-26 must be in the Finance Act; for an added row every word must be."""
    d = pymupdf.open(RAW / S.FA2026)
    toks = set()
    for p in range(72, 77):
        for w in d[p - 1].get_text("words"):
            toks.update(t.lower() for t in tokens_of(w[4]))
    old = {}
    for r in rows25:
        old.setdefault((r["table_no"], r["s_no"]), set()).update(
            t.lower() for t in tokens_of(" ".join([r["description"], r["sub_desc"] or "", r["heading_raw"], r["rate_raw"]])))
    n_ok = n = 0
    for r in rows:
        if r["fy"] != "FY2026-27" or (r["table_no"], r["s_no"]) not in S.CHANGES_2026:
            continue
        n += 1
        want = set(t.lower() for t in tokens_of(" ".join([r["description"], r["sub_desc"] or "", r["heading_raw"],
                                                          "" if r["table_no"] == "Third-I" else r["rate_raw"]])))
        if (r["table_no"], r["s_no"]) in old:
            want -= old[(r["table_no"], r["s_no"])]
        elif r["table_no"] == "Third-I":
            want = set(t.lower() for t in tokens_of(r["description"]))
        else:
            want = set(t.lower() for t in tokens_of(" ".join([r["sub_desc"] or "", r["heading_raw"], r["rate_raw"]])))
        missing = sorted(w for w in want if w not in toks)
        if missing:
            fails.append(dict(check="second_source_finance_act_2026", fy=r["fy"], table=r["table_no"], s_no=r["s_no"], sub=r["sub"],
                              page=r["page"], severity="error", detail=f"tokens not in Finance Act 2026 pp.72-76: {missing}"))
        else:
            n_ok += 1
    return {"rows_checked": n, "rows_ok": n_ok}


def diff_years(r25, r26, red26, red25, fails):
    """Compare the two snapshots on (table, s_no, sub, code) and explain each difference."""
    def key(r):
        return (r["table_no"], r["s_no"], r["sub"], r["code_norm"] or r["heading_raw"])

    def sig(r):
        return (r["description"], r["sub_desc"], r["heading_raw"], r["rate_raw"])

    k25 = {key(r): r for r in r25}
    k26 = {key(r): r for r in r26}
    diffs = []
    for k in sorted(set(k25) | set(k26), key=lambda k: (k[0], re.sub(r"\D", "", k[1]).zfill(3), k[1], k[2], k[3])):
        a, b = k25.get(k), k26.get(k)
        if a and b and sig(a) == sig(b):
            continue
        kind = "added" if not a else "removed" if not b else "changed"
        what = []
        if a and b:
            for f, lab in zip(("description", "sub_desc", "heading_raw", "rate_raw"), ("description", "sub-clause", "codes", "rate")):
                if a[f] != b[f]:
                    what.append(f"{lab}: [{a[f]}] -> [{b[f]}]")
        ref = S.CHANGES_2026.get((k[0], k[1]))
        diffs.append(dict(table=k[0], s_no=k[1], sub=k[2], code=k[3], kind=kind, what=" | ".join(what),
                          explained_by=ref[0] if ref else "", fa_page=ref[1] if ref else "",
                          red_in_2026_pdf=("True" if k[1].lower() in red26 else "False") if k[0] == "I" else "n/a (whole table is new and red)"))
    # every diff must be explained by a Finance Act 2026 clause and be red in the 2026 PDF; every red serial must be a diff
    diff_serials = {(d["table"], d["s_no"].lower()) for d in diffs}
    for d in diffs:
        if not d["explained_by"]:
            fails.append(dict(check="diff_unexplained", fy="FY2026-27", table=d["table"], s_no=d["s_no"], sub=d["sub"], page="",
                              severity="error", detail=f"{d['kind']} between FY2025-26 and FY2026-27 but no Finance Act 2026 clause is recorded: {d['what']}"))
        if d["table"] == "I" and d["red_in_2026_pdf"] != "True" and not d["kind"] == "removed":
            fails.append(dict(check="diff_not_red", fy="FY2026-27", table=d["table"], s_no=d["s_no"], sub=d["sub"], page="",
                              severity="warning", detail="differs from FY2025-26 but its cells are not red in the 2026 consolidation"))
    for s in sorted(red26):
        if ("I", s) not in diff_serials:
            note = ("this is the 'Restriction' text under the table (Restriction-2 substituted by Finance Act 2026 s.6(14)(1)(h), page 74 of the Act; "
                    "cigarette brand rules, no rate) and not a table row" if 79 in red26[s] else
                    "red text but identical rate/description to FY2025-26 (wording-only amendment)")
            fails.append(dict(check="red_not_in_diff", fy="FY2026-27", table="I", s_no=s, sub="", page=",".join(map(str, red26[s])),
                              severity="info", detail="red text in the 2026 consolidation but not a rate change: " + note))
    return diffs


def main():
    out = {}
    all_rows, all_fails = [], []
    reports = {}
    byyear = {}
    for year in ("2025", "2026"):
        rows, fails = build_year(year)
        reports[year] = validate(year, rows, fails)
        byyear[year] = (rows, fails)
    r25, f25 = byyear["2025"]
    r26, f26 = byyear["2026"]
    reports["second_source_FA2026"] = second_source_check(r26, r25, f26)
    a26 = anchors_by_page("2026", "I")
    a25 = anchors_by_page("2025", "I")
    red26 = {k: v for k, v in red_rows("2026", "I", a26).items()}
    red25 = {k: v for k, v in red_rows("2025", "I", a25).items()}
    reports["red_rows_2026_table_I"] = red26
    reports["red_rows_2025_table_I"] = red25
    # 2025 red = Finance Act 2025 changes: read from the Finance Act 2025 scan pp.116-118 (image) -> S.No 64 inserted, Table III S.No 1 omitted
    expected25 = {"64"}
    if set(red25) != expected25:
        f25.append(dict(check="red_vs_finance_act_2025", fy="FY2025-26", table="I", s_no="", sub="", page="", severity="warning",
                        detail=f"red serials in the 2025 consolidation {sorted(red25)} vs Finance Act 2025 s.11(8) (page 118 image): {sorted(expected25)}"))
    diffs = diff_years(r25, r26, red26, red25, f26)
    all_rows = r25 + r26
    all_fails = f25 + f26
    return all_rows, all_fails, reports, diffs




# ---------------------------------------------------------------------------------------------------- Third Schedule

THIRD_PAGES = {"2026": (88, 100), "2025": (90, 102)}
THIRD_SNO = re.compile(r"^(?:\d+\[)?\(?(\d{1,2}[A-B]?)\)?(?:[.*\]\[]|\*\*\*)*$")


def third_schedule(year: str):
    """Third Schedule Table-I (Goods): conditional exemptions. Column split by x (S.No < 170, description 170-400, heading >= 400)."""
    a, b = THIRD_PAGES[year]
    d = doc(year)
    items, cur = [], None
    for pn in range(a, b + 1):
        page = d[pn - 1]
        body, _foot = page_rows(page)
        body = [w for w in body if w[1] > 120]
        # drop table header words on the first page of the schedule and repeated headers
        lines = {}
        for w in sorted(body, key=lambda w: (round(w[1]), w[0])):
            lines.setdefault(round(w[1] / 4), []).append(w)
        for k in sorted(lines):
            ws = sorted(lines[k], key=lambda w: w[0])
            c0 = [w[4] for w in ws if w[0] < 170]
            c1 = [w[4] for w in ws if 170 <= w[0] < 400]
            c2 = [w[4] for w in ws if w[0] >= 400]
            if year == "2025":
                pass
            head = " ".join(c0).strip()
            if re.match(r"^(S\.No\.?|Col\.?\(\d\))$", head):
                continue
            if c1 and c1[0] in ("Description", "Heading/") or (c2 and c2[0] in ("Heading/", "sub-heading", "Number", "Col.(3)")):
                continue
            m = THIRD_SNO.match(c0[0]) if c0 else None
            if m and not (len(c0) > 1 and not re.match(r"^\*+\]?$", c0[1])) or (m and len(c0) == 1):
                cur = dict(s_no=m.group(1), page=pn, desc=[], head=[], raw_marker=" ".join(c0))
                items.append(cur)
            elif c0 and cur is not None and re.match(r"^\d+\[\d", c0[0]):
                m2 = THIRD_SNO.match(c0[0])
                if m2:
                    cur = dict(s_no=m2.group(1), page=pn, desc=[], head=[], raw_marker=" ".join(c0))
                    items.append(cur)
            if cur is None:
                continue
            cur["desc"] += c1
            cur["head"] += c2
    for it in items:
        it["desc"] = re.sub(r"\s+", " ", " ".join(it["desc"])).strip()
        it["head"] = re.sub(r"\s+", " ", " ".join(it["head"])).strip()
    return items


COLS = ["row_id", "fy", "schedule", "table_no", "s_no", "sub", "description", "sub_desc", "heading_raw", "code_norm", "match_level",
        "except_codes", "unparsed_except_text", "rule_group", "applies_to", "rate_kind", "rate_basis", "rate_pct",
        "rate_specific_amount", "rate_specific_unit", "rate_ref_s_no", "compound_rule", "cc_ge", "cc_gt", "cc_le", "usd_gt", "usd_le",
        "condition_text", "effective_note", "amended_by", "rate_raw", "issues", "status", "valid_from", "valid_to", "source_file", "page"]


def write_outputs(rows, fails, reports, diffs):
    PROC.mkdir(parents=True, exist_ok=True)
    # a row with an error-level finding is needs_review (loaded, not dropped, not fixed)
    bad = {(f["fy"], f["table"], f["s_no"], f["sub"]) for f in fails if f["severity"] == "error"}
    for r in rows:
        if (r["fy"], r["table_no"], r["s_no"], r["sub"]) in bad and r["status"] == "accepted":
            r["status"] = "needs_review"
    # rate by reference ("the rate of duty as prescribed against S. No. 9"): take the amount of the referenced serial of the same snapshot
    for r in rows:
        if r["rate_ref_s_no"] and r["rate_specific_amount"] is None:
            ref = [x for x in rows if x["fy"] == r["fy"] and x["table_no"] == r["table_no"] and x["s_no"] == r["rate_ref_s_no"]
                   and x["rate_specific_amount"] is not None]
            if len(ref) == 1:
                r["rate_specific_amount"], r["rate_specific_unit"] = ref[0]["rate_specific_amount"], ref[0]["rate_specific_unit"]
                r["issues"] += (f"specific part taken from S.No {r['rate_ref_s_no']} by the printed reference (Rs. "
                                f"{ref[0]['rate_specific_amount']:g} per {ref[0]['rate_specific_unit']});")
            else:
                r["issues"] += f"reference to S.No {r['rate_ref_s_no']} could not be resolved;"
                r["status"] = "needs_review"
    # interpretation flags that stay needs_review until the owner or a customs expert decides
    OPEN = {
        "8": "rate by reference: 'the rate of duty as prescribed against S. No. 9' (S.No 9 prints Rs. 16,500 per thousand cigarettes for local cigarettes above Rs. 12,500; "
             "S.No 10 prints Rs. 5,050 below that). The reference is resolved here to the S.No 9 amount: reading, not printed text;",
        "55": "electric vehicles (4 wheelers) are named inside S.No 55 until 30 June of the year printed AND in S.No 55A (from Finance Act 2026) with USD value bands; the Act does not say which "
              "applies to an imported electric car, or whether both are charged; engine-capacity bands leave 3001 cc in no band;",
        "55A": "see S.No 55: overlap with the electric-vehicle words inside S.No 55; heading column prints 'Respective Heading' (no code), so the row never matches a code;",
        "IA": "Special Excise Duty is in addition to Table-I duty (s.3(3B)); Table IA names 'electric vehicles (4 wheelers)' and double cabin pickups with engine-capacity bands, "
              "and the Board may prescribe the time and manner of collection (no such notification is in data/raw);",
    }
    for r in rows:
        key = r["s_no"] if r["table_no"] == "I" else ("IA" if r["table_no"] == "IA" else None)
        if key in OPEN:
            r["issues"] += OPEN[key]
            r["status"] = "needs_review"
        if r["match_level"] == "unmapped" and r["table_no"] != "Third-I":
            r["issues"] += "heading column prints 'Respective heading(s)': no code, stored unmapped (never matches a code lookup);"
    with open(PROC / "a6_fed_rules.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in COLS})
    (PROC / "a6_fed_rules.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(PROC / "a6_fed_failures.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["severity", "check", "fy", "table", "s_no", "sub", "page", "detail"])
        w.writeheader()
        for x in sorted(fails, key=lambda x: ({"error": 0, "warning": 1, "info": 2}[x["severity"]], x["fy"], x["table"], x["s_no"])):
            w.writerow({k: x.get(k, "") for k in w.fieldnames})
    with open(PROC / "a6_fed_diff_2025_2026.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "s_no", "sub", "code", "kind", "what", "explained_by", "fa_page", "red_in_2026_pdf"])
        w.writeheader()
        w.writerows(diffs)
    items = {}
    for r in rows:
        items.setdefault(r["fy"], set()).add((r["table_no"], r["s_no"], r["sub"]))
    summary = dict(
        rows={fy: sum(1 for r in rows if r["fy"] == fy) for fy in items},
        printed_items={fy: len(v) for fy, v in items.items()},
        by_table={f"{fy}|{t}": sum(1 for r in rows if r["fy"] == fy and r["table_no"] == t) for fy in items
                  for t in sorted({r["table_no"] for r in rows})},
        needs_review=sum(1 for r in rows if r["status"] == "needs_review"),
        unmapped=sum(1 for r in rows if r["match_level"] == "unmapped"),
        findings={sev: sum(1 for f in fails if f["severity"] == sev) for sev in ("error", "warning", "info")},
        reports=reports)
    (PROC / "a6_fed_validation.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    return summary


if __name__ == "__main__":
    rows, fails, reports, diffs = main()
    summary = write_outputs(rows, fails, reports, diffs)
    print(json.dumps({k: v for k, v in summary.items() if k != "reports"}, indent=1))
    for f in fails:
        if f["severity"] != "info":
            print(f["severity"], f["check"], f["fy"], f["table"], f["s_no"], f["detail"][:200])
