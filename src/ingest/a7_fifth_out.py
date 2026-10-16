"""A7: Fifth Schedule rule rows, validators and output files (see a7_fifth.py for the table reader).

Usage: python -m src.ingest.a7_fifth_out
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict

import pymupdf

from src.ingest.a7_fifth import (CODE8, PROC, RAW, SKIP_PAGES, ONLY_FIRST_BLOCK, SOURCE, VALID_FROM, VALID_TO, norm_codes,
                                 parse_rate, read_all)
from src.ingest.pdf_grid import table_blocks

SCOPE = {
    ("I", "main"): "plant_machinery_part_I",
    ("II", "A"): "pharma_api", ("II", "B"): "pharma_excipients", ("II", "C"): "pharma_drugs_packing",
    ("II", "D"): "pharma_packing_inputs", ("II", "E"): "pharma_kits",
    ("III", "main"): "sector_inputs_poultry_textile_other",
    ("IV", "main"): "textile_machinery",
    ("V(A)", "I"): "ev_cbu", ("V(A)", "II"): "ev_ckd_parts", ("V(A)", "III"): "ev_plant_inputs",
    ("V(B)", "I"): "hybrid_cbu", ("V(B)", "II"): "hybrid_parts",
    ("V(C)", "main"): "agricultural_tractors",
    ("VI", "main"): "aviation",
    ("VIII", "main"): "border_markets",
}
PART_CONDITION_REF = {
    "I": "Part I Note (i)-(v) and Explanations I-IV (pages 2-3): local-manufacture test, chief-executive certificate (Annex-A), "
         "slab test for entries that list several rates",
    "II": "Part II conditions (i)-(v) (page 23): in-house use, DRAP/IOCO determination; note (v) slab test for 'Respective Headings' with two rates",
    "III": "Part III conditions (i)-(iii) (page 41) plus the Conditions column",
    "IV": "Part IV Conditions column (page 49)",
    "V(A)": "Part V(A) Conditions column (EV policy 2020, EDB certification)",
    "V(B)": "Part V(B) Conditions column (AIDEP 2021-26, EDB certification)",
    "V(C)": "Part V(C) printed table (page 55)",
    "VI": "Part VI conditions (ia)-(iii) and Special Condition column (page 56)",
    "VIII": "Part VIII conditions (i)-(vi): border markets, US$50 per visitor per day (page 56)",
}
MARK_RE = re.compile(r"^\s*(\(?(?:\d{1,2}|[ivxlc]{1,6}|[a-zA-Z])\)?[\.\)]?)\s+")
LETTER_HEADING = re.compile(r"^\(?[A-Z]\)\s")


def link_context(rows):
    """Attach title / group heading, trailing sub-lines and inherited rates. Returns the rule-bearing rows."""
    out = []
    cur_key, title, group, parent, head_rate, serial_rate = None, "", "", None, "", ""
    for r in rows:
        k = r["row_kind"]
        if k in ("table_header", "empty", "unparsed_block"):
            continue
        key = (r["part"], r["table"], r["s_no"])
        if key != cur_key:
            cur_key, title, group, parent, head_rate, serial_rate = key, "", "", None, "", ""
        desc = r.get("description", "")
        if k == "omitted":
            parent = None
            continue
        if k == "heading":
            if parent is not None and desc and not LETTER_HEADING.match(desc):
                parent.setdefault("sub_lines", []).append(desc)
                continue
            if not title and r.get("s_no_printed"):
                title = desc
            else:
                group = desc
            if r["rate_raw"]:
                head_rate = r["rate_raw"]
            continue
        if k == "item_without_code":
            if parent is not None and parent.get("_respective") and not r.get("s_no_printed"):
                parent.setdefault("sub_lines", []).append(desc)
                continue
            r["_codes"], r["_levels"], r["_respective"] = [], [], False
            if r["rate_raw"]:
                head_rate = r["rate_raw"]
            parent = r
        else:  # item
            codes, levels, resp = norm_codes(r["pct_raw"])
            r["_codes"], r["_levels"], r["_respective"] = codes, levels, resp
            if not r["rate_raw"] and head_rate:
                r["rate_raw"] = head_rate
                r["rate_inherited_from_heading"] = True
            elif not r["rate_raw"] and serial_rate:
                r["rate_raw"] = serial_rate
                r["rate_inherited_from_earlier_row_of_same_serial"] = True
            parent = r
        if r["rate_raw"] and not r.get("rate_inherited_from_heading") and not r.get("rate_inherited_from_earlier_row_of_same_serial"):
            serial_rate = r["rate_raw"]
        r["_title"], r["_group"] = title, group
        out.append(r)
    return out


def to_rules(rows):
    rules, n = [], 0
    for r in link_context(rows):
        kind, pcts, frac, note = parse_rate(r["rate_raw"])
        pcts = [str(p) for p in pcts]
        codes, levels = r.get("_codes", []), r.get("_levels", [])
        issues = [x for x in [r.get("issues", "")] if x and x != "description_shared_by_several_codes"]
        info = ["description_shared_by_several_codes"] if r.get("issues") == "description_shared_by_several_codes" else []
        if not codes and r.get("description2"):
            c2, l2, _ = norm_codes(re.sub(r"PCT code", " ", r["description2"]))
            if c2:
                codes, levels = c2, l2
                info.append("code_taken_from_description_text")
        if r.get("rate_inherited_from_heading"):
            issues.append("rate_inherited_from_heading_row")
        if r.get("rate_inherited_from_earlier_row_of_same_serial"):
            issues.append("rate_inherited_from_earlier_row_of_same_serial")
        if r.get("rate_carried_over_page_break"):
            info.append("rate_carried_over_page_break")
        if not r["rate_raw"]:
            issues.append("no_rate_found")
        if kind == "other":
            issues.append("rate_text_not_a_plain_percentage")
        if len(pcts) > 1 and kind == "percent":
            info.append("several_rates_slab_rule_applies")
        marker = MARK_RE.match(r.get("description", ""))
        common = dict(
            part=r["part"], table=r["table"], s_no=r["s_no"], sub_ref=marker.group(1) if marker else "",
            description=r.get("description", ""), description2=r.get("description2", ""),
            title=r.get("_title", ""), group_context=r.get("_group", ""), sub_items_text=" | ".join(r.get("sub_lines", [])),
            scope=SCOPE.get((r["part"], r["table"]), "other"), rate_raw=r["rate_raw"], rate_kind=kind,
            rate_pcts=json.dumps(pcts), rate_fraction_pct=frac or "", rate_note=note,
            conditions=r.get("conditions", ""), part_conditions_ref=PART_CONDITION_REF.get(r["part"], ""),
            valid_from=VALID_FROM, valid_to=VALID_TO, source_file=SOURCE, page=r["page"], band_y=f'{r["y0"]}-{r["y1"]}',
            extraction_method="text layer + ruling-line cell grid (pdf_grid.py)",
        )
        for code, level in (list(zip(codes, levels)) or [("", "unmapped")]):
            n += 1
            these = list(issues) + list(info)
            if level == "unmapped":
                these.append("named_by_description_only")
            rules.append(dict(rule_id=f"A7F-{n:05d}", code_raw=r["pct_raw"], code_norm=code, match_level=level,
                              issues="; ".join(these), status="needs_review" if issues else "accepted", **common))
    return rules


def tariff_codes():
    out = {}
    for fy, f in (("FY2026-27", "tariff_2026_27.csv"), ("FY2025-26", "tariff_2025_26.csv")):
        out[fy] = {r["code"].replace(".", "") for r in csv.DictReader(open(PROC / f, encoding="utf-8"))}
    return out


def serial_key(s: str):
    m = re.match(r"^(\d+)\(?([A-Za-z]*)", s)
    return (int(m.group(1)), m.group(2).upper()) if m else (10**9, s)


def validate(rows, rules):
    """Every finding is a row of the failures report; nothing is fixed silently."""
    fails = []

    def add(check, page, part, table, s_no, detail):
        fails.append(dict(check=check, page=page, part=part, table=table, s_no=s_no, detail=detail))

    tc = tariff_codes()
    for r in rules:
        lvl, c = r["match_level"], r["code_norm"]
        if lvl == "code8" and c not in tc["FY2026-27"]:
            note = "also not in FY2025-26 tariff" if c not in tc["FY2025-26"] else "exists in FY2025-26 tariff only"
            add("code_not_in_tariff_2026_27", r["page"], r["part"], r["table"], r["s_no"], f"{c} ({note})")
        elif lvl in ("code6", "heading4") and not any(t.startswith(c) for t in tc["FY2026-27"]):
            add(f"{lvl}_matches_no_tariff_line", r["page"], r["part"], r["table"], r["s_no"], c)
    # serial continuity per (part, table)
    ser = defaultdict(list)
    for r in rows:
        if r.get("s_no_printed") and r["row_kind"] in ("item", "item_without_code", "omitted", "heading"):
            ser[(r["part"], r["table"])].append((r["s_no"], r["page"]))
    for (part, table), lst in ser.items():
        seen, last = set(), None
        for s, pg in lst:
            if s in seen:
                continue
            seen.add(s)
            k = serial_key(s)
            if k[0] == 10**9:
                continue
            if last is not None:
                if k[0] < last[0] or (k[0] == last[0] and k[1] <= last[1]):
                    add("serial_not_increasing", pg, part, table, s, f"after {last}")
                elif k[0] - last[0] > 1:
                    add("serial_gap", pg, part, table, s, f"jumps from {last[0]} to {k[0]}")
            last = k
    # rate sanity
    ok_rates = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "15", "16", "20", "25", "35", "40", "50", "60", "100"}
    for r in rules:
        if r["rate_kind"] == "percent":
            for p in json.loads(r["rate_pcts"]):
                if p not in ok_rates:
                    add("unusual_rate", r["page"], r["part"], r["table"], r["s_no"], f'{p} in "{r["rate_raw"]}"')
            ps = [float(x) for x in json.loads(r["rate_pcts"])]
            if ps != sorted(ps):
                add("rates_not_ascending", r["page"], r["part"], r["table"], r["s_no"], r["rate_raw"])
        if r["rate_kind"] == "none" and r["match_level"] != "unmapped":
            add("coded_row_without_rate", r["page"], r["part"], r["table"], r["s_no"], r["code_raw"])
        for tag in ("rate_inherited_from_heading_row", "rate_inherited_from_earlier_row_of_same_serial",
                    "description_shared_by_several_codes", "rate_carried_over_page_break"):
            if tag in r["issues"]:
                add(tag, r["page"], r["part"], r["table"], r["s_no"], (r["rate_raw"] or r["description"])[:60])
    # completeness against the page text layer: every 8-digit code printed in a PCT cell must be in a parsed row
    doc = pymupdf.open(RAW / SOURCE)
    parsed = defaultdict(Counter)
    for r in rows:
        if r["row_kind"] in ("item", "item_without_code", "omitted"):
            for c in norm_codes(r.get("pct_raw", ""))[0]:
                parsed[r["page"]][c] += 1
    for pno in range(2, len(doc) + 1):
        if pno in SKIP_PAGES:
            continue
        page = doc[pno - 1]
        blocks = table_blocks(page)
        if pno in ONLY_FIRST_BLOCK:
            blocks = blocks[:1]
        found = Counter()
        for w in page.get_text("words"):
            xc, yc = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
            tok = w[4].strip(",;.")
            if CODE8.fullmatch(tok) and any(b["y0"] <= yc <= b["y1"] and b["xs"][0] <= xc <= b["xs"][-1] for b in blocks):
                found[tok.replace(".", "")] += 1
        for c, nn in (found - parsed[pno]).items():
            add("code_in_page_text_not_in_parsed_rows", pno, "", "", "", f"{c} x{nn} (may be a code quoted inside a description or condition)")
    # two-tool diff against pymupdf.find_tables
    for pno in range(2, len(doc) + 1):
        if pno in SKIP_PAGES:
            continue
        try:
            tabs = doc[pno - 1].find_tables()
        except Exception:
            continue
        theirs = set()
        for t in tabs.tables:
            for row in t.extract():
                for cell in row:
                    for m in CODE8.finditer(cell or ""):
                        theirs.add(m.group(1) + m.group(2))
        only = theirs - set(parsed[pno])
        if only:
            add("two_tool_diff_codes_only_in_find_tables", pno, "", "", "", ",".join(sorted(only)[:12]))
    return fails


def write_outputs():
    rows = read_all()
    rules = to_rules(rows)
    fails = validate(rows, rules)
    PROC.mkdir(exist_ok=True, parents=True)

    def dump(name, data, fields=None):
        fields = fields or sorted({k for d in data for k in d})
        with open(PROC / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)
        with open(PROC / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, default=str)

    flat = [{k: (json.dumps(v) if isinstance(v, (list, tuple, dict)) else v) for k, v in r.items() if not k.startswith("_")} for r in rows]
    dump("a7_fifth_rows", flat)
    rf = ["rule_id", "part", "table", "s_no", "sub_ref", "description", "description2", "title", "group_context", "sub_items_text",
          "scope", "code_raw", "code_norm", "match_level", "rate_raw", "rate_kind", "rate_pcts", "rate_fraction_pct", "rate_note",
          "conditions", "part_conditions_ref", "valid_from", "valid_to", "source_file", "page", "band_y", "status", "issues",
          "extraction_method"]
    dump("a7_fifth_rules", rules, rf)
    agg = {}
    for fl in fails:
        k = (fl["check"], fl["page"], fl["part"], fl["table"], fl["s_no"], fl["detail"])
        agg.setdefault(k, dict(fl, count=0))["count"] += 1
    with open(PROC / "a7_fifth_failures.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["check", "page", "part", "table", "s_no", "detail", "count"])
        w.writeheader()
        w.writerows(agg.values())
    summary = {
        "source": SOURCE, "valid_from": VALID_FROM, "rows_total": len(rows), "rules_total": len(rules),
        "rules_by_scope": dict(Counter(r["scope"] for r in rules)),
        "rules_by_match_level": dict(Counter(r["match_level"] for r in rules)),
        "rules_by_status": dict(Counter(r["status"] for r in rules)),
        "failures_by_check": dict(Counter(f["check"] for f in fails)),
    }
    json.dump(summary, open(PROC / "a7_fifth_validation.json", "w", encoding="utf-8"), indent=1)
    return rows, rules, fails, summary


if __name__ == "__main__":
    _, _, _, summary = write_outputs()
    print(json.dumps(summary, indent=1))
