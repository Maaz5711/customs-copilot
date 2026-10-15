"""Heading hints (C2 improvement): the LLM may propose 4-digit headings; they only WIDEN the candidate pool.
Search stays tariff-only, the classifier still picks among real lines, and every code is still validated by the exact tools.
"""
from pathlib import Path

import pytest

from src.agent import CustomsAgent, FakeLLM
from src.agent.nodes import Config
from src.agent.retrieval import gather
from src.store.build import build
from tests.agent_fakes import IMPORTER_FULL, RecordingTools, StubRetriever, cand, classify, no_notes, understand, verify

PROC = Path("data/processed")
pytestmark = pytest.mark.skipif(not (PROC / "a3_acd_rules.csv").exists(), reason="processed data not present")
D15 = "2026-07-15"


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("hints") / "store.sqlite"
    build(path)
    return str(path)


def test_hinted_heading_lines_join_the_pool_even_when_search_did_not_return_them():
    ret = StubRetriever()
    plain = gather(ret, no_notes, query="men's cotton T-shirts", as_of_date=D15)
    assert not any(ln["norm"].startswith("8471") for ln in plain["lines"])
    hinted = gather(StubRetriever(), no_notes, query="men's cotton T-shirts", as_of_date=D15, hint_headings=["8471"])
    assert {"84713010", "84713020"} <= {ln["norm"] for ln in hinted["lines"]}
    assert hinted["hint_headings"] == ["8471"]
    assert {ln["norm"] for ln in plain["lines"]} <= {ln["norm"] for ln in hinted["lines"]}        # hints only add, never remove


def test_junk_hints_are_ignored_and_a_hint_for_no_such_heading_adds_nothing():
    base = gather(StubRetriever(), no_notes, query="men's cotton T-shirts", as_of_date=D15)
    junk = gather(StubRetriever(), no_notes, query="men's cotton T-shirts", as_of_date=D15, hint_headings=["abc", "99", "0000", ""])
    assert [ln["norm"] for ln in junk["lines"]] == [ln["norm"] for ln in base["lines"]]


def test_big_hinted_heading_is_cut_to_the_lines_that_share_words_with_the_query():
    from tests.agent_fakes import _line

    many = [_line(f"8703{i:04d}", "87.03", f"Motor cars. > Of {'diesel' if i % 2 else 'petrol'} engine variant {i}", 265) for i in range(1, 90)]
    ev = gather(StubRetriever(lines=many), no_notes, query="petrol car", as_of_date=D15, hint_headings=["8703"], max_hint_lines=20)
    kept = [ln for ln in ev["lines"] if ln["norm"].startswith("8703")]
    assert 0 < len(kept) <= 20 + 10 and sum("petrol" in ln["description"] for ln in kept) >= 15


def test_agent_calls_the_hint_step_once_and_still_validates_the_final_code(db):
    llm = FakeLLM({"understand": understand(goods_description="slim travel computer", value_text="PKR 1,000,000", **IMPORTER_FULL),
                   "hint_headings": {"headings": ["8471", "8473"]},
                   "classify": classify(cand("8471.3010", 0.9), cand("9999.9999", 0.05)), "verify": verify()})
    agent = CustomsAgent(llm, retriever=StubRetriever(), notes_loader=no_notes, tools=RecordingTools(db), cfg=Config(use_hints=True))
    turn = agent.ask("slim travel computer, value PKR 1,000,000, registered importer, commercial importer", as_of_date=D15)
    assert llm.count("hint_headings") == 1
    assert turn.state["hint_headings"] == ["8471", "8473"]
    # no word of the description matches a laptop line in the stub search; the 8471 lines came only from the hinted heading
    assert not any(w in "slim travel computer" for w in ["laptop", "notebook"])
    assert turn.state["chosen_code"] == "84713010"          # then it asks the duty inputs (manufacturer question), as for any laptop
    assert any(r["code"].startswith("9999") for r in turn.state["rejected_codes"])          # an invented code is still rejected


def test_hint_answer_that_is_not_json_object_only_means_plain_search(db):
    llm = FakeLLM({"understand": understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000", **IMPORTER_FULL),
                   "hint_headings": lambda p, n: ["6109"],
                   "classify": classify(cand("6109.1000", 0.92)), "verify": verify()})
    agent = CustomsAgent(llm, retriever=StubRetriever(), notes_loader=no_notes, tools=RecordingTools(db), cfg=Config(use_hints=True))
    turn = agent.ask("men's cotton T-shirts, value PKR 1,000,000, registered importer, commercial importer", as_of_date=D15)
    assert turn.final["status"] == "answer" and turn.state["hint_headings"] == []


def test_hints_can_be_switched_off(db):
    llm = FakeLLM({"understand": understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000", **IMPORTER_FULL),
                   "classify": classify(cand("6109.1000", 0.92)), "verify": verify()})
    agent = CustomsAgent(llm, retriever=StubRetriever(), notes_loader=no_notes, tools=RecordingTools(db), cfg=Config(use_hints=False))
    turn = agent.ask("men's cotton T-shirts, value PKR 1,000,000, registered importer, commercial importer", as_of_date=D15)
    assert llm.count("hint_headings") == 0 and turn.final["status"] == "answer"
