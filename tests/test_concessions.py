"""Customs-duty concessions in compute_duty / get_applicable_sros (Fifth Schedule and China FTA Phase II).

Hand-computed cases: every rate comes from the page named in the comment (page numbers of the PDF in data/raw), the arithmetic was done by hand
(V = 1,000,000 PKR, registered, filer, not a commercial importer, manufacturer importing for its own use so no value addition tax,
order of docs/duty_formula.md). A concession is applied only when the caller claims it."""
from decimal import Decimal

import pytest

from src.tools import compute_duty, get_applicable_sros
from src.tools.concessions import fifth_effective_rate

IMP = {"registration_status": "registered", "commercial_importer": False, "manufacturer_in_house_use": True, "active_taxpayer": True}
GOODS = {"plant_machinery_for_manufacturing": True}
V = 1000000


def bill(code, date="2026-08-01", claimed=None, goods=None, importer=None):
    return compute_duty(code, V, date, importer=importer or IMP, goods=goods if goods is not None else GOODS, claimed_rules=claimed)


def fifth_id(res, s_no, page=None):
    opts = [o for o in res["concessions"]["fifth_schedule"]["options"] if o["clause"].startswith(f"Part I, S.No {s_no}") and (page is None or o["page"] == page)]
    assert len(opts) == 1, [o["clause"] for o in res["concessions"]["fifth_schedule"]["options"]]
    return opts[0]["rule_id"]


def tot(res):
    return res["totals"]


# ---------------------------------------------------------------- slab rule (Part I note (iv), Explanations I-IV, pages 2-3)
@pytest.mark.parametrize("listed,cd,expect", [
    (["0", "3", "5"], "0", "0"), (["0", "3", "5"], "3", "3"), (["0", "3", "5"], "11", "5"), (["0", "3", "5"], "20", "5"),   # Explanation I
    (["3", "5"], "3", "3"), (["3", "5"], "16", "5"),                                                                          # Explanation II
    (["0", "3", "10"], "11", "10"), (["0", "3", "11", "15"], "11", "11"), (["0", "3", "11", "15"], "20", "15"),               # III, IV
    (["2"], "20", "2"),
])
def test_slab_rule(listed, cd, expect):
    rate, _, flags = fifth_effective_rate([Decimal(x) for x in listed], Decimal(cd))
    assert rate == Decimal(expect) and not flags


def test_slab_not_listed_keeps_normal_rate_and_says_so():
    rate, why, flags = fifth_effective_rate([Decimal(x) for x in ("0", "3", "5")], Decimal("1"))
    assert rate == Decimal("1") and "slab_not_listed_normal_rate_kept" in flags


# ---------------------------------------------------------------- Fifth Schedule, hand-computed
def test_fifth_1_fodder_rake_zero_percent():
    # Tariff 2026-27 p.202: 8201.3000 CD 15%. Fifth Schedule (2026-27 file) p.3 Part I S.No 1 D(1): 0%. SRO 1064 RD 0; ACD 0 (15% slab).
    # Without: CD 150,000; ST 18% x 1,150,000 = 207,000; IT 5.5% x 1,357,000 = 74,635; total 431,635.
    # With: CD 0; ACD not levied (SRO 1063 para 3(iii)); ST 18% x 1,000,000 = 180,000; IT 5.5% x 1,180,000 = 64,900; total 244,900.
    base = bill("8201.3000")
    assert tot(base)["total_payable_pkr"] == "431635.00" and base["concessions"]["applied"] == []
    rid = fifth_id(base, "1", 3)
    opt = base["concessions"]["fifth_schedule"]["options"][0]
    assert opt["effective_cd_pct"] == "0" and opt["bill_if_applied"]["totals"]["total_payable_pkr"] == "244900.00"
    assert opt["bill_if_applied"]["difference_vs_normal_bill"]["total_payable_pkr"] == "-186735.00"
    r = bill("8201.3000", claimed=[rid])
    assert tot(r) == {"customs_duties": "0.00", "federal_excise_duty": "0.00", "sales_tax": "180000.00", "income_tax": "64900.00", "total_payable_pkr": "244900.00"}
    assert r["concessions"]["applied"][0]["rule_id"] == rid
    assert r["concessions"]["bill_without_concession"]["totals"]["total_payable_pkr"] == "431635.00"
    assert r["review_required"] and any("concession_applied_conditions_unchecked" in f for f in r["flags"])
    assert any(a["id"] == "CONCESSION_CONDITIONS" for a in r["assumptions"])


