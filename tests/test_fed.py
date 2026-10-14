"""A6: federal excise duty (FED) rules of the Federal Excise Act 2005 loaded into the store; hand-checked lookups.

Expected values were read from the page named in each comment (page images of the FED files in data/raw), not from memory.
FED file pages: FY2026-27 = 20267171373633512FEDAct2005updatedupto30-06-2026.pdf, FY2025-26 = 202588138517680FEDAct,2005withindexupdatedupto30-06-2025.pdf.
"""
import csv
import json
import sqlite3
from pathlib import Path

import pytest

from src.ingest.a6_fed import parse_band, parse_codes, parse_rate, words_to_number
from src.store import connect, get_rule_on_date
from src.store.build import build
from src.store.resolve import get_fed_on_date

PROC = Path("data/processed")
pytestmark = pytest.mark.skipif(not (PROC / "a6_fed_rules.csv").exists(), reason="A6 files not built")


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("a6") / "store.sqlite"
    report = build(path)
    c = connect(path)
    yield c, report
    c.close()


def pick(res, s_no, sub=None):
    return [r for r in res["applicable_first_schedule"] + res["local_only_not_applied"]
            if r["s_no"] == s_no and (sub is None or r["sub"] == sub)]


# ------------------------------------------------------------------------------------------- loader and counts
def test_counts_match_csv(db):
    c, rep = db
    csv_rows = list(csv.DictReader(open(PROC / "a6_fed_rules.csv", encoding="utf-8")))
    assert rep["fed_rules"] == len(csv_rows)
    for fy in ("FY2025-26", "FY2026-27"):
        n = c.execute("SELECT COUNT(*) FROM fed_rules WHERE fy = ?", (fy,)).fetchone()[0]
        assert n == sum(1 for r in csv_rows if r["fy"] == fy)
    # Table IA exists only in the FY2026-27 file (Finance Act 2026), serial 55A and 65 too; serial 64 (Finance Act 2025) in both
    q = lambda sql, *a: {tuple(r) for r in c.execute(sql, a)}
    assert q("SELECT DISTINCT fy FROM fed_rules WHERE table_no = 'IA'") == {("FY2026-27",)}
    assert q("SELECT DISTINCT fy FROM fed_rules WHERE table_no = 'I' AND s_no = '55A'") == {("FY2026-27",)}
    assert q("SELECT DISTINCT fy FROM fed_rules WHERE table_no = 'I' AND s_no = '65'") == {("FY2026-27",)}
    assert q("SELECT DISTINCT fy FROM fed_rules WHERE table_no = 'I' AND s_no = '64'") == {("FY2025-26",), ("FY2026-27",)}
    assert q("SELECT DISTINCT fy FROM fed_rules WHERE table_no = 'Third-I' AND s_no = '28'") == {("FY2026-27",)}


def test_every_row_has_dates_source_page(db):
    c, _ = db
    bad = c.execute("SELECT COUNT(*) FROM fed_rules WHERE valid_from IS NULL OR valid_to IS NULL OR source_file IS NULL OR page IS NULL "
                    "OR page < 1 OR valid_to < valid_from").fetchone()[0]
    assert bad == 0
    fy = {r[0]: (r[1], r[2]) for r in c.execute("SELECT fy, MIN(valid_from), MAX(valid_to) FROM fed_rules GROUP BY fy")}
    assert fy["FY2025-26"] == ("2025-07-01", "2026-06-30")
    assert fy["FY2026-27"] == ("2026-07-01", "9999-12-31")


