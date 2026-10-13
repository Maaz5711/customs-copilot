"""A3 / B1: ACD, sales tax, income tax and legal notes loaded into the store; hand-checked lookups.

Every expected value below was read from the source page named in the comment, not from memory.
"""
import json
from pathlib import Path

import pytest

from src.store import connect, get_rule_on_date
from src.store.build import build

PROC = Path("data/processed")
pytestmark = pytest.mark.skipif(not (PROC / "a3_acd_rules.csv").exists(), reason="A3 files not built")


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("a3") / "store.sqlite"
    report = build(path)
    c = connect(path)
    yield c, report
    c.close()


def q(c, sql, *a):
    return [tuple(r) for r in c.execute(sql, a)]


def rate_rows(c, table, code, date, group_prefix=None):
    rows = get_rule_on_date(c, table, code, date)
    return [r for r in rows if group_prefix is None or r["rule_group"].startswith(group_prefix)]


# ----------------------------------------------------------------------------- counts
def test_report_counts(db):
    _, rep = db
    assert rep["acd_rules"] == 314
    assert rep["legal_notes"] == 484
    assert rep["income_tax_rules"] == 652
    assert rep["sales_tax_rules"] >= 904
    assert rep["a3_instruments"] == 13


def test_acd_row_counts_per_sro(db):
    c, _ = db
    assert q(c, "select sro_number, count(*) from acd_rules group by 1 order by 1") == [("1063(I)/2026", 184), ("1151(I)/2025", 130)]
    # the 167 listed codes of SRO 1063 and 112 of SRO 1151 (A2 findings) are all present as code8 rows:
    # 164 + 3 (para 3(xi), exempt) and 109 + 3
    assert q(c, "select count(*) from acd_rules where sro_number='1063(I)/2026' and match_level='code8' and rate_kind='percent'")[0][0] == 164
    assert q(c, "select count(*) from acd_rules where sro_number='1151(I)/2025' and match_level='code8' and rate_kind='percent'")[0][0] == 109
    assert q(c, "select count(*) from acd_rules where sro_number='1151(I)/2025' and match_level='code8' and rate_kind='exempt'")[0][0] == 3
    assert q(c, "select count(*) from acd_rules where sro_number='1063(I)/2026' and match_level='code8' and rate_kind='exempt'")[0][0] == 3


# ----------------------------------------------------------------------------- tariff heading fix
def test_tariff_heading_for_1103(db):
    c, _ = db
    for fy in ("FY2026-27", "FY2025-26"):
        assert q(c, "select distinct heading from tariff_lines where fy=? and code like '1103.%'", fy) == [("11.03",)]
        assert q(c, "select count(*) from tariff_lines where fy=? and level=8 and substr(code,1,2)||'.'||substr(code,3,2) != heading", fy) == [(0,)]
    assert q(c, "select count(*) from tariff_headings where heading='11.03'")[0][0] == 2


# ----------------------------------------------------------------------------- ACD lookups
def test_acd_exception_list_code_on_boundary_dates(db):
    c, _ = db
    # SRO 1063 (i)(a) exception list, 0103.1000 charged 4% (page 1); 1063 in force from 1 Jul 2026 (page 2, para 4)
    new = rate_rows(c, "acd_rules", "01031000", "2026-07-01", "1063(I)/2026")
    main = [r for r in new if r["rule_group"] == "1063(I)/2026"]
    assert [(r["rate_pct"], r["clause"], r["slab_pct"]) for r in main] == [(4.0, "(i)(a) except-list", 20.0)]
    # the day before, SRO 1151 applies: slab rows 15/20/30+ (page 1); the caller picks by the code's tariff slab (20% -> four percent)
    old = rate_rows(c, "acd_rules", "01031000", "2026-06-30", "1151(I)/2025")
    assert {(r["clause"], r["rate_pct"], r["slab_pct"]) for r in old if r["rule_group"] == "1151(I)/2025"} == {
        ("(i)(a)", 2.0, 15.0), ("(ii)", 4.0, 20.0), ("(iv)", 6.0, 30.0)}
    assert not rate_rows(c, "acd_rules", "01031000", "2026-06-30", "1063(I)/2026")
    assert not rate_rows(c, "acd_rules", "01031000", "2026-07-01", "1151(I)/2025")