def test_fifth_2_polish_5_percent_and_acd_dropped():
    # Tariff p.89: 3405.9000 CD 20% (ACD 2% in the 20% slab, SRO 1063 p.1). Fifth Schedule p.10 Part I S.No 17 (1): 5%.
    # Without: CD 200,000 + ACD 20,000; ST 18% x 1,220,000 = 219,600; IT 5.5% x 1,439,600 = 79,178; total 518,778.
    # With: CD 50,000; ACD 0 (para 3(iii)); ST 18% x 1,050,000 = 189,000; IT 5.5% x 1,239,000 = 68,145; total 307,145.
    base = bill("3405.9000")
    assert tot(base)["total_payable_pkr"] == "518778.00"
    r = bill("3405.9000", claimed=[fifth_id(base, "17", 10)])
    assert tot(r) == {"customs_duties": "50000.00", "federal_excise_duty": "0.00", "sales_tax": "189000.00", "income_tax": "68145.00", "total_payable_pkr": "307145.00"}
    assert [ln["amount_pkr"] for ln in r["lines"] if ln["tax"] == "ACD"] == ["0.00"]


def test_fifth_3_tourism_half_of_prevailing_rate():
    # Tariff p.321: 9406.1090 CD 20%. Fifth Schedule p.19 Part I S.No 39: "50% of the prevailing rate of customs duty" = 10%.
    # With: CD 100,000; ACD 0; ST 18% x 1,100,000 = 198,000; IT 5.5% x 1,298,000 = 71,390; total 369,390.
    base = bill("9406.1090")
    rid = fifth_id(base, "39", 19)
    o = [x for x in base["concessions"]["fifth_schedule"]["options"] if x["rule_id"] == rid][0]
    assert o["listed_rate"].startswith("50% of the prevailing") and o["effective_cd_pct"] == "10"
    r = bill("9406.1090", claimed=[rid])
    assert tot(r)["customs_duties"] == "100000.00" and tot(r)["total_payable_pkr"] == "369390.00"
    # the same code has two other Fifth Schedule options (S.No 1, S.No 30 at 8%): all listed, none applied
    assert len(base["concessions"]["fifth_schedule"]["options"]) == 3 and base["concessions"]["applied"] == []


def test_fifth_4_serial_33_is_excluded_from_the_acd_exemption():
    # Tariff p.271: 8705.3000 CD 30% (ACD 4% in the 30% slab). Fifth Schedule p.17 Part I S.No 33 (fire-fighting vehicles): 10%.
    # ACD clause 3(iii) of SRO 1063 (p.2) excludes serial numbers 30, 33 and 35 of Part I: ACD is still charged.
    # With: CD 100,000 + ACD 40,000; ST 18% x 1,140,000 = 205,200; IT 5.5% x 1,345,200 = 73,986; total 419,186.
    base = bill("8705.3000")
    assert tot(base)["total_payable_pkr"] == "668166.00"
    o = base["concessions"]["fifth_schedule"]["options"][0]
    assert o["acd_not_levied"] is False
    r = bill("8705.3000", claimed=[o["rule_id"]])
    assert tot(r)["customs_duties"] == "140000.00" and tot(r)["total_payable_pkr"] == "419186.00"


# ---------------------------------------------------------------- never applied silently
def test_not_claimed_means_normal_bill_everywhere():
    for code in ("8201.3000", "3405.9000", "9406.1090", "8705.3000"):
        r = bill(code)
        assert r["concessions"]["applied"] == [] and not any("concession" in ln for ln in r["lines"])
        assert all(o["bill_if_applied"] for o in r["concessions"]["fifth_schedule"]["options"] if o["effective_cd_pct"] is not None)
        assert r["concessions"]["questions"], "the agent must be given a question about the concession"


