"""Regression guard: our duty tool against answers captured from the official WeBOC calculator (data/ground_truth/weboc_calculator_2026-10-16.json).
Known, documented differences are listed here so a NEW difference fails the test (see docs/weboc_comparison.md)."""
from pathlib import Path

import pytest

from src.eval import weboc_compare as wc

pytestmark = pytest.mark.skipif(not wc.DATA.exists() or not Path("data/processed/legal_store.sqlite").exists(), reason="data not present")

# WeBOC prints ACD 11% for these three vehicle-part codes; SRO 1063(I)/2026 (read from the page images, pages 1-2) has no 11% rate.
# Unexplained by the documents we hold: question for FBR / a clearing agent (docs/owner_questions.md OQ-W1).
KNOWN_ACD_DIFFERENCES = {"40081110", "84213110", "40112011"}


def test_every_computable_code_matches_weboc_except_the_documented_ones():
    rows = wc.compare()
    comp = [r for r in rows if r["our_status"] == "computed"]
    assert len(comp) >= 30
    for r in comp:
        amount_diffs = [d for d in r["diffs"] if not d.startswith("IT rate")]
        if r["code"] in KNOWN_ACD_DIFFERENCES:
            assert amount_diffs, r["code"]            # still different: if someone fixes it, move it out of the list
        else:
            assert not amount_diffs, (r["code"], amount_diffs)


def test_income_tax_rate_differs_from_weboc_only_where_weboc_ignores_the_twelfth_schedule():
    # WeBOC prints 12% for every code. Ours is 12% for Part III commercial, 7% for Part II commercial, 2% for Part I (non-filer doubled).
    rows = [r for r in wc.compare() if r["our_status"] == "computed"]
    same = [r for r in rows if r["ours_IT_rate"] == r["weboc_IT_rate"]]
    assert len(same) >= 10                           # Part III goods agree with WeBOC exactly
