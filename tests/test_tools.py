"""B3: exact tools (lookup_code, get_applicable_sros, compute_duty) and the MCP server.

HAND CASES. Every expected number below was worked out by hand from the source documents BEFORE it was compared with the
tools. The arithmetic is written in the comments, the clause and page are cited next to each rate. The rates are read from:
  * Tariff PDFs (text layer):         20268251181330180Tariff-2026-27.pdf, 20258111683941732Tariff-2025-26.pdf
  * RD SRO page images:               SRO 1064(I)/2026, SRO 1152(I)/2025, SRO 1065(I)/2026 p.1, SRO 1898(I)/2025 p.1
  * ACD SRO page images:              SRO 1063(I)/2026 p.1-2, SRO 1151(I)/2025 p.1
  * Sales Tax Act (30.06.2026 file):  s.3(1) p.28 (18%), s.3(2)(a) p.29, Eighth Schedule S.No 77 p.210, Twelfth Schedule p.225-226 (3%)
  * SRO 297(I)/2023 p.1 (Table-I S.No 3: CBU vehicles 25%)
  * Income Tax Ordinance (30.06.2026 file): First Schedule Part II p.551-552 (1% / 2% / 3.5% commercial / 5.5% / 6% commercial),
    Twelfth Schedule p.811-832 (Part I p.811-815, Part II p.815-832, Part III residual p.832)
Rounding convention (no document states one, OPEN-5): each line rounded half-up to 0.01 PKR; rounded amounts feed the next base.

One hand case disagreed with the tool at first: vehicle 8703.2113. I had assumed 18% sales tax; the tool applied 25%.
Cause: my hand case forgot SRO 297(I)/2023 Table-I S.No 3 (p.1), which lists 8703.2113 under "Vehicles in CBU condition" at 25%.
The tool was right; the hand case below now includes it.
"""
import asyncio
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from src.store.build import build
from src.tools import compute_duty, get_applicable_sros, lookup_code

PROC = Path("data/processed")
pytestmark = pytest.mark.skipif(not (PROC / "a3_acd_rules.csv").exists(), reason="processed data not present")

D = Decimal
IMP = {"registration_status": "registered", "commercial_importer": True, "manufacturer_in_house_use": False, "active_taxpayer": True}


@pytest.fixture(scope="module", autouse=True)
def store(tmp_path_factory):
    path = tmp_path_factory.mktemp("tools") / "store.sqlite"
    build(path)
    import os

    old = os.environ.get("CUSTOMS_DB")
    os.environ["CUSTOMS_DB"] = str(path)
    yield path
    if old is None:
        os.environ.pop("CUSTOMS_DB", None)
    else:
        os.environ["CUSTOMS_DB"] = old


def pct(base, rate):
    """Independent arithmetic used in the hand cases: base x rate / 100, half-up to 0.01."""
    return (D(base) * D(rate) / 100).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def amounts(res):
    return {ln["tax"]: ln["amount_pkr"] for ln in res["lines"]}


def check(res, expected, total):
    assert res["status"] == "computed", res.get("missing_inputs") or res.get("cannot_compute")
    assert amounts(res) == expected
    assert res["totals"]["total_payable_pkr"] == total
    assert sum(D(v) for v in expected.values()) == D(total)  # the hand arithmetic itself adds up


# ===================================================================== hand cases
def test_hand_1_plain_cd_only_item_class_III():
    # 6005.4400 (knitted fabric, printed), 2026-07-15, V = 1,000,000. Tariff 2026-27 p.153: CD 10.
    # RD: no entry in SRO 1064 (no 60.05 / 6005.4400 row). ACD: tariff slab 10% is not a slab of SRO 1063 (20%, 25%+) and the code is
    # in none of its lists (p.1-2) -> 0.
    # CD  = 10% x 1,000,000                           = 100,000.00
    # V_ST = 1,000,000 + 100,000                      = 1,100,000.00      (Sales Tax Act s.2(46)(d))
    # ST  = 18% x 1,100,000                           = 198,000.00        (s.3(1) p.28)
    # VAT = 3% x 1,100,000                            =  33,000.00        (Twelfth Schedule p.225)
    # IT: not in Twelfth Schedule Part I/II (p.811-832) -> Part III, commercial importer 6% (First Schedule Part II S.No 3, p.552)
    # V_IT = 1,100,000 + 198,000 + 33,000             = 1,331,000.00 ; IT = 6% x 1,331,000 = 79,860.00
    # total = 100,000 + 198,000 + 33,000 + 79,860     = 410,860.00
    res = compute_duty("6005.4400", 1000000, "2026-07-15", importer=IMP)
    check(res, {"CD": "100000.00", "RD": "0.00", "ACD": "0.00", "ST": "198000.00", "VAT": "33000.00", "IT": "79860.00"}, "410860.00")
    assert pct(1100000, 18) == D("198000.00") and pct(1331000, 6) == D("79860.00")
    cd = res["lines"][0]
    assert (cd["source_file"], cd["page"]) == ("20268251181330180Tariff-2026-27.pdf", 153)


