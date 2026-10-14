"""Tests for the ground-truth evaluation cases (C2-prep). No LLM, no network."""
import copy
import re
from pathlib import Path

import pytest

from src.eval import validate_cases as v

GT = v.GT_DIR


@pytest.fixture(scope="module")
def tariffs():
    return v.load_tariffs()


@pytest.fixture(scope="module")
def real():
    return v.read_csv(GT / v.REAL_FILE)


@pytest.fixture(scope="module")
def syn():
    return v.read_csv(GT / v.SYN_FILE)


@pytest.fixture(scope="module")
def sample():
    return v.read_csv(GT / v.SAMPLE_FILE)


def test_all_files_exist():
    for name in (v.REAL_FILE, v.OOS_FILE, v.SYN_FILE, v.SAMPLE_FILE, "README.md"):
        assert (GT / name).exists(), name


def test_validate_all_is_clean():
    problems, stats = v.validate_all()
    assert problems == []
    assert stats["real"] >= 40 and stats["synthetic"] == 60 and stats["owner_review_sample"] == 20


def test_every_real_code_exists_in_its_fiscal_year(real, tariffs):
    for r in real:
        fy = v.fy_for_date(r["as_of_date"])
        assert fy in ("FY2025-26", "FY2026-27"), r["id"]
        assert r["fiscal_year"] == fy
        assert v.code_exists(r["expected_code"], fy, tariffs), (r["id"], r["expected_code"])


def test_real_cases_have_a_url_and_a_reference(real):
    for r in real:
        assert r["source_url"].startswith("http"), r["id"]
        assert r["source_ref"].strip() and r["page_or_section"].strip(), r["id"]
        assert r["source"] in v.SOURCES


def test_real_descriptions_are_short(real):
    assert max(len(r["description"].split()) for r in real) <= v.MAX_REAL_WORDS


def test_real_level_notes_match_code_length(real):
    for r in real:
        assert v._level_ok(r["expected_code"], r["expected_level_note"]), r["id"]
    levels = {len(v.digits(r["expected_code"])) for r in real}
    assert levels <= {4, 6, 8} and 8 in levels


def test_out_of_scope_rows_have_reasons_and_missing_codes(tariffs):
    rows = v.read_csv(GT / v.OOS_FILE)
    assert len(rows) >= 1
    for r in rows:
        assert r["reason"].strip()
        fy = v.fy_for_date(r["as_of_date"])
        if r["reason"].startswith("Printed code"):
            assert not v.code_exists(r["expected_code"], fy, tariffs), r["id"]


def test_synthetic_cases_are_labelled_unverified(syn):
    assert len(syn) == 60
    for r in syn:
        assert r["verified"] == "false"
        assert v.LABEL_TEXT in r["label"]


def test_synthetic_behaviour_mix(syn):
    kinds = {r["expected_behavior"] for r in syn}
    assert kinds == v.BEHAVIORS
    clarify = [r for r in syn if r["expected_behavior"] == "not_sure_or_clarify"]
    assert len(clarify) >= 5 and all(r["candidate_headings"].strip() for r in clarify)
    refuse = [r for r in syn if r["expected_behavior"] == "refuse"]
    assert len(refuse) >= 2 and all(not r["expected_code"] for r in refuse)


def test_synthetic_answers_exist_in_the_tariff_of_their_date(syn, tariffs):
    answers = [r for r in syn if r["expected_behavior"] == "answer"]
    assert len(answers) >= 40
    for r in answers:
        fy = v.fy_for_date(r["as_of_date"])
        assert v.code_exists(r["expected_code"], fy, tariffs), (r["id"], r["expected_code"], fy)


def test_synthetic_hard_case_categories_are_covered(syn):
    tags = ";".join(r["hardness_tags"] for r in syn)
    for needed in ("parts_vs_complete", "used", "set_gri3b", "residual_other", "vehicle_cc", "ckd", "cbu", "mobile",
                   "specific_duty", "chapter99_special", "composite_gri3", "clarify_missing_info", "date_dependent_line"):
        assert needed in tags, needed


def test_date_dependent_twin_cases_use_different_codes(syn):
    twins = [r for r in syn if "date_dependent_line" in r["hardness_tags"]]
    assert len(twins) == 2
    assert {r["expected_code"] for r in twins} == {"6309.0000", "6309.1010"}
    assert {r["fiscal_year"] for r in twins} == {"FY2025-26", "FY2026-27"}


