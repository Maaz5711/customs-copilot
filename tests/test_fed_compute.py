"""A6: federal excise duty in compute_duty (hand-computed bills) and the 'Respective heading' mapping.

FED file pages: FY2026-27 = 20267171373633512FEDAct2005updatedupto30-06-2026.pdf, FY2025-26 = 202588138517680FEDAct,2005withindexupdatedupto30-06-2025.pdf.
Only the FED / SED lines and the bases are hand-computed here; the CD / ACD / ST / VAT / IT rates are the ones the existing hand cases
(tests/test_tools.py) already checked, and each test re-derives the bases from the tool's own lines with independent Decimal arithmetic.
"""
import csv
import json
from decimal import ROUND_HALF_UP, Decimal as D
from pathlib import Path

import pytest

from src.tools import compute_duty, get_applicable_sros

PROC = Path("data/processed")
IMP = {"registration_status": "registered", "commercial_importer": True, "licensed_oil_marketing_company": False, "active_taxpayer": True}
NEW = {"vehicle_form": "CBU", "used_vehicle_commercial_import_ipo": False}


def r2(x):
    return D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def lines(res):
    return {ln["tax"]: ln for ln in res["lines"]}


def amt(res, tax):
    return D(lines(res)[tax]["amount_pkr"])


def chain_ok(res, V):
    """Independent check of the bases: V_ST = V+CD+RD+ACD+FED+SED (Sales Tax Act s.2(46)(d)); V_IT adds ST and VAT (ITO Part II col. 3)."""
    ln = lines(res)
    got = lambda t: D(ln[t]["amount_pkr"]) if t in ln else D(0)  # noqa: E731
    v_st = D(V) + got("CD") + got("RD") + got("RD_USED_VEHICLE") + got("ACD") + got("FED") + got("SED")
    assert D(ln["ST"]["base_pkr"]) == v_st
    assert D(ln["ST"]["amount_pkr"]) == r2(v_st * D(ln["ST"]["rate"]["pct"]) / 100)
    if "VAT" in ln:
        assert D(ln["VAT"]["base_pkr"]) == v_st
    v_it = v_st + got("ST") + got("VAT")
    assert D(ln["IT"]["base_pkr"]) == v_it
    assert D(ln["IT"]["amount_pkr"]) == r2(v_it * D(ln["IT"]["rate"]["pct"]) / 100)
    tot = sum(D(x["amount_pkr"]) for x in res["lines"])
    assert D(res["totals"]["total_payable_pkr"]) == tot
    assert D(res["totals"]["federal_excise_duty"]) == got("FED") + got("SED")


# ---------------------------------------------------------------- hand case 1: cement, Rs per kg
def test_fed_hand_1_cement_rs4_per_kg():
    # 2523.1000, 2026-07-15, V = 1,000,000, 1000 kg. FED Act FY2026-27 p.72, Table I S.No 13 (2523): "four rupees per kilogram".
    # FED = 4 x 1000 = 4,000. CD 10% = 100,000 (tariff). V_ST = 1,000,000 + 100,000 + 4,000 = 1,104,000 ; ST 18% = 198,720 ; VAT 3% = 33,120
    # V_IT = 1,104,000 + 198,720 + 33,120 = 1,335,840 ; IT 6% = 80,150.40 ; total = 100,000 + 4,000 + 198,720 + 33,120 + 80,150.40 = 415,990.40
    res = compute_duty("2523.1000", 1000000, "2026-07-15", importer=IMP, quantity=1000, quantity_unit="kg")
    assert res["status"] == "computed"
    fed = lines(res)["FED"]
    assert fed["amount_pkr"] == "4000.00" and fed["page"] == 72 and fed["clause"] == "S.No 13"
    assert fed["instrument"] == "Federal Excise Act 2005, First Schedule Table I" and fed["source_file"].startswith("20267171373633512")
    assert fed["rate"] == {"kind": "specific", "amount_pkr": "4", "unit": "kg", "quantity": "1000"}
    assert res["totals"]["total_payable_pkr"] == "415990.40"
    chain_ok(res, 1000000)
    # the quantity is required (no guess)
    res = compute_duty("2523.1000", 1000000, "2026-07-15", importer=IMP)
    assert res["status"] == "needs_input" and "goods.fed_quantity" in {m["field"] for m in res["missing_inputs"]} and res["totals"] is None


