"""search_codes: keyword and code lookup over the dated store. The search is faked (no models, no network); the store is the real one."""
from pathlib import Path

import pytest

from src.tools.code_lookup import search_codes

pytestmark = pytest.mark.skipif(not Path("data/processed/legal_store.sqlite").exists(), reason="legal store not built")
D = "2026-10-18"


def fake(hits):
    return lambda q, d, k: hits


LINE = lambda c: {"kind": "line", "code": c}    # noqa: E731


def test_a_code_goes_to_the_exact_lookup():
    r = search_codes("8471.3010", D)
    assert r["mode"] == "code" and r["status"] == "found" and r["result"]["code_norm"] == "84713010"
    assert search_codes("8471", D)["result"]["status"] == "not_a_full_code"


def test_keyword_hits_are_reread_from_the_store_with_cd_page_and_source():
    r = search_codes("laptop", D, k=3, retriever=fake([LINE("84713010"), LINE("84713010"), {"kind": "heading", "code": "8471"}, LINE("84713020")]))
    assert r["status"] == "ok" and [x["code"] for x in r["results"]] == ["8471.3010", "8471.3020"]      # duplicate and heading dropped
    x = r["results"][0]
    assert x["cd_text"].endswith("%") and x["page"] and x["source_file"] and x["rank"] == 1 and "agent" in r["agent_hint"]


def test_chapter_and_duty_filters_and_no_match():
    hits = [LINE("84713010"), LINE("85076000"), LINE("85063000")]
    assert [x["code"] for x in search_codes("x", D, chapter="85", retriever=fake(hits))["results"]] == ["8507.6000", "8506.3000"]
    assert [x["code"] for x in search_codes("x", D, cd_pct="10", retriever=fake(hits))["results"]] == ["8507.6000", "8506.3000"]
    r = search_codes("zzz", D, retriever=fake([]))
    assert r["status"] == "no_match" and r["note"]


def test_bad_input_and_date_outside_the_store():
    assert search_codes("", D)["status"] == "invalid_input"
    assert search_codes("laptop", "not a date", retriever=fake([]))["status"] == "invalid_input"
    assert search_codes("laptop", D, cd_pct="abc", retriever=fake([LINE("84713010")]))["status"] == "invalid_input"
    assert search_codes("84713010", "2019-01-01")["status"] == "date_outside_store"
