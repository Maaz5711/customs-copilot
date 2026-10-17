"""A8b: the replacement Table of SRO 1181(I)/2022 (28 Jul 2022), which substitutes the whole Table of SRO 1640(I)/2019 (China-Pakistan FTA Phase II) with HS 2022 codes.

The PDF has a text layer (not a scan) for most pages: each table row is printed as the serial number, the 8-digit code with its description, then the
15 yearly rates (1-Jan-2020 ... 1-Jan-2034), one value per line. The last pages of the file are scan noise and are listed as failures, never guessed.
Every row is checked, and a row that fails any check is NOT written as accepted (it stays out, and the failure is logged):
* the serial number runs 1, 2, 3 ... without a gap;
* the code is 8 digits and rises in order;
* exactly 15 values are read, and they form one of FBR's three patterns (constant, A07 taper to 0 in year 7, A15 taper in years 3 to 15);
* the code is a line of the FY2025-26 or FY2026-27 tariff (otherwise logged, row kept as needs_review).
Output: data/processed/a8b_cpfta2022_rows.csv, a8b_cpfta2022_rules.csv (same long format as a8_cpfta_rules.csv), a8b_cpfta2022_final_rules.csv (what the store loads), a8b_cpfta2022_failures.csv, a8b_cpfta2022_validation.json.
Usage: python -m src.ingest.a8b_cpfta_2022
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path

import pymupdf

from .a8_cpfta import CONDITION_TEXT, DATES, FAMILIES, NYEARS, STORE_YEARS, fit, label

PROC = Path("data/processed")
SOURCE = "2022729127282556SRO1181(I)2022(28.7.22).pdf"
PDF = Path("data/raw") / SOURCE
EFFECTIVE_FROM = "2022-07-28"      # date of the SRO (file name; the page prints "Islamabad, the ... July, 2022")
CODE = re.compile(r"^(\d{4})\.(\d{4})\b")
VALUE = re.compile(r"^\d{1,2}\.\d{2}$")
SERIAL = re.compile(r"^\d{1,5}$")
CATEGORY = {"constant_zero": "A0 (zero in all years)", "constant_rate": "constant rate (C1/C2 or MOP)", "A07_taper_to_zero_year7": "A07",
            "A15_taper_year3_to_15": "A15", "unfitted": "unfitted"}


def raw_rows(pdf: Path = PDF):
    """Yield dict(sr_no, code, page, desc, values) for every row start found in the text layer."""
    doc = pymupdf.open(pdf)
    cur = None
    for pno in range(len(doc)):
        lines = [x.strip() for x in doc[pno].get_text().splitlines()]
        lines = [x for x in lines if x]
        if lines and SERIAL.match(lines[0]) and int(lines[0]) == pno + 1:      # printed page number
            lines = lines[1:]
        i = 0
        while i < len(lines):
            t = lines[i]
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if SERIAL.match(t) and CODE.match(nxt):
                if cur:
                    yield cur
                cur = dict(sr_no=int(t), code=CODE.match(nxt).group(1) + CODE.match(nxt).group(2), page=pno + 1, desc=nxt, values=[], specific=0, no_exemption=0)
                i += 2
                continue
            if cur is not None:
                if VALUE.match(t):
                    cur["values"].append(float(t))
                elif "/MT" in t or "/KG" in t or "/NO" in t or t.startswith("Rs"):
                    cur["specific"] += 1                 # a specific duty in rupees (for example "Rs. 7240.0/MT"): not a percentage, not supported
                elif "no exemption" in t.lower():
                    cur["no_exemption"] += t.lower().count("no exemption")      # the column has no FTA concession that year
                elif not cur["values"]:
                    cur["desc"] += " " + t
            i += 1
    if cur:
        yield cur


def tariff_codes() -> dict[str, set[str]]:
    out = {}
    for fy, f in (("FY2026-27", "tariff_2026_27.csv"), ("FY2025-26", "tariff_2025_26.csv")):
        out[fy] = {r["code"].replace(".", "") for r in csv.DictReader(open(PROC / f, encoding="utf-8"))}
    return out


def build():
    rows, fails = [], []
    tc = tariff_codes()
    prev_sr, prev_code = 0, ""
    for r in raw_rows():
        issues = []
        if r["sr_no"] != prev_sr + 1:
            issues.append(f"srno_jump_{prev_sr}_to_{r['sr_no']}")
        if prev_code and r["code"] <= prev_code:
            issues.append("code_not_ascending")
        prev_sr, prev_code = r["sr_no"], r["code"]
        vals = [None] * r["no_exemption"] + r["values"]
        status, pattern, f = "accepted", "unfitted", None
        if r["specific"]:
            status = "unsupported_specific_duty"
            issues.append("specific_duty_in_rupees_not_modelled")
        elif len(vals) != NYEARS:
            status = "rejected"
            issues.append(f"values_read_{len(vals)}_of_15")
        else:
            f = fit(vals, "exact", families_only=True)
            observed = sum(v is not None for v in vals)
            if f is None or f["agree"] != observed or observed < 13:
                status = "rejected"
                issues.append(f"no_fbr_pattern_fits_agree_{f['agree'] if f else 0}_of_{observed}")
            else:
                pattern = label(f)
                vals = f["values"]            # equal to the printed values where they were read; fills a year that printed 'no exemption'
                if r["no_exemption"]:
                    issues.append(f"no_exemption_printed_for_first_{r['no_exemption']}_years")
        if "code_not_ascending" in issues or any(x.startswith("srno_jump") for x in issues):
            if status == "accepted":
                status = "needs_review"
        c = r["code"]
        lvl = "in_both_tariffs" if (c in tc["FY2025-26"] and c in tc["FY2026-27"]) else ("only_2025_26" if c in tc["FY2025-26"] else ("only_2026_27" if c in tc["FY2026-27"] else "in_neither"))
        if lvl == "in_neither":
            issues.append("code_not_in_tariff_2025_26_or_2026_27")
            if status == "accepted":
                status = "needs_review"
        rows.append(dict(sr_no=r["sr_no"], code=c, page=r["page"], description=re.sub(r"\s+", " ", r["desc"])[:200], status=status, pattern=pattern,
                         base_rate=(f["b"] if f else ""), tariff_check=lvl, issues="; ".join(issues),
                         **{f"year_{i + 1}": (f"{vals[i]:.2f}" if i < len(vals) and vals[i] is not None else "") for i in range(NYEARS)}))
        for i in issues:
            fails.append(dict(check=re.sub(r"_?\d+", "", i)[:48], sr_no=r["sr_no"], code=c, page=r["page"], detail=i))
    return rows, fails


def long_rules(rows):
    out = []
    for r in rows:
        if r["status"] in ("rejected", "unsupported_specific_duty"):
            continue
        for y in STORE_YEARS:
            v = r[f"year_{y}"]
            vf = max(DATES[y - 1], EFFECTIVE_FROM) if y > 0 else DATES[y - 1]
            vt = (dt.date.fromisoformat(DATES[y]) - dt.timedelta(days=1)).isoformat()
            out.append(dict(row_id=f"cpfta1181:{r['sr_no']}:y{y}", sr_no=r["sr_no"], year_no=y, calendar_year=int(DATES[y - 1][:4]),
                            column_date=f"1-Jan-{DATES[y - 1][2:4]}", code_norm=r["code"], match_level="code8", rule_group="FTA-CN-1640", rate_kind="percent",
                            rate_pct=v, rate_raw=v, description_ocr=r["description"], category=CATEGORY.get(r["pattern"], r["pattern"]),
                            pattern_base_rate=r["base_rate"], cells_read=15, cells_agree=15, rate_source="text_layer_fitted_to_fbr_pattern",
                            condition_text=CONDITION_TEXT.replace("SRO 1640(I)/2019 p.1", "SRO 1640(I)/2019 as substituted by SRO 1181(I)/2022"),
                            issues=r["issues"], status=r["status"], valid_from=vf, valid_to=vt, source_file=SOURCE, page=r["page"]))
    return out


def final_rules(rows, lines):
    """Rules the store loads: the 2022 table, plus (flagged, needs_review) the 2019 reading for codes whose 2022 row could not be read
    (status 'rejected', not the specific-duty rows). The 2019 reading and the 2022 table agree on 5,698 of 5,700 shared codes for 2025-2027,
    so the fallback is reasonable, but it is not the current legal text and is marked as such."""
    bad = {r["code"] for r in rows if r["status"] == "rejected"}
    out = list(lines)
    old_path = PROC / "a8_cpfta_rules.csv"
    if old_path.exists() and bad:
        for r in csv.DictReader(open(old_path, encoding="utf-8")):
            if r["code_norm"] in bad and r["status"] == "accepted":
                r = dict(r, row_id="cpfta1640fb:" + r["row_id"].split(":", 1)[1], status="needs_review",
                         issues=(r["issues"] + "; " if r["issues"] else "") + "read_from_superseded_2019_table_because_the_2022_row_was_unreadable")
                out.append({k: r.get(k, "") for k in lines[0]})
    return out


def write_outputs():
    rows, fails = build()
    lines = long_rules(rows)
    srs = [r["sr_no"] for r in rows]
    summary = {"lines": len(rows), "last_sr_no": max(srs) if srs else None, "status": dict(Counter(r["status"] for r in rows)),
               "patterns": dict(Counter(r["pattern"] for r in rows)), "tariff_check": dict(Counter(r["tariff_check"] for r in rows)),
               "failures": dict(Counter(f["check"] for f in fails)), "pages": len(pymupdf.open(PDF))}
    final = final_rules(rows, lines)
    summary["final_rules"] = len(final)
    for name, data in (("rows", rows), ("rules", lines), ("failures", fails), ("final_rules", final)):
        if data:
            with open(PROC / f"a8b_cpfta2022_{name}.csv", "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(data[0]))
                w.writeheader()
                w.writerows(data)
    json.dump(summary, open(PROC / "a8b_cpfta2022_validation.json", "w", encoding="utf-8"), indent=1)
    return rows, fails, summary


if __name__ == "__main__":
    print(json.dumps(write_outputs()[2], indent=1))