# ---------------------------------------------------------------- hand case 2: car by engine band, two fiscal years
def test_fed_hand_2_car_1500cc_fy2026_27_no_table_ia():
    # 8703.2115 CBU 1500 cc, 2026-07-15, V = 2,000,000. CD 30% = 600,000 ; ACD 4% = 80,000 (same slab as hand case 4 in test_tools).
    # FED Table I S.No 55(b) p.75: 1001cc-1799cc 10% ad valorem x (2,000,000 + 600,000 + 80,000) = 10% x 2,680,000 = 268,000 (s.12(3) p.20)
    # Table IA (p.80) starts at 2000 cc: no SED.
    res = compute_duty("8703.2115", 2000000, "2026-07-15", importer=IMP, goods={**NEW, "engine_cc": 1500})
    assert res["status"] == "computed"
    ln = lines(res)
    assert ln["FED"]["amount_pkr"] == "268000.00" and ln["FED"]["base_pkr"] == "2680000.00" and ln["FED"]["clause"] == "S.No 55(b)" and ln["FED"]["page"] == 75
    assert "SED" not in ln and "needs_review" in ln["FED"]["flags"] and res["review_required"]
    chain_ok(res, 2000000)


def test_fed_hand_3_car_2500cc_fy2026_27_with_table_ia_and_open_sed_base():
    # same car, 2500 cc: S.No 55(c) 1800-3000cc 30% x 2,680,000 = 804,000 (p.75). Table IA (a) 2000-3000 cc 86% x 2,680,000 = 2,304,800 (p.80).
    # If the SED base also held the FED (OQ-A6-2): 86% x (2,680,000 + 804,000) = 2,996,240 -> shown in the note, not in the total.
    res = compute_duty("8703.2115", 2000000, "2026-07-15", importer=IMP, goods={**NEW, "engine_cc": 2500})
    ln = lines(res)
    assert ln["FED"]["amount_pkr"] == "804000.00" and ln["SED"]["amount_pkr"] == "2304800.00" and ln["SED"]["page"] == 80
    assert ln["SED"]["clause"] == "S.No 1(a)" and "2996240.00" in ln["SED"]["note"] and "OQ-A6-2" in ln["SED"]["note"]
    assert "SED_BASE" in {a["id"] for a in res["assumptions"]}
    chain_ok(res, 2000000)
    # above 3000 cc: 40% (d) needs cc > 3001 ; use 3500 cc: FED 40% x 2,680,000 = 1,072,000 ; SED 92% x 2,680,000 = 2,465,600
    res = compute_duty("8703.2115", 2000000, "2026-07-15", importer=IMP, goods={**NEW, "engine_cc": 3500})
    assert amt(res, "FED") == D("1072000.00") and amt(res, "SED") == D("2465600.00")
    chain_ok(res, 2000000)


def test_fed_hand_4_car_2500cc_in_fy2025_26_has_no_table_ia():
    # 2025-12-01, 8703.2115 2500 cc, V = 2,000,000. Tariff 2025-26: CD 50% = 1,000,000 ; ACD 6% = 120,000 (SRO 1151 (iv)).
    # FED Table I S.No 55(c) FY2025-26 file p.79: 30% x (2,000,000 + 1,000,000 + 120,000) = 30% x 3,120,000 = 936,000. Table IA does not exist before 1 Jul 2026.
    res = compute_duty("8703.2115", 2000000, "2025-12-01", importer=IMP, goods={**NEW, "engine_cc": 2500})
    ln = lines(res)
    assert ln["FED"]["amount_pkr"] == "936000.00" and ln["FED"]["page"] == 79 and "SED" not in ln
    assert ln["FED"]["valid_from"] == "2025-07-01" and ln["FED"]["valid_to"] == "2026-06-30"
    chain_ok(res, 2000000)


