"""compute_duty: itemised import bill (CD, RD, ACD, sales tax, value addition tax, income tax) for a code on a date.

Exact arithmetic with Decimal. Order and bases follow docs/duty_formula.md. All rates are read from the store.
When an input the documents require is missing, the result carries `missing_inputs` and NO total.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from ._util import (
    D, collect, coverage, fmt, get_conn, group_rows, money, norm_code, rule_view, rows, sro_info, to_iso,
)
from .lookup import lookup_code
from .rules import (
    USED_VEHICLE_SROS, Facts, acd_kind, age_rate, income_tax_class, make_acd_prefilter, make_st_prefilter, norm_unit, tier_bounds,
)

HUNDRED = Decimal(100)
ROMAN = {1: "I", 2: "II", 3: "III"}

ORDER = [
    "V = assessable value (Customs Act s.25), given by the caller",
    "CD  = tariff CD rate x V, or specific Rs x quantity (Customs Act s.18(1), Tariff column CD)",
    "RD  = RD SRO rate in force on the date x V; used-vehicle SROs 1898/1065 are separate 'in addition' lines (Customs Act s.18(3)-(4))",
    "ACD = ACD SRO rate (by the code's tariff CD slab) x V (Customs Act s.18(5)-(6))",
    "V_ST = V + CD + RD + ACD  [FED omitted: OPEN-1]  (Sales Tax Act s.2(46)(d)); Third Schedule goods: retail price (s.3(2)(a))",
    "ST  = sales tax rate x V_ST (exemption > Eighth Schedule > SRO 297 Table-I > standard 18%; Sales Tax Act s.3)",
    "VAT = 3% value addition tax at import x V_ST (Sales Tax Act s.7A(2), Twelfth Schedule), unless an exclusion applies",
    "V_IT = V + CD + RD + ACD + ST + VAT; Third Schedule goods: retail price + ST (ITO s.148(9))",
    "IT  = Part II rate for the Twelfth Schedule class x V_IT (ITO s.148, First Schedule Part II)",
    "Total = CD + RD + ACD + ST + VAT + IT  (further tax for unregistered importers is shown separately, OPEN-4)",
]

ASSUME_TEXT = {
    "ROUNDING": "No source document states a rounding rule (OPEN-5). Each line is rounded half-up to 0.01 PKR (or 1 PKR with rounding='rupee') and the rounded amounts feed the next base.",
    "FED": "Federal excise duty is not included in any base (OPEN-1: the Federal Excise Act is not in data/raw). For vehicles and other FED goods the real bill is higher.",
    "OPEN2": "RD and ACD are counted as 'customs-duties' inside the sales tax and income tax bases (inference from Customs Act s.18A, OPEN-2).",
    "OPEN10": "Value addition tax (Sales Tax Act s.7A(2), Twelfth Schedule: 3% ad valorem at import) is taken on the same base as sales tax and counted as sales tax inside the income tax base. The Schedule says only 'ad valorem' (OPEN-10).",
    "OPEN4": "Further tax (s.3(1A), 4%) is written in the Act for supplies to unregistered persons. Whether Customs collects it at import is not in the documents (OPEN-4), so it is shown but not added to the total.",
    "REGIME": "Ordinary commercial import assumed: none of the ACD para 3 'not levied' regimes (Fifth Schedule, Baggage Rules, SROs 577/565/693/492/678 or 655/656) was claimed.",
    "VATFACTS": "No value-addition-tax exclusion that depends on the importer was claimed (manufacturer raw material for in-house use, registered service provider in-house use).",
    "TWELFTH_P3": "Income-tax class Part III (residual) was chosen because no Part I or Part II entry matched the code. Twelfth Schedule entries that name goods only in words cannot be matched by code (OPEN-9).",
    "PROVISOS": "None of the First Schedule Part II provisos (SRO 1125 manufacturers, DRAP-certified pharmaceuticals, EV CKD kits) was claimed.",
    "OPEN3": "More than one sales-tax rate source matched; the documented precedence was applied (OPEN-3).",
}

NOT_APPLIED = [
    "Customs duty exemptions and concessions under the Fifth Schedule, FTA/PTA and other SROs are not in the store; only the tariff CD is applied.",
    "Conditional sales tax exemptions and reduced rates (Sixth, Eighth and Fifth Schedule rows with conditions) are NOT applied unless the caller lists the rule id in claimed_rules; see possible_rules_not_applied.",
    "Schedule entries that name goods only in words (no PCT code) cannot be matched by code and are not checked.",
    "Section 53A ITO (possible 1% reduction of withholding taxes from 1 Jul 2026) is not applied: no notification under it is in data/raw (OQ-A3-7).",
    "Minimum values notified under ITO s.148(6A) and the Customs valuation rulings are not applied: the caller supplies the assessable value.",
]

PHONE_PREFIXES = ("851713", "851714")


class _Bill:
    def __init__(self):
        self.lines, self.optional = [], []
        self.missing, self.cannot = [], []
        self.assumptions: dict[str, str] = {}
        self.flags: list[str] = []
        self.possible: list[dict] = []
        self.notes: list[str] = []

    def need(self, field, question, why, allowed=None, affects=None):
        if any(m["field"] == field for m in self.missing):
            return
        m = {"field": field, "question": question, "why": why}
        if allowed:
            m["allowed"] = allowed
        if affects:
            m["affects"] = affects
        self.missing.append(m)

    def no(self, item, reason, owner=None):
        self.cannot.append({"item": item, "reason": reason, **({"owner_question": owner} if owner else {})})

    def assume(self, key):
        self.assumptions[key] = ASSUME_TEXT[key]

    def flag(self, text):
        if text not in self.flags:
            self.flags.append(text)


def _cite(table, row, kind):
    v = rule_view(table, row, kind)
    return {k: v[k] for k in ("rule_id", "instrument", "clause", "source_file", "page", "valid_from", "valid_to", "status", "rule_group") if k in v}


def _line(bill, tax, label, rate, base_label, base, amount, cite, row=None, assumptions=(), flags=(), included=True, note=None):
    ln = {
        "tax": tax,
        "label": label,
        "rate": rate,
        "base_label": base_label,
        "base_pkr": fmt(base, 2) if base is not None else None,
        "amount_pkr": fmt(amount, 2) if amount is not None else None,
        **cite,
        "assumptions": list(assumptions),
        "flags": list(flags),
        "included_in_total": included,
    }
    if row is not None and row.get("status") == "needs_review":
        ln["flags"].append("needs_review")
        bill.flag(f"needs_review: {cite.get('rule_id')} ({tax})")
    if row is not None:
        ln["flags"].extend(f for f in row.get("_flags", []) if f not in ln["flags"])
    if note:
        ln["note"] = note
    for a in assumptions:
        bill.assume(a)
    (bill.lines if included else bill.optional).append(ln)
    return ln


def _pct(r):
    return D(r["rate_pct"])


def _specific_qty(bill, facts, unit, quantity, quantity_unit, what):
    """Quantity needed for a rupees-per-unit rate. Returns Decimal or None (and records the missing input)."""
    u = norm_unit(unit)
    if u == "minute":
        v = facts.g("running_time_minutes")
        if v is None:
            bill.need("goods.running_time_minutes", f"Running time of the film in minutes ({what} is Rs per minute).", f"{what} is a specific rate per minute.")
            return None
        return D(v)
    if quantity is None or norm_unit(quantity_unit) != u:
        bill.need("quantity", f"Quantity in {unit} (with quantity_unit='{unit}'). {what} is a specific rate per {unit}.",
                  f"{what} is Rs per {unit}; the tools do not convert between units.", affects=["CD", "RD"])
        return None
    return D(quantity)


def _tariff_row(conn, fy, c):
    r = rows(conn, "SELECT * FROM tariff_lines WHERE fy=? AND code_norm=? ORDER BY page", [fy, c])
    return r[0] if r else None


def _no_entry_line(conn, kind, d, table_label, excluded):
    """Citation + note for a 'no rule applies' line: cites the notification in force on the date (where the search was made)."""
    from ._util import sros_of_kind

    ins, _ = sros_of_kind(conn, kind, d)
    i0 = ins[0] if ins else {}
    cite = {"rule_id": None, "instrument": i0.get("sro_number"), "clause": "no entry for this code",
            "source_file": i0.get("source_file"), "page": i0.get("page"),
            "valid_from": i0.get("valid_from"), "valid_to": i0.get("valid_to"), "status": "accepted", "rule_group": None}
    note = f"no row of {table_label} covers this code on {d}"
    ex = [r for r, why in excluded if why.startswith("excluded_by_except")]
    if ex:
        note += "; removed by an 'except' clause: " + ", ".join(f"{r.get('sro_number')} S.No {r.get('s_no') or r.get('clause')}" for r in ex[:5])
    return cite, note


def compute_duty(code, assessable_value_pkr, as_of_date, importer=None, quantity=None, quantity_unit=None,
                 goods=None, claimed_rules=None, rounding="paisa", db_path=None) -> dict:
    """Itemised duty bill. See docs/tools.md for inputs, order of calculation and statuses.

    importer: {'registration_status': 'registered'|'unregistered', 'commercial_importer': bool,
               'manufacturer_in_house_use': bool, 'registered_service_provider_in_house_use': bool,
               'licensed_oil_marketing_company': bool, 'income_tax_category': None|'sro_1125_manufacturer'|'pharma_drap_certified'|'ckd_ev_kit'}
    goods:    {'vehicle_form': 'CKD'|'CBU', 'engine_cc': number, 'used_vehicle_commercial_import_ipo': bool,
               'import_regime': [..], 'plant_machinery_for_manufacturing': bool, 'c_and_f_value_usd_per_unit': number,
               'retail_price_total_pkr': number, 'running_time_minutes': number, 'age_years': number}
    claimed_rules: rule ids (e.g. 'sales_tax_rules:321') whose stated conditions the caller confirms are met.
    """
    try:
        d = to_iso(as_of_date)
        c = norm_code(code)
        V = D(assessable_value_pkr)
        if V <= 0:
            raise ValueError("assessable_value_pkr must be greater than zero")
        if rounding not in ("paisa", "rupee"):
            raise ValueError("rounding must be 'paisa' or 'rupee'")
    except (ValueError, TypeError, InvalidOperation) as e:
        return {"status": "invalid_input", "reason": str(e)}
    conn = get_conn(db_path)
    lo, hi = coverage(conn)
    inputs = {"code": str(code), "assessable_value_pkr": fmt(V, 2), "as_of_date": d, "importer": importer or {}, "goods": goods or {},
              "quantity": quantity, "quantity_unit": quantity_unit, "claimed_rules": list(claimed_rules or [])}
    if not (lo <= d <= hi):
        return {"status": "cannot_compute", "inputs": inputs, "reason": f"date outside the store ({lo} to {hi})"}
    tl = lookup_code(c, d, db_path)
    if tl["status"] != "found":
        return {"status": "not_found" if tl["status"] in ("not_found", "not_a_full_code") else "invalid_input", "inputs": inputs, "lookup": tl}
    if tl["level"] != 8:
        return {"status": "cannot_compute", "inputs": inputs, "lookup": tl,
                "reason": "Chapter 99 entries are conditional import regimes; compute_duty works on eight-digit lines only"}
    fy = tl["fy"]
    trow = _tariff_row(conn, fy, c)
    facts = Facts(importer, goods, claimed_rules)
    bill = _Bill()
    bill.assume("ROUNDING")
    bill.assume("FED")
    R = lambda x: money(x, rounding)  # noqa: E731

    # ---------------- importer status (required: further tax and the documents' registered/unregistered split)
    reg = str(facts.i("registration_status") or "").strip().lower()
    if reg not in ("registered", "unregistered"):
        bill.need("importer.registration_status", "Is the importer registered under the Sales Tax Act 1990 (registered) or not (unregistered)?",
                  "Sales Tax Act s.3(1A): further tax applies to unregistered persons (docs/duty_formula.md step 7).", ["registered", "unregistered"], ["further_tax"])

    # ---------------- CD
    cd_amt = None
    cd_cite = {"rule_id": f"tariff_lines:{trow['id']}", "instrument": f"Pakistan Customs Tariff {fy}", "clause": f"PCT {trow['code']}, column CD",
               "source_file": trow["source_file"], "page": trow["page"], "valid_from": trow["valid_from"], "valid_to": trow["valid_to"],
               "status": trow["status"], "rule_group": "TARIFF"}
    if trow["cd_kind"] == "plain":
        rate = D(trow["cd_rate"])
        cd_amt = R(V * rate / HUNDRED)
        _line(bill, "CD", "Customs duty", {"kind": "percent", "pct": fmt(rate)}, "assessable value", V, cd_amt, cd_cite, trow)
    elif trow["cd_kind"] == "specific":
        q = _specific_qty(bill, facts, trow["cd_specific_unit"], quantity, quantity_unit, "Customs duty")
        if q is not None:
            amt = D(trow["cd_specific_amount"])
            cd_amt = R(amt * q)
            _line(bill, "CD", "Customs duty (specific)", {"kind": "specific", "amount_pkr": fmt(amt), "unit": trow["cd_specific_unit"], "quantity": fmt(q)},
                  f"quantity ({trow['cd_specific_unit']})", q, cd_amt, cd_cite, trow)
    else:
        bill.no("CD", f"the tariff duty cell is compound/unparsed ('{trow['cd_raw']}')", "Read the duty from the tariff page and tell me the rule.")

    # ---------------- RD
    rd_app, rd_exc = collect(conn, "rd_rules", c, d)
    by_group = defaultdict(list)
    for r in rd_app:
        by_group[r["rule_group"]].append(r)
    rd_total = Decimal(0)
    rd_known = True
    main_groups = [g for g in by_group if g not in USED_VEHICLE_SROS]
    if not main_groups:
        cite, note = _no_entry_line(conn, "RD", d, "the RD SRO in force", rd_exc)
        _line(bill, "RD", "Regulatory duty", {"kind": "percent", "pct": "0"}, "assessable value", V, Decimal("0.00"), cite, note=note)
    for g in main_groups:
        rs = by_group[g]
        if len(rs) > 1:
            tiers = [(r, tier_bounds(r["description"])) for r in rs]
            val = facts.g("c_and_f_value_usd_per_unit")
            if any(t is None for _, t in tiers):
                bill.no("RD", f"{len(rs)} rows of {g} cover this code and the tiers cannot be read from their descriptions", "Choose the row by hand.")
                rd_known = False
                continue
            if val is None:
                bill.need("goods.c_and_f_value_usd_per_unit", "C&F value in US dollars per unit (set) of the goods.",
                          f"RD SRO {g} gives a different RD per C&F value tier for this code.", affects=["RD"])
                rd_known = False
                continue
            v = D(val)
            pick = [r for r, (lo_, hi_) in tiers if v > lo_ and (hi_ is None or v <= hi_) or (lo_ == 0 and v == 0)]
            if len(pick) != 1:
                bill.no("RD", f"C&F value {v} USD matched {len(pick)} tiers", "Check the tier by hand.")
                rd_known = False
                continue
            rs = pick
        r = rs[0]
        cite = _cite("rd_rules", r, "RD")
        lab = f"Regulatory duty ({r['sro_number']} S.No {r['s_no']})"
        if r["rate_kind"] == "percent":
            amt = R(V * _pct(r) / HUNDRED)
            _line(bill, "RD", lab, {"kind": "percent", "pct": fmt(_pct(r))}, "assessable value", V, amt, cite, r)
            rd_total += amt
        elif r["rate_kind"] == "specific":
            q = _specific_qty(bill, facts, r["rate_specific_unit"], quantity, quantity_unit, "Regulatory duty")
            if q is None:
                rd_known = False
                continue
            a = D(r["rate_specific_amount"])
            amt = R(a * q)
            _line(bill, "RD", lab + " specific", {"kind": "specific", "amount_pkr": fmt(a), "unit": r["rate_specific_unit"], "quantity": fmt(q)},
                  f"quantity ({r['rate_specific_unit']})", q, amt, cite, r)
            rd_total += amt
        else:  # conditional (age bands)
            age = facts.g("age_years")
            if age is None:
                bill.need("goods.age_years", "Age of the machine in years.", f"RD rate for this code depends on age: {r['rate_raw']}", affects=["RD"])
                rd_known = False
                continue
            pct = age_rate(r["rate_raw"], age)
            if pct is None:
                bill.no("RD", f"age {age} is not covered by the printed bands: {r['rate_raw']}", "Tell me which rate applies for this age.")
                rd_known = False
                continue
            amt = R(V * pct / HUNDRED)
            _line(bill, "RD", lab + " by age", {"kind": "percent", "pct": fmt(pct)}, "assessable value", V, amt, cite, r)
            rd_total += amt
    for g in [g for g in by_group if g in USED_VEHICLE_SROS]:
        r = by_group[g][0]
        used = facts.gb("used_vehicle_commercial_import_ipo")
        if used is None:
            bill.need("goods.used_vehicle_commercial_import_ipo",
                      "Is this a commercial import of a USED vehicle under clause (xvi) of S.No.10, Table of Appendix-C, Import Policy Order 2022? (yes/no)",
                      f"{r['sro_number']} adds RD of {fmt(_pct(r))}% on used vehicles (para 1-2).", [True, False], ["RD"])
            rd_known = False
        elif used:
            amt = R(V * _pct(r) / HUNDRED)
            _line(bill, "RD_USED_VEHICLE", f"Regulatory duty on used vehicles, in addition ({r['sro_number']})", {"kind": "percent", "pct": fmt(_pct(r))},
                  "assessable value", V, amt, _cite("rd_rules", r, "RD"), r)
            rd_total += amt
        else:
            bill.notes.append(f"{r['sro_number']} (used vehicles) not applied: caller says this is not a used-vehicle commercial import.")

    # ---------------- ACD
    need_acd: list[str] = []
    acd_amt = None
    acd_app, acd_exc = collect(conn, "acd_rules", c, d, prefilter=make_acd_prefilter(trow, facts, need_acd))
    levy = [r for r in acd_app if r["rate_kind"] == "percent"]
    exempt = [r for r in acd_app if r["rate_kind"] == "exempt"]
    over = [r for r in levy if acd_kind(r)[0] in ("regime", "ckd_levy")]
    if over:
        levy = over
    levy_positive = any(_pct(r) > 0 for r in levy)
    for f in need_acd:
        if f == "goods.plant_machinery_for_manufacturing" and not levy_positive:
            continue
        label = {"goods.vehicle_form": ("Is the vehicle imported in CKD or CBU condition?", ["CKD", "CBU"]),
                 "goods.engine_cc": ("Engine capacity in cc.", None),
                 "goods.plant_machinery_for_manufacturing": ("Is this plant and machinery used in manufacturing or production of goods? (yes/no)", [True, False])}[f]
        bill.need(f, label[0], "ACD notification para 3: ACD is not levied on such imports (CKD up to 1,000cc, CBU up to 850cc, plant and machinery of Chapters 84/85).", label[1], ["ACD"])
    if exempt:
        r = exempt[0]
        acd_amt = Decimal("0.00")
        _line(bill, "ACD", f"Additional customs duty not levied ({r['sro_number']} para {r['clause']})", {"kind": "exempt"}, "assessable value", V, acd_amt,
              _cite("acd_rules", r, "ACD"), r)
    elif levy:
        pcts = {_pct(r) for r in levy}
        if len(pcts) > 1:
            bill.no("ACD", "rows with different rates match (" + ", ".join(f"{r['sro_number']} {r['clause']}={fmt(_pct(r))}%" for r in levy) + ")", "Choose the clause by hand.")
        else:
            r = levy[0]
            acd_amt = R(V * _pct(r) / HUNDRED)
            _line(bill, "ACD", f"Additional customs duty ({r['sro_number']} {r['clause']})", {"kind": "percent", "pct": fmt(_pct(r))}, "assessable value", V, acd_amt,
                  _cite("acd_rules", r, "ACD"), r, assumptions=("REGIME",))
    else:
        cite, note = _no_entry_line(conn, "ACD", d, "the ACD SRO in force", acd_exc)
        slab = [why for _, why in acd_exc if why.startswith("slab_mismatch")]
        if slab:
            note += f" (tariff CD slab {fmt(D(trow['cd_rate'])) if trow['cd_kind']=='plain' else 'specific'}: no slab clause covers it)"
        acd_amt = Decimal("0.00")
        _line(bill, "ACD", "Additional customs duty", {"kind": "percent", "pct": "0"}, "assessable value", V, acd_amt, cite, note=note, assumptions=("REGIME",))

    # ---------------- sales tax
    st_app, st_exc = collect(conn, "sales_tax_rules", c, d, prefilter=make_st_prefilter(facts))
    for r, why in st_exc:
        if why.startswith("conditional_rule_not_claimed"):
            v = rule_view("sales_tax_rules", r, "ST")
            v["why_not_applied"] = why
            bill.possible.append(v)
    known = cd_amt is not None and rd_known and acd_amt is not None
    st_amt = vat_amt = it_amt = None
    third = [r for r in st_app if r["rule_group"] == "ST-3RD"]
    st_rows_exempt = [r for r in st_app if r["rate_kind"] == "exempt" and r["rule_group"] in ("ST-6TH-T1", "ST-6TH-T3")]
    zero5 = [r for r in st_app if r["rule_group"] == "ST-5TH"]
    eighth = [r for r in st_app if r["rule_group"] == "ST-8TH-T1"]
    s297 = [r for r in st_app if r["rule_group"] == "ST-SRO297-T1"]
    excl12 = [r for r in st_app if r["rule_group"] == "ST-12TH-EXCL"]
    std = group_rows(conn, "sales_tax_rules", "ST-ACT-S3", d)
    third_rate = group_rows(conn, "sales_tax_rules", "ST-ACT-S3-2A", d)

    V_ST = None
    if known:
        V_ST = V + cd_amt + rd_total + acd_amt
    st_decision = None  # (kind, pct, row, extra_assumption)
    if st_rows_exempt:
        st_decision = ("exempt", Decimal(0), st_rows_exempt[0])
    elif zero5:
        st_decision = ("zero", Decimal(0), zero5[0])
    else:
        e_pct = [r for r in eighth if r["rate_kind"] == "percent"]
        if [r for r in eighth if r["rate_kind"] != "percent"]:
            r = [r for r in eighth if r["rate_kind"] != "percent"][0]
            bill.no("sales tax", f"the Eighth Schedule rate for this code is a formula, not a percentage ('{r['rate_raw']}')", "Tell me how to compute this rate (e.g. Rs per MT or 18% whichever is higher).")
        elif e_pct:
            if len({_pct(r) for r in e_pct}) > 1:
                bill.no("sales tax", "Eighth Schedule rows with different rates match this code", "Choose the row by hand.")
            else:
                st_decision = ("percent", _pct(e_pct[0]), e_pct[0])
                if s297:
                    bill.assume("OPEN3")
        elif s297:
            if len({_pct(r) for r in s297}) > 1:
                bill.no("sales tax", "SRO 297 Table-I rows with different rates match this code", "Choose the row by hand.")
            else:
                st_decision = ("percent", _pct(s297[0]), s297[0])
        elif third and third_rate:
            st_decision = ("percent", _pct(third_rate[0]), third_rate[0])
        elif std:
            st_decision = ("percent", _pct(std[0]), std[0])
        else:
            bill.no("sales tax", "no sales tax rate row is valid on this date")
    if c.startswith(PHONE_PREFIXES):
        st_decision = None
        bill.no("sales tax", "mobile phones: sales tax is set by Ninth Schedule Table-II (18% or 25% by C&F value band and CBU/CKD, plus the Twelfth Schedule exclusion). Those rows name no PCT code, so they cannot be matched to this tariff line",
                "Which tariff lines are the Ninth Schedule Table-II columns CBU / CKD-SKD (8517.1310, 8517.1390, 8517.1411, 8517.1419)?")
    if st_decision and st_decision[0] in ("exempt", "zero") and third:
        bill.flag("also_a_Third_Schedule_item: exemption/zero rate applied, so the retail-price basis is not used (check the exemption row)")
        if st_decision[2]["status"] == "needs_review":
            bill.notes.append("The exemption row is needs_review and the code is also in the Third Schedule (retail-price goods): if the exemption row is wrong, sales tax would be charged on the retail price.")
        third = []
    base_st, base_st_label = V_ST, "V + CD + RD + ACD (sales tax value, s.2(46)(d))"
    if third and st_decision and st_decision[0] == "percent":
        rp = facts.g("retail_price_total_pkr")
        if rp is None:
            bill.need("goods.retail_price_total_pkr", "Total retail price printed on the packs of the whole consignment (PKR).",
                      "Third Schedule goods pay sales tax on the retail price (Sales Tax Act s.3(2)(a)).", affects=["sales_tax", "income_tax"])
            base_st = None
        else:
            base_st, base_st_label = D(rp), "retail price (Third Schedule, s.3(2)(a))"
    st_amt = None
    if st_decision and (base_st is not None or st_decision[0] in ("exempt", "zero")):
        kind, pct, r = st_decision
        cite = _cite("sales_tax_rules", r, "ST")
        if kind == "exempt":
            st_amt = Decimal("0.00")
            _line(bill, "ST", "Sales tax exempt", {"kind": "exempt"}, "-", None, st_amt, cite, r, flags=["exemption_applied_from_store_row"])
        elif kind == "zero":
            st_amt = Decimal("0.00")
            _line(bill, "ST", "Sales tax zero-rated (claimed rule)", {"kind": "percent", "pct": "0"}, "-", None, st_amt, cite, r)
        else:
            st_amt = R(base_st * pct / HUNDRED)
            _line(bill, "ST", "Sales tax", {"kind": "percent", "pct": fmt(pct)}, base_st_label, base_st, st_amt, cite, r, assumptions=("OPEN2",) if not third else ())
    # value addition tax (Twelfth Schedule)
    vat_rows = group_rows(conn, "sales_tax_rules", "ST-12TH", d)
    if vat_rows and st_decision and st_decision[0] == "percent" and st_amt is not None:
        excluded_by, ask = None, False
        for r in excl12:
            cl = r["clause"]
            if "(2)(ii)" in cl:
                v = facts.ib("licensed_oil_marketing_company")
                if v is None:
                    bill.need("importer.licensed_oil_marketing_company", "Is the importer a licensed Oil Marketing Company importing petroleum products for sale in the country? (yes/no)",
                              "Value addition tax is not charged on such imports (Sales Tax Act Twelfth Schedule cond. (2)(ii)).", [True, False], ["VAT"])
                    ask = True
                elif v:
                    excluded_by = r
            elif "(2)(x)" in cl:
                v = facts.ib("manufacturer_in_house_use")
                if v is None:
                    bill.need("importer.manufacturer_in_house_use", "Is the importer a manufacturer importing this plant/machinery for in-house installation or use? (yes/no)",
                              "Value addition tax is not charged on such imports (Twelfth Schedule cond. (2)(x)).", [True, False], ["VAT"])
                    ask = True
                elif v:
                    excluded_by = r
            else:
                excluded_by = r  # unconditional code-based exclusion (phones, second-hand clothing)
        if third:
            excluded_by = excluded_by or {"_third": True}
        if not excluded_by and c.startswith("8703") and facts.g("engine_cc") is not None and D(facts.g("engine_cc")) <= 850:
            excluded_by = {"_cc": True}
        if not excluded_by and facts.ib("manufacturer_in_house_use"):
            excluded_by = {"_mfr": True}
        if not excluded_by and facts.ib("registered_service_provider_in_house_use"):
            excluded_by = {"_svc": True}
        if excluded_by:
            reason = {"_third": "goods taxed on retail price under the Third Schedule (cond. (2)(ix))", "_cc": "motor cars up to 850cc (cond. (2)(xiv))",
                      "_mfr": "manufacturer's raw material for in-house use (cond. (2)(i))", "_svc": "registered service provider's in-house use (cond. (2)(iii))"}
            key = next((k for k in reason if k in excluded_by), None)
            why = reason[key] if key else f"{excluded_by['clause']}"
            bill.notes.append(f"Value addition tax not charged: {why}.")
            if not key:
                bill.flag(f"vat_excluded_by: {excluded_by['clause']} [{excluded_by['rule_id'] if 'rule_id' in excluded_by else 'sales_tax_rules:' + str(excluded_by['id'])}]")
        elif not ask:
            r = vat_rows[0]
            vat_amt = R(V_ST * _pct(r) / HUNDRED)
            _line(bill, "VAT", "Value addition tax at import (Twelfth Schedule)", {"kind": "percent", "pct": fmt(_pct(r))},
                  "V + CD + RD + ACD", V_ST, vat_amt, _cite("sales_tax_rules", r, "ST"), r, assumptions=("OPEN10", "VATFACTS"))
    # further tax (unregistered) - shown, not in total
    ft = group_rows(conn, "sales_tax_rules", "ST-ACT-S3-1A", d)
    if reg == "unregistered" and ft and st_decision and st_decision[0] == "percent" and V_ST is not None:
        r = ft[0]
        amt = R(V_ST * _pct(r) / HUNDRED)
        _line(bill, "FURTHER_TAX", "Further tax, unregistered person (s.3(1A)) - NOT in total", {"kind": "percent", "pct": fmt(_pct(r))},
              "V + CD + RD + ACD", V_ST, amt, _cite("sales_tax_rules", r, "ST"), r, assumptions=("OPEN4",), included=False,
              note="The Act text puts this on supplies to unregistered persons; collection at import is unconfirmed (OPEN-4).")
    bill.notes.append("Extra tax (s.3(5)) is a power clause with no rate in the Act; nothing is added.")

    # ---------------- income tax
    it_amt = None
    if c.startswith(PHONE_PREFIXES):
        bill.no("income tax", "mobile phones: the First Schedule Part II mobile table is keyed to PCT 8517.1219/8517.1211, which are not lines of the FY2025-26/2026-27 tariff, so it cannot be matched by code",
                "Which tariff lines does the Part II mobile-phone table (C&F US$ bands) mean after the HS 2022 renumbering?")
    else:
        it_app, _ = collect(conn, "income_tax_rules", c, d)
        cls, cls_row, problem = income_tax_class(it_app)
        if cls == 3:
            bill.assume("TWELFTH_P3")
        elif problem:
            bill.no("income tax", problem, "Which Part applies?")
        if cls and st_amt is not None and known:
            rate_rows = group_rows(conn, "income_tax_rules", f"IT-S148-RATE-P{cls}", d)
            cat = (facts.i("income_tax_category") or "").strip().lower()
            prov_key = {"sro_1125_manufacturer": "manufacturers covered under sro 1125", "pharma_drap_certified": "persons importing finished pharmaceutical",
                        "ckd_ev_kit": "importers of ckd kits"}.get(cat)
            chosen = None
            if prov_key:
                pr = [r for r in group_rows(conn, "income_tax_rules", "IT-S148-RATE-PROVISO", d) if prov_key in (r["importer_category"] or "").lower()]
                chosen = pr[0] if pr else None
                if not chosen:
                    bill.no("income tax", f"income_tax_category '{cat}' is not recognised", None)
            else:
                bill.assume("PROVISOS")
                comm = facts.ib("commercial_importer")
                if cls >= 2 and comm is None:
                    bill.need("importer.commercial_importer", "Is the importer a commercial importer (imports for sale in the same condition)? (yes/no)",
                              "First Schedule Part II: Part II goods 2% or 3.5% for a commercial importer; Part III 5.5% or 6% (docs/duty_formula.md OPEN-7).", [True, False], ["income_tax"])
                else:
                    want = "commercial importer" if (cls >= 2 and comm) else "persons (any importer)"
                    pr = [r for r in rate_rows if r["importer_category"] == want]
                    chosen = pr[0] if pr else None
                    if not chosen:
                        bill.no("income tax", f"no First Schedule Part II rate row '{want}' for Part {cls} on {d}")
            if chosen is not None:
                third_goods = bool(third)
                if third_goods:
                    rp = facts.g("retail_price_total_pkr")
                    base_it = None if rp is None else D(rp) + st_amt
                    base_it_label = "retail price + sales tax (ITO s.148(9)(a))"
                else:
                    base_it = V + cd_amt + rd_total + acd_amt + st_amt + (vat_amt or Decimal(0))
                    base_it_label = "V + CD + RD + ACD + ST + VAT (ITO First Schedule Part II col. 3, s.148(9)(b))"
                if base_it is not None:
                    pct = _pct(chosen)
                    it_amt = R(base_it * pct / HUNDRED)
                    cite = _cite("income_tax_rules", chosen, "IT")
                    _line(bill, "IT", f"Income tax at import, s.148 (Twelfth Schedule Part {ROMAN[cls]})", {"kind": "percent", "pct": fmt(pct)}, base_it_label, base_it, it_amt, cite, chosen,
                          assumptions=("OPEN2", "OPEN10") if not third_goods else (), note=f"Class Part {ROMAN[cls]}: " + (cls_row["clause"] if cls_row else "residual (no Part I/II entry)"))
        bill.notes.append("Income tax at import is a minimum tax on the importer's income (ITO s.148(7)); it is not shown as adjustable here.")

    if c.startswith(("8702", "8703", "8704", "8711")):
        bill.flag("FED_not_included: federal excise duty may apply to vehicles (Salient Features 2026-27; Federal Excise Act not in data/raw, OPEN-1)")
    if c.startswith("1701"):
        bill.flag("sugar_notifications_not_applied: SRO 1215/1217/1832/527/663 (sugar) name no PCT code; the reduced sugar rates are stored needs_review and are NOT applied. Ask Maaz (OQ-A3-3).")
    if c.startswith(PHONE_PREFIXES):
        bill.flag("mobile_phone: sales tax and income tax special tables are not matched by code; see cannot_compute")

    # ---------------- result
    status = "computed"
    have = {ln["tax"] for ln in bill.lines}
    if not bill.cannot and not bill.missing and not {"CD", "RD", "ACD", "ST", "IT"} <= have:
        bill.no("internal", f"a required line is missing ({sorted({'CD', 'RD', 'ACD', 'ST', 'IT'} - have)}) without a stated reason; no total is given")
    if bill.cannot:
        status = "cannot_compute"
    if bill.missing:
        status = "needs_input"
    res = {
        "status": status,
        "code": tl["code"],
        "description": tl["description"],
        "fy": fy,
        "as_of_date": d,
        "inputs": inputs,
        "lines": bill.lines,
        "optional_lines_not_in_total": bill.optional,
        "missing_inputs": bill.missing,
        "cannot_compute": bill.cannot,
        "assumptions": [{"id": k, "text": v} for k, v in bill.assumptions.items()],
        "flags": bill.flags,
        "review_required": bool(bill.flags) or bool(bill.assumptions.keys() - {"ROUNDING", "FED"}),
        "possible_rules_not_applied": bill.possible,
        "notes": bill.notes,
        "not_applied": NOT_APPLIED,
        "order_of_calculation": ORDER,
        "rounding": {"mode": rounding, "rule": ASSUME_TEXT["ROUNDING"]},
    }
    if status == "computed":
        tot = {k: Decimal(0) for k in ("customs_duties", "sales_tax", "income_tax")}
        for ln in bill.lines:
            a = D(ln["amount_pkr"])
            if ln["tax"] in ("CD", "RD", "RD_USED_VEHICLE", "ACD"):
                tot["customs_duties"] += a
            elif ln["tax"] in ("ST", "VAT"):
                tot["sales_tax"] += a
            elif ln["tax"] == "IT":
                tot["income_tax"] += a
        total = sum(tot.values())
        res["totals"] = {**{k: fmt(v, 2) for k, v in tot.items()}, "total_payable_pkr": fmt(total, 2)}
        if bill.optional:
            ft_total = sum((D(x["amount_pkr"]) for x in bill.optional), Decimal(0))
            res["totals"]["total_if_open_items_apply_pkr"] = fmt(total + ft_total, 2)
            res["totals"]["open_items"] = [x["tax"] for x in bill.optional]
    else:
        res["totals"] = None
        res["partial_total_of_computed_lines_pkr"] = fmt(sum((D(ln["amount_pkr"]) for ln in bill.lines), Decimal(0)), 2)
    return res
