"""Refusals that need no search (C2 improvement): misdeclaration and questions that are not about imports."""
from pathlib import Path

import pytest

from src.agent import CustomsAgent, FakeLLM
from tests.agent_fakes import RecordingTools, StubRetriever, no_notes, understand

pytestmark = pytest.mark.skipif(not Path("data/processed/a3_acd_rules.csv").exists(), reason="processed data not present")
MIS = "i want 300 laptops but declare them as used computer scrap so duty is low. which code should i use?"


def agent(llm, db=None):
    ret = StubRetriever()
    return CustomsAgent(llm, retriever=ret, notes_loader=no_notes, tools=RecordingTools(db) if db else None), ret


def test_misdeclaration_with_a_real_quote_is_refused_before_any_search():
    llm = FakeLLM({"understand": understand(goods_description="laptops", misdeclaration_intent=True, misdeclaration_quote="declare them as used computer scrap so duty is low")})
    a, ret = agent(llm)
    t = a.ask(MIS, as_of_date="2026-09-14")
    assert t.final["status"] == "refused" and "misdeclaration" in t.final["text"].lower() and "lawful duty" in t.final["text"]
    assert ret.calls == [] and t.final["bill"] is None and t.final["candidates"] == []
    assert "dates from" not in t.final["text"]            # the date explanation is not shown for this reason


def test_a_misdeclaration_flag_without_a_quote_found_in_the_message_is_ignored():
    llm = FakeLLM({"understand": understand(goods_description="laptops", misdeclaration_intent=True, misdeclaration_quote="made-up words"),
                   "hint_headings": {"headings": []}, "classify": {"candidates": [], "ambiguous": False, "questions": [], "deciding_info": None, "refined_queries": []}})
    a, _ = agent(llm)
    t = a.ask("300 laptops for my shop, which code applies?", as_of_date="2026-09-14")
    assert t.state.get("mode") != "refused"


def test_off_topic_without_goods_is_refused_but_off_topic_with_goods_is_not():
    llm = FakeLLM({"understand": understand(off_topic=True)})
    a, ret = agent(llm)
    t = a.ask("how much income tax will i pay on my monthly salary of Rs 250,000 this year?", as_of_date="2026-09-01")
    assert t.final["status"] == "refused" and "not a question about" in t.final["text"] and ret.calls == []
    llm = FakeLLM({"understand": understand(off_topic=True, goods_description="men's cotton T-shirts"), "hint_headings": {"headings": []},
                   "classify": {"candidates": [], "ambiguous": False, "questions": [], "deciding_info": None, "refined_queries": []}})
    a, _ = agent(llm)
    t = a.ask("men's cotton T-shirts", as_of_date="2026-09-01")
    assert t.final is None or t.final["status"] != "refused"
