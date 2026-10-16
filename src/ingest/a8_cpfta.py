"""A8: rows of SRO 1640(I)/2019 (China-Pakistan FTA Phase II) from the OCR tokens (a8_cpfta_ocr.py).

Every value is an AI reading (local OCR) of a scan. Nothing is trusted just because the OCR printed it:
* Sr.No must run 1, 2, 3 ... 6786 without a gap (the SRO prints them in order);
* the PCT code must be eight digits and the codes must rise in order inside the table;
* the 15 yearly rates of a line are a straight-line taper: flat at the starting rate up to a start year, then equal steps down to
  0 at an end year (examples on page 1 of the SRO: 20.00, 16.67, 13.33, 10.00, 6.67, 3.33, 0.00, ...). Each line is fitted to that
  pattern and compared cell by cell with what the OCR read. A line whose OCR cells agree with a pattern in nearly all cells gets the
  pattern's values (the OCR cells that disagree are LOGGED, not hidden); a line that fits no pattern keeps its OCR values and is
  `needs_review`.
Outputs: data/processed/a8_cpfta_rows.csv/json (wide: year_1..year_15), a8_cpfta_failures.csv, a8_cpfta_validation.json.
Usage: python -m src.ingest.a8_cpfta
"""
from __future__ import annotations

import csv
import json
import re
import statistics
from collections import Counter
from pathlib import Path

PROC = Path("data/processed")
OCR = PROC / "cpfta_ocr"
SOURCE = "2020111213219376SRO1640(I)2019dated31.12.2019.pdf"
DATES = ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01", "2024-01-01", "2025-01-01", "2026-01-01", "2027-01-01", "2028-01-01",
         "2029-01-01", "2030-01-01", "2031-01-01", "2032-01-01", "2033-01-01", "2034-01-01"]
NYEARS = 15
LAST_SR = 6786

# template of the 15 column positions (left x of each number box at 200 dpi, page 3, straightened); shifted per page
TEMPLATE = [798, 894, 985, 1107, 1198, 1290, 1382, 1473, 1565, 1658, 1750, 1841, 1934, 2026, 2118]

CHAR_DIGIT = str.maketrans({"O": "0", "o": "0", "C": "0", "c": "0", "Q": "0", "D": "0", "G": "0", "I": "1", "l": "1", "|": "1", "S": "5", "B": "8", "Z": "2"})


def clean_digits(text: str) -> str:
    return re.sub(r"\D", "", text.translate(CHAR_DIGIT))


def parse_number(text: str):
    """OCR token -> (value | None, how). The rates always have two decimals: 0.00 ... 25.00 (never above 100)."""
    t = text.strip().strip("|[]() ").replace(",", ".")
    if re.fullmatch(r"\d{1,3}\.\d{2}", t):
        v = float(t)
        return (v, "exact") if v <= 100 else (None, "out_of_range")
    # a point read as ' : - ° or dropped: keep only digits and re-insert the point before the last two
    d = clean_digits(t)
    if len(d) == 3:
        return float(d[0] + "." + d[1:]), "repaired"
    if len(d) == 4:
        v = float(d[:2] + "." + d[2:])
        return (v, "repaired") if v <= 100 else (None, "out_of_range")
    return None, "unreadable"


def column_of(xc: float, shift: float):
    best, bi = None, None
    for i, x in enumerate(TEMPLATE):
        d = abs(xc - (x + shift))
        if best is None or d < best:
            best, bi = d, i
    return (bi, best)