def test_hand_2_item_with_rd():
    # 9506.9911 (football cover), 2026-07-15, V = 500,000. Tariff 2026-27 p.323: CD 10.
    # RD: SRO 1064(I)/2026 S.No 673, heading 95.06 "except PCT code 9506.9100", rate 20.0 (p.28) -> 20%.
    # ACD: CD slab 10% -> none.
    # CD = 50,000.00 ; RD = 20% x 500,000 = 100,000.00 (on V, not on V+CD: Customs Act s.18(3))
    # V_ST = 500,000 + 50,000 + 100,000 = 650,000 ; ST = 18% = 117,000.00 ; VAT = 3% = 19,500.00
    # V_IT = 650,000 + 117,000 + 19,500 = 786,500 ; IT = 6% (Part III, commercial) = 47,190.00
    # total = 50,000 + 100,000 + 117,000 + 19,500 + 47,190 = 333,690.00
    res = compute_duty("9506.9911", 500000, "2026-07-15", importer=IMP)
    check(res, {"CD": "50000.00", "RD": "100000.00", "ACD": "0.00", "ST": "117000.00", "VAT": "19500.00", "IT": "47190.00"}, "333690.00")
    rd = [ln for ln in res["lines"] if ln["tax"] == "RD"][0]
    assert rd["instrument"] == "1064(I)/2026" and rd["page"] == 28


def test_hand_3_acd_slab_20_percent_and_25_plus():
    # 6704.2000 (human hair articles), 2026-07-15, V = 800,000. Tariff p.166: CD 20 -> slab 20%.
    # SRO 1063(I)/2026 p.1 clause (i)(a): "two per cent on goods falling under tariff slab of twenty per cent" (code not in the
    # 4% list nor in the (b) list) -> ACD 2%. RD: no entry.
    # CD = 20% x 800,000 = 160,000.00 ; ACD = 2% x 800,000 = 16,000.00
    # V_ST = 800,000 + 160,000 + 16,000 = 976,000 ; ST = 18% = 175,680.00 ; VAT = 3% = 29,280.00
    # V_IT = 976,000 + 175,680 + 29,280 = 1,180,960 ; IT = 6% = 70,857.60
    # total = 160,000 + 16,000 + 175,680 + 29,280 + 70,857.60 = 451,817.60
    res = compute_duty("6704.2000", 800000, "2026-07-15", importer=IMP)
    check(res, {"CD": "160000.00", "RD": "0.00", "ACD": "16000.00", "ST": "175680.00", "VAT": "29280.00", "IT": "70857.60"}, "451817.60")
    acd = [ln for ln in res["lines"] if ln["tax"] == "ACD"][0]
    assert acd["instrument"] == "1063(I)/2026" and acd["clause"].startswith("(i)(a)")

    # 8708.9210 (silencers), V = 1,000,000. Tariff p.289: CD 25 -> "twenty-five per cent and higher slabs": 4% (SRO 1063 p.1 clause (ii)).
    # CD = 250,000 ; ACD = 4% x 1,000,000 = 40,000 ; V_ST = 1,290,000 ; ST = 232,200 ; VAT = 38,700
    # V_IT = 1,290,000 + 232,200 + 38,700 = 1,560,900 ; IT = 6% = 93,654.00
    # total = 250,000 + 40,000 + 232,200 + 38,700 + 93,654 = 654,554.00
    res = compute_duty("8708.9210", 1000000, "2026-07-15", importer=IMP)
    check(res, {"CD": "250000.00", "RD": "0.00", "ACD": "40000.00", "ST": "232200.00", "VAT": "38700.00", "IT": "93654.00"}, "654554.00")


