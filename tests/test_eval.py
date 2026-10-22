"""Tests for the evaluation harness (C2). No network: FakeLLM and the stub retriever from the agent tests."""
from pathlib import Path

import pytest

from src.agent import FakeLLM
from src.agent.llm import LLMRateLimited
from src.eval import metrics
from src.eval.cases import Case, load_cases, load_duty_cases
from src.eval.report import build
from src.eval.run import load_results, run, select
from src.eval.systems import leak_free, run_llm_rag, run_plain_llm
from tests.agent_fakes import StubRetriever

pytestmark = pytest.mark.skipif(not Path("data/ground_truth/cases_real.csv").exists(), reason="ground truth not present")


def case(id="X1", kind="real", expected="61091000", **kw):
    return Case(id=id, kind=kind, description="men's cotton T-shirts", as_of_date="2026-07-15", behavior="answer", expected=expected, **kw)


# ------------------------------------------------------------------ metrics
def test_wilson_interval_known_values():
    lo, hi = metrics.wilson(8, 10)
    assert 0.49 < lo < 0.50 and 0.94 < hi < 0.95            # standard Wilson 95% for 8/10
    assert metrics.wilson(0, 0) == (0.0, 0.0)
    assert metrics.wilson(0, 5)[0] == 0.0 and metrics.wilson(5, 5)[1] == 1.0


def test_hit_at_levels_and_short_expected_code():
    assert metrics.hit_at(["61091000"], ["61091000"], 8, 1) is True
    assert metrics.hit_at(["61099090"], ["61091000"], 6, 1) is False
    assert metrics.hit_at(["61099090"], ["61091000"], 4, 1) is True
    assert metrics.hit_at(["99999999", "61091000"], ["61091000"], 8, 1) is False
    assert metrics.hit_at(["99999999", "61091000"], ["61091000"], 8, 5) is True
    assert metrics.hit_at(["61091000"], ["6109"], 8, 1) is None        # expected code only 4 digits: not scorable at 8
    assert metrics.hit_at(["39249000"], ["39269099", "39249000"], 8, 1) is True      # accepted alternative


def test_code_metrics_counts_n_per_cell():
    rows = [dict(expected=["61091000"], pred=["61091000"]), dict(expected=["6109"], pred=["61099090"]), dict(expected=["84151021"], pred=[])]
    m = metrics.code_metrics(rows)
    assert m[(1, 8)] == (1, 2) and m[(1, 4)] == (2, 3)


def test_refusal_metrics():
    rows = [dict(expected_behavior="not_sure_or_clarify", behavior="not_sure_or_clarify", pred=["87032113"], candidate_headings=["8703"]),
            dict(expected_behavior="not_sure_or_clarify", behavior="answer", pred=["87032113"], candidate_headings=["8703"]),
            dict(expected_behavior="refuse", behavior="refuse", pred=[], candidate_headings=[]),
            dict(expected_behavior="answer", behavior="not_sure_or_clarify", pred=[], candidate_headings=[])]
    m = metrics.refusal_metrics(rows)
    assert m["not_sure_or_clarify"] == (1, 2) and m["refuse"] == (1, 1) and m["answer"] == (0, 1) and m["not_sure_shows_right_heading"] == (1, 1)


def test_duty_match_to_the_paisa():
    assert metrics.duty_match({"total_payable_pkr": "667380.00"}, "667380.00")
    assert not metrics.duty_match({"total_payable_pkr": "667380.05"}, "667380.00")
    assert not metrics.duty_match(None, "1.00")


# ------------------------------------------------------------------ cases
def test_cases_load_with_the_documented_counts():
    cs = load_cases()
    assert sum(c.kind == "real" for c in cs) == 79 and sum(c.kind == "synthetic" for c in cs) == 60
    assert all(c.expected for c in cs if c.kind == "real") and all(len(c.expected) in (4, 6, 8) for c in cs if c.expected)
    assert len({c.id for c in cs}) == len(cs)
    assert load_duty_cases() and all(c.kind == "duty" for c in load_duty_cases())