def page_rows(page: int):
    d = json.loads((OCR / f"p{page:03d}.json").read_text(encoding="utf-8"))
    toks = d["tokens"]
    for t in toks:
        t["xc"] = (t["x0"] + t["x1"]) / 2
        t["yc"] = (t["y0"] + t["y1"]) / 2
    # the table starts below the header (rows "Sr.No PCT Code ... Year n", dates, "(1) (2) ... (18)")
    hdr = [t["yc"] for t in toks if re.search(r"Sr\.?\s?N|PCT\s?Code", t["text"]) and t["x0"] < 450 and len(t["text"]) < 20]
    ycut = (max(hdr) + 50) if hdr else 185.0
    # numeric-looking tokens below the header in the year area
    year_area = [t for t in toks if t["x0"] > 700 and t["yc"] > ycut and re.search(r"\d", t["text"]) and not re.search(r"[A-Za-z]{3,}", t["text"])]
    shifts = []
    for t in year_area:
        i, dist = column_of(t["x0"], 0)
        if dist < 30:
            shifts.append(t["x0"] - TEMPLATE[i])
    shift = statistics.median(shifts) if shifts else 0.0
    # anchors: tokens left of the description column (Sr.No, PCT code) and the number tokens
    left = [t for t in toks if t["x0"] < 375 and t["yc"] > ycut]
    rows = []
    # row anchors = y of each code / sr.no cluster plus number rows; cluster all "row tokens" by y
    row_tokens = left + year_area
    row_tokens.sort(key=lambda t: t["yc"])
    cluster, clusters = [], []
    for t in row_tokens:
        if cluster and t["yc"] - statistics.mean(c["yc"] for c in cluster) > 7.5:
            clusters.append(cluster)
            cluster = []
        cluster.append(t)
    if cluster:
        clusters.append(cluster)
    prev_y = ycut
    for cl in clusters:
        y = statistics.mean(t["yc"] for t in cl)
        left_t = sorted((t for t in cl if t["x0"] < 375), key=lambda t: t["x0"])
        parts = re.findall(r"[0-9A-Za-z:|.\-\[\]\(\)]+", " ".join(t["text"] for t in left_t))
        srno_parts, code_parts = [], []
        for pt in parts:
            dg = clean_digits(pt)
            if len(dg) >= 9:
                code_parts.append(dg[-8:])
                srno_parts.append(dg[:-8])
            elif len(dg) == 8:
                code_parts.append(dg)
            elif 1 <= len(dg) <= 4:
                srno_parts.append(dg)
        srno_t = [{"text": "".join(srno_parts[:1])}]
        code_t = [{"text": "".join(code_parts[:1])}]
        nums = [t for t in cl if t["x0"] >= 700]
        cells = [None] * NYEARS
        how = [""] * NYEARS
        raw = [""] * NYEARS
        for t in nums:
            i, dist = column_of(t["x0"], shift)
            if dist > 45:
                continue
            v, h = parse_number(t["text"])
            if cells[i] is None or (h == "exact" and how[i] != "exact"):
                cells[i], how[i], raw[i] = v, h, t["text"]
            elif raw[i] and t["text"] != raw[i]:
                how[i] = "conflict"
        desc = " ".join(t["text"] for t in sorted((t for t in toks if 380 <= t["x0"] < 780 and prev_y + 5 < t["yc"] <= y + 4), key=lambda t: (round(t["yc"] / 6), t["x0"])))
        rows.append(dict(page=page, y=round(y, 1), srno_raw=" ".join(t["text"] for t in srno_t), code_raw=" ".join(t["text"] for t in code_t),
                         cells=cells, how=how, raw=raw, desc=desc, n_tokens=len(cl)))
        prev_y = y
    return rows, {"page": page, "shift": round(shift, 1), "skew": d["skew_deg"], "ycut": round(ycut, 1)}


# ---------------------------------------------------------------------------------------------------- pattern fit
def taper(b: float, s: int, e: float):
    """Rate in year y (1..15) of a line that starts at b, is flat up to year s, falls in equal steps to 0 at year e."""
    out = []
    for y in range(1, NYEARS + 1):
        if y <= s:
            v = b
        elif y >= e:
            v = 0.0
        else:
            v = b * (e - y) / (e - s)
        out.append(round(v + 1e-9, 2))
    return out


def _unit_matrix():
    import numpy as np

    cands = [(1, 1)] + [(s, e) for s in range(1, 16) for e in range(s + 1, 31)]
    U = np.array([taper(1.0, s, e if e > 1 else 99) if (s, e) != (1, 1) else [1.0] * NYEARS for s, e in cands])
    # taper() rounds to 2 decimals; keep the unrounded shape here
    def raw(s, e):
        return [1.0 if y <= s else (0.0 if y >= e else (e - y) / (e - s)) for y in range(1, NYEARS + 1)]
    U = np.array([[1.0] * NYEARS if (s, e) == (1, 1) else raw(s, e) for s, e in cands])
    return cands, U


_CANDS = _U = None


FAMILIES = [(1, 1), (1, 7), (3, 15)]   # constant (incl. zero), A07 (taper year 2 to 7), A15 (taper year 4 to 15): FBR's categories