def test_hand_4_used_vehicle_sro_1065_with_sro_297_25_percent():
    # 8703.2113 (mini vans, CBU), 2026-07-15, V = 2,000,000, used vehicle, commercial import under IPO cl.(xvi), CBU 1300 cc.
    # Tariff 2026-27 p.265: CD 30. RD main SRO 1064: no row for 8703.2113. SRO 1065(I)/2026 p.1: 30% on used vehicles, "in addition to"
    # the RD of SRO 1064 (para 2) -> a separate line.
    # ACD: slab 30% is in "25% and higher" -> 4% (SRO 1063 p.1 (ii)); 3(x) does not apply (CBU, 1300 cc > 850 cc).
    # CD = 30% x 2,000,000 = 600,000 ; RD(1065) = 30% x 2,000,000 = 600,000 ; ACD = 4% x 2,000,000 = 80,000
    # FED (added in A6): Federal Excise Act First Schedule Table I S.No 55(b), FY2026-27 file p.75: imported cars 1001cc to 1799cc = 10% ad valorem
    #   on the value incl. customs duties (s.12(3) p.20): 10% x (2,000,000 + 600,000 + 600,000 + 80,000) = 10% x 3,280,000 = 328,000. 1300 cc < 2000 cc: no Table IA.
    # V_ST = 3,280,000 + 328,000 = 3,608,000
    # ST = 25% (SRO 297(I)/2023 Table-I S.No 3 p.1 lists 8703.2113 "Vehicles in CBU condition") x 3,608,000 = 902,000
    # VAT = 3% x 3,608,000 = 108,240 (cond. (2)(xiv) excludes only motor cars up to 850 cc)
    # V_IT = 3,608,000 + 902,000 + 108,240 = 4,618,240 ; IT = 6% (Part III: only CKD *components* of 87.03 are in Part II) = 277,094.40
    # total = 600,000 + 600,000 + 80,000 + 328,000 + 902,000 + 108,240 + 277,094.40 = 2,895,334.40
    goods = {"vehicle_form": "CBU", "engine_cc": 1300, "used_vehicle_commercial_import_ipo": True}
    res = compute_duty("8703.2113", 2000000, "2026-07-15", importer=IMP, goods=goods)
    check(res, {"CD": "600000.00", "RD": "0.00", "RD_USED_VEHICLE": "600000.00", "ACD": "80000.00", "FED": "328000.00", "ST": "902000.00", "VAT": "108240.00", "IT": "277094.40"}, "2895334.40")
    used = [ln for ln in res["lines"] if ln["tax"] == "RD_USED_VEHICLE"][0]
    assert used["instrument"] == "1065(I)/2026" and used["page"] == 1
    assert "needs_review" in used["flags"]                      # 1065 prints no effective-date clause (OQ-A3-4)
    # changed expectation (A6): the old test asserted the flag "FED_not_included"; this vehicle now carries FED (S.No 55(b)), so the flag is gone
    assert not any(f.startswith("FED_not_included") for f in res["flags"]) and "FED" in amounts(res)


def test_hand_5_fy2025_26_date_used_vehicle_sro_1898():
    # Same code, date 2025-11-01 (FY2025-26), V = 2,000,000. Tariff 2025-26 p.265: CD 50. SRO 1898(I)/2025 p.1: 40% used vehicles
    # (from 1 Oct 2025), in addition to SRO 1152. SRO 1152: no row for 8703.2113.
    # ACD: SRO 1151(I)/2025 p.1 clause (iv): six percent on slab 30% and higher -> 6%.
    # CD = 1,000,000 ; RD(1898) = 800,000 ; ACD = 6% x 2,000,000 = 120,000
    # FED (A6): Table I S.No 55(b), FY2025-26 file p.79: 1001-1799cc = 10% x (2,000,000 + 1,000,000 + 800,000 + 120,000) = 10% x 3,920,000 = 392,000
    # V_ST = 3,920,000 + 392,000 = 4,312,000 ; ST = 25% (SRO 297 Table-I S.No 3) = 1,078,000 ; VAT = 3% = 129,360
    # V_IT = 4,312,000 + 1,078,000 + 129,360 = 5,519,360 ; IT = 6% = 331,161.60
    # total = 1,000,000 + 800,000 + 120,000 + 392,000 + 1,078,000 + 129,360 + 331,161.60 = 3,850,521.60
    goods = {"vehicle_form": "CBU", "engine_cc": 1300, "used_vehicle_commercial_import_ipo": True}
    res = compute_duty("8703.2113", 2000000, "2025-11-01", importer=IMP, goods=goods)
    check(res, {"CD": "1000000.00", "RD": "0.00", "RD_USED_VEHICLE": "800000.00", "ACD": "120000.00", "FED": "392000.00", "ST": "1078000.00", "VAT": "129360.00", "IT": "331161.60"}, "3850521.60")
    assert res["fy"] == "FY2025-26"
    assert [ln for ln in res["lines"] if ln["tax"] == "RD_USED_VEHICLE"][0]["instrument"] == "1898(I)/2025"