def test_fed_car_without_inputs_or_in_the_3001cc_gap_refuses():
    res = compute_duty("8703.2115", 2000000, "2026-07-15", importer=IMP, goods={"used_vehicle_commercial_import_ipo": False})
    assert res["status"] == "needs_input" and {"goods.vehicle_form", "goods.engine_cc"} <= {m["field"] for m in res["missing_inputs"]} and res["totals"] is None
    # 3001 cc is in no band of S.No 55 ((c) 1800-3000, (d) exceeding 3001): OQ-A6-4, no FED figure, no total
    res = compute_duty("8703.2115", 2000000, "2026-07-15", importer=IMP, goods={**NEW, "engine_cc": 3001})
    assert res["status"] == "cannot_compute" and res["totals"] is None and "FED" not in lines(res)
    assert any(c["item"] == "FED" and "OQ-A6-4" in c["owner_question"] for c in res["cannot_compute"])
    # CKD: not covered by the stored rows
    res = compute_duty("8703.2115", 2000000, "2026-07-15", importer=IMP, goods={"vehicle_form": "CKD", "engine_cc": 1500, "used_vehicle_commercial_import_ipo": False})
    assert res["status"] == "cannot_compute" and res["totals"] is None and "FED" not in lines(res)


def test_fed_double_cabin_pickup_table_i_55c_and_table_ia():
    # 8704.2190, 2026-07-15, V = 3,000,000, 2400 cc CBU. CD 40% = 1,200,000 ; ACD 4% = 120,000 ; base = 4,320,000.
    # Table I S.No 55C p.76: 30% x 4,320,000 = 1,296,000 ; Table IA (a) 2000-3000cc 86% x 4,320,000 = 3,715,200 (p.80)
    res = compute_duty("8704.2190", 3000000, "2026-07-15", importer=IMP, goods={**NEW, "engine_cc": 2400})
    ln = lines(res)
    assert ln["FED"]["clause"] == "S.No 55C" and ln["FED"]["amount_pkr"] == "1296000.00" and ln["SED"]["amount_pkr"] == "3715200.00"
    chain_ok(res, 3000000)


# ---------------------------------------------------------------- hand case 5: cigarettes, higher of two parts (retail price input)
def test_fed_hand_5_cigarettes_higher_of_65pct_retail_and_rs16500_per_1000():
    # 2402.2000, 2026-07-15. FED Table I S.No 8 p.71: 65% of retail price or the rate against S.No 9 (Rs 16,500 per 1000 cigarettes), whichever is higher.
    # 100 thousand sticks, retail price total 3,000,000: 65% x 3,000,000 = 1,950,000 ; 16,500 x 100 = 1,650,000 -> 1,950,000 (percentage part)
    g = {"retail_price_total_pkr": 3000000}
    res = compute_duty("2402.2000", 1000000, "2026-07-15", importer=IMP, goods=g, quantity=100, quantity_unit="1000 cigarettes")
    assert lines(res)["FED"]["amount_pkr"] == "1950000.00" and "percentage part" in lines(res)["FED"]["note"] and "needs_review" in lines(res)["FED"]["flags"]
    # retail price 2,000,000: 65% = 1,300,000 < 1,650,000 -> the specific part
    res = compute_duty("2402.2000", 1000000, "2026-07-15", importer=IMP, goods={"retail_price_total_pkr": 2000000}, quantity=100, quantity_unit="1000 cigarettes")
    assert lines(res)["FED"]["amount_pkr"] == "1650000.00" and "specific part" in lines(res)["FED"]["note"]
    # no retail price: ask, never guess
    res = compute_duty("2402.2000", 1000000, "2026-07-15", importer=IMP, quantity=100, quantity_unit="1000 cigarettes")
    assert res["status"] == "needs_input" and "goods.retail_price_total_pkr" in {m["field"] for m in res["missing_inputs"]}


# ---------------------------------------------------------------- hand case 6: naphtha Rs per liter, date boundary 30 Jun / 1 Jul 2026
def test_fed_hand_6_naphtha_rs80_per_liter_starts_1_july_2026():
    # 2710.1942, V = 1,000,000, 1000 liter. FED S.No 65(i) (new by Finance Act 2026 s.6(14)(1)(g)), FY2026-27 p.78: Rs 80 per liter -> 80 x 1000 = 80,000.
    res = compute_duty("2710.1942", 1000000, "2026-07-01", importer=IMP, quantity=1000, quantity_unit="liter")
    assert res["status"] == "computed" and lines(res)["FED"]["amount_pkr"] == "80000.00" and lines(res)["FED"]["page"] == 78
    assert any(f.startswith("fed_sales_tax_mode") for f in lines(res)["FED"]["flags"])
    chain_ok(res, 1000000)
    # 30 June 2026 (FY2025-26 file): S.No 65 does not exist yet -> no FED line, no quantity asked
    res = compute_duty("2710.1942", 1000000, "2026-06-30", importer=IMP)
    assert res["status"] == "computed" and "FED" not in lines(res)
    chain_ok(res, 1000000)


