"""Autonomous research step (src/agent/explore.py): the model picks lookups, code runs them. It only WIDENS the pool; the final code is
still validated against that pool by the exact tools. No network: scripted FakeLLM and a stub retriever."""
from pathlib import Path

import pytest

from src.agent import CustomsAgent, FakeLLM
from src.agent.explore import explore, pool_view, run_step, validate_explore
from src.agent.nodes import Config
from src.agent.retrieval import gather
from src.store.build import build
from tests.agent_fakes import IMPORTER_FULL, RecordingTools, StubRetriever, cand, classify, no_notes, understand, verify

PROC = Path("data/processed")
D15 = "2026-07-15"
FLOORS = {"tariff": -9.0, "notes": -4.0, "sro": -3.0, "rulings": 0.0}


def pool(query="men's cotton T-shirts"):
    return gather(StubRetriever(), no_notes, query=query, as_of_date=D15)


def test_validate_explore_reads_good_steps_and_turns_junk_into_done():
    assert validate_explore({"action": "browse", "heading": "84.71"}) == {"action": "browse", "thought": "", "heading": "8471"}
    assert validate_explore({"action": "search", "query": "  laptop   computer "})["query"] == "laptop computer"
    assert validate_explore({"action": "notes", "chapter": "85"})["chapter"] == "85"
    for junk in (None, [], "x", {"action": "delete everything"}, {"action": "browse", "heading": "7"}, {"action": "search", "query": "a"}, {"action": "notes"}):
        assert validate_explore(junk)["action"] == "done"


def test_browse_adds_every_line_of_the_heading_and_search_adds_only_new_lines():
    ev = pool()
    before = {ln["norm"] for ln in ev["lines"]}
    obs = run_step({"action": "browse", "heading": "8471"}, ev, StubRetriever(), D15, FLOORS)
    assert {"84713010", "84713020"} <= {ln["norm"] for ln in ev["lines"]} and "8471.3010" in obs and before <= {ln["norm"] for ln in ev["lines"]}
    n = len(ev["lines"])
    assert "already in the pool" in run_step({"action": "browse", "heading": "8471"}, ev, StubRetriever(), D15, FLOORS) and len(ev["lines"]) == n
    labels = [ln["label"] for ln in ev["lines"]]
    assert len(set(labels)) == len(labels)                        # new lines get fresh T labels


def test_notes_action_adds_the_chapter_notes_with_new_labels():
    ev = pool()
    n0 = len(ev["notes"])
    obs = run_step({"action": "notes", "chapter": "84"}, ev, StubRetriever(), D15, FLOORS)
    assert len(ev["notes"]) == n0 + 1 and "Chapter 84 note 6" in obs and len({n["label"] for n in ev["notes"]}) == len(ev["notes"])


def test_explore_runs_the_models_actions_then_stops_on_done():
    ev = pool()
    llm = FakeLLM({"explore": [{"thought": "could be a computer", "action": "browse", "heading": "8471"}, {"action": "done", "reason": "enough"}]})
    ev, log, trace = explore(llm, StubRetriever(), ev, goods="slim travel computer", as_of_date=D15, steps=4, floors=FLOORS)
    assert llm.count("explore") == 2 and any(ln["norm"] == "84713010" for ln in ev["lines"])
    assert any("browse '8471'" in t for t in trace) and any("done after 1 action" in t for t in trace) and len(log) == 2


def test_explore_stops_on_a_repeated_action_and_at_the_step_limit():
    llm = FakeLLM({"explore": [{"action": "browse", "heading": "8471"}] * 5})
    _, _, trace = explore(llm, StubRetriever(), pool(), goods="x y z", as_of_date=D15, steps=4, floors=FLOORS)
    assert llm.count("explore") == 2 and any("repeated action" in t for t in trace)
    llm2 = FakeLLM({"explore": [{"action": "browse", "heading": "8471"}, {"action": "browse", "heading": "6109"}, {"action": "notes", "chapter": "61"}]})
    _, _, trace2 = explore(llm2, StubRetriever(), pool(), goods="x y z", as_of_date=D15, steps=2, floors=FLOORS)
    assert llm2.count("explore") == 2 and any("step limit (2)" in t for t in trace2)


def test_pool_is_capped_and_pool_view_lists_headings():
    from src.agent.explore import MAX_POOL_LINES
    from tests.agent_fakes import _line

    many = [_line(f"8703{i:04d}", "87.03", f"Motor cars. > variant {i}", 265) for i in range(1, 300)]
    ev = pool()
    run_step({"action": "browse", "heading": "8703"}, ev, StubRetriever(lines=many), D15, FLOORS)
    assert len(ev["lines"]) <= MAX_POOL_LINES
    assert "Heading 61.09" in pool_view(ev) and "legal notes" in pool_view(ev)


@pytest.mark.skipif(not (PROC / "a3_acd_rules.csv").exists(), reason="processed data not present")
def test_agent_with_exploration_finds_a_line_only_reachable_by_browsing_and_still_rejects_invented_codes(tmp_path):
    path = tmp_path / "store.sqlite"
    build(path)
    llm = FakeLLM({"understand": understand(goods_description="slim travel computer", value_text="PKR 1,000,000", **IMPORTER_FULL),
                   "explore": [{"action": "browse", "heading": "8471"}, {"action": "done", "reason": "found the heading"}],
                   "classify": classify(cand("8471.3010", 0.9), cand("9999.9999", 0.05)), "verify": verify()})
    agent = CustomsAgent(llm, retriever=StubRetriever(), notes_loader=no_notes, tools=RecordingTools(str(path)), cfg=Config(use_hints=False, explore_steps=4))
    turn = agent.ask("slim travel computer, value PKR 1,000,000, registered importer, commercial importer, filer", as_of_date=D15)
    assert llm.count("explore") == 2 and turn.state["chosen_code"] == "84713010"
    assert any(r["code"].startswith("9999") for r in turn.state["rejected_codes"])
    assert any(t.startswith("explore:") for t in turn.state["trace"])


@pytest.mark.skipif(not (PROC / "a3_acd_rules.csv").exists(), reason="processed data not present")
def test_exploration_can_be_switched_off_and_is_skipped_for_a_code_only_question(tmp_path):
    path = tmp_path / "store.sqlite"
    build(path)
    llm = FakeLLM({"understand": understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000", **IMPORTER_FULL),
                   "classify": classify(cand("6109.1000", 0.92)), "verify": verify()})
    agent = CustomsAgent(llm, retriever=StubRetriever(), notes_loader=no_notes, tools=RecordingTools(str(path)), cfg=Config(use_hints=False, explore_steps=0))
    turn = agent.ask("men's cotton T-shirts, value PKR 1,000,000, registered importer, commercial importer, filer", as_of_date=D15)
    assert llm.count("explore") == 0 and turn.final["status"] == "answer"