def test_hand_6_specific_duty_and_rounding():
    # 1507.1000 (crude soya-bean oil), 2026-07-15, V = 1,000,000, quantity 2 MT. Tariff 2026-27 p.30 prints "Rs. 105 50/ MT" = Rs.10550/MT.
    # RD none. ACD: SRO 1063 p.2 (ii)(b)(i) lists 1507.1000 at two percent -> 2%.
    # CD = 10,550 x 2 = 21,100.00 ; ACD = 2% x 1,000,000 = 20,000.00
    # V_ST = 1,000,000 + 21,100 + 20,000 = 1,041,100 ; ST = 18% = 187,398.00 ; VAT = 3% = 31,233.00
    # Income tax: heading 15.07 is in Twelfth Schedule Part II (p.816; Part II starts p.815) -> commercial importer 3.5% (p.551-552)
    # V_IT = 1,041,100 + 187,398 + 31,233 = 1,259,731 ; IT = 3.5% x 1,259,731 = 44,090.585 -> 44,090.59 (half-up to the paisa)
    # total = 21,100 + 20,000 + 187,398 + 31,233 + 44,090.59 = 303,821.59
    res = compute_duty("1507.1000", 1000000, "2026-07-15", importer=IMP, quantity=2, quantity_unit="MT")
    check(res, {"CD": "21100.00", "RD": "0.00", "ACD": "20000.00", "ST": "187398.00", "VAT": "31233.00", "IT": "44090.59"}, "303821.59")
    cd = res["lines"][0]
    assert cd["rate"] == {"kind": "specific", "amount_pkr": "10550", "unit": "MT", "quantity": "2"}
    assert "needs_review" in cd["flags"]   # rotated cell, amount reassembled from wrapped text (A1)
    # rupee rounding: IT 44,090.585 -> 44,091 ; the other lines are whole rupees already
    r2 = compute_duty("1507.1000", 1000000, "2026-07-15", importer=IMP, quantity=2, quantity_unit="MT", rounding="rupee")
    assert amounts(r2)["IT"] == "44091.00" and r2["totals"]["total_payable_pkr"] == "303822.00"
    # a specific duty without its quantity is not guessed
    r3 = compute_duty("1507.1000", 1000000, "2026-07-15", importer=IMP)
    assert r3["status"] == "needs_input" and r3["totals"] is None
    assert [m["field"] for m in r3["missing_inputs"]] == ["quantity"]


def test_hand_7_sales_tax_reduced_rate_laptop():
    # 8471.3010 (laptops), 2026-07-15, V = 1,000,000. Tariff p.233: CD 0. RD none; ACD none (CD 0).
    # Sales Tax Act Eighth Schedule S.No 77 "Imported personal computers and laptop computers" 8471.3020 and 8471.3010: 10% (p.210).
    # (s.3(2)(a) p.29: Eighth Schedule rate replaces the 18% for goods also in the Third Schedule; reduced rate beats the standard rate)
    # ST = 10% x 1,000,000 = 100,000 ; VAT = 3% x 1,000,000 = 30,000 (a laptop is not "plant and machinery"; caller says no)
    # IT: 84.71 not in Twelfth Schedule Part I/II -> Part III 6% x (1,000,000 + 100,000 + 30,000 = 1,130,000) = 67,800
    # total = 100,000 + 30,000 + 67,800 = 197,800
    res = compute_duty("8471.3010", 1000000, "2026-07-15", importer=IMP)
    check(res, {"CD": "0.00", "RD": "0.00", "ACD": "0.00", "ST": "100000.00", "VAT": "30000.00", "IT": "67800.00"}, "197800.00")
    st = [ln for ln in res["lines"] if ln["tax"] == "ST"][0]
    assert st["page"] == 210 and "Eighth Schedule" in st["instrument"]
    # chapter 84: the VAT exclusion for manufacturers' plant and machinery needs an answer
    r2 = compute_duty("8471.3010", 1000000, "2026-07-15", importer={"registration_status": "registered", "commercial_importer": True, "active_taxpayer": True})
    assert r2["status"] == "needs_input"
    assert [m["field"] for m in r2["missing_inputs"]] == ["importer.manufacturer_in_house_use"]


def test_hand_8_unregistered_further_tax_is_added_at_the_standard_rate():
    # Same goods as hand case 1 (6005.4400) but an UNREGISTERED importer. Further tax s.3(1A) (p.28): "four percent of the value" for supplies to unregistered persons.
    # CHANGED 2026-10-16: real assessed Goods Declarations (importer extract, Chapter 85, Feb 2026, docs/gd_findings.md) show Customs collecting the 3% value addition tax plus this
    # 4% (7% of V_ST in total) at import and putting it into the income-tax base, on lines taxed at the standard 18%. So at 18% it is now added.
    # further tax = 4% x V_ST (1,100,000) = 44,000 ; V_IT = 1,100,000 + ST 198,000 + VAT 33,000 + further tax 44,000 = 1,375,000 ; IT 6% = 82,500
    # total = 100,000 + 198,000 + 33,000 + 44,000 + 82,500 = 457,500
    imp = {**IMP, "registration_status": "unregistered"}
    res = compute_duty("6005.4400", 1000000, "2026-07-15", importer=imp)
    check(res, {"CD": "100000.00", "RD": "0.00", "ACD": "0.00", "ST": "198000.00", "VAT": "33000.00", "FURTHER_TAX": "44000.00", "IT": "82500.00"}, "457500.00")
    assert res["optional_lines_not_in_total"] == []
    ft = next(ln for ln in res["lines"] if ln["tax"] == "FURTHER_TAX")
    assert ft["included_in_total"] is True and "OPEN4" in {a["id"] for a in res["assumptions"]}
    reg = compute_duty("6005.4400", 1000000, "2026-07-15", importer=IMP)
    assert reg["optional_lines_not_in_total"] == [] and "FURTHER_TAX" not in amounts(reg)