@pytest.mark.parametrize("column", ["valid_from", "valid_to", "source_file", "page"])
def test_missing_fact_column_rejected(db, column):
    c, _ = db
    row = dict(row_id="x", fy="FY2026-27", schedule="First", table_no="I", s_no="1", description="d", match_level="all",
               code_norm="", rule_group="g", applies_to="import_and_local", rate_kind="exempt", valid_from="2026-07-01",
               valid_to="2026-12-31", source_file="f.pdf", page=1)
    del row[column]
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(f"INSERT INTO fed_rules ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))
    c.rollback()


@pytest.mark.parametrize("patch", [
    dict(rate_kind="percent", rate_pct=20),                                   # percent without a basis
    dict(rate_kind="specific", rate_specific_amount=0, rate_specific_unit="kg"),   # zero amount
    dict(rate_kind="compound", rate_pct=65, rate_specific_amount=100, rate_specific_unit="kg"),   # no 'higher_of'
    dict(rate_kind="percent", rate_pct=150, rate_basis="ad_valorem"),         # percent above 100
    dict(match_level="code8", code_norm="2401"),                              # level and length disagree
    dict(valid_from="2026-13-01"),                                            # impossible date
])
def test_bad_values_rejected(db, patch):
    c, _ = db
    row = dict(row_id="y", fy="FY2026-27", schedule="First", table_no="I", s_no="1", description="d", match_level="all",
               code_norm="", rule_group="g", applies_to="import_and_local", rate_kind="exempt", valid_from="2026-07-01",
               valid_to="2026-12-31", source_file="f.pdf", page=1)
    row.update(patch)
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(f"INSERT INTO fed_rules ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))
    c.rollback()


# ------------------------------------------------------------------------------------------- hand-checked lookups
def test_unmanufactured_tobacco_rs390_per_kg_both_years(db):
    c, _ = db
    # FY2026-27 file p.71 and FY2025-26 file p.73: S.No 7, 24.01, "Three hundred and ninety rupees per kilogram"
    for date, page, fy in (("2026-07-15", 71, "FY2026-27"), ("2025-12-01", 73, "FY2025-26")):
        r = pick(get_fed_on_date(c, "24011000", date), "7")
        assert len(r) == 1 and r[0]["rate_kind"] == "specific"
        assert r[0]["rate_specific_amount"] == 390 and r[0]["rate_specific_unit"] == "kg"
        assert r[0]["page"] == page and r[0]["fy"] == fy and r[0]["match_level"] == "heading4"


def test_cement_rs4_per_kg(db):
    c, _ = db
    # FY2026-27 p.72, FY2025-26 p.76: S.No 13, 25.23, "four rupees per kilogram"
    assert [(r["rate_specific_amount"], r["page"]) for r in pick(get_fed_on_date(c, "25231000", "2026-07-15"), "13")] == [(4, 72)]
    assert [(r["rate_specific_amount"], r["page"]) for r in pick(get_fed_on_date(c, "25231000", "2025-12-01"), "13")] == [(4, 76)]


def test_flavours_and_incandescent_bulbs(db):
    c, _ = db
    r = pick(get_fed_on_date(c, "33021010", "2026-07-15"), "41")[0]      # p.74: 3302.1010 Fifty per cent ad valorem
    assert (r["rate_pct"], r["rate_basis"], r["page"], r["match_level"]) == (50, "ad_valorem", 74, "code8")
    r = pick(get_fed_on_date(c, "85392200", "2026-07-15"), "61")[0]      # p.77: 8539.2200 and 8539.2990 Twenty percent ad valorem
    assert (r["rate_pct"], r["page"]) == (20, 77)
    assert pick(get_fed_on_date(c, "85392910", "2026-07-15"), "61") == []   # 8539.2910 is not one of the two printed codes
    r = pick(get_fed_on_date(c, "85392200", "2025-12-01"), "61")[0]      # FY2025-26 file p.81
    assert (r["rate_pct"], r["page"]) == (20, 81)


def test_lpg_ng_units(db):
    c, _ = db
    r = pick(get_fed_on_date(c, "27111200", "2026-07-15"), "32")[0]      # p.73: propane, 17 rupees 18 paisa per 100 cubic meters
    assert (r["rate_specific_amount"], r["rate_specific_unit"], r["page"]) == (17.18, "100 m3", 73)
    r = pick(get_fed_on_date(c, "27112100", "2026-07-15"), "36")[0]      # p.74: natural gas, ten rupees per MMBTu
    assert (r["rate_specific_amount"], r["rate_specific_unit"], r["page"]) == (10, "MMBTu", 74)
    r = pick(get_fed_on_date(c, "27111910", "2026-07-15"), "35")[0]      # p.74 prints 2711.1900; stored as the 6-digit prefix, needs_review
    assert (r["match_level"], r["code_norm"], r["status"], r["rate_specific_amount"]) == ("code6", "271119", "needs_review", 60)


def test_vehicles_engine_capacity_bands(db):
    c, _ = db
    res = get_fed_on_date(c, "87032115", "2026-07-15")
    bands = {r["sub"]: r for r in pick(res, "55")}
    # FY2026-27 file p.75: (a) up to 1000cc 2.5%, (b) 1001-1799cc 10%, (c) 1800-3000cc 30%, (d) exceeding 3001cc 40%
    assert {k: v["rate_pct"] for k, v in bands.items()} == {"(a)": 2.5, "(b)": 10, "(c)": 30, "(d)": 40}
    assert (bands["(a)"]["cc_ge"], bands["(a)"]["cc_le"]) == (None, 1000)
    assert (bands["(b)"]["cc_ge"], bands["(b)"]["cc_le"]) == (1001, 1799)
    assert (bands["(c)"]["cc_ge"], bands["(c)"]["cc_le"]) == (1800, 3000)
    assert (bands["(d)"]["cc_gt"], bands["(d)"]["cc_le"]) == (3001, None)
    assert all(b["applies_to"] == "import_only" and b["page"] == 75 for b in bands.values())
    # locally manufactured bands (55B, p.76) are kept visible but never applied to imports
    assert {r["sub"] for r in pick(res, "55B")} == {"(a)", "(b)", "(c)"}
    assert all(r in res["local_only_not_applied"] for r in pick(res, "55B"))


def test_table_ia_special_excise_duty_starts_1_july_2026(db):
    c, _ = db
    before = get_fed_on_date(c, "87032115", "2026-06-30")
    after = get_fed_on_date(c, "87032115", "2026-07-01")
    assert pick(before, "1") == []                                   # Table IA is not in the FY2025-26 file
    assert {r["fy"] for r in before["applicable_first_schedule"]} == {"FY2025-26"}
    ia = [r for r in after["applicable_first_schedule"] if r["table_no"] == "IA"]
    assert {(r["sub"], r["rate_pct"], r["cc_ge"], r["cc_gt"], r["cc_le"], r["page"]) for r in ia} == {
        ("(a)", 86, 2000, None, 3000, 80), ("(b)", 92, None, 3000, None, 80)}   # FY2026-27 p.80: 86% ad val (2000-3000cc), 92% above 3000cc
    assert all(r["rule_group"] == "FED-T1A" for r in ia)             # separate group: cumulative with Table I (section 3(3B) "in addition")
    t1 = [r for r in after["applicable_first_schedule"] if r["table_no"] == "I"]
    assert len(t1) == 4 and all(r["rule_group"] == "FED-T1" for r in t1)
    # double cabin 4x4 pickups: Table I S.No 55C (30%) and Table IA both name 8704.2190 / 8704.3190
    pick_up = get_fed_on_date(c, "87042190", "2026-07-15")
    assert [(r["s_no"], r["rate_pct"]) for r in pick_up["applicable_first_schedule"]] == [("55C", 30), ("1", 86), ("1", 92)]
    assert [r["s_no"] for r in pick_up["local_only_not_applied"]] == ["55D"]


def test_date_boundary_new_serials_30_june_vs_1_july_2026(db):
    c, _ = db
    # Finance Act 2026 s.6(14)(1)(f)-(g): S.No 63 gains 2710.1993 and S.No 65 is new; both start 1 Jul 2026 (Finance Act s.1(2))
    assert pick(get_fed_on_date(c, "27101993", "2026-06-30"), "63") == []
    r = pick(get_fed_on_date(c, "27101993", "2026-07-01"), "63")
    assert len(r) == 1 and r[0]["rate_pct"] == 5 and r[0]["page"] == 78
    assert pick(get_fed_on_date(c, "27101942", "2026-06-30"), "65") == []
    r = pick(get_fed_on_date(c, "27101942", "2026-07-01"), "65")
    assert len(r) == 1 and r[0]["rate_specific_amount"] == 80 and r[0]["rate_specific_unit"] == "liter" and r[0]["page"] == 78
    # the day before FY2025-26 starts nothing is in the store; the first day finds the old rules
    assert get_fed_on_date(c, "24011000", "2025-06-30") == {"applicable_first_schedule": [], "local_only_not_applied": [], "possible_exemptions": []}
    assert pick(get_fed_on_date(c, "24011000", "2025-07-01"), "7")[0]["fy"] == "FY2025-26"
    # 2710.1951 is in S.No 63 in both years (2025 file p.81, 2026 file p.78)
    assert pick(get_fed_on_date(c, "27101951", "2026-06-30"), "63")[0]["page"] == 81
    assert pick(get_fed_on_date(c, "27101951", "2026-07-01"), "63")[0]["page"] == 78


def test_acetate_tow_and_eliquid_changes_are_unmapped_but_dated(db):
    c, _ = db
    # S.No 7a: Rs. 44000 (FY2025-26 p.73) -> Rs. 10000 (FY2026-27 p.71): Finance Act 2026 s.6(14)(1)(a)
    rows = c.execute("SELECT fy, rate_specific_amount, page FROM fed_rules WHERE s_no = '7a' ORDER BY fy").fetchall()
    assert [tuple(r) for r in rows] == [("FY2025-26", 44000, 73), ("FY2026-27", 10000, 71)]
    # S.No 8a: 'Rupees ten thousand per kg or sixty five percent of retail price whichever is higher' -> Rs. 16500 per kg
    r = c.execute("SELECT fy, rate_kind, rate_pct, rate_specific_amount FROM fed_rules WHERE s_no = '8a' ORDER BY fy").fetchall()
    assert [tuple(x) for x in r] == [("FY2025-26", "compound", 65, 10000), ("FY2026-27", "specific", None, 16500)]


def test_cigarettes_import_rate_by_reference(db):
    c, _ = db
    res = get_fed_on_date(c, "24022000", "2026-07-15")
    imp = pick(res, "8")[0]                                          # p.71: 65% of retail price or the rate against S.No 9, whichever is higher
    assert (imp["rate_kind"], imp["rate_pct"], imp["rate_basis"], imp["rate_ref_s_no"], imp["compound_rule"]) == (
        "compound", 65, "retail_price", "9", "higher_of")
    assert (imp["rate_specific_amount"], imp["rate_specific_unit"], imp["status"]) == (16500, "1000 cigarettes", "needs_review")
    assert {r["s_no"] for r in res["local_only_not_applied"]} == {"9", "10", "12"}   # locally produced cigarettes (p.72)


# ------------------------------------------------------------------------------------------- unmapped never match
def test_unmapped_rows_never_match(db):
    c, _ = db
    n = c.execute("SELECT COUNT(*) FROM fed_rules WHERE match_level = 'unmapped'").fetchone()[0]
    assert n >= 40
    assert c.execute("SELECT COUNT(*) FROM fed_rules WHERE match_level = 'unmapped' AND code_norm IS NOT NULL").fetchone()[0] == 0
    unmapped_ids = {r[0] for r in c.execute("SELECT id FROM fed_rules WHERE match_level = 'unmapped'")}
    tariff = json.loads((PROC / "tariff_2026_27.json").read_text(encoding="utf-8"))
    codes = [r["code"].replace(".", "") for r in tariff["rows"]]
    for code in codes[::7]:
        for date in ("2025-12-01", "2026-07-15"):
            got = get_rule_on_date(c, "fed_rules", code, date)
            assert not any(r["id"] in unmapped_ids for r in got)
    # fertilizers (S.No 62, 'Respective heading') do not attach to a Chapter 31 code
    assert get_fed_on_date(c, "31021000", "2026-07-15") == {"applicable_first_schedule": [], "local_only_not_applied": [], "possible_exemptions": []}


# ------------------------------------------------------------------------------------------- Third Schedule and validators
def test_third_schedule_rows_are_exemptions_never_applied(db):
    c, _ = db
    res = get_fed_on_date(c, "27079910", "2026-07-15")
    ex = res["possible_exemptions"]
    assert [r["s_no"] for r in ex] == ["11"] and ex[0]["rate_kind"] == "exempt" and ex[0]["page"] == 90   # carbon black oil, p.90
    assert res["applicable_first_schedule"] == []
    assert c.execute("SELECT COUNT(*) FROM fed_rules WHERE schedule = 'Third' AND rate_kind <> 'exempt'").fetchone()[0] == 0


def test_validator_findings_logged_and_known():
    rows = list(csv.DictReader(open(PROC / "a6_fed_failures.csv", encoding="utf-8")))
    errors = [r for r in rows if r["severity"] == "error"]
    # the only error: Third Schedule S.No 6 prints 2710.1110, which is not a code of either tariff (logged, row needs_review)
    assert {(r["check"], r["s_no"]) for r in errors} == {("code_in_tariff", "6")}
    assert any(r["check"] == "band_continuity" for r in rows)       # 3001 cc falls in no engine-capacity band (printed gap)
    st = json.loads((PROC / "a6_fed_validation.json").read_text(encoding="utf-8"))
    for y in ("2025", "2026"):
        assert st["reports"][y]["serial_gaps"] == [] and st["reports"][y]["live_serials_not_found_by_coordinates"] == []
    assert st["reports"]["second_source_FA2026"]["rows_checked"] == st["reports"]["second_source_FA2026"]["rows_ok"] > 0
    assert set(st["reports"]["red_rows_2025_table_I"]) == {"64"}


def test_every_year_difference_is_explained_by_a_finance_act_clause():
    diff = list(csv.DictReader(open(PROC / "a6_fed_diff_2025_2026.csv", encoding="utf-8")))
    assert diff and all(d["explained_by"].startswith("Finance Act 2026") for d in diff)
    assert {d["s_no"] for d in diff if d["table"] == "I"} == {"7a", "8a", "55", "55A", "55B", "59", "63", "65"}
    assert all(d["red_in_2026_pdf"] == "True" for d in diff if d["table"] == "I")


# ------------------------------------------------------------------------------------------- parser units
def test_words_to_number():
    assert words_to_number("three hundred and ninety".split()) == 390
    assert words_to_number("one thousand and two hundred".split()) == 1200
    assert words_to_number("five thousand and fifty".split()) == 5050
    assert words_to_number("sixteen thousand five hundred".split()) == 16500
    assert words_to_number("forty four thousand".split()) == 44000
    assert words_to_number("one hundred and ten thousand".split()) == 110000


def test_parse_rate_examples():
    r = parse_rate("Seventeen rupees and eighteen paisa per hundred cubic meters.")
    assert (float(r["amount"]), r["unit"], r["kind"]) == (17.18, "100 m3", "specific")
    r = parse_rate("Sixty five percent of retail price or rupees ten thousand per kg whichever is higher.")
    assert (r["kind"], float(r["pct"]), float(r["amount"]), r["unit"], r["basis"]) == ("compound", 65, 10000, "kg", "retail_price")
    r = parse_rate("Rupees two thousand per fan with effect from the 1st day of January, 2024")
    assert (float(r["amount"]), r["unit"]) == (2000, "fan") and "1st day of January" in r["effective_note"]
    r = parse_rate("86%ad val")
    assert (r["kind"], float(r["pct"]), r["basis"]) == ("percent", 86, "ad_valorem")


def test_parse_band_and_codes():
    assert parse_band("of cylinder capacity from 1001cc to 1799cc") == {"cc_ge": 1001, "cc_le": 1799}
    assert parse_band("of cylinder capacity exceeding 3001cc") == {"cc_gt": 3001}
    assert parse_band("of cylinder capacity 2000cc and above but not exceeding 3000cc") == {"cc_ge": 2000, "cc_le": 3000}
    assert parse_band("exceeding USD seventy-five thousand and upto USD one hundred and ten thousand") == {"usd_gt": 75000, "usd_le": 110000}
    assert parse_codes("87.03 8704.2190 8704.3190") == [("8704" "2190", "code8"), ("8704" "3190", "code8"), ("8703", "heading4")]
    assert parse_codes("Respective headings") == [("", "unmapped")]
