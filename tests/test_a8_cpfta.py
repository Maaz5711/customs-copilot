"""A8: China-Pakistan FTA Phase II (SRO 1640(I)/2019) read from the scan. Expected values were read by eye from the page images
(data/raw/cpfta/...SRO1640(I)2019dated31.12.2019.pdf; page numbers in the comments), an AI second reader, not the owner."""
import csv
import json
from pathlib import Path

import pytest

from src.ingest.a8_cpfta import NYEARS, parse_number, taper
from src.store import connect, get_rule_on_date
from src.store.build import build

PROC = Path("data/processed")
pytestmark = pytest.mark.skipif(not (PROC / "a8_cpfta_rows.csv").exists(), reason="A8 files not built")


@pytest.fixture(scope="module")
def rows():
    return {r["code"]: r for r in csv.DictReader(open(PROC / "a8_cpfta_rows.csv", encoding="utf-8")) if r["code"]}


def vals(r):
    return [r[f"year_{i}"] for i in range(1, 16)]


def test_size_and_serials():
    allrows = list(csv.DictReader(open(PROC / "a8_cpfta_rows.csv", encoding="utf-8")))
    summary = json.load(open(PROC / "a8_cpfta_validation.json", encoding="utf-8"))
    assert summary["pages_read"] == 177 and 6700 <= len(allrows) <= 6786 and summary["last_sr_no"] == 6786
    assert summary["sr_no_missing"] <= 12            # lines the OCR did not read are listed in the failures report, never invented
    srs = [int(r["sr_no"]) for r in allrows]
    assert len(set(srs)) == len(srs)


def test_every_line_follows_a_printed_pattern_or_is_flagged():
    for r in csv.DictReader(open(PROC / "a8_cpfta_rows.csv", encoding="utf-8")):
        if r["reading"] == "ocr_fitted_to_taper_pattern":
            b = float(r["base_rate"])
            s, e = int(r["start_year"]), (int(r["end_year"]) if r["end_year"] else None)
            want = [b] * NYEARS if e is None else taper(b, s, e)
            assert vals(r) == [f"{v:.2f}" for v in want], r["sr_no"]
        else:
            assert r["status"] == "needs_review"


# page 17: Sr.No 567 09024020 black tea 5.00 ... 0.00 (7-year taper, A07); 575 09042110 red chillies 12.00 in every year; 592 09083120 small cardamoms 2.50 A07;
# 600 09101100 ginger 5.00, 5.00, 5.00, 4.58 ... (A15)
@pytest.mark.parametrize("code,y6,y7,y8", [("09024020", "0.83", "0.00", "0.00"), ("09042110", "12.00", "12.00", "12.00"),
                                           ("09083120", "0.42", "0.00", "0.00"), ("09101100", "3.75", "3.33", "2.92")])
def test_page_17_rows(rows, code, y6, y7, y8):
    r = rows[code]
    assert r["page"] == "17" and (r["year_6"], r["year_7"], r["year_8"]) == (y6, y7, y8)


# page 100: 62062000 20.00 flat then 18.33, 16.67, 15.00, 13.33, 11.67 (A15); 62072200 16.00 flat; 62046290 20.00 flat
@pytest.mark.parametrize("code,y6,y7,y8", [("62062000", "15.00", "13.33", "11.67"), ("62072200", "16.00", "16.00", "16.00"), ("62046290", "20.00", "20.00", "20.00")])
def test_page_100_rows(rows, code, y6, y7, y8):
    r = rows[code]
    assert r["page"] == "100" and (r["year_6"], r["year_7"], r["year_8"]) == (y6, y7, y8)


# page 3: 02071200 25.00 25.00 25.00 22.92 20.83 18.75 16.67 14.58 ... (A15); 02050000 20.00, 16.67, 13.33, 10.00, 6.67, 3.33, 0.00 (A07); 02071100 20.00 flat
@pytest.mark.parametrize("code,y6,y7,y8", [("02071200", "18.75", "16.67", "14.58"), ("02050000", "3.33", "0.00", "0.00"), ("02071100", "20.00", "20.00", "20.00")])
def test_page_3_rows(rows, code, y6, y7, y8):
    r = rows[code]
    assert r["page"] == "3" and (r["year_6"], r["year_7"], r["year_8"]) == (y6, y7, y8)


def test_ocr_number_reading_rules():
    assert parse_number("20.83") == (20.83, "exact")
    assert parse_number("00'0") == (0.0, "repaired")      # a printed 0.00 whose point was read as a quote
    assert parse_number("833") == (8.33, "repaired")
    assert parse_number("EE8")[0] is None


def test_fba_category_cross_check_is_close():
    s = json.load(open(PROC / "a8_cpfta_validation.json", encoding="utf-8"))
    z = s["fbr_category_cross_check"]
    assert abs(z["reading_constant_zero_lines"] - z["fbr_A0_lines"]) <= 100         # FBR: 3,251 A0 lines


def test_spot_check_sheet_covers_ten_percent():
    sheet = list(csv.DictReader(open(PROC / "spotcheck_a8_cpfta.csv", encoding="utf-8")))
    total = len(list(csv.DictReader(open(PROC / "a8_cpfta_rows.csv", encoding="utf-8"))))
    assert len(sheet) >= 0.10 * total


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("a8") / "store.sqlite"
    build(path)
    c = connect(path)
    yield c
    c.close()


def test_store_rows_are_dated_by_calendar_year(db):
    # 02071200 (Sr.No 74, A15, base 25): 2025 column 18.75, 2026 column 16.67, 2027 column 14.58, from the page-3 image
    def rate(d):
        x = [r for r in get_rule_on_date(db, "fta_rules", "0207.1200", d)]
        assert len(x) == 1 and x[0]["page"] == 3
        return x[0]["rate_pct"], x[0]["valid_from"], x[0]["valid_to"]

    assert rate("2025-09-01") == (18.75, "2025-01-01", "2025-12-31")
    assert rate("2026-06-30") == (16.67, "2026-01-01", "2026-12-31")
    assert rate("2026-07-01") == (16.67, "2026-01-01", "2026-12-31")
    assert rate("2027-01-01") == (14.58, "2027-01-01", "2027-12-31")
    assert get_rule_on_date(db, "fta_rules", "0207.1200", "2024-12-31") == []        # older years are out of scope and not loaded


def test_notification_row_in_sros(db):
    s = get_rule_on_date(db, "sros", "1640(I)/2019", "2026-08-01")
    assert s and s[0]["valid_from"] == "2020-01-01" and s[0]["instrument_kind"] == "CD"