def test_hand_9_income_tax_classes_I_II_III():
    # Class I: 8445.3000 (textile doubling machines). Heading 84.45 is in Twelfth Schedule Part I (p.813; Part I = p.811-815) -> 1% (p.551).
    # CD 0 (p.225), no RD/ACD. ST = 18% x 1,000,000 = 180,000 ; VAT = 30,000 (caller: not a manufacturer's in-house use)
    # V_IT = 1,000,000 + 180,000 + 30,000 = 1,210,000 ; IT = 1% = 12,100 ; total = 222,100
    res = compute_duty("8445.3000", 1000000, "2026-07-15", importer=IMP)
    check(res, {"CD": "0.00", "RD": "0.00", "ACD": "0.00", "ST": "180000.00", "VAT": "30000.00", "IT": "12100.00"}, "222100.00")
    assert "Part I)" in [ln for ln in res["lines"] if ln["tax"] == "IT"][0]["label"]
    # Class II: 7208.3910 (flat-rolled steel). Heading 72.08 is in Part II (p.827). CD 0 (p.180). 2026-27: no RD row in SRO 1064.
    # Same ST/VAT; V_IT = 1,210,000. Commercial importer: 3.5% = 42,350 ; total 252,350.   Non-commercial: 2% = 24,200 ; total 234,200.
    res = compute_duty("7208.3910", 1000000, "2026-07-15", importer=IMP)
    check(res, {"CD": "0.00", "RD": "0.00", "ACD": "0.00", "ST": "180000.00", "VAT": "30000.00", "IT": "42350.00"}, "252350.00")
    res = compute_duty("7208.3910", 1000000, "2026-07-15", importer={**IMP, "commercial_importer": False})
    check(res, {"CD": "0.00", "RD": "0.00", "ACD": "0.00", "ST": "180000.00", "VAT": "30000.00", "IT": "24200.00"}, "234200.00")
    # Class III: hand case 1 (6% commercial) ; non-commercial Part III = 5.5% x 1,331,000 = 73,205 -> total 404,205
    res = compute_duty("6005.4400", 1000000, "2026-07-15", importer={**IMP, "commercial_importer": False})
    check(res, {"CD": "100000.00", "RD": "0.00", "ACD": "0.00", "ST": "198000.00", "VAT": "33000.00", "IT": "73205.00"}, "404205.00")
    # Part I does not depend on commercial status: not asked
    r = compute_duty("8445.3000", 1000000, "2026-07-15", importer={"registration_status": "registered", "manufacturer_in_house_use": False, "active_taxpayer": True})
    assert r["status"] == "computed"
    # Part II/III need it
    r = compute_duty("6005.4400", 1000000, "2026-07-15", importer={"registration_status": "registered", "active_taxpayer": True})
    assert r["status"] == "needs_input" and r["missing_inputs"][0]["field"] == "importer.commercial_importer"


def test_hand_10_date_boundary_30_june_vs_1_july_2026():
    # 6109.1000 (T-shirts), V = 1,000,000. Tariff 2025-26 p.156 and 2026-27 p.156: CD 20 on both sides.
    # 2026-06-30 (last day of SRO 1152 and 1151): RD 10 (SRO 1152 S.No 287, heading 61.09, p.17) ; ACD 4 (SRO 1151 p.1 (ii): slab 20%)
    #   CD 200,000 ; RD 100,000 ; ACD 40,000 ; V_ST = 1,340,000 ; ST 241,200 ; VAT 40,200
    #   V_IT = 1,340,000 + 241,200 + 40,200 = 1,621,400 ; IT 6% = 97,284 ; total 718,684
    # 2026-07-01 (first day of SRO 1064 and 1063): RD 8.0 (SRO 1064 S.No 290, p.14) ; ACD 2 (SRO 1063 p.1 (i)(a))
    #   CD 200,000 ; RD 80,000 ; ACD 20,000 ; V_ST = 1,300,000 ; ST 234,000 ; VAT 39,000
    #   V_IT = 1,300,000 + 234,000 + 39,000 = 1,573,000 ; IT 6% = 94,380 ; total 667,380
    before = compute_duty("6109.1000", 1000000, "2026-06-30", importer=IMP)
    after = compute_duty("6109.1000", 1000000, "2026-07-01", importer=IMP)
    check(before, {"CD": "200000.00", "RD": "100000.00", "ACD": "40000.00", "ST": "241200.00", "VAT": "40200.00", "IT": "97284.00"}, "718684.00")
    check(after, {"CD": "200000.00", "RD": "80000.00", "ACD": "20000.00", "ST": "234000.00", "VAT": "39000.00", "IT": "94380.00"}, "667380.00")
    assert before["fy"] == "FY2025-26" and after["fy"] == "FY2026-27"
    by = {ln["tax"]: ln for ln in before["lines"]}
    af = {ln["tax"]: ln for ln in after["lines"]}
    assert by["RD"]["instrument"] == "1152(I)/2025" and by["RD"]["page"] == 17
    assert af["RD"]["instrument"] == "1064(I)/2026" and af["RD"]["page"] == 14
    assert by["ACD"]["instrument"] == "1151(I)/2025" and af["ACD"]["instrument"] == "1063(I)/2026"