# ------------------------------------------------------------------ systems
def test_plain_llm_keeps_invented_codes_so_they_can_be_scored_as_wrong():
    llm = FakeLLM({"eval_plain": {"behavior": "answer", "codes": ["6109.1000", "1234.5678"], "reason": "t-shirt"}})
    p = run_plain_llm(case(), llm)
    assert p["codes"] == ["61091000", "12345678"] and p["behavior"] == "answer"


def test_rag_only_keeps_offered_codes_and_states_how_many_were_dropped():
    llm = FakeLLM({"eval_rag": {"behavior": "answer", "codes": ["6109.1000", "1234.5678"], "reason": "x"}})
    p = run_llm_rag(case(), llm, retriever=StubRetriever())
    assert p["codes"] == ["61091000"] and "1 codes dropped" in p["note"]
    assert "6109.1000" in llm.calls[0]["prompt"]


def test_not_sure_and_refuse_map_to_expected_behaviour_names():
    llm = FakeLLM({"eval_plain": {"behavior": "not_sure", "codes": [], "reason": ""}})
    assert run_plain_llm(case(), llm)["behavior"] == "not_sure_or_clarify"
    llm = FakeLLM({"eval_plain": {"behavior": "refuse", "codes": [], "reason": ""}})
    assert run_plain_llm(case(), llm)["behavior"] == "refuse"


def test_leak_free_removes_the_cases_own_ruling_only():
    own = "202588981923512PublicNotice05-2025.pdf"
    other = "202571715701other.pdf"

    def retr(q, index, d, k):
        return [dict(source_file=f"data/raw/{own}"), dict(source_file="9999PublicNotice05-2025.pdf"), dict(source_file=other)] if index == "rulings" else [dict(source_file=own)]
    got = leak_free(retr, case(source_file=own))(" ", "rulings", "2026-01-01", 5)
    assert [h["source_file"] for h in got] == [other]
    assert leak_free(retr, case(source_file=own))(" ", "tariff", "2026-01-01", 5) == [dict(source_file=own)]      # only rulings are filtered
    assert leak_free(retr, case())(" ", "rulings", "2026-01-01", 5) == retr(" ", "rulings", "2026-01-01", 5)       # synthetic: nothing to remove


# ------------------------------------------------------------------ runner
def test_run_is_resumable_and_stops_cleanly_on_quota(tmp_path):
    cases = [case("A"), case("B"), case("C")]
    seq = [{"behavior": "answer", "codes": ["6109.1000"], "reason": ""}, LLMRateLimited("daily limit")]
    llm = FakeLLM({"eval_plain": seq})
    r = run(["plain_llm"], cases, llm, tmp_path, log=lambda *_: None)
    assert r["done"] == 1 and r["stopped"] and set(load_results("plain_llm", tmp_path)) == {"A"}
    llm2 = FakeLLM({"eval_plain": {"behavior": "answer", "codes": ["6109.1000"], "reason": ""}})
    r2 = run(["plain_llm"], cases, llm2, tmp_path, log=lambda *_: None)
    assert r2["done"] == 2 and r2["skipped"] == 1 and llm2.count("eval_plain") == 2 and set(load_results("plain_llm", tmp_path)) == {"A", "B", "C"}


def test_a_crash_is_saved_as_error_and_counted_wrong(tmp_path):
    llm = FakeLLM({"eval_plain": ValueError("boom")})
    run(["plain_llm"], [case("A")], llm, tmp_path, log=lambda *_: None)
    rec = load_results("plain_llm", tmp_path)["A"]
    assert rec["pred"]["behavior"] == "error" and "boom" in rec["pred"]["note"]


def test_sample_is_fixed_and_per_kind():
    cs = load_cases()
    a, b = select(cs, 5, 1, None), select(cs, 5, 1, None)
    assert [c.id for c in a] == [c.id for c in b] and sum(c.kind == "real" for c in a) == 5 and sum(c.kind == "synthetic" for c in a) == 5


