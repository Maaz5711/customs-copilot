"""Daily free-tier runner: never starts a case it cannot finish, reports a small-n summary, explains a missing key. No network."""
import pytest

from src.eval import daily_free, run as runner
from src.eval.cases import Case


class Llm:
    def __init__(self, cap, used=0):
        self.max_calls, self.stats = cap, {"live_calls": used}


def case(i):
    return Case(id=f"C{i:03d}", kind="catalog", description="x", as_of_date="2026-09-15", behavior="answer", expected="84713010", split="dev")


def test_a_case_is_not_started_when_the_budget_cannot_finish_it(tmp_path, monkeypatch):
    llm, started = Llm(cap=12), []

    def fake(case, llm, **kw):
        started.append(case.id)
        llm.stats["live_calls"] += 5
        return dict(behavior="answer", codes=["84713010"], status="answer", citations=[], bill_totals=None)

    monkeypatch.setitem(runner.RUNNERS, "full_graph", fake)
    res = runner.run(["full_graph"], [case(i) for i in range(1, 6)], llm, tmp_path, log=lambda *_: None, reserve=6)
    assert started == ["C001", "C002"]                       # 0 -> 5 -> 10; at 10 of 12 a case needing up to 6 is not started
    assert res["done"] == 2 and "budget" in res["stopped"]
    res2 = runner.run(["full_graph"], [case(i) for i in range(1, 6)], Llm(cap=30), tmp_path, log=lambda *_: None, reserve=6)
    assert res2["skipped"] == 2                              # tomorrow's run continues where today stopped


def test_summary_counts_hits_and_warns_about_small_n():
    cases = {"a": case(1), "b": case(2)}
    res = {"a": dict(pred=dict(behavior="answer", codes=["84713010"])), "b": dict(pred=dict(behavior="not_sure_or_clarify", codes=["84713020", "84719000"]))}
    text = "\n".join(daily_free.summarize(res, cases))
    assert "finished cases: 2" in text and "1/2 (50%" in text and "small n" in text
    assert daily_free.summarize({}, cases) == ["no finished cases yet"]


def test_missing_key_gives_a_plain_message(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)                              # no .env here
    with pytest.raises(SystemExit, match="OPENROUTER_API_KEY"):
        daily_free.main([])