# ===================================================================== other behaviour
def test_every_line_has_a_citation_and_money_is_strings():
    res = compute_duty("9506.9911", 500000, "2026-07-15", importer=IMP)
    for ln in res["lines"]:
        assert ln["source_file"] and isinstance(ln["page"], int) and ln["instrument"] and ln["clause"]
        assert isinstance(ln["amount_pkr"], str)
    json.dumps(res)  # JSON-able, no Decimal / float money


def test_missing_inputs_are_a_list_not_a_number():
    res = compute_duty("8703.2113", 1000000, "2026-07-15", importer={"registration_status": "registered", "commercial_importer": True, "active_taxpayer": True})
    assert res["status"] == "needs_input" and res["totals"] is None
    assert {m["field"] for m in res["missing_inputs"]} == {"goods.used_vehicle_commercial_import_ipo", "goods.vehicle_form", "goods.engine_cc"}
    # no importer at all
    res = compute_duty("6005.4400", 1000000, "2026-07-15")
    assert res["status"] == "needs_input"
    assert {m["field"] for m in res["missing_inputs"]} == {"importer.registration_status", "importer.commercial_importer"}
    # film running time (RD Rs 2,400 per minute, SRO 1064 S.No 687 heading 37.06) and meters (tariff CD in Rs per meter)
    res = compute_duty("3706.1000", 1000000, "2026-07-15", importer=IMP)
    assert "goods.running_time_minutes" in {m["field"] for m in res["missing_inputs"]}


def test_ckd_cbu_engine_rules_for_acd_vehicle_clause():
    # SRO 1063 para 3(x): ACD not levied on CBU up to 850 cc -> line is 0 and cites 3(x)
    goods = {"vehicle_form": "CBU", "engine_cc": 800, "used_vehicle_commercial_import_ipo": False}
    res = compute_duty("8703.2113", 1000000, "2026-07-15", importer=IMP, goods=goods)
    acd = [ln for ln in res["lines"] if ln["tax"] == "ACD"][0]
    assert acd["amount_pkr"] == "0.00" and acd["clause"] == "3(x)"
    assert "RD_USED_VEHICLE" not in amounts(res)
    # CKD above 1000 cc: 2% (para 1 (ii)(b)(ii)), needs_review (the SRO prints vehicle classes, not PCT codes: OQ-A3-1)
    goods = {"vehicle_form": "CKD", "engine_cc": 1500, "used_vehicle_commercial_import_ipo": False}
    res = compute_duty("8703.2113", 1000000, "2026-07-15", importer=IMP, goods=goods)
    acd = [ln for ln in res["lines"] if ln["tax"] == "ACD"][0]
    assert acd["amount_pkr"] == "20000.00" and "needs_review" in acd["flags"]


def test_unconfirmed_and_unmatchable_things_are_not_computed():
    # Chapter 99 conditional entry
    assert compute_duty("9908", 1000000, "2026-07-15", importer=IMP)["status"] == "cannot_compute"
    # mobile phones: Ninth Schedule and the First Schedule mobile table are not matchable by code
    res = compute_duty("8517.1390", 1000000, "2026-07-15", importer=IMP, quantity=10, quantity_unit="set",
                       goods={"c_and_f_value_usd_per_unit": 150, "plant_machinery_for_manufacturing": False})
    assert res["status"] == "cannot_compute" and res["totals"] is None
    assert {c["item"] for c in res["cannot_compute"]} == {"sales tax", "income tax"}
    # RD C&F tier chosen by value: 8517.1390, SRO 1064 S.No 552 "above US$ 100 but not exceeding US$ 200 per set" Rs 6,000/set -> 10 sets = 60,000
    assert amounts(res)["RD"] == "60000.00"
    # date outside the store
    assert compute_duty("6109.1000", 1000000, "2028-01-01", importer=IMP)["status"] == "cannot_compute"
    assert compute_duty("6109.1000", -1, "2026-07-15", importer=IMP)["status"] == "invalid_input"


