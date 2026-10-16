"""A7: Fifth Schedule rules (FY2026-27 text). Expected values were read from the page images of
data/raw/2026825118858478FifthSchedule2026-27.pdf (page numbers in the comments), not from memory."""
import csv
import json
from pathlib import Path

import pytest

from src.ingest.a7_fifth import norm_codes, parse_rate

PROC = Path("data/processed")
pytestmark = pytest.mark.skipif(not (PROC / "a7_fifth_rules.csv").exists(), reason="A7 files not built")


@pytest.fixture(scope="module")
def rules():
    return list(csv.DictReader(open(PROC / "a7_fifth_rules.csv", encoding="utf-8")))


def find(rules, **kw):
    return [r for r in rules if all(r[k] == v for k, v in kw.items())]


def test_every_row_is_dated_and_sourced(rules):
    assert len(rules) > 1200
    for r in rules:
        assert r["valid_from"] == "2026-07-01" and r["valid_to"] == "9999-12-31"
        assert r["source_file"].endswith("FifthSchedule2026-27.pdf") and int(r["page"]) >= 2
        assert r["s_no"] and r["part"]


# page 3: Part I S.No 1 C(1) submersible pumps 8413.7011 and 8413.7019 at 0%
def test_part1_agricultural_pumps(rules):
    got = [r for r in find(rules, part="I", s_no="1", page="3") if r["code_norm"] in ("84137011", "84137019")]
    assert {r["code_norm"] for r in got} == {"84137011", "84137019"}
    assert all(r["rate_raw"] == "0%" and r["rate_kind"] == "percent" for r in got)


# page 3: F(1) milk chillers 8418.6910 / 8418.6990 at 2%
def test_part1_milk_chillers_two_percent(rules):
    got = find(rules, part="I", s_no="1", page="3", code_norm="84186910")
    assert got and got[0]["rate_pcts"] == '["2"]'


# page 11: S.No 17 (7) "Respective headings" with the slab list 0%,3%,5% is not tied to a code
def test_part1_respective_headings_slab_list(rules):
    got = [r for r in find(rules, part="I", s_no="17", page="11") if r["match_level"] == "unmapped"]
    assert got and json.loads(got[0]["rate_pcts"]) == ["0", "3", "5"]


# page 19: S.No 39 tourism entries are "50% of the prevailing rate": a fraction, not a plain rate
def test_part1_tourism_fraction(rules):
    got = find(rules, part="I", s_no="39", code_norm="94061090")
    assert got and got[0]["rate_kind"] == "fraction_of_first_schedule" and got[0]["rate_fraction_pct"] == "50"
    # the rate is printed on page 19 and carried over the page break to pages 20-21 (flagged, not silent)
    far = find(rules, part="I", s_no="39", code_norm="84186990")
    assert far and far[0]["rate_kind"] == "fraction_of_first_schedule" and "rate_carried_over_page_break" in far[0]["issues"]


# page 23: Part II Table A (API) serial 1 Acyclovir 2933.5990 customs duty 0
def test_part2_table_a_first_rows(rules):
    r = find(rules, part="II", table="A", s_no="1")
    assert len(r) == 1 and r[0]["code_norm"] == "29335990" and r[0]["rate_pcts"] == '["0"]' and r[0]["page"] == "23"
    assert find(rules, part="II", table="A", s_no="2")[0]["code_norm"] == "29339990"


# page 45: S.No 108 (iv) polyester rigid film 3920.6310 5%
def test_part3_polyester_film(rules):
    got = [r for r in find(rules, part="III", s_no="108") if r["code_norm"] == "39206310"]
    assert got and got[0]["rate_raw"] == "5%" and got[0]["page"] == "45"
    assert "Sales Tax registered person" in got[0]["conditions"]


# page 49: Part IV S.No 15 textile machinery 8446.1000 at 0%; the other 39 rows of the table print "Omitted"
def test_part4_textile_machinery(rules):
    got = find(rules, part="IV", code_norm="84461000")
    assert got and got[0]["rate_raw"] == "0%" and got[0]["page"] == "49"
    assert len(find(rules, part="IV")) == 6


# page 56: Part VI aircraft 8802.4000 0% ; page 56: Part VIII seed potatoes 0701.1000 duty 5
def test_aviation_and_border_markets(rules):
    assert find(rules, part="VI", code_norm="88024000")[0]["rate_raw"] == "0%"
    assert find(rules, part="VIII", code_norm="07011000")[0]["rate_raw"] == "5"


