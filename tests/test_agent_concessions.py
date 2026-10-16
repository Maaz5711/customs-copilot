"""Agent behaviour for customs-duty concessions (Fifth Schedule, China FTA): it asks, shows both bills, never applies one silently.
Real tools over a fresh store, scripted LLM (same helpers as tests/test_agent.py)."""
from pathlib import Path

import pytest

from src.agent.nodes import Config
from tests.test_agent import IMPORTER_FULL, build, code_only_llm, make_agent, questions  # noqa: F401

PROC = Path("data/processed")
pytestmark = pytest.mark.skipif(not (PROC / "a7_fifth_rules.csv").exists(), reason="A7 files not built")

D = "2026-08-01"
MSG = "duty on 8201.3000, value PKR 1,000,000, registered importer, commercial importer, filer"


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("agent_con") / "store.sqlite"
    build(path)
    return str(path)


def claim_id(t1):
    return next(k for k in questions(t1) if k.startswith("claim."))


def answers(t1, claim):
    """Answer the concession claim and say the goods are of German origin (so the China FTA question is settled as 'not applicable')."""
    return {"answers": {claim_id(t1): claim, "goods.origin_country": "Germany"}}


def first_turn(db):
    agent, tools = make_agent(code_only_llm("PKR 1,000,000", "8201.3000", **IMPORTER_FULL), db, cfg=Config(ask_concessions=True))
    return agent, agent.ask(MSG, as_of_date=D)


def test_agent_asks_about_the_fifth_schedule_conditions_before_the_bill(db):
    agent, t1 = first_turn(db)
    assert t1.interrupt and t1.final is None
    allq = questions(t1)
    assert "goods.origin_country" in allq                       # asked for every code, because the China FTA could apply to any of them
    q = [v for k, v in allq.items() if k.startswith("claim.")]
    assert len(q) == 1 and q[0]["id"].startswith("claim.fifth_schedule_rules:") and q[0]["type"] == "bool"
    assert "Fifth Schedule" in q[0]["question"] and "0%" in q[0]["question"] and "15%" in q[0]["question"] and "Conditions (not checked by me)" in q[0]["question"]


def test_yes_applies_the_concession_and_shows_both_bills(db):
    agent, t1 = first_turn(db)
    t2 = agent.resume(t1.thread_id, answers(t1, "yes"))
    f = t2.final
    assert f["status"] == "answer"
    # hand case: Fifth Schedule p.3 Part I S.No 1 D(1) 0% instead of 15% (tariff p.202); commercial importer, VAT 3%, income tax Part III 6%
    # with: ST 180,000 + VAT 30,000 + IT 6% x 1,210,000 = 72,600 -> 282,600 ; without: CD 150,000 + ST 207,000 + VAT 34,500 + IT 6% x 1,391,500 = 83,490 -> 474,990
    assert "TOTAL PAYABLE: PKR 282,600.00" in f["text"] and "Bill WITHOUT the concession: total payable PKR 474,990.00" in f["text"]
    assert "CUSTOMS-DUTY CONCESSION APPLIED (because you claimed it)" in f["text"] and "Conditions that nobody has checked" in f["text"]
    assert any(c.get("source_file", "").endswith("FifthSchedule2026-27.pdf") and c.get("page") == 3 for c in f["citations"])


def test_no_keeps_the_normal_bill_and_still_shows_the_option(db):
    agent, t1 = first_turn(db)
    t2 = agent.resume(t1.thread_id, answers(t1, "no"))
    f = t2.final
    assert f["status"] == "answer" and "TOTAL PAYABLE: PKR 474,990.00" in f["text"]
    assert "NOT applied" in f["text"] and "Bill WITH it: total PKR 282,600.00" in f["text"] and "CONCESSION APPLIED" not in f["text"]


def test_dont_know_is_not_a_claim(db):
    agent, t1 = first_turn(db)
    t2 = agent.resume(t1.thread_id, answers(t1, "I don't know"))
    assert t2.final and "TOTAL PAYABLE: PKR 474,990.00" in t2.final["text"] and "CONCESSION APPLIED" not in t2.final["text"]
