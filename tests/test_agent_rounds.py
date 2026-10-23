"""Fewer question rounds: the origin question joins the FIRST round of duty questions (taken from a tool response that is already computed, so no extra
tool or model call), concession questions are marked optional, and nothing about a bill changes. Real tools over a fresh store, scripted LLM."""
from pathlib import Path

import pytest

from src.agent.nodes import Config
from tests.test_agent import build, code_only_llm, make_agent, questions  # noqa: F401

PROC = Path("data/processed")
pytestmark = pytest.mark.skipif(not (PROC / "a7_fifth_rules.csv").exists(), reason="A7 files not built")

D = "2026-08-01"
MSG = "duty on 8201.3000, value PKR 1,000,000"            # no importer facts: the agent must ask for them


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("agent_rounds") / "store.sqlite"
    build(path)
    return str(path)


def agent_for(db, ask_concessions=True):
    return make_agent(code_only_llm("PKR 1,000,000", "8201.3000"), db, cfg=Config(ask_concessions=ask_concessions))


def test_origin_is_asked_in_the_first_round_together_with_the_importer_facts(db):
    agent, tools = agent_for(db)
    t1 = agent.ask(MSG, as_of_date=D)
    q = questions(t1)
    assert "importer.registration_status" in q and "goods.origin_country" in q          # one round, not two
    assert q["goods.origin_country"]["optional"] is True and q["importer.registration_status"]["optional"] is False


def test_the_early_origin_question_costs_no_extra_tool_call_and_no_model_call(db):
    agent, tools = agent_for(db)
    base_agent, base_tools = agent_for(db, ask_concessions=False)
    agent.ask(MSG, as_of_date=D)
    base_agent.ask(MSG, as_of_date=D)
    assert len(tools.calls) == len(base_tools.calls)                                    # the probe response that was already fetched is reused


def test_origin_is_not_asked_a_second_time_after_it_was_answered(db):
    agent, _ = agent_for(db)
    t1 = agent.ask(MSG, as_of_date=D)
    answers = {"importer.registration_status": "registered", "importer.commercial_importer": "yes", "importer.active_taxpayer": "yes", "goods.origin_country": "Germany"}
    t2 = agent.resume(t1.thread_id, {"answers": {k: v for k, v in answers.items() if k in questions(t1)}})
    again = questions(t2) if t2.interrupt else {}
    assert "goods.origin_country" not in again                                           # and a Form E question never appears for a German origin
    assert "goods.has_certificate_of_origin" not in again


def test_skipping_the_optional_question_is_accepted_and_the_bill_is_the_standard_one(db):
    agent, _ = agent_for(db)
    t1 = agent.ask(MSG, as_of_date=D)
    answers = {"importer.registration_status": "registered", "importer.commercial_importer": "yes", "importer.active_taxpayer": "yes", "goods.origin_country": "I don't know"}
    t2 = agent.resume(t1.thread_id, {"answers": {k: v for k, v in answers.items() if k in questions(t1)}})
    q2 = questions(t2) if t2.interrupt else {}
    assert "goods.origin_country" not in q2 and "goods.has_certificate_of_origin" not in q2
    for qid, q in q2.items():                                                            # whatever is still asked (a Fifth Schedule claim) is optional too
        assert q["optional"] is True, qid
    t3 = agent.resume(t2.thread_id, {"answers": {k: "I don't know" for k in q2}}) if t2.interrupt else t2
    assert t3.final and "CONCESSION APPLIED" not in t3.final["text"]


def test_the_rewritten_questions_keep_their_field_ids_and_answer_types(db):
    agent, _ = agent_for(db)
    q = questions(agent.ask(MSG, as_of_date=D))
    assert q["importer.registration_status"]["allowed"] == ["registered", "unregistered"]
    assert "STRN" in q["importer.registration_status"]["question"] and "Sales Tax Act 1990" not in q["importer.registration_status"]["question"]