def test_acd_six_percent_list_and_specific_rate_exceptions(db):
    c, _ = db
    beer = [r for r in rate_rows(c, "acd_rules", "22030000", "2026-07-01", "1063(I)/2026") if r["rule_group"] == "1063(I)/2026"]
    assert [(r["rate_pct"], r["clause"]) for r in beer] == [(6.0, "(ii)(a)")]          # page 2
    oil = [r for r in rate_rows(c, "acd_rules", "15079000", "2026-07-01", "1063(I)/2026") if r["rule_group"] == "1063(I)/2026"]
    assert [(r["rate_pct"], r["clause"]) for r in oil] == [(2.0, "(ii)(b)(i)")]        # page 2
    oil25 = [r for r in rate_rows(c, "acd_rules", "15079000", "2025-07-01", "1151(I)/2025") if r["rule_group"] == "1151(I)/2025"]
    assert [(r["rate_pct"], r["clause"]) for r in oil25] == [(2.0, "(iv)(a)")]         # page 1


def test_acd_non_levy_clause_3xi(db):
    c, _ = db
    rows = [r for r in rate_rows(c, "acd_rules", "87038030", "2026-07-01") if r["rule_group"].endswith("#3(xi)")]
    assert len(rows) == 1 and rows[0]["rate_kind"] == "exempt" and rows[0]["page"] == 2


def test_acd_ckd_vehicle_rows_need_review(db):
    c, _ = db
    rows = q(c, "select status, match_level from acd_rules where clause in ('(ii)(b)(ii)','(iv)(b)')")
    assert rows and all(r == ("needs_review", "heading4") for r in rows)


# ----------------------------------------------------------------------------- SRO chain
def test_sro_chain_acd_and_sugar(db):
    c, _ = db
    assert q(c, "select sro_status, superseded_by, valid_to from sros where sro_number='1151(I)/2025'") == [("superseded", "1063(I)/2026", "2026-06-30")]
    assert q(c, "select sro_status, superseded_by, valid_to from sros where sro_number='527(I)/2026'") == [("rescinded", "663(I)/2026", "2026-04-21")]
    assert q(c, "select sro_status, superseded_by, valid_to from sros where sro_number='455(I)/2026'") == [("rescinded", "663(I)/2026", "2026-04-21")]
    assert q(c, "select sro_date from sros where sro_number='1216(I)/2025'") == [("2025-07-08",)]   # owner confirmed 8 Jul 2025
    # sugar sales tax windows: A and B read from the SRO pages (accepted), the 527 window and the rescission are doubtful
    w = q(c, "select valid_from, valid_to, status from sales_tax_rules where rule_group='ST-SRO1217-SUGAR' order by valid_from")
    assert w == [("2025-07-08", "2025-09-21", "accepted"), ("2025-09-22", "2025-11-30", "accepted"),
                 ("2026-03-19", "2026-04-21", "needs_review"), ("2026-04-22", "9999-12-31", "needs_review")]
    # income tax clause (9AD): same windows, 455 issued 5 Mar 2026
    w = q(c, "select valid_from, valid_to, status from income_tax_rules where clause like '%clause (9AD)%' order by valid_from")
    assert w == [("2025-07-08", "2025-09-21", "accepted"), ("2025-09-22", "2025-11-30", "accepted"),
                 ("2026-03-05", "2026-04-21", "needs_review"), ("2026-04-22", "9999-12-31", "needs_review")]


# ----------------------------------------------------------------------------- sales tax
def test_sales_tax_standard_rate_chain(db):
    c, _ = db
    for d in ("2025-07-01", "2026-06-30", "2026-07-01", "2027-06-30"):
        std = [r for r in get_rule_on_date(c, "sales_tax_rules", "07131000", d) if r["rule_group"] == "ST-ACT-S3"]
        assert len(std) == 1 and std[0]["rate_pct"] == 18.0     # Sales Tax Act s.3(1)(b)