def test_age_banded_rd():
    # SRO 1152 S.No 511 (8433.5100): "10% (5 to 10 years old) and 20% (Above 10 years old)", FY2025-26
    res = compute_duty("8433.5100", 1000000, "2025-08-15", importer=IMP, goods={"age_years": 7, "plant_machinery_for_manufacturing": False})
    assert amounts(res)["RD"] == "100000.00"
    res = compute_duty("8433.5100", 1000000, "2025-08-15", importer=IMP, goods={"age_years": 12, "plant_machinery_for_manufacturing": False})
    assert amounts(res)["RD"] == "200000.00"
    res = compute_duty("8433.5100", 1000000, "2025-08-15", importer=IMP, goods={"age_years": 2, "plant_machinery_for_manufacturing": False})
    assert res["status"] == "cannot_compute"


# ===================================================================== lookup_code
def test_lookup_code_found_and_dated():
    r = lookup_code("8471.3010", "2026-07-15")
    assert r["status"] == "found" and r["code"] == "8471.3010" and r["fy"] == "FY2026-27"
    assert r["cd"]["rate_pct"] == "0" and r["page"] == 233 and r["heading"]["code"] == "84.71"
    r2 = lookup_code("84713010", "2026-06-30")  # undotted, other fiscal year
    assert r2["fy"] == "FY2025-26" and r2["source_file"].startswith("20258111683941732")
    r3 = lookup_code("8703.2113", "2025-11-01")
    assert r3["cd"]["rate_pct"] == "50"
    assert lookup_code("8703.2113", "2026-07-01")["cd"]["rate_pct"] == "30"


def test_lookup_code_specific_and_not_found():
    r = lookup_code("1507.1000", "2026-07-15")
    assert r["cd"]["kind"] == "specific" and r["cd"]["amount_pkr"] == "10550" and r["cd"]["unit"] == "MT"
    assert "tariff_row_needs_review" in r["flags"]
    nf = lookup_code("0101.2199", "2026-07-15")
    assert nf["status"] == "not_found" and len(nf["nearest_codes"]) == 5 and nf["nearest_codes"][0]["code"].startswith("0101")
    assert lookup_code("8703", "2026-07-15")["status"] == "not_a_full_code"
    assert lookup_code("12345", "2026-07-15")["status"] == "invalid_input"
    assert lookup_code("8471.3010", "2030-01-01")["status"] == "date_outside_store"


# ===================================================================== get_applicable_sros
def test_get_applicable_sros_dates_and_exclusions():
    a = get_applicable_sros("6109.1000", "2026-06-30")
    b = get_applicable_sros("6109.1000", "2026-07-01")
    assert [v["instrument"] for v in a["rd"]["applicable"]] == ["1152(I)/2025"]
    assert [v["instrument"] for v in b["rd"]["applicable"]] == ["1064(I)/2026"]
    assert any(v["instrument"] == "1064(I)/2026" and v["excluded_because"].startswith("not_in_force_on_date") for v in a["rd"]["excluded"])
    assert any(v["instrument"] == "1152(I)/2025" and v["excluded_because"].startswith("not_in_force_on_date") for v in b["rd"]["excluded"])
    # ACD slab test: a 20% code does not take the 25%+ clause
    acd_ex = [v for v in b["acd"]["excluded"] if v["clause"] == "(ii)" and v["instrument"] == "1063(I)/2026"]
    assert acd_ex and acd_ex[0]["excluded_because"].startswith("slab_mismatch")
    for blk in ("rd", "acd", "sales_tax", "income_tax"):
        for v in b[blk]["applicable"]:
            assert v["source_file"] and v["page"] and v["rule_id"]