def test_part_sections_present(rules):
    parts = {r["part"] for r in rules}
    assert {"I", "II", "III", "IV", "V(A)", "V(B)", "V(C)", "VI", "VIII"} <= parts


def test_validators_ran_and_page_text_complete():
    fails = list(csv.DictReader(open(PROC / "a7_fifth_failures.csv", encoding="utf-8")))
    checks = {f["check"] for f in fails}
    # every 8-digit code printed in a code column of the PDF text is in the parsed rows
    assert "code_in_page_text_not_in_parsed_rows" not in checks
    assert "serial_gap" not in checks and "serial_not_increasing" not in checks


def test_spot_check_sheet_covers_ten_percent(rules):
    sheet = list(csv.DictReader(open(PROC / "spotcheck_a7_fifth.csv", encoding="utf-8")))
    assert len(sheet) >= 0.10 * len(rules)


def test_parse_rate_cases():
    assert parse_rate("0%,3%, 5%")[:2] == ("percent", ["0", "3", "5"])
    assert parse_rate("0% 0%")[:2] == ("percent", ["0"])
    assert parse_rate("50% of the prevailing rate of customs duty")[0] == "fraction_of_first_schedule"
    assert parse_rate("Nil")[0] == "nil"
    assert parse_rate('20\u201d.')[:2] == ("percent", ["20"])
    assert parse_rate("1% (notwithstanding the rate of customs duty ...)")[0] == "other"
    assert parse_rate("")[0] == "none"


def test_norm_codes():
    assert norm_codes("8701.9220 8701.9320")[0] == ["87019220", "87019320"]
    assert norm_codes("Respective headings")[2] is True
    assert norm_codes("PCT code 85.07")[:2] == (["8507"], ["heading4"])


# ---------------------------------------------------------------- FY2025-26 file (202585238495687Fifth-Schedule.pdf, FBR)
@pytest.fixture(scope="module")
def rules25():
    return list(csv.DictReader(open(PROC / "a7_fifth_rules_2025_26.csv", encoding="utf-8")))


def test_2025_26_dates_and_source(rules25):
    assert len(rules25) > 1400
    for r in rules25:
        assert r["valid_from"] == "2025-07-01" and r["valid_to"] == "2026-06-30" and r["source_file"] == "202585238495687Fifth-Schedule.pdf"


# page 38 of the FY2025-26 file: S.No 36 (i) tubes/pipes 7303.0000 0%; S.No 37 8544.6090 11%; S.No 38 5%; S.No 39 tourism 50% of the prevailing rate
def test_2025_26_page_38_rows(rules25):
    a = find(rules25, part="I", s_no="36", code_norm="73030000")
    assert a and a[0]["rate_raw"] == "0%" and a[0]["page"] == "38"
    assert find(rules25, part="I", s_no="37", code_norm="85446090")[0]["rate_raw"] == "11%"
    t = find(rules25, part="I", s_no="39", code_norm="94061090")
    assert t and t[0]["rate_kind"] == "fraction_of_first_schedule"


def test_2025_26_table_e_diagnostic_kits_exist_only_in_2025(rules25, rules):
    # Part II Table E (3822.0000 diagnostic kits) is printed in the FY2025-26 file and "[Omitted]" in the FY2026-27 file (p.41)
    assert [r for r in rules25 if r["part"] == "II" and r["table"] == "E"]
    assert not [r for r in rules if r["part"] == "II" and r["table"] == "E"]


def test_2025_26_validators_clean_of_structural_failures():
    fails = list(csv.DictReader(open(PROC / "a7_fifth_failures_2025_26.csv", encoding="utf-8")))
    checks = {f["check"] for f in fails}
    assert "code_in_page_text_not_in_parsed_rows" not in checks and "serial_gap" not in checks


def test_diff_report_exists_and_records_a_real_rate_change():
    d = list(csv.DictReader(open(PROC / "a7_fifth_diff_2025_26_vs_2026_27.csv", encoding="utf-8")))
    # S.No 27 motor vehicles for the transport of goods: 20% in the FY2025-26 file (p.29), 10% in the FY2026-27 file (p.16)
    x = [r for r in d if r["part"] == "I" and r["s_no"] == "27" and r["key"] == "87041090"]
    assert x and x[0]["change"] == "rate_changed" and x[0]["rate_2025_26"] == "20%" and x[0]["rate_2026_27"] == "10%"


def test_spot_check_2025_26(rules25):
    sheet = list(csv.DictReader(open(PROC / "spotcheck_a7_fifth_2025_26.csv", encoding="utf-8")))
    assert len(sheet) >= 0.10 * len(rules25)