# ------------------------------------------------------------------ report
def test_report_states_sizes_and_limits_and_never_mixes_kinds(tmp_path):
    real = next(c for c in load_cases() if c.kind == "real")
    syn = next(c for c in load_cases() if c.kind == "synthetic" and c.behavior == "answer")
    for c in (real, syn):
        llm = FakeLLM({"eval_plain": {"behavior": "answer", "codes": [c.expected], "reason": ""}})
        run(["plain_llm"], [c], llm, tmp_path, log=lambda *_: None)
    text = build(tmp_path)
    assert "small" in text and "never averaged" in text
    assert "Code accuracy: real" in text and "Code accuracy: synthetic" in text and "(1/1;" in text
    assert "n=0: there are no hand-computed bills" in text
    assert "Danial" in text


# ------------------------------------------------------------------ shards (parallel workers) and merging
def test_two_shards_cover_every_case_once_and_merge_without_duplicates(tmp_path):
    from src.eval.run import merge_results

    cases = [case(f"C{i}") for i in range(6)]
    seq = {"eval_plain": {"behavior": "answer", "codes": ["6109.1000"], "reason": ""}}
    out0, out1, main = tmp_path / "s0", tmp_path / "s1", tmp_path / "main"
    run(["plain_llm"], cases[0::2], FakeLLM(dict(seq)), out0, log=lambda *_: None)
    run(["plain_llm"], cases[1::2], FakeLLM(dict(seq)), out1, log=lambda *_: None)
    assert merge_results([out0, out1], main) == 6
    assert set(load_results("plain_llm", main)) == {f"C{i}" for i in range(6)}
    assert merge_results([out0, out1], main) == 0                      # merging again adds nothing


def test_cases_finished_in_another_folder_are_skipped(tmp_path):
    cases = [case("A"), case("B")]
    seq = {"eval_plain": {"behavior": "answer", "codes": ["6109.1000"], "reason": ""}}
    done = tmp_path / "done"
    run(["plain_llm"], [cases[0]], FakeLLM(dict(seq)), done, log=lambda *_: None)
    llm = FakeLLM(dict(seq))
    r = run(["plain_llm"], cases, llm, tmp_path / "new", skip_dirs=[done], log=lambda *_: None)
    assert r["done"] == 1 and r["skipped"] == 1 and llm.count("eval_plain") == 1


def test_results_file_survives_a_locked_replace(tmp_path, monkeypatch):
    """OneDrive can lock the file for a moment: the replace is retried, then written in place. Nothing is lost."""
    from pathlib import Path as P

    from src.eval import run as runmod

    real = P.replace
    calls = {"n": 0}

    def flaky(self, target):
        calls["n"] += 1
        raise PermissionError("locked")

    monkeypatch.setattr(P, "replace", flaky)
    monkeypatch.setattr(runmod.time, "sleep", lambda s: None)
    runmod._write_all("plain_llm", {"A": {"case_id": "A", "pred": {"behavior": "answer", "codes": []}}}, tmp_path)
    monkeypatch.setattr(P, "replace", real)
    assert calls["n"] == 6 and set(load_results("plain_llm", tmp_path)) == {"A"}


def test_deepseek_peak_window_guard():
    import datetime as dt

    from src.eval.run import is_deepseek_peak

    utc = dt.timezone.utc
    assert is_deepseek_peak(dt.datetime(2026, 10, 22, 6, 46, tzinfo=utc))        # Thursday 06:46: peak
    assert is_deepseek_peak(dt.datetime(2026, 10, 22, 1, 0, tzinfo=utc))
    assert not is_deepseek_peak(dt.datetime(2026, 10, 22, 4, 0, tzinfo=utc))
    assert not is_deepseek_peak(dt.datetime(2026, 10, 22, 10, 0, tzinfo=utc))
    assert not is_deepseek_peak(dt.datetime(2026, 10, 24, 7, 0, tzinfo=utc))     # Saturday: off-peak
