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
    assert not any(r["status"] == "accepted" and "code_out_of_order" in r["issues"] for r in rows)


def test_a_misprinted_code_row_is_rejected_and_the_in_order_row_is_used(built):
    _, rows = built
    sixes = [r for r in rows if r["code"] == "85078000"]          # sr 5888 prints 8507.8000 between 8507.3000 and 8507.5000 (a misprint); sr 5891 is the real line
    assert {r["sr_no"]: r["status"] for r in sixes}[5888] == "rejected" and {r["sr_no"]: r["status"] for r in sixes}[5891] == "accepted"
    assert [r["year_7"] for r in sixes if r["sr_no"] == 5891] == ["3.33"]