def fit(cells, how, families_only=True):
    """Best (b, s, e) for the readable cells among the FBR families. Returns dict(b, s, e, values, agree, observed, misfit)."""
    import numpy as np

    global _CANDS, _U
    if _U is None:
        _CANDS, _U = _unit_matrix()
    obs = [(i, v) for i, v in enumerate(cells) if v is not None]
    if len(obs) < 5:
        return None
    idx = np.array([i for i, _ in obs])
    ov = np.array([v for _, v in obs])
    bs = [0.0] + sorted({v for _, v in obs if v > 0}, reverse=True)[:4]
    allowed = set(FAMILIES) if families_only else None
    best = None
    for b in bs:
        V = np.round(b * _U + 1e-9, 2)
        agree = (np.abs(V[:, idx] - ov) <= 0.015).sum(axis=1)
        for k in range(len(_CANDS)):
            s, e = _CANDS[k]
            if allowed is not None and (s, e) not in allowed:
                continue
            if b == 0.0 and (s, e) != (1, 1):
                continue
            key = (int(agree[k]), 1 if (s, e) == (1, 1) else 0, -b if (s, e) == (1, 1) else 0)
            if best is None or key > best[0]:
                best = (key, b, s, e, V[k].tolist(), int(agree[k]))
    _, b, s, e, vals, agree = best
    if (s, e) == (1, 1):
        e = None
    mis = [(i, cells[i], vals[i]) for i, v in obs if abs(vals[i] - v) > 0.015]
    return dict(b=b, s=s, e=e, values=vals, agree=agree, observed=len(obs), misfit=mis)


def label(f):
    if f is None:
        return "unfitted"
    if f["e"] is None:
        return "constant_zero" if f["b"] == 0 else "constant_rate"
    if f["s"] == 1 and f["e"] == 7:
        return "A07_taper_to_zero_year7"
    if f["s"] == 3 and f["e"] == 15:
        return "A15_taper_year3_to_15"
    return f"taper_start{f['s']}_end{f['e']}"


# ---------------------------------------------------------------------------------------------------- whole document
def build():
    allrows, pages = [], []
    for page in range(1, 178):
        if not (OCR / f"p{page:03d}.json").exists():
            continue
        rows, meta = page_rows(page)
        pages.append(meta)
        allrows += rows
    return allrows, pages


def _read_sr(r):
    d = clean_digits(r["srno_raw"])
    if len(d) >= 9:
        d = d[:-8]
    return int(d) if d.isdigit() and 0 < len(d) <= 4 else None


def numbered(allrows, code_fixes=None):
    """Assign Sr.No / code to the rows (continuity check) and fit patterns. Returns (lines, failures).

    Sr.No is printed 1, 2, 3 ... without gaps. A row whose Sr.No does not equal the running count is kept at the running count
    (the OCR misread it) unless the NEXT rows also continue from the number read (a real gap: rows lost by the OCR), which is logged."""
    cand = []
    for r in allrows:
        has_num = sum(1 for v in r["cells"] if v is not None)
        code_digits = clean_digits(r["code_raw"])
        if has_num < 3 and len(code_digits) < 8:
            continue
        cand.append(r)
    reads = [_read_sr(r) for r in cand]
    lines, fails = [], []
    expected, last_code = 1, None
    for i, r in enumerate(cand):
        code_digits = clean_digits(r["code_raw"])
        code_digits = code_digits if len(code_digits) == 8 else ""
        issues = []
        sr = reads[i]
        if sr is None:
            sr = expected
            issues.append("srno_not_read_inferred_from_sequence")
        elif sr != expected:
            nxt = [reads[j] for j in range(i + 1, min(i + 3, len(cand)))]
            real_jump = len(nxt) >= 1 and all(x == sr + k + 1 for k, x in enumerate(nxt)) and abs(sr - expected) <= 12
            if real_jump:
                issues.append(f"srno_resync_{expected}_to_{sr}" + ("_rows_not_read_by_ocr" if sr > expected else "_extra_rows_counted"))
            else:
                issues.append(f"srno_misread_{sr}_kept_{expected}")
                sr = expected
        expected = sr + 1
        code = code_digits or None
        key = (r["page"], r["y"])
        if code_fixes and key in code_fixes:
            code = code_fixes[key]
            issues.append("code_taken_from_second_reading")
        if code is None:
            issues.append("code_not_read")
        elif last_code and code < last_code:
            issues.append(f"code_not_ascending_after_{last_code}")
        if code:
            last_code = code
        f = fit(r["cells"], r["how"])
        lines.append(dict(sr_no=sr, code=code, code_raw=r["code_raw"], page=r["page"], y=r["y"], desc=r["desc"], cells=r["cells"], how=r["how"], fit=f, issues=issues))
    return lines, fails