def test_get_applicable_sros_except_list_and_local_supply_rule():
    # 0203.1100 is in the 4% exception list of 1063(I)/2026 (i)(a) (p.1) and so is not charged the general 2% of the 20% slab
    r = get_applicable_sros("0203.1100", "2026-07-01")
    pct_rows = [(v["clause"], v["rate"]["pct"]) for v in r["acd"]["applicable"] if v["rate"]["kind"] == "percent" and v["rule_group"] == "1063(I)/2026"]
    assert pct_rows == [("(i)(a) except-list", "4")]
    assert any(v["clause"] == "(i)(a)" and v["excluded_because"].startswith("excluded_by_except_clause") for v in r["acd"]["excluded"])
    # SRO 297 Table-II (locally made vehicles) is not an import rule even after 13 Sep 2026
    v = get_applicable_sros("8703.2113", "2026-09-20")
    assert any("locally made" in x["excluded_because"] for x in v["sales_tax"]["excluded"])
    assert not any(x["rule_group"].startswith("ST-SRO297-T2") for x in v["sales_tax"]["applicable"])
    assert [x["rate"]["pct"] for x in v["sales_tax"]["applicable"] if x["rule_group"] == "ST-SRO297-T1"] == ["25"]
    # used-vehicle RD: 1898 until 29 Jun 2026, 1065 from 30 Jun 2026, both needs_review
    assert [x["instrument"] for x in get_applicable_sros("8703.2113", "2026-06-29")["rd"]["applicable"]] == ["1898(I)/2025"]
    assert [x["instrument"] for x in get_applicable_sros("8703.2113", "2026-06-30")["rd"]["applicable"]] == ["1065(I)/2026"]
    assert get_applicable_sros("8703.2113", "2026-06-30")["rd"]["applicable"][0]["status"] == "needs_review"
    assert get_applicable_sros("9999.9999", "2026-07-15")["status"] == "not_found"


# ===================================================================== MCP server (stdio)
def test_mcp_server_lists_and_calls_the_three_tools(store):
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "src.tools.mcp_server"], cwd=str(Path.cwd()),
                                       env={**os.environ, "CUSTOMS_DB": str(store)})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = {t.name for t in (await s.list_tools()).tools}
                res = await s.call_tool("compute_duty", {"code": "6005.4400", "assessable_value_pkr": "1000000", "as_of_date": "2026-07-15", "importer": IMP})
                look = await s.call_tool("lookup_code", {"code": "8471.3010", "as_of_date": "2026-07-15"})
                sro = await s.call_tool("get_applicable_sros", {"code": "6109.1000", "as_of_date": "2026-07-01"})
                return names, json.loads(res.content[0].text), json.loads(look.content[0].text), json.loads(sro.content[0].text)

    names, bill, look, sro = asyncio.run(go())
    assert names == {"lookup_code", "get_applicable_sros", "compute_duty"}
    assert bill["totals"]["total_payable_pkr"] == "410860.00"
    assert look["status"] == "found" and sro["rd"]["applicable"][0]["instrument"] == "1064(I)/2026"


# ===================================================================== non-filer income tax (ITO Tenth Schedule rule 1)
def test_hand_11_non_filer_income_tax_is_doubled_and_cited():
    # 6109.1000, V = 1,000,000, 2026-07-15, same as hand case 10 (after): V_IT = 1,573,000.
    # Filer (on the Active Taxpayers' List): IT 6% = 94,380 (First Schedule Part II: commercial importer, Twelfth Schedule Part III).
    # Not on the list: ITO Tenth Schedule rule 1 raises the collected rate by 100% -> 12% x 1,573,000 = 188,760. FBR WHT rate card TY2027 prints 6% / 12%.
    # Total: 667,380 - 94,380 + 188,760 = 761,760.
    non_filer = compute_duty("6109.1000", 1000000, "2026-07-15", importer={**IMP, "active_taxpayer": False})
    check(non_filer, {"CD": "200000.00", "RD": "80000.00", "ACD": "20000.00", "ST": "234000.00", "VAT": "39000.00", "IT": "188760.00"}, "761760.00")
    it = next(ln for ln in non_filer["lines"] if ln["tax"] == "IT")
    assert it["rate"]["pct"] == "12" and "NOT on the Active Taxpayers List" in it["note"]
    assert it["atl_rule"]["page"] == 798 and "Tenth Schedule rule 1" in it["atl_rule"]["clause"]
    filer = compute_duty("6109.1000", 1000000, "2026-07-15", importer={**IMP, "active_taxpayer": True})
    assert amounts(filer)["IT"] == "94380.00" and "atl_rule" not in next(ln for ln in filer["lines"] if ln["tax"] == "IT")


def test_filer_status_is_asked_never_assumed():
    imp = {k: v for k, v in IMP.items() if k != "active_taxpayer"}
    r = compute_duty("6109.1000", 1000000, "2026-07-15", importer=imp)
    assert r["status"] == "needs_input" and "importer.active_taxpayer" in {m["field"] for m in r["missing_inputs"]}
    assert r.get("totals") is None


def test_non_filer_rule_cites_the_file_valid_on_the_date():
    r = compute_duty("6109.1000", 1000000, "2025-12-01", importer={**IMP, "active_taxpayer": False})
    it = next(ln for ln in r["lines"] if ln["tax"] == "IT")
    assert it["atl_rule"]["page"] == 780 and "20.02.2026" in it["atl_rule"]["source_file"]
