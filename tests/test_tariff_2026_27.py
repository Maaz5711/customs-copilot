"""A1 tests. They need the original PDF in data/raw/ and skip when it is absent."""
import collections
from pathlib import Path

import pytest

from src.ingest import run_tariff

PDF = Path("data/raw") / run_tariff.TARIFFS["2026_27"][0]
pytestmark = pytest.mark.skipif(not PDF.exists(), reason="raw tariff PDF not present")


@pytest.fixture(scope="module")
def parsed():
    return run_tariff.run("2026_27")


def test_counts(parsed):
    headings, rows, special = parsed
    assert len(headings) == 1228  # 1017 printed + 211 derived from code (see test_heading_matches_code)
    assert len(rows) == 7605
    assert len({r["code"] for r in rows}) == 7605  # no duplicate codes
    assert len(special) == 56  # Chapter 99 four-digit codes


def test_rate_kinds(parsed):
    _, rows, _ = parsed
    kinds = collections.Counter(r["cd_kind"] for r in rows)
    assert kinds == {"plain": 7551, "specific": 54}


def test_every_row_has_dates_and_source(parsed):
    headings, rows, special = parsed
    for r in headings + rows + special:
        assert r["valid_from"] and r["valid_to"] and r["source_file"] and r["page"]


def test_plain_rates_in_range(parsed):
    _, rows, _ = parsed
    assert all(0 <= r["cd_plain"] <= 150 for r in rows if r["cd_kind"] == "plain")


def test_known_rows(parsed):
    _, rows, _ = parsed
    by = {r["code"]: r for r in rows}
    assert by["0101.2100"]["cd_plain"] == 0
    assert by["0103.1000"]["cd_plain"] == 20
    assert by["8703.2115"]["cd_plain"] == 30
    assert by["4009.2110"]["cd_plain"] == 25  # digits split by a gap in the PDF
    assert by["9706.9000"]["cd_plain"] == 0   # must not pick up the 9901 row's value
    assert by["1507.9000"]["cd_specific"] == {"amount": 11700.0, "unit": "MT"}
    assert by["8517.1310"]["cd_specific"] == {"amount": 250.0, "unit": "set"}
    assert by["3706.1000"]["cd_specific"] == {"amount": 5.0, "unit": "meter"}


def test_tariff_2025_26_counts():
    pdf = Path("data/raw") / run_tariff.TARIFFS["2025_26"][0]
    if not pdf.exists():
        pytest.skip("raw FY2025-26 tariff PDF not present")
    headings, rows, special = run_tariff.run("2025_26")
    assert len(headings) == 1228  # 1017 printed + 211 derived from code (see test_heading_matches_code)
    assert len(rows) == 7590
    assert len({r["code"] for r in rows}) == 7590
    assert collections.Counter(r["cd_kind"] for r in rows) == {"plain": 7536, "specific": 54}


def test_heading_matches_code(parsed):
    """A1 bug: heading line 11.03 is not in the text layer, so 1103.xxxx carried 11.02."""
    headings, rows, _ = parsed
    assert all(r["heading"] == r["code"][:2] + "." + r["code"][2:4] for r in rows)
    by = {h["heading"]: h for h in headings}
    assert len(by) == len(headings)  # unique
    assert by["11.03"]["derived_from_code"] is True
    assert {r["heading"] for r in rows if r["code"].startswith("1103.")} == {"11.03"}
    assert by["02.05"]["text"].startswith("Meat of horses")  # single-code heading, text from the code row
    assert sum(1 for h in headings if h.get("derived_from_code")) == 211
    assert {h["heading"] for h in headings} == {r["heading"] for r in rows}