def finalize(lines):
    out, fails = [], []
    for ln in lines:
        f = ln["fit"]
        issues = list(ln["issues"])
        if f is None:
            vals, reading, status = ln["cells"], "ocr_cells_only", "needs_review"
            issues.append("fewer_than_5_cells_read")
        else:
            ratio = f["agree"] / f["observed"]
            if f["agree"] >= 10 and len(f["misfit"]) <= 3 and ratio >= 0.8:
                vals, reading, status = f["values"], "ocr_fitted_to_taper_pattern", "accepted"
                for i, got, want in f["misfit"]:
                    fails.append(dict(check="ocr_cell_disagrees_with_pattern", sr_no=ln["sr_no"], code=ln["code"], page=ln["page"],
                                      detail=f"year {i + 1}: OCR read {got}, pattern {label(f)} (start {f['s']}, end {f['e']}, base {f['b']}) gives {f['values'][i]}"))
            else:
                vals, reading, status = ln["cells"], "ocr_cells_only", "needs_review"
                issues.append(f"no_pattern_fits_agree_{f['agree']}_of_{f['observed']}")
        if any(not (i.startswith("srno_not_read") or i.startswith("srno_misread") or i == "code_taken_from_second_reading") for i in ln["issues"]):
            status = "needs_review"
        out.append(dict(sr_no=ln["sr_no"], code=ln["code"] or "", page=ln["page"], description_ocr=ln["desc"], reading=reading, status=status,
                        pattern=label(f), base_rate=(f["b"] if f else ""), start_year=(f["s"] if f else ""), end_year=(f["e"] if f else ""),
                        cells_read=(f["observed"] if f else sum(v is not None for v in ln["cells"])), cells_agree=(f["agree"] if f else ""),
                        issues="; ".join(issues), **{f"year_{i + 1}": ("" if vals[i] is None else f"{vals[i]:.2f}") for i in range(NYEARS)}))
        for i in issues:
            fails.append(dict(check=re.sub(r"[_0-9]+$", "", re.sub(r"_(\d+)", "", i))[:40], sr_no=ln["sr_no"], code=ln["code"] or "", page=ln["page"], detail=i))
    return out, fails


CONDITION_TEXT = ("Goods of the People's Republic of China only (SRO 1640(I)/2019 p.1). Proviso: manufactured or produced in China and imported in "
                  "conformity with the Rules of Determination of Origin and the certification procedure of S.R.O. 1286(I)/2005 (Certificate of Origin, Form E) "
                  "read with the Import Policy Order 2016. The importer pays the lower of the First Schedule duty and the rate printed here.")
STORE_YEARS = (6, 7, 8)       # 1-Jan-2025, 1-Jan-2026, 1-Jan-2027: the calendar years that touch FY2025-26 and FY2026-27
CATEGORY = {"constant_zero": "A0 (zero in all years)", "constant_rate": "constant rate (C1/C2 or MOP)", "A07_taper_to_zero_year7": "A07",
            "A15_taper_year3_to_15": "A15", "unfitted": "unfitted"}


def _tariff_sets():
    out = {}
    for fy, f in (("FY2026-27", "tariff_2026_27.csv"), ("FY2025-26", "tariff_2025_26.csv")):
        out[fy] = {r["code"].replace(".", "") for r in csv.DictReader(open(PROC / f, encoding="utf-8"))}
    return out


def _good_code(ln):
    return ln["code"] and not any(x.startswith("code_not_ascending") for x in ln["issues"])