def test_fed_date_boundary_for_table_ia_30_june_vs_1_july_2026():
    g = {**NEW, "engine_cc": 2500}
    before = compute_duty("8703.2115", 2000000, "2026-06-30", importer=IMP, goods=g)
    after = compute_duty("8703.2115", 2000000, "2026-07-01", importer=IMP, goods=g)
    assert "SED" not in lines(before) and "SED" in lines(after)
    assert lines(before)["FED"]["valid_to"] == "2026-06-30" and lines(after)["FED"]["valid_from"] == "2026-07-01"


# ---------------------------------------------------------------- unmapped / EV: refuse, never guess
def test_fed_electric_vehicle_is_refused_oq_a6_1():
    res = compute_duty("8703.8090", 2000000, "2026-07-15", importer=IMP, goods={**NEW, "engine_cc": 1500})
    assert res["status"] == "cannot_compute" and res["totals"] is None and "FED" not in lines(res) and "SED" not in lines(res)
    assert any(c["item"] == "FED" and "OQ-A6-1" in c["owner_question"] for c in res["cannot_compute"])
    assert any(f.startswith("fed_electric_vehicle_not_computed") for f in res["flags"])


def test_fed_unmapped_serial_is_flagged_not_applied():
    # 5502.9090: S.No 56 'Filter rod for cigarettes' prints 'Respective headings'; ambiguous, left unmapped -> no FED line, a flag and a note
    res = compute_duty("5502.9090", 1000000, "2026-07-15", importer=IMP)
    assert res["status"] == "computed" and "FED" not in lines(res)
    assert any(f.startswith("fed_unmapped_serial_possible") and "S.No 56" in f for f in res["flags"]) and res["review_required"]


def test_fed_third_schedule_exemption_is_listed_never_applied():
    # 2707.9910 carbon black oil: Third Schedule S.No 11 (FY2026-27 p.90) is a conditional exemption
    res = compute_duty("2707.9910", 1000000, "2026-07-15", importer=IMP)
    assert "FED" not in lines(res)
    assert any(p.get("clause") == "S.No 11" and p["instrument"].endswith("Third Schedule Table I") for p in res["possible_rules_not_applied"])
    sr = get_applicable_sros("2707.9910", "2026-07-15")
    assert [r["clause"] for r in sr["fed"]["possible_exemptions"]] == ["S.No 11"] and sr["fed"]["applicable"] == []


def test_get_applicable_sros_lists_fed_rows_and_what_was_excluded():
    sr = get_applicable_sros("8704.2190", "2026-07-15")
    assert [r["clause"] for r in sr["fed"]["applicable"]] == ["S.No 55C", "S.No 1(a)", "S.No 1(b)"]
    ex = [(r["clause"], r["why_not_applied"]) for r in sr["fed"]["excluded"]]
    assert any(c == "S.No 55D" and w.startswith("local_supply_only") for c, w in ex)
    # FY2025-26 rows do not apply on a FY2026-27 date and say so
    sr = get_applicable_sros("2523.1000", "2026-07-15")
    assert [r["clause"] for r in sr["fed"]["applicable"]] == ["S.No 13"]
    assert any(r["why_not_applied"].startswith("not_in_force_on_date") for r in sr["fed"]["excluded"])


# ---------------------------------------------------------------- the mapping of 'Respective heading' rows
def _mapping():
    return list(csv.DictReader(open(PROC / "a6_fed_mapping.csv", encoding="utf-8")))


