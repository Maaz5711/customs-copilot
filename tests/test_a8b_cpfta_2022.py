"""SRO 1181(I)/2022 China FTA table: parser checks on known rows of the real file (skipped when the PDF is not in data/raw)."""
from pathlib import Path

import pytest

from src.ingest import a8b_cpfta_2022 as a8b

pytestmark = pytest.mark.skipif(not a8b.PDF.exists() or not Path("data/processed/tariff_2026_27.csv").exists(), reason="source files not present")


@pytest.fixture(scope="module")
def built():
    rows, fails = a8b.build()
    return {r["code"]: r for r in rows}, rows


def test_a_taper_row_is_read_and_fitted(built):
    by, _ = built
    r = by["14049041"]                      # sr 747, page 24: 16.00, 13.33 ... 0.00 (A07 taper from 16%)
    assert r["status"] == "accepted" and r["pattern"] == "A07_taper_to_zero_year7"
    assert (r["year_6"], r["year_7"], r["year_8"]) == ("2.67", "0.00", "0.00")


def test_constant_taper_and_a15_rows(built):
    by, _ = built
    assert by["14049050"]["pattern"] == "constant_zero"
    assert by["14049090"]["pattern"] == "A15_taper_year3_to_15" and by["14049090"]["year_7"] == "16.67"


def test_specific_duty_rows_are_not_turned_into_percentages(built):
    by, _ = built
    r = by["15071000"]                      # sr 764, "Rs. 7240.0/MT"
    assert r["status"] == "unsupported_specific_duty"
    assert not any(x["code_norm"] == "15071000" for x in a8b.long_rules(list(by.values())))


def test_no_exemption_years_are_counted_not_guessed(built):
    by, _ = built
    r = by["87082919"]                      # sr 6296, page 200: 'no exemption' for the first two years, 28.00 after
    assert r["status"] in ("accepted", "needs_review") and r["year_7"] == "28.00" and "no_exemption_printed_for_first_2_years" in r["issues"]


def test_serials_are_continuous_for_almost_all_rows(built):
    _, rows = built
    assert len(rows) > 6800 and sum(1 for r in rows if r["status"] == "accepted") > 6500
    assert not any(r["status"] == "accepted" and "code_not_ascending" in r["issues"] for r in rows)
