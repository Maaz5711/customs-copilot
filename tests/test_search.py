"""Tests for src/search. Needs the index: python -m src.search.build"""
import pytest

from src.search import search
from src.search.engine import INDEX_DIR, extract_codes

pytestmark = pytest.mark.skipif(
    not (INDEX_DIR / "tariff" / "emb.npy").exists(), reason="search index not built (python -m src.search.build)"
)

FY27, FY26 = "2026-07-15", "2025-12-01"


def chapters(hits):
    return [h["code"][:2] for h in hits if h.get("code")]


def test_extract_codes():
    assert extract_codes("8703.2115") == (["87032115"], True)
    assert extract_codes("87.03") == (["8703"], True)
    assert extract_codes("8703") == (["8703"], True)
    assert extract_codes("duty on 8703.2115 please")[0] == ["87032115"]
    assert extract_codes("used car 1800cc") == ([], False)


def test_exact_8_digit_lookup():
    hits = search("8703.2115", index="tariff", as_of_date=FY27)
    assert hits[0]["code"] == "87032115" and hits[0]["method"] == "exact_code"
    assert hits[0]["fy"] == "2026-27"
    for h in hits:
        assert h["source_file"] and h["page"] and h["id"]


def test_exact_heading_lookup_returns_heading_and_children():
    hits = search("8703", index="tariff", as_of_date=FY27, k=20)
    assert hits[0]["kind"] == "heading" and hits[0]["code"] == "8703"
    assert all(h["method"] == "exact_code" for h in hits)
    assert any(h["code"].startswith("8703") and len(h["code"]) == 8 for h in hits)


def test_exact_code_in_sro_index_finds_covering_heading_row():
    hits = search("0105.1100", index="sro", as_of_date=FY27)
    assert any(h["sro"] == "1064(I)/2026" and h["code"] == "01051100" for h in hits)


@pytest.mark.parametrize("query,chapter_set", [
    ("frozen chicken", {"02"}),
    ("mobile phone", {"85"}),
    ("used car 1800cc", {"87"}),
])
def test_natural_language_chapter(query, chapter_set):
    hits = search(query, index="tariff", as_of_date=FY27, k=10)
    assert set(chapters(hits[:5])) & chapter_set, [h["text"][:80] for h in hits[:5]]


def test_date_filter_separates_fiscal_years():
    h27 = search("frozen chicken", index="tariff", as_of_date=FY27, k=10)
    h26 = search("frozen chicken", index="tariff", as_of_date=FY26, k=10)
    assert h27 and h26
    assert {h["fy"] for h in h27} == {"2026-27"}
    assert {h["fy"] for h in h26} == {"2025-26"}
    # boundaries are inclusive
    assert {h["fy"] for h in search("8703.2115", index="tariff", as_of_date="2026-06-30")} == {"2025-26"}
    assert {h["fy"] for h in search("8703.2115", index="tariff", as_of_date="2026-07-01")} == {"2026-27"}


def test_date_filter_on_sro_versions():
    new = search("regulatory duty live poultry", index="sro", as_of_date="2026-07-01")
    old = search("regulatory duty live poultry", index="sro", as_of_date="2026-06-30")
    assert all("1064" in h["sro"] or "1065" in h["sro"] or "1063" in h["sro"] for h in new)
    assert all(("1152" in h["sro"] or "1151" in h["sro"] or "1898" in h["sro"] or "1065" in h["sro"]) for h in old)


def test_no_date_returns_both_years():
    hits = search("8703.2115", index="tariff")
    assert {h["fy"] for h in hits} == {"2025-26", "2026-27"}


def test_bad_date_and_index_raise():
    with pytest.raises(ValueError):
        search("x", as_of_date="2026-13-45")
    with pytest.raises(ValueError):
        search("x", index="nope")


def test_every_hit_is_citable_across_all_indexes():
    hits = search("classification of curing chamber dryer", k=12, as_of_date=FY27)
    assert {h["index"] for h in hits} >= {"tariff", "rulings"}
    for h in hits:
        for f in ("id", "source_file", "page", "valid_from", "valid_to", "text"):
            assert h[f], (h["id"], f)


def test_rulings_index_finds_massage_chair_ruling():
    hits = search("massage chair valuation", index="rulings", k=5)
    assert "2110" in hits[0]["ruling"] or any("2110" in h["ruling"] for h in hits[:3])