def test_mapping_csv_covers_all_54_unmapped_rows_with_reasons():
    rules = list(csv.DictReader(open(PROC / "a6_fed_rules.csv", encoding="utf-8")))
    unm = {r["row_id"] for r in rules if r["match_level"] == "unmapped"}
    m = _mapping()
    assert len(unm) == 54 and {r["fed_row_id"] for r in m} == unm
    assert all(r["reason"] and r["confidence"] in ("high", "medium", "none") for r in m)
    mapped = {r["fed_row_id"] for r in m if r["mapped_code"]}
    assert len(mapped) == 16 and len({r["fed_row_id"] for r in m if not r["mapped_code"]}) == 38
    # left unmapped on purpose
    left = {(r["s_no"]) for r in m if not r["mapped_code"] and r["table_no"] == "I"}
    assert left == {"6", "55A", "56", "59"}


def test_mapped_codes_exist_in_the_tariff_of_the_same_year():
    for fy, f in (("FY2025-26", "tariff_2025_26"), ("FY2026-27", "tariff_2026_27")):
        d = json.loads((PROC / f"{f}.json").read_text(encoding="utf-8"))
        lines_ = {r["code"].replace(".", "") for r in d["rows"]}
        heads = {h["heading"].replace(".", "") for h in d["headings"]}
        for r in _mapping():
            if r["fy"] == fy and r["mapped_code"]:
                code = r["mapped_code"].replace(".", "")
                assert code in (lines_ if r["match_level"] == "code8" else heads), (fy, code)


def test_mapped_rows_are_needs_review_with_provenance_and_original_stays_unmapped():
    from src.tools._util import get_conn

    c = get_conn()
    rows = c.execute("SELECT * FROM fed_rules WHERE issues LIKE '%mapped by description match%'").fetchall()
    assert len(rows) == 34 and all(r["status"] == "needs_review" and "owner has not verified" in r["issues"] for r in rows)
    assert all("Respective" in r["heading_raw"] for r in rows)                     # the printed text is kept
    orig = c.execute("SELECT COUNT(*) FROM fed_rules WHERE match_level='unmapped' AND code_norm IS NULL").fetchone()[0]
    assert orig == 54


def test_mapped_goods_get_fed_lines_with_the_mapping_flag():
    # day-old chicks 0105.1100, Rs 10 per DOC (S.No 64, p.78): 1000 DOC = 10,000
    res = compute_duty("0105.1100", 1000000, "2026-07-15", importer=IMP, quantity=1000, quantity_unit="DOC")
    f = lines(res)["FED"]
    assert f["amount_pkr"] == "10000.00" and "fed_row_mapped_by_description_not_owner_verified" in f["flags"] and "FED_MAPPED" in {a["id"] for a in res["assumptions"]}
    chain_ok(res, 1000000)
    # fertilizers 3102.1000: 5% ad valorem on V + CD + RD + ACD = 5% x 1,000,000 (all three are 0 for this code) = 50,000 (S.No 62, p.77)
    res = compute_duty("3102.1000", 1000000, "2026-07-15", importer=IMP)
    assert lines(res)["FED"]["amount_pkr"] == "50000.00" and lines(res)["FED"]["base_pkr"] == "1000000.00"
    # cigars 2402.1000 use S.No 8b (65% of retail or Rs 10,000/kg), not the cigarette row S.No 8: retail 2,000,000 -> 1,300,000 vs 10,000 x 50 kg = 500,000
    res = compute_duty("2402.1000", 1000000, "2026-07-15", importer=IMP, goods={"retail_price_total_pkr": 2000000}, quantity=50, quantity_unit="kg")
    f = lines(res)["FED"]
    assert f["clause"] == "S.No 8b" and f["amount_pkr"] == "1300000.00"
    # fans 8414.5110: only if the fans fail the MEPS (asked); 2000 x 10 fans = 20,000
    res = compute_duty("8414.5110", 1000000, "2026-07-15", importer=IMP, quantity=10, quantity_unit="fan")
    assert "goods.fan_not_meps_compliant" in {m["field"] for m in res["missing_inputs"]}
    res = compute_duty("8414.5110", 1000000, "2026-07-15", importer=IMP, quantity=10, quantity_unit="fan", goods={"fan_not_meps_compliant": True})
    assert lines(res)["FED"]["amount_pkr"] == "20000.00"
    res = compute_duty("8414.5110", 1000000, "2026-07-15", importer=IMP, goods={"fan_not_meps_compliant": False})
    assert "FED" not in lines(res)