def test_two_concessions_claimed_is_refused_not_guessed():
    base = bill("9406.1090")
    ids = [fifth_id(base, "30"), fifth_id(base, "39", 19)]
    r = bill("9406.1090", claimed=ids)
    assert r["status"] == "needs_input" and r["totals"] is None and r["concessions"]["applied"] == []


def test_unknown_claim_is_not_applied():
    r = bill("8201.3000", claimed=["fifth_schedule_rules:99999"])
    assert tot(r)["total_payable_pkr"] == "431635.00" and r["concessions"]["notes"]


def test_get_applicable_sros_lists_options_without_applying():
    r = get_applicable_sros("8201.3000", "2026-08-01")
    c = r["concessions"]["fifth_schedule"]
    assert c["status"] == "checked" and c["options"][0]["clause"].startswith("Part I, S.No 1") and r["concessions"]["applicable"] == []


# ================================================================ China-Pakistan FTA Phase II (SRO 1640(I)/2019), hand-computed
# V = 1,000,000, registered, commercial importer, not a manufacturer (VAT 3% charged), filer. Rates read from the SRO page images (page 3):
# Sr.No 74 (0207.1200): A15 line 25.00 25.00 25.00 22.92 20.83 18.75 16.67 14.58 ...; Sr.No 63 (0205.0000): 20.00 16.67 13.33 10.00 6.67 3.33 0.00 ...;
# Sr.No 73 (0207.1100): 20.00 in all years. Normal CD of all three is 20% (tariff), ST 25%, VAT 3%, IT 6% (Part III commercial).
CN = {"origin_country": "CN", "has_certificate_of_origin": True}
COMM = {"registration_status": "registered", "commercial_importer": True, "manufacturer_in_house_use": False, "active_taxpayer": True}


def fta(code, date, goods=None):
    return compute_duty(code, V, date, importer=COMM, goods=goods if goods is not None else {})


def test_fta_1_poultry_2026_16_67_percent():
    # Year 7 column (1-Jan-26): 16.67%. Without: CD 200,000 + ACD 2% 20,000; ST 25% x 1,220,000 = 305,000; VAT 3% x 1,220,000 = 36,600;
    # IT 6% x 1,561,600 = 93,696; total 655,296.  With: CD 166,700 + ACD 20,000 (ACD stays); V_ST 1,186,700: ST 296,675; VAT 35,601;
    # IT 6% x 1,518,976 = 91,138.56; total 610,114.56.
    base = fta("0207.1200", "2026-08-01", CN)
    assert base["totals"]["total_payable_pkr"] == "655296.00" and base["concessions"]["applied"] == []
    o = base["concessions"]["china_fta"]["options"][0]
    assert o["listed_rate"] == "16.67%" and o["effective_cd_pct"] == "16.67" and o["page"] == 3 and o["bill_if_applied"]["totals"]["total_payable_pkr"] == "610114.56"
    assert [q["id"] for q in base["concessions"]["questions"]] == []               # origin and certificate already given: nothing left to ask
    r = fta("0207.1200", "2026-08-01", dict(CN, claim_china_fta=True))
    assert r["totals"] == {"customs_duties": "186700.00", "federal_excise_duty": "0.00", "sales_tax": "332276.00", "income_tax": "91138.56", "total_payable_pkr": "610114.56"}
    assert r["concessions"]["bill_without_concession"]["totals"]["total_payable_pkr"] == "655296.00"
    assert any(a["id"] == "FTA_BASE" for a in r["assumptions"]) and r["review_required"]


def test_fta_2_same_code_in_2025_uses_the_2025_column():
    # 1 Sep 2025 (FY2025-26, SRO 1151: ACD 4% in the 20% slab): Year 6 column 18.75%. CD 187,500 + ACD 40,000; V_ST 1,227,500: ST 306,875; VAT 36,825;
    # IT 6% x 1,571,200 = 94,272; total 665,472 (without: 682,432).
    r = fta("0207.1200", "2025-09-01", dict(CN, claim_china_fta=True))
    assert r["totals"]["total_payable_pkr"] == "665472.00" and r["concessions"]["bill_without_concession"]["totals"]["total_payable_pkr"] == "682432.00"
    assert r["concessions"]["applied"][0]["clause"].startswith("Table Sr.No 74, column for 2025")


