"""Customs-duty concessions for compute_duty / get_applicable_sros: Fifth Schedule (Customs Act s.18(1A)) and the
China-Pakistan FTA Phase II (SRO 1640(I)/2019).

Exact arithmetic only (Decimal, no LLM). A concession is never applied unless the caller lists its rule id in `claimed_rules`:
the tools OFFER it (rate, bill if applied, conditions the system cannot check) and the agent asks the importer.
Rates are read from the dated store (tables fifth_schedule_rules, fta_rules); nothing is written from memory here.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal

from ._util import D, collect, fmt, rows

# Chapters where the Fifth Schedule "capital goods" definition (Chapters 84, 85 or any other chapter) most often matters: the agent asks.
CAPITAL_GOODS_CHAPTERS = ("84", "85", "90")
BORDER_MARKET_SCOPE = "border_markets"
FIFTH_INSTRUMENT = "Fifth Schedule to the Customs Act 1969 (substituted by Finance Act 2026 s.3(14), from 1 Jul 2026)"
FIFTH_INSTRUMENT_2025 = "Fifth Schedule to the Customs Act 1969 (FY2025-26 version, FBR file)"
FTA_INSTRUMENT = "SRO 1640(I)/2019 (China-Pakistan FTA Phase II), Table substituted by SRO 1181(I)/2022"
ORIGIN_CN = {"cn", "chn", "china", "prc", "people's republic of china", "peoples republic of china"}


# --------------------------------------------------------------------------------------------------- Fifth Schedule
def fifth_effective_rate(listed: list[Decimal], cd: Decimal | None):
    """Customs duty the Fifth Schedule entry gives for goods whose First Schedule CD is `cd`.

    Source: Part I note (iv) and Explanations I-IV (pages 2-3) and Part II note (v) (page 23): of the rates listed in column (4), the
    LOWER ones (0%, 3%, 11%) apply only to goods whose First Schedule CD is that same rate; goods in any higher slab pay the LAST
    (maximum) listed rate. One listed rate = that rate (Customs Act s.18(1A): "customs duties shall be levied at such rates ...
    as are prescribed in the Fifth Schedule").
    Returns (rate | None, explanation, flags).
    """
    if not listed:
        return None, "no percentage printed", ["no_rate"]
    if len(listed) == 1:
        return listed[0], f"entry prints one rate, {fmt(listed[0])}%", []
    if cd is None:
        return None, "the entry lists several rates by slab; the tariff duty of this code is not a plain percentage, so the slab cannot be tested", ["tariff_cd_not_plain"]
    lows, top = listed[:-1], listed[-1]
    if cd in lows:
        return cd, f"tariff CD {fmt(cd)}% is one of the listed lower rates, so that rate applies", []
    if cd >= top:
        return top, f"tariff CD {fmt(cd)}% is in a higher slab, so the maximum concessionary rate {fmt(top)}% applies", []
    return cd, (f"tariff CD {fmt(cd)}% is below the maximum {fmt(top)}% and is not a listed slab: the normal rate is kept (assumption, OQ-A7-4)"), \
        ["slab_not_listed_normal_rate_kept"]


_EXCL_SEG = re.compile(r"serial numbers?\s+([\d,\s\(\)a-zA-Z]+?)\s+of the Table of Part[- ]?(III|I)\b", re.I)


def fifth_acd_exclusions(conn, d: str) -> dict:
    """Serials of the Fifth Schedule that are EXCLUDED from the ACD 'not levied' clause 3(iii) of the ACD SRO in force on `d`.

    Read from the stored clause text, e.g. 'excluding serial numbers 30, 33 and 35 of the Table of Part-I and serial numbers
    102, 111, 116 (except xvi), 117 and 118 of the Table of Part III'. Returns {part: {serial: None | 'xvi'(allowed sub-item)}}.
    """
    r = rows(conn, "SELECT * FROM acd_rules WHERE clause = '3(iii)' AND valid_from <= ? AND valid_to >= ? ORDER BY id", [d, d])
    if not r:
        return {"_source": None}
    text = r[0]["condition_text"] or ""
    out: dict = {"_source": {"rule_id": f"acd_rules:{r[0]['id']}", "sro_number": r[0]["sro_number"], "clause": r[0]["clause"],
                             "source_file": r[0]["source_file"], "page": r[0]["page"], "text": text}}
    for m in _EXCL_SEG.finditer(text):
        part = m.group(2).upper()
        for tok in re.findall(r"(\d+[A-Za-z]?)(?:\s*\(\s*except\s+([ivx]+)\s*\))?", m.group(1)):
            out.setdefault(part, {})[tok[0]] = tok[1] or None
    return out


def _acd_exempt_under_fifth(excl: dict, part: str, s_no: str, sub_ref: str) -> tuple[bool | None, str]:
    """True if the ACD 'not levied' clause 3(iii) covers this Fifth Schedule serial; None if the clause is not in the store."""
    if not excl.get("_source"):
        return None, "ACD clause 3(iii) not found in the store for this date"
    if part not in ("I", "III"):
        return True, "Fifth Schedule import: ACD not levied (SRO para 3(iii)); only Part I serials 30, 33, 35 and some Part III serials are excluded"
    ser = re.match(r"\d+[A-Za-z]?", s_no or "")
    ser = ser.group(0) if ser else s_no
    if ser in excl.get(part, {}):
        keep = excl[part][ser]
        if keep and keep.lower() in (sub_ref or "").lower():
            return True, f"serial {ser} is excluded from clause 3(iii) except sub-item ({keep}), which is covered"
        return False, f"serial {ser} of Part {part} is excluded from the ACD 'not levied' clause 3(iii): ACD is still charged"
    return True, "Fifth Schedule import: ACD not levied (SRO para 3(iii))"


def _tariff_cd(trow):
    return D(trow["cd_rate"]) if trow["cd_kind"] == "plain" else None


def _short(s, n=240):
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "..."


def _fifth_option(conn, r: dict, trow: dict, d: str, excl: dict) -> dict:
    listed = [D(x) for x in json.loads(r["rate_pcts"] or "[]")]
    cd = _tariff_cd(trow)
    eff, how, flags = None, "", list(r.get("_flags", []))
    if r["rate_kind"] == "percent":
        eff, how, f2 = fifth_effective_rate(listed, cd)
        flags += f2
    elif r["rate_kind"] == "fraction_of_first_schedule":
        if cd is None:
            how, flags = "a fraction of a non-percentage tariff duty cannot be computed", flags + ["tariff_cd_not_plain"]
        else:
            frac = D(r["rate_fraction_pct"])
            eff = cd * frac / 100
            how = f"{fmt(frac)}% of the prevailing First Schedule rate {fmt(cd)}%"
    else:
        how = f"rate printed as text, not a percentage: '{_short(r['rate_raw'], 120)}'"
        flags.append("rate_not_computable")
    if eff is not None and cd is not None and eff > cd:
        flags.append("concession_rate_higher_than_normal_cd")
    if r["status"] == "needs_review":
        flags.append("row_needs_review")
    issues = [x.strip() for x in (r.get("issues") or "").split(";") if x.strip()]
    for x in issues:
        if x not in flags and x in ("rate_inherited_from_heading_row", "rate_inherited_from_earlier_row_of_same_serial", "code_taken_from_description_text"):
            flags.append(x)
    acd_ok, acd_why = _acd_exempt_under_fifth(excl, r["part"], r["s_no"], r.get("sub_ref"))
    title = " > ".join(x for x in (_short(r["title"], 80), _short(r["group_context"], 80), _short(r["description"], 140)) if x)
    conds = [c for c in (r["conditions"], r["part_conditions_ref"]) if c]
    return {
        "rule_id": f"fifth_schedule_rules:{r['id']}",
        "kind": "FIFTH_SCHEDULE",
        "instrument": FIFTH_INSTRUMENT if r["valid_from"] >= "2026-07-01" else FIFTH_INSTRUMENT_2025,
        "clause": f"Part {r['part']}" + (f" Table {r['table_no']}" if r["table_no"] not in ("main",) else "") + f", S.No {r['s_no']} {r.get('sub_ref') or ''}".rstrip(),
        "description": title,
        "listed_rate": r["rate_raw"],
        "effective_cd_pct": fmt(eff) if eff is not None else None,
        "tariff_cd_pct": fmt(cd) if cd is not None else None,
        "how": how,
        "conditions_the_system_cannot_check": [_short(c, 700) for c in conds],
        "acd_not_levied": acd_ok,
        "acd_note": acd_why,
        "scope": r["scope"],
        "matched_on": r.get("_resolution", r["match_level"]),
        "valid_from": r["valid_from"], "valid_to": r["valid_to"], "source_file": r["source_file"], "page": r["page"],
        "status": r["status"], "flags": flags,
        "_row": r, "_effective": eff,
    }


def fifth_block(conn, c: str, d: str, trow: dict) -> dict:
    """Fifth Schedule options for an 8-digit code on a date (matched by code only)."""
    n_in_store = rows(conn, "SELECT count(*) AS n FROM fifth_schedule_rules")[0]["n"]
    first = rows(conn, "SELECT min(valid_from) AS a, max(valid_to) AS b FROM fifth_schedule_rules")[0]
    out = {"in_store": n_in_store > 0, "valid_from": first["a"], "valid_to": first["b"], "options": [], "not_offered": [], "possible_by_description": [],
           "notes": []}
    if not n_in_store:
        out["notes"].append("Fifth Schedule rows are not in the store.")
        return out
    if not (first["a"] <= d <= first["b"]):
        out["notes"].append(f"The Fifth Schedule versions in the store cover {first['a']} onwards; none is stored for {d}. No Fifth Schedule concession is offered.")
        out["status"] = "not_in_store_for_date"
        return out
    out["status"] = "checked"
    app, exc = collect(conn, "fifth_schedule_rules", c, d)
    excl = fifth_acd_exclusions(conn, d)
    for r in app:
        o = _fifth_option(conn, r, trow, d, excl)
        if r["scope"] == BORDER_MARKET_SCOPE:
            o["not_offered_because"] = "Part VIII applies only to purchases by visitors at Joint Border Sustenance Markets (US$50 per visitor per day), not to commercial imports"
            out["not_offered"].append({k: v for k, v in o.items() if not k.startswith("_")})
            continue
        out["options"].append(o)
    # entries that name the goods only in words (Respective Headings) in Part I: shown for capital-goods chapters, never matched by code
    if c[:2] in CAPITAL_GOODS_CHAPTERS:
        for r in rows(conn, "SELECT * FROM fifth_schedule_rules WHERE part='I' AND match_level='unmapped' AND valid_from <= ? AND valid_to >= ? ORDER BY id", [d, d]):
            out["possible_by_description"].append({
                "rule_id": f"fifth_schedule_rules:{r['id']}", "clause": f"Part I, S.No {r['s_no']} {r.get('sub_ref') or ''}".strip(),
                "title": _short(r["title"], 120), "description": _short(r["description"], 160), "listed_rate": r["rate_raw"],
                "page": r["page"], "source_file": r["source_file"], "status": r["status"]})
        out["notes"].append("Part I entries printed 'Respective Headings' name the goods only in words; they cannot be matched to a code by machine. "
                            "They are listed under possible_by_description for the importer or agent to compare with the description of the goods.")
    return out


# --------------------------------------------------------------------------------------------------- China FTA
def origin_is_china(goods: dict | None) -> bool | None:
    v = (goods or {}).get("origin_country")
    if v is None or str(v).strip() == "":
        return None
    return str(v).strip().lower() in ORIGIN_CN


def fta_effective_rate(rate_pct: Decimal, cd: Decimal | None):
    """SRO 1640(I)/2019 exempts the goods from "so much of the customs duty ... as is in excess of" the listed rate, so the
    importer pays the LOWER of the normal CD and the listed rate (page 1). Returns (rate | None, explanation, flags)."""
    if cd is None:
        return rate_pct, f"listed preferential rate {fmt(rate_pct)}% (the tariff duty is not a plain percentage, so the 'lower of' test was not made)", ["tariff_cd_not_plain"]
    eff = min(cd, rate_pct)
    return eff, (f"lower of the normal CD {fmt(cd)}% and the preferential rate {fmt(rate_pct)}%"), []


def fta_block(conn, c: str, d: str, trow: dict, goods: dict | None) -> dict:
    """China FTA option for an 8-digit code on a date. The rate is offered only as an option (origin and certificate are facts)."""
    have = rows(conn, "SELECT count(*) AS n FROM sqlite_master WHERE type='table' AND name='fta_rules'")[0]["n"]
    out = {"in_store": False, "options": [], "notes": [], "origin": None, "certificate": None}
    if not have:
        out["notes"].append("China FTA rows are not in the store.")
        return out
    n = rows(conn, "SELECT count(*) AS n FROM fta_rules")[0]["n"]
    out["in_store"] = n > 0
    if not n:
        return out
    org = origin_is_china(goods)
    cert = (goods or {}).get("has_certificate_of_origin")
    out["origin"] = org
    out["certificate"] = cert if isinstance(cert, bool) else (str(cert).strip().lower() in ("yes", "y", "true", "1") if cert is not None else None)
    app, exc = collect(conn, "fta_rules", c, d)
    cd = _tariff_cd(trow)
    for r in app:
        eff, how, flags = fta_effective_rate(D(r["rate_pct"]), cd)
        flags = flags + list(r.get("_flags", []))
        if r["status"] == "needs_review":
            flags.append("row_needs_review")
        if eff is not None and cd is not None and eff >= cd:
            flags.append("no_saving_preferential_rate_not_lower_than_normal_cd")
        conds = [r["condition_text"]] if r.get("condition_text") else []
        o = {
            "rule_id": f"fta_rules:{r['id']}", "kind": "CHINA_FTA", "instrument": FTA_INSTRUMENT,
            "clause": f"Table Sr.No {r['sr_no']}, column for {r['calendar_year']} (Year {r['year_no']}, from {r['column_date']})",
            "description": _short(r.get("description_ocr") or "", 140),
            "listed_rate": fmt(D(r["rate_pct"])) + "%", "effective_cd_pct": fmt(eff) if eff is not None else None,
            "tariff_cd_pct": fmt(cd) if cd is not None else None, "how": how,
            "conditions_the_system_cannot_check": [_short(x, 700) for x in conds],
            "acd_not_levied": False, "acd_note": "The FTA reduces customs duty only: RD and ACD stay as in their own SROs; sales tax and income tax bases use the CD actually paid.",
            "scope": "china_fta", "matched_on": r.get("_resolution", r["match_level"]),
            "valid_from": r["valid_from"], "valid_to": r["valid_to"], "source_file": r["source_file"], "page": r["page"],
            "status": r["status"], "flags": flags, "reading": r.get("rate_source"), "category": r.get("category"),
            "_row": r, "_effective": eff,
        }
        out["options"].append(o)
    if not out["options"]:
        out["notes"].append("No SRO 1640(I)/2019 (as substituted by SRO 1181(I)/2022) row for this code on this date (the code may not be in the table substituted by SRO 1181(I)/2022, or its row could not be read).")
        # Neighbouring lines of the same 6-digit family, shown as INFORMATION only. Tested against real assessed duties (importer GD extract, Feb 2026, 1,162 China FTA
        # lines whose code is missing from the table): a single-rate family gave the charged duty on 136 of 182 lines (75%), a multi-rate family on about half,
        # so the rate is never offered or applied; the importer is told to ask the clearing agent.
        fam = rows(conn, "SELECT DISTINCT rate_pct FROM fta_rules WHERE substr(code_norm,1,6)=? AND match_level='code8' AND valid_from <= ? AND valid_to >= ?", [c[:6], d, d])
        if fam:
            rates = sorted({D(x["rate_pct"]) for x in fam})
            out["possible_by_family"] = {"six_digit_family": c[:6], "listed_rates_pct": [fmt(x) for x in rates], "single_rate": len(rates) == 1,
                                         "reliability": "about 75% right when the family has one rate, about 50% when it has several (tested on real assessed duties)",
                                         "note": "NOT offered and NOT applied. Ask your clearing agent for the current preferential rate of this code."}
    return out


def public(o: dict) -> dict:
    return {k: v for k, v in o.items() if not k.startswith("_")}