def test_synthetic_descriptions_do_not_leak_the_answer(syn):
    for r in syn:
        if r["expected_behavior"] != "answer":
            continue
        assert r["expected_code"] not in r["description"], r["id"]
        assert v.digits(r["expected_code"]) not in re.sub(r"[^0-9]", "", r["description"]), r["id"]


def test_owner_sample_is_10_real_and_10_synthetic(sample, real, syn):
    assert len(sample) == 20
    assert sum(r["kind"] == "real" for r in sample) == 10
    assert sum(r["kind"] == "synthetic" for r in sample) == 10
    real_ids = {r["id"] for r in real}
    syn_ids = {r["id"] for r in syn}
    for r in sample:
        assert r["case_id"] in (real_ids if r["kind"] == "real" else syn_ids)
        assert "owner_agrees_Y_or_N" in r and "owner_correction" in r


def test_readme_counts_match_the_csv_files(real, syn, sample):
    text = (GT / "README.md").read_text(encoding="utf-8")
    m = re.search(r"Counts \(checked by tests\): real=(\d+); real_out_of_scope=(\d+); synthetic=(\d+); owner_review_sample=(\d+)", text)
    assert m, "README must contain the counts line"
    oos = v.read_csv(GT / v.OOS_FILE)
    assert tuple(map(int, m.groups())) == (len(real), len(oos), len(syn), len(sample))
    low = text.lower()
    for phrase in ("small", "synthetic", "not been checked by a customs expert", "sample size"):
        assert phrase in low, phrase


# ---- the validator itself must catch mistakes
def test_validator_flags_a_code_that_is_not_in_the_tariff(real, tariffs):
    bad = copy.deepcopy(real[:1])
    bad[0]["expected_code"] = "9999.9999"
    bad[0]["expected_level_note"] = "8-digit as printed in the source"
    probs = v.validate_real(bad, tariffs)
    assert any("not in the" in p for p in probs)


def test_validator_flags_a_wrong_fiscal_year(real, tariffs):
    bad = copy.deepcopy(real[:1])
    bad[0]["as_of_date"] = "2019-01-01"
    probs = v.validate_real(bad, tariffs)
    assert any("outside FY2025-26 and FY2026-27" in p for p in probs)


def test_validator_flags_a_code_that_changed_between_years(real, tariffs):
    # 6309.0000 (worn clothing) is a line of FY2025-26 only, 6309.1010 of FY2026-27 only
    assert v.code_exists("6309.0000", "FY2025-26", tariffs) and not v.code_exists("6309.0000", "FY2026-27", tariffs)
    assert v.code_exists("6309.1010", "FY2026-27", tariffs) and not v.code_exists("6309.1010", "FY2025-26", tariffs)
    bad = copy.deepcopy(real[:1])
    bad[0].update(expected_code="6309.1010", expected_level_note="8-digit as printed in the source", as_of_date="2026-01-15", fiscal_year="FY2025-26")
    probs = v.validate_real(bad, tariffs)
    assert any("6309.1010 is not in the FY2025-26 tariff" in p for p in probs)


def test_validator_flags_unlabelled_or_leaking_synthetic_rows(syn, tariffs):
    bad = copy.deepcopy([r for r in syn if r["expected_behavior"] == "answer"][:1])
    bad[0]["verified"] = "true"
    bad[0]["label"] = ""
    bad[0]["description"] = "buy item " + bad[0]["expected_code"]
    probs = v.validate_synthetic(bad, tariffs)
    assert any("verified must be false" in p for p in probs)
    assert any("label must contain" in p for p in probs)
    assert any("contains the expected code" in p for p in probs)


def test_code_levels_prefix_logic(tariffs):
    assert v.code_exists("7210.49", "FY2025-26", tariffs)  # 6-digit prefix of 7210.4910 / 7210.4990
    assert not v.code_exists("7210.4999", "FY2025-26", tariffs)  # not an exact line
    assert v.code_exists("9902", "FY2026-27", tariffs)  # chapter 99 special entry
    assert v.code_exists("2710", "FY2026-27", tariffs)  # heading prefix
    assert not v.code_exists("123", "FY2026-27", tariffs)