def test_sixth_schedule_s152_ends_30_june_2026(db):
    c, _ = db
    # S.No 152 (electricity, tribal areas): printed "till 30th June, 2026" (page 176 of the FY2026-27 file)
    assert q(c, "select valid_to from sales_tax_rules where clause like 'Sixth Schedule, Table-1, S.No 152,%'") == [("2026-06-30",)]
    assert [x for x in get_rule_on_date(c, "sales_tax_rules", "27160000", "2026-06-30") if "S.No 152," in x["clause"]]
    assert not [x for x in get_rule_on_date(c, "sales_tax_rules", "27160000", "2026-07-01") if "S.No 152," in x["clause"]]


def test_ev_exclusions_xi_xii_end_30_june_2026(db):
    c, _ = db
    r = q(c, "select clause, valid_to from sales_tax_rules where clause like '%(2)(xi)' or clause like '%(2)(xii)'")
    assert len(r) == 2 and all(v == "2026-06-30" for _, v in r)


def test_sixth_schedule_133_has_eleven_respective_headings_entries(db):
    c, _ = db
    # page 171 prints 902-905 and 907-912, page 170 prints 901: 11 'Respective headings' entries (A3 fix: two were dropped)
    rows = q(c, "select page, count(*) from sales_tax_rules where clause like 'Sixth Schedule, Table-1, S.No 133,%' "
                "and match_level='unmapped' group by page order by page")
    assert sum(x[1] for x in rows) == 12          # 11 'Respective headings' + 1 blank-code row (Ethion ..., page 171)
    assert {x[0] for x in rows} <= {169, 170, 171, 172}
    assert q(c, "select count(distinct page) from sales_tax_rules where clause like 'Sixth Schedule, Table-1, S.No 133,%'")[0][0] == 4


def test_schedule_rows_without_code_cannot_match_every_code(db):
    c, _ = db
    rows = get_rule_on_date(c, "sales_tax_rules", "07131000", "2026-10-13")
    assert not [r for r in rows if r["match_level"] == "all" and r["rule_group"] in ("ST-6TH-T1", "ST-3RD", "ST-8TH-T1")]
    assert q(c, "select count(*) from sales_tax_rules where match_level='all' and rule_group in "
                "('ST-6TH-T1','ST-3RD','ST-8TH-T1','ST-6TH-T3','ST-12TH','ST-12TH-EXCL','ST-12TH-PROV')") == [(0,)]


def test_sro297_table2_hybrid_carve_out(db):
    c, _ = db
    day_before = [r for r in get_rule_on_date(c, "sales_tax_rules", "87032100", "2026-09-12") if r["rule_group"].startswith("ST-SRO297-T2")]
    assert {r["rule_group"] for r in day_before} == {"ST-SRO297-T2"}
    after = [r for r in get_rule_on_date(c, "sales_tax_rules", "87032100", "2026-09-13") if r["rule_group"].startswith("ST-SRO297-T2")]
    assert {r["rule_group"] for r in after} == {"ST-SRO297-T2", "ST-SRO297-T2-1525-HYBRID"}
    t2 = [r for r in after if r["rule_group"] == "ST-SRO297-T2"]
    assert all("hybrid electric vehicles with engine capacity upto 2000cc" in r["condition_text"] for r in t2)
    hy = [r for r in after if r["rule_group"] == "ST-SRO297-T2-1525-HYBRID"][0]
    assert hy["rate_kind"] == "exempt" and hy["source_file"].endswith("SRO1525.pdf") and hy["page"] == 1
    assert hy["valid_from"] == "2026-09-13"


# ----------------------------------------------------------------------------- income tax
def test_s53a_literal_wording_and_dates(db):
    c, _ = db
    rows = q(c, "select clause, rate_raw, valid_from, page from income_tax_rules where clause like '%53A%'")
    assert len(rows) == 1
    clause, rate_raw, vf, page = rows[0]
    assert "by one percent" in rate_raw and "percentage point" not in rate_raw
    assert "continues p.127" in clause and page == 126
    assert vf == "2026-07-01"
    assert not [r for r in get_rule_on_date(c, "income_tax_rules", "07131000", "2026-06-30") if "53A" in r["clause"]]
    assert [r for r in get_rule_on_date(c, "income_tax_rules", "07131000", "2026-07-01") if "53A" in r["clause"]]