def write_outputs(reread=True):
    import datetime as _dt

    allrows, pages = build()
    lines, _ = numbered(allrows)
    fixes_log = []
    if reread:
        need = []
        for i, ln in enumerate(lines):
            if not _good_code(ln):
                prev = next((lines[j]["code"] for j in range(i - 1, -1, -1) if _good_code(lines[j])), None)
                nxt = next((lines[j]["code"] for j in range(i + 1, len(lines)) if _good_code(lines[j])), None)
                need.append(dict(page=ln["page"], y=ln["y"], sr_no=ln["sr_no"], code=ln["code"], prev_code=prev, next_code=nxt))
        from src.ingest.a8_cpfta_codes import main as reread_main

        fx, fixes_log = reread_main(need)
        by_sr = {n["sr_no"]: (n["page"], n["y"]) for n in need}
        code_fixes = {by_sr[sr]: c for sr, c in fx.items()}
        lines, _ = numbered(allrows, code_fixes)
    rows, fails = finalize(lines)
    inferred = {x["sr_no"] for x in fixes_log if "inferred" in x.get("how", "") and x["accepted_code"]}
    for r in rows:
        if r["sr_no"] in inferred:
            r["status"] = "needs_review"
            r["issues"] = (r["issues"] + "; " if r["issues"] else "") + "code_one_character_inferred"
            fails.append(dict(check="code_one_character_inferred", sr_no=r["sr_no"], code=r["code"], page=r["page"], detail="one unreadable digit filled from neighbours and tariff"))
    tc = _tariff_sets()
    srs = [r["sr_no"] for r in rows]
    missing = sorted(set(range(1, LAST_SR + 1)) - set(srs))
    for sr in missing[:2000]:
        fails.append(dict(check="srno_missing_from_reading", sr_no=sr, code="", page="", detail="Sr.No 1..6786 must all be present"))
    for r in rows:
        c = r["code"]
        if c:
            lvl = "in_both_tariffs" if (c in tc["FY2025-26"] and c in tc["FY2026-27"]) else ("only_2025_26" if c in tc["FY2025-26"] else ("only_2026_27" if c in tc["FY2026-27"] else "in_neither"))
            r["tariff_check"] = lvl
            if lvl == "in_neither":
                fails.append(dict(check="code_not_in_tariff_2025_26_or_2026_27", sr_no=r["sr_no"], code=c, page=r["page"],
                                  detail="not a line of either tariff (HS 2017 code of the 2019 SRO, or misread; OQ-A8-1)"))
        else:
            r["tariff_check"] = "no_code"
    summary = {
        "pages_read": len(pages), "lines": len(rows), "last_sr_no": max(srs) if srs else None, "expected_lines": LAST_SR,
        "sr_no_missing": len(missing), "status": dict(Counter(r["status"] for r in rows)), "reading": dict(Counter(r["reading"] for r in rows)),
        "patterns": dict(Counter(r["pattern"] for r in rows)), "tariff_check": dict(Counter(r.get("tariff_check") for r in rows)),
        "failures": dict(Counter(f["check"] for f in fails)), "code_rereads": len(fixes_log),
        "code_rereads_accepted": sum(1 for x in fixes_log if x["accepted_code"]),
        "fbr_category_cross_check": {"fbr_A0_lines": 3251, "reading_constant_zero_lines": sum(1 for r in rows if r["pattern"] == "constant_zero")},
    }
    with open(PROC / "a8_cpfta_rows.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    json.dump(rows, open(PROC / "a8_cpfta_rows.json", "w", encoding="utf-8"), ensure_ascii=False)
    agg = {}
    for fl in fails:
        k = (fl["check"], fl.get("sr_no"), fl.get("code"), fl.get("page"), fl.get("detail"))
        agg.setdefault(k, dict(fl, count=0))["count"] += 1
    with open(PROC / "a8_cpfta_failures.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["check", "sr_no", "code", "page", "detail", "count"], extrasaction="ignore")
        w.writeheader()
        w.writerows(agg.values())
    with open(PROC / "a8_cpfta_code_reread.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sr_no", "page", "old_code", "reread_text", "accepted_code", "how", "why_not"])
        w.writeheader()
        w.writerows(fixes_log)
    long = []
    for r in rows:
        if not r["code"]:
            continue
        for y in STORE_YEARS:
            v = r[f"year_{y}"]
            if v == "":
                continue
            vf = DATES[y - 1]
            vt = (_dt.date.fromisoformat(DATES[y]) - _dt.timedelta(days=1)).isoformat() if y < 15 else "9999-12-31"
            long.append(dict(row_id=f"cpfta1640:{r['sr_no']}:y{y}", sr_no=r["sr_no"], year_no=y, calendar_year=int(vf[:4]), column_date=f"1-Jan-{vf[2:4]}",
                             code_norm=r["code"], match_level="code8", rule_group="FTA-CN-1640", rate_kind="percent", rate_pct=v, rate_raw=v,
                             description_ocr=r["description_ocr"], category=CATEGORY.get(r["pattern"], r["pattern"]),
                             pattern_base_rate=r["base_rate"], cells_read=r["cells_read"], cells_agree=r["cells_agree"], rate_source=r["reading"],
                             condition_text=CONDITION_TEXT, issues=r["issues"], status=r["status"],
                             valid_from=vf, valid_to=vt, source_file=SOURCE, page=r["page"]))
    with open(PROC / "a8_cpfta_rules.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(long[0]))
        w.writeheader()
        w.writerows(long)
    json.dump(summary, open(PROC / "a8_cpfta_validation.json", "w", encoding="utf-8"), indent=1)
    return rows, fails, summary


if __name__ == "__main__":
    import sys
    _, _, summary = write_outputs(reread="--no-reread" not in sys.argv)
    print(json.dumps(summary, indent=1))