def test_fta_3_a07_line_nearly_phased_out():
    # Sr.No 63 (0205.0000, A07 base 20): 1-Jan-25 column 3.33%. CD 33,300 + ACD 40,000; V_ST 1,073,300: ST 268,325; VAT 32,199; IT 6% x 1,373,824 = 82,429.44; total 456,253.44.
    r = fta("0205.0000", "2025-09-01", dict(CN, claim_china_fta=True))
    assert r["totals"]["total_payable_pkr"] == "456253.44"
    r2 = fta("0205.0000", "2026-08-01", dict(CN, claim_china_fta=True))      # 1-Jan-26 column: 0.00%
    assert r2["concessions"]["applied"][0]["effective_cd_pct"] == "0"


def test_fta_4_constant_line_gives_no_saving_and_says_so():
    base = fta("0207.1100", "2027-02-01", CN)       # Sr.No 73: 20.00 in 2027, equal to the tariff CD
    o = base["concessions"]["china_fta"]["options"][0]
    assert o["effective_cd_pct"] == "20" and "no_saving_preferential_rate_not_lower_than_normal_cd" in o["flags"]
    assert o["bill_if_applied"]["totals"]["total_payable_pkr"] == base["totals"]["total_payable_pkr"]


@pytest.mark.parametrize("goods", [{"claim_china_fta": True},                                                     # origin unknown
                                   {"origin_country": "India", "has_certificate_of_origin": True, "claim_china_fta": True},
                                   {"origin_country": "CN", "has_certificate_of_origin": False, "claim_china_fta": True},
                                   {"origin_country": "CN", "claim_china_fta": True}])                            # certificate not answered
def test_fta_never_applied_without_origin_and_certificate(goods):
    r = fta("0207.1200", "2026-08-01", goods)
    assert r["totals"]["total_payable_pkr"] == "655296.00" and r["concessions"]["applied"] == [] and r["concessions"]["notes"]


def test_fta_questions_for_the_agent():
    q0 = [q["id"] for q in fta("0207.1200", "2026-08-01", {})["concessions"]["questions"]]
    assert q0 == ["origin_country"]
    q1 = [q["id"] for q in fta("0207.1200", "2026-08-01", {"origin_country": "China"})["concessions"]["questions"]]
    assert q1 == ["certificate_of_origin"]


def test_code_without_a_row_in_the_2019_sro_offers_nothing():
    r = fta("8201.3000", "2026-08-01", CN)
    assert r["concessions"]["china_fta"]["options"] == [] and r["concessions"]["questions"] == [] or r["concessions"]["questions"][0]["id"] != "origin_country"


def test_a_code_missing_from_the_2019_china_table_gets_information_only_never_a_rate():
    from src.tools._util import get_conn, rows

    conn = get_conn()
    code = None
    for r in rows(conn, "SELECT code_norm FROM tariff_lines WHERE fy='FY2025-26' AND level=8 AND cd_kind='plain' ORDER BY code_norm"):
        c = r["code_norm"]
        if rows(conn, "SELECT 1 FROM fta_rules WHERE code_norm=? LIMIT 1", [c]) or not rows(conn, "SELECT 1 FROM fta_rules WHERE substr(code_norm,1,6)=? AND match_level='code8' LIMIT 1", [c[:6]]):
            continue
        code = c
        break
    assert code, "no code with a family but no row of its own"
    res = compute_duty(code, V, "2026-02-10", importer={**IMP, "commercial_importer": True}, goods={"origin_country": "CN", "plant_machinery_for_manufacturing": False})
    fta = res["concessions"]["china_fta"]
    assert fta["options"] == [] and fta["possible_by_family"]["six_digit_family"] == code[:6]
    assert "NOT offered and NOT applied" in fta["possible_by_family"]["note"] and fta["possible_by_family"]["listed_rates_pct"]