def test_time_limited_income_tax_clauses_are_not_in_scope(db):
    c, _ = db
    # 12B ends 31 Dec 2021, 12C 30 Sep 2020, 12H/12K/12M 3 months / 180 days from 2020-21 dates, 123 3 months from 1 Dec 2022,
    # 124 till 31 Dec 2022 (all printed in the Second Schedule text): none reaches FY2025-26, so none is loaded
    for no in ("12B", "12C", "12H", "12K", "12M", "123", "124"):
        assert q(c, "select count(*) from income_tax_rules where clause like ?", f"%clause ({no})%") == [(0,)]
    src = json.loads((PROC / "a3_it_s148_special_rules.json").read_text(encoding="utf-8"))["rows"]
    ends = {r["clause"].split("clause (")[1].split(")")[0]: r["valid_to"] for r in src if "clause (" in r["clause"]}
    assert ends["12B"] == "2021-12-31" and ends["12C"] == "2020-09-30" and ends["124"] == "2022-12-31"
    assert all(ends[k] < "2025-07-01" for k in ("12B", "12C", "12H", "12K", "12M", "123", "124"))


def test_twelfth_schedule_rows_use_row_index_not_serial():
    rows = json.loads((PROC / "a3_it_twelfth_schedule.json").read_text(encoding="utf-8"))["rows"]
    assert rows and all(r["s_no"] == "" and r["row_index"].split("-")[0] in ("I", "II", "III") for r in rows)


def test_s148_class_rates(db):
    c, _ = db
    rows = [r for r in get_rule_on_date(c, "income_tax_rules", "07131000", "2026-10-13") if r["rule_group"].startswith("IT-S148-RATE-P")]
    assert sorted(r["rate_pct"] for r in rows) == [1.0, 2.0, 3.5, 5.5, 6.0]


# ----------------------------------------------------------------------------- legal notes
def test_legal_notes_loaded_with_assumption_label(db):
    c, _ = db
    assert q(c, "select note_kind, count(*) from legal_notes group by 1 order by 1") == [
        ("chapter_note", 355), ("general_rule", 8), ("section_note", 45), ("subheading_note", 76)]
    assert q(c, "select count(*) from legal_notes where hs_edition not like '%applicability to FY2025-26 and FY2026-27 assumed, not proven%'") == [(0,)]
    assert q(c, "select count(distinct valid_from||valid_to) from legal_notes") == [(1,)]
    ch87 = get_rule_on_date(c, "legal_notes", "Chapter 87", "2026-10-13")
    assert ch87 and all(r["valid_from"] == "2025-07-01" and r["valid_to"] == "9999-12-31" for r in ch87)
    assert get_rule_on_date(c, "legal_notes", "Chapter 87", "2025-06-30") == []     # before the assumed start


# ----------------------------------------------------------------------------- tariff specific duties
def test_loader_uses_parsed_specific_amount_not_cd_raw_digits(db):
    c, _ = db
    for fy, key in (("FY2026-27", "tariff_2026_27"), ("FY2025-26", "tariff_2025_26")):
        data = json.loads((PROC / f"{key}.json").read_text(encoding="utf-8"))["rows"]
        spec = {r["code"]: r["cd_specific"] for r in data if r["cd_kind"] == "specific"}
        got = {r[0]: (r[1], r[2]) for r in q(c, "select code, cd_specific_amount, cd_specific_unit from tariff_lines "
                                               "where fy=? and cd_kind='specific'", fy)}
        assert set(got) == set(spec) and len(got) == 54
        for code, s in spec.items():
            assert got[code] == (s["amount"], s["unit"])
    assert q(c, "select cd_specific_amount from tariff_lines where fy='FY2026-27' and code='1507.9000'") == [(11700.0,)]
