"""Federal excise duty (FED) at import: rows of the Federal Excise Act 2005 First Schedule from the dated store `fed_rules`.

Spec: docs/a6_fed_findings.md section 6; order and bases: docs/duty_formula.md section 7. Exact Decimal arithmetic, no LLM.
Rules this module follows:
* Only Table I and Table IA rows that can be charged on an import (applies_to import_only / import_and_local) are applied.
  Rows for locally made goods are listed as excluded. Third Schedule exemptions are NEVER applied; they are listed as possible.
* Rows printed with 'Respective heading(s)' match a code only through the description-match mapping (a6_fed_mapping.csv,
  status needs_review, owner has not verified). Unmapped rows never match.
* Electric vehicles (OQ-A6-1) and engine capacity 3001 cc (OQ-A6-4) are refused, not guessed. The base of the Special Excise
  Duty (OQ-A6-2) is a flagged assumption with the alternative amount shown.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from ._util import D, collect, fmt

HUNDRED = Decimal(100)
EV_PREFIXES = ("870380",)          # HS 2022 8703.80 'Other vehicles, with only electric motor for propulsion' (S.No 55 EV words, 55A, Table IA)
MAPPED_MARK = "mapped by description match"

# Goods that might match a Table I serial printed without a code and NOT mapped (ambiguous): the tool cannot match them, so it tells the caller.
# code prefix -> serial numbers (Table I) to mention
UNMAPPED_WATCH = {"2009": ["59"], "2106": ["59"], "2201": ["6", "59"], "2202": ["6", "59"],
                  "5502": ["56"], "5601": ["56"], "2403": ["56"], "2402": ["56"]}

_UNIT_ALIASES = {"litre": "liter", "litres": "liter", "liters": "liter", "ltr": "liter", "l": "liter", "kgs": "kg", "kilogram": "kg",
                 "kilograms": "kg", "docs": "doc", "fans": "fan"}


def fed_unit(u) -> str:
    u = " ".join(str(u or "").strip().lower().replace("³", "3").split())
    return _UNIT_ALIASES.get(u, u)


def fed_instrument(r) -> str:
    return f"Federal Excise Act 2005, {r['schedule']} Schedule Table {r['table_no'].replace('Third-', '')}"


def fed_clause(r) -> str:
    return f"S.No {r['s_no']}{r.get('sub') or ''}"


def fed_cite(r) -> dict:
    return {"rule_id": f"fed_rules:{r['id']}", "instrument": fed_instrument(r), "clause": fed_clause(r), "source_file": r["source_file"],
            "page": r["page"], "valid_from": r["valid_from"], "valid_to": r["valid_to"], "status": r["status"], "rule_group": r["rule_group"]}


def fed_rate(r) -> dict:
    k = r["rate_kind"]
    out = {"kind": k, "raw": r.get("rate_raw")}
    if k in ("percent", "compound"):
        out["pct"] = fmt(D(r["rate_pct"]))
        out["basis"] = r.get("rate_basis")
    if k in ("specific", "compound"):
        out["amount_pkr"] = fmt(D(r["rate_specific_amount"]))
        out["unit"] = r["rate_specific_unit"]
    if k == "compound":
        out["rule"] = r.get("compound_rule")
    return out


def fed_view(r, why=None) -> dict:
    v = {**fed_cite(r), "kind": "FED", "rate": fed_rate(r), "condition": r.get("condition_text"), "description": r["description"],
         "sub_description": r.get("sub_desc"), "applies_to": r["applies_to"], "matched_on": r.get("_resolution") or r["match_level"],
         "code_norm": r["code_norm"], "flags": list(r.get("_flags", []))}
    if MAPPED_MARK in (r.get("issues") or ""):
        v["flags"].append("fed_row_mapped_by_description_not_owner_verified")
    if r.get("issues"):
        v["issues"] = r["issues"]
    if why:
        v["why_not_applied"] = why
    return v


def fed_rows(conn, code8: str, d: str):
    """(applicable Table I/IA import rows, local-only rows, Third Schedule rows, excluded [(row, why)]) for an 8-digit code on a date."""
    app, exc = collect(conn, "fed_rules", code8, d)
    first, local, third = [], [], []
    for r in app:
        if r["schedule"] == "Third":
            third.append(r)
        elif r["applies_to"] == "local_only":
            local.append(r)
        else:
            first.append(r)
    return first, local, third, exc


def _in_band(r, cc: Decimal) -> bool:
    if r.get("cc_ge") is not None and cc < D(r["cc_ge"]):
        return False
    if r.get("cc_gt") is not None and cc <= D(r["cc_gt"]):
        return False
    if r.get("cc_le") is not None and cc > D(r["cc_le"]):
        return False
    return True


def _has_band(r) -> bool:
    return any(r.get(k) is not None for k in ("cc_ge", "cc_gt", "cc_le"))


def _qty(bill, facts, unit, quantity, quantity_unit, what):
    """Quantity in the unit the FED rate is printed in. Uses goods.fed_quantity, or `quantity` when its unit is the same."""
    u = fed_unit(unit)
    fq = facts.g("fed_quantity")
    if fq is not None:
        try:
            v = D(fq)
            if v > 0:
                return v
        except (InvalidOperation, ValueError):
            pass
    if quantity is not None and quantity_unit and fed_unit(quantity_unit) == u:
        try:
            v = D(quantity)
            if v > 0:
                return v
        except (InvalidOperation, ValueError):
            pass
    bill.need("goods.fed_quantity", f"Quantity of the goods in {unit} (the unit the federal excise duty rate is printed in).",
              f"{what} is a specific rate per {unit}; the tools do not convert between units.", affects=["FED"])
    return None


def _retail(bill, facts, what):
    rp = facts.g("retail_price_total_pkr")
    try:
        v = D(rp) if rp is not None else None
    except (InvalidOperation, ValueError):
        v = None
    if v is None or v <= 0:
        bill.need("goods.retail_price_total_pkr", "Total retail price printed on the packs of the whole consignment (PKR).",
                  f"{what} is charged on the retail price printed on the pack (FED Act s.12(4) and proviso).", affects=["FED"])
        return None
    return v


def apply_fed(conn, c, d, base, facts, bill, quantity, quantity_unit, R, line) -> dict:
    """Add FED / SED lines to `bill`. Returns {'fed': Decimal, 'sed': Decimal, 'ok': bool}.

    base = V + CD + RD + ACD (None when one of those could not be computed). `line` is compute._line.
    ok is False when a FED line could not be computed (missing input or refusal): the caller then gives no total.
    """
    first, local, third, exc = fed_rows(conn, c, d)
    out = {"fed": Decimal(0), "sed": Decimal(0), "ok": True}
    # ---- exemptions: listed, never applied
    for r in third:
        bill.possible.append(fed_view(r, "third_schedule_exemption_conditional: never applied automatically (importer, project or purpose decides)"))
    if third:
        bill.flag("fed_third_schedule_exemption_possible: " + ", ".join(sorted({"S.No " + r["s_no"] for r in third})) + " (not applied)")
    # ---- electric vehicles: refuse (OQ-A6-1)
    if c.startswith(EV_PREFIXES):
        bill.no("FED", "electric vehicle (HS 8703.80): the Federal Excise Act names electric vehicles in S.No 55 (until 30 June 2027), in S.No 55A (new, USD value bands, "
                       "printed 'Respective Heading') and in Table IA; it does not say which applies or whether they add up. No FED figure is guessed",
                "OQ-A6-1: for an imported electric car, which of S.No 55, S.No 55A and Table IA is charged, and are they charged together? (FED Act, FY2026-27 file pp.74-75 and p.80)")
        bill.flag("fed_electric_vehicle_not_computed: OQ-A6-1")
        out["ok"] = False
        return out
    # ---- goods that might match a serial printed without a code (not mapped): tell the caller
    watch = sorted({s for pre, ss in UNMAPPED_WATCH.items() if c.startswith(pre) for s in ss})
    if watch:
        miss = conn.execute("SELECT s_no, description, page FROM fed_rules WHERE match_level='unmapped' AND schedule='First' AND table_no='I' "
                            "AND valid_from<=? AND valid_to>=? AND s_no IN (%s) ORDER BY s_no" % ",".join("?" * len(watch)), [d, d, *watch]).fetchall()
        if miss:
            txt = "; ".join(f"S.No {m[0]} '{m[1][:70]}' (FED Act p.{m[2]})" for m in miss)
            bill.flag("fed_unmapped_serial_possible: " + txt + " - printed without a tariff code, so it is not matched automatically; check the goods against it")
            bill.notes.append("FED serials printed with 'Respective heading(s)' that were NOT mapped to codes (ambiguous) may apply to these goods: " + txt + ".")
    for r in local:
        bill.notes.append(f"FED row {fed_instrument(r)} {fed_clause(r)} not applied: it is for locally made goods (applies_to local_only).")
    if not first:
        return out
    groups: dict[tuple, list] = defaultdict(list)
    for r in first:
        groups[(r["table_no"], r["s_no"])].append(r)
    t1 = [k for k in groups if k[0] == "I"]
    if len(t1) > 1:
        bill.no("FED", "several First Schedule Table I serials match this code (" + ", ".join("S.No " + k[1] for k in t1) + "); the tool cannot tell whether they add up",
                "Which serial applies, or do they add up?")
        out["ok"] = False
        return out
    is_vehicle = c.startswith("87")
    if is_vehicle:
        form, _cc = facts.vehicle()
        if form is None:
            bill.need("goods.vehicle_form", "Is the vehicle imported in CKD or CBU condition?",
                      "FED Table I S.No 55 / 55C and Table IA are printed for imported (CBU) vehicles; CKD kits are not covered by the stored rows.", ["CKD", "CBU"], ["FED"])
            out["ok"] = False
        elif form == "CKD":
            bill.no("FED", "CKD condition: FED Table I S.No 55 / 55C and Table IA name 'imported motor cars ... double cabin pick-up vehicles'; the stored rows do not say how a CKD kit is charged",
                    "How is FED charged on CKD kits of vehicles at import?")
            bill.notes.append("CKD vehicle: no FED line is given, so the sales tax and income tax lines below do NOT include FED; there is no total.")
            return out
    for key in sorted(groups, key=lambda k: (k[0] != "I", k[1])):
        rows_ = groups[key]
        table, s_no = key
        sed = table == "IA"
        tax = "SED" if sed else "FED"
        # ----- choose the row inside the serial
        if any(r.get("usd_gt") is not None or r.get("usd_le") is not None for r in rows_):
            bill.no(tax, f"S.No {s_no} has value (USD) bands; the tool does not apply them (OQ-A6-1)", "OQ-A6-1")
            out["ok"] = False
            continue
        if any(_has_band(r) for r in rows_):
            _, cc = facts.vehicle()
            if cc is None:
                bill.need("goods.engine_cc", "Engine capacity in cc.", f"FED {fed_instrument(rows_[0])} S.No {s_no} is charged by engine-capacity band.", None, ["FED"])
                out["ok"] = False
                continue
            fits = [r for r in rows_ if _in_band(r, cc)]
            if len(fits) > 1:
                bill.no(tax, f"S.No {s_no}: {len(fits)} engine-capacity bands fit {cc} cc", "Choose the band by hand.")
                out["ok"] = False
                continue
            if not fits:
                if sed:
                    bill.notes.append(f"Table IA (Special Excise Duty): no band covers {fmt(cc)} cc (the bands start at 2000 cc), so no SED is charged (FED Act FY2026-27 p.80).")
                    continue
                bill.no(tax, f"engine capacity {fmt(cc)} cc falls in no band of S.No {s_no}: the Act prints '1800cc to 3000cc' and 'exceeding 3001cc', so 3001 cc "
                             "(and anything between 3000 and 3001) is in neither band",
                        "OQ-A6-4: which rate applies to an engine capacity of 3001 cc? (FED Act S.No 55(c) and (d), FY2026-27 p.75; FY2025-26 p.79)")
                out["ok"] = False
                continue
            row = fits[0]
        else:
            if len(rows_) > 1:
                bill.no(tax, f"S.No {s_no}: {len(rows_)} rows match this code and no band decides between them", "Choose the row by hand.")
                out["ok"] = False
                continue
            row = rows_[0]
        if is_vehicle and not out["ok"] and any(m["field"] == "goods.vehicle_form" for m in bill.missing):
            continue                                              # vehicle form still unknown: ask first, compute after
        # ----- serial-specific conditions printed in the description
        if table == "I" and s_no == "60":
            v = facts.gb("fan_not_meps_compliant")
            if v is None:
                bill.need("goods.fan_not_meps_compliant", "Do these fans fail the minimum energy performance standard (MEPS) notified by PSQCA? (yes/no)",
                          "FED S.No 60 is charged only on energy-inefficient fans that do not comply with the MEPS.", [True, False], ["FED"])
                out["ok"] = False
                continue
            if not v:
                bill.notes.append("FED S.No 60 not applied: the caller says the fans comply with the MEPS.")
                continue
        row = dict(row)
        row["_flags"] = [f for f in row.get("_flags", []) if not f.startswith("multiple_rows_same_specificity")]   # the band / serial choice above settled it
        cite = fed_cite(row)
        mapped = MAPPED_MARK in (row.get("issues") or "")
        ass = ["FED_DATE"] + (["FED_MAPPED"] if mapped else []) + (["SED_BASE"] if sed else [])
        flags = ["fed_row_mapped_by_description_not_owner_verified"] if mapped else []
        if "not charged" in (row.get("condition_text") or "").lower():
            bill.possible.append(fed_view(row, "proviso printed under the serial: conditions not checked, never applied automatically"))
        if table == "I" and s_no == "65":
            flags.append("fed_sales_tax_mode: Second Schedule S.No 5 (FED collected as if sales tax); no adjustment is claimed here")
        kind = row["rate_kind"]
        label = f"{'Special excise duty' if sed else 'Federal excise duty'} (Table {table} S.No {s_no}{row.get('sub') or ''})"
        amt = None
        if kind == "percent" and row["rate_basis"] == "ad_valorem":
            if base is None:
                out["ok"] = False
                continue
            pct = D(row["rate_pct"])
            amt = R(base * pct / HUNDRED)
            note = None
            if sed:
                alt = R((base + out["fed"]) * pct / HUNDRED)
                note = (f"Base of the Special Excise Duty is open (OQ-A6-2): used V + CD + RD + ACD. If the base also includes the Table I FED, "
                        f"the amount would be PKR {fmt(alt, 2)}. The Board may prescribe the mode of collection (s.3(3B) proviso; no notification in data/raw, OQ-A6-5).")
            line(bill, tax, label, {"kind": "percent", "pct": fmt(pct)}, "V + CD + RD + ACD (FED Act s.12(3))", base, amt, cite, row, assumptions=ass, flags=flags, note=note)
        elif kind == "percent":                                     # retail price
            rp = _retail(bill, facts, label)
            if rp is None:
                out["ok"] = False
                continue
            pct = D(row["rate_pct"])
            amt = R(rp * pct / HUNDRED)
            line(bill, tax, label, {"kind": "percent", "pct": fmt(pct)}, "retail price (FED Act s.12(4))", rp, amt, cite, row, assumptions=ass + ["FED_RETAIL"], flags=flags)
        elif kind == "specific":
            q = _qty(bill, facts, row["rate_specific_unit"], quantity, quantity_unit, label)
            if q is None:
                out["ok"] = False
                continue
            a = D(row["rate_specific_amount"])
            amt = R(a * q)
            line(bill, tax, label, {"kind": "specific", "amount_pkr": fmt(a), "unit": row["rate_specific_unit"], "quantity": fmt(q)},
                 f"quantity ({row['rate_specific_unit']})", q, amt, cite, row, assumptions=ass, flags=flags)
        elif kind == "compound":
            rp = _retail(bill, facts, label) if row["rate_basis"] == "retail_price" else base
            q = _qty(bill, facts, row["rate_specific_unit"], quantity, quantity_unit, label)
            if rp is None or q is None:
                out["ok"] = False
                continue
            pct, a = D(row["rate_pct"]), D(row["rate_specific_amount"])
            p_amt, s_amt = R(rp * pct / HUNDRED), R(a * q)
            amt = max(p_amt, s_amt)
            note = (f"higher of {fmt(pct)}% x {fmt(rp, 2)} = {fmt(p_amt, 2)} and Rs {fmt(a)} x {fmt(q)} {row['rate_specific_unit']} = {fmt(s_amt, 2)}; "
                    f"{'the percentage part' if p_amt >= s_amt else 'the specific part'} is taken")
            line(bill, tax, label, {"kind": "compound", "pct": fmt(pct), "amount_pkr": fmt(a), "unit": row["rate_specific_unit"], "quantity": fmt(q), "rule": "higher_of"},
                 "retail price vs quantity", rp, amt, cite, row, assumptions=ass + (["FED_RETAIL"] if row["rate_basis"] == "retail_price" else []), flags=flags, note=note)
        else:
            bill.no(tax, f"S.No {s_no}: rate kind '{kind}' is not computed", None)
            out["ok"] = False
            continue
        out["sed" if sed else "fed"] += amt
    return out


def fed_block(conn, c, d) -> dict:
    """The `fed` block of get_applicable_sros: rows that apply, the ones excluded and why, and the Third Schedule exemptions."""
    first, local, third, exc = fed_rows(conn, c, d)
    excluded = [fed_view(r, f"local_supply_only_not_an_import_rule (applies_to {r['applies_to']})") for r in local]
    for r, why in sorted(exc, key=lambda x: x[1].startswith("not_in_force_on_date")):
        excluded.append(fed_view(r, why))
    watch = sorted({s for pre, ss in UNMAPPED_WATCH.items() if c.startswith(pre) for s in ss})
    notes = []
    if c.startswith(EV_PREFIXES):
        notes.append("electric vehicle: S.No 55 (EV words), S.No 55A (unmapped) and Table IA overlap; compute_duty refuses (OQ-A6-1)")
    if watch:
        notes.append("FED serial(s) " + ", ".join(watch) + " are printed without a tariff code and not mapped (ambiguous); check the goods against them")
    return {"applicable": [fed_view(r) for r in first], "possible_exemptions": [fed_view(r, "third_schedule_exemption_conditional: never applied automatically") for r in third],
            "excluded": excluded[:60], "excluded_total": len(excluded), "notes": notes}
