"""Tests for the LangGraph agent (C1). The LLM is a FakeLLM (scripted); the tools are the REAL exact tools over a freshly built store;
retrieval is a stub with real tariff codes (one test uses the real search index and is skipped when it is not built).

Required behaviours covered here:
  clarify interrupt/resume round trip, not-sure mode after 2 failed verifications, invalid LLM code rejected,
  answer numbers equal the tool output, missing_inputs trigger Clarify instead of a number, unsupported date refused.
"""
import json
import re
import sqlite3
from pathlib import Path

import pytest

from src.agent import CustomsAgent, FakeLLM
from src.agent.ground import Corpus, check_text, clean_llm_text
from src.agent.llm import LLMRateLimited
from src.agent.nodes import Config, bill_checks, validate_candidates
from src.agent.retrieval import gather
from src.store.build import build
from src.tools import compute_duty

from tests.agent_fakes import (
    IMPORTER_FULL, LINES, RecordingTools, StubRetriever, cand, classify, no_notes, understand, verify,
)

PROC = Path("data/processed")
pytestmark = pytest.mark.skipif(not (PROC / "a3_acd_rules.csv").exists(), reason="processed data not present")

D15 = "2026-07-15"
TSHIRT_MSG = "men's cotton T-shirts, value PKR 1,000,000, registered importer, commercial importer, filer"
IMP_RC = {"registration_status": "registered", "commercial_importer": True, "active_taxpayer": True}


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("agent") / "store.sqlite"
    build(path)
    return str(path)


def make_agent(llm, db, retriever=None, cfg=None, **kw):
    tools = RecordingTools(db)
    agent = CustomsAgent(llm, retriever=retriever or StubRetriever(), notes_loader=no_notes, tools=tools, cfg=cfg or Config(), **kw)
    return agent, tools


def tshirt_llm(**over):
    script = {"understand": understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000", **IMPORTER_FULL),
              "classify": classify(cand("6109.1000", 0.92), cand("6109.9090", 0.05), cand("6105.1000", 0.03)), "verify": verify()}
    script.update(over)
    return FakeLLM(script)


def money(text):
    return {m.replace(",", "") for m in re.findall(r"(?<![\d.,])\d{1,3}(?:,\d{3})*\.\d{2}(?!\d)", text)}


def questions(turn):
    return {q["id"]: q for q in turn.interrupt["questions"]}


# ===================================================================== happy path
def test_happy_path_gives_bill_citations_flags_and_disclaimer(db):
    llm = tshirt_llm()
    agent, tools = make_agent(llm, db)
    turn = agent.ask(TSHIRT_MSG, as_of_date=D15)
    assert turn.interrupt is None and turn.final["status"] == "answer"
    assert turn.path == ["understand", "search", "classify", "calculate", "verify", "respond"]
    assert (llm.count("understand"), llm.count("classify"), llm.count("verify")) == (1, 1, 1)       # Verify is its own, separate call
    t = turn.final["text"]
    assert "6109.1000" in t and "667,380.00" in t                                                   # hand case: tests/test_tools.py hand case 10
    assert "decision support, not legal advice" in t
    for needle in ("Sales Tax Act", "1064(I)/2026", "1063(I)/2026", "p.156", "WHAT IS NOT VERIFIED", "ASSUMPTIONS MADE BY THE CALCULATION", "[FED]", "[ROUNDING]"):
        assert needle in t, needle
    assert turn.final["citations"] and all(c.get("source_file") and c.get("page") for c in turn.final["citations"])
    assert turn.final["verification"]["passed"] and turn.final["verification"]["checks"]["code_exists_on_date"]
    json.dumps(turn.final)             # JSON-able (the checkpointer and a future API need this)


# ===================================================================== clarify: interrupt() and Command(resume=...)
def test_clarify_interrupt_resume_round_trip(db):
    """Two pauses: first the date (never assumed), then the duty inputs the rules ask for. Answers are read by code, not by the LLM."""
    llm = FakeLLM({"understand": understand(goods_description="laptop computers"), "classify": classify(cand("8471.3010", 0.9)), "verify": verify()})
    agent, tools = make_agent(llm, db)
    t1 = agent.ask("I want to import laptop computers")
    assert t1.final is None and t1.interrupt["type"] == "clarify" and t1.interrupt["kind"] == "request"
    assert list(questions(t1)) == ["as_of_date"] and "do not assume today" in questions(t1)["as_of_date"]["question"]
    assert tools.calls == []                                           # nothing is searched or calculated before the date is known

    t2 = agent.resume(t1.thread_id, "15 July 2026")
    assert t2.final is None and t2.interrupt["kind"] == "duty_input"
    q = questions(t2)
    assert set(q) == {"assessable_value_pkr", "importer.registration_status", "importer.commercial_importer", "importer.active_taxpayer", "importer.manufacturer_in_house_use"}
    assert q["importer.registration_status"]["allowed"] == ["registered", "unregistered"] and q["importer.manufacturer_in_house_use"]["allowed"] == [True, False]
    assert t2.state.get("duty") is None                                # the probe's numbers were thrown away, not stored or shown

    t3 = agent.resume(t2.thread_id, {"answers": {"assessable_value_pkr": "1,000,000", "importer.registration_status": "registered",
                                                 "importer.commercial_importer": "yes", "importer.active_taxpayer": "yes", "importer.manufacturer_in_house_use": "no"}})
    assert t3.interrupt is None and t3.final["status"] == "answer"
    direct = compute_duty("8471.3010", 1000000, D15, importer={**IMP_RC, "manufacturer_in_house_use": False}, db_path=db)
    assert direct["totals"]["total_payable_pkr"] == "197800.00"        # hand case 7 in tests/test_tools.py
    assert fmt(direct["totals"]["total_payable_pkr"]) in t3.final["text"]
    assert t3.path == ["understand", "clarify", "understand", "search", "classify", "calculate", "clarify", "understand", "calculate", "verify", "respond"]
    assert (llm.count("understand"), llm.count("classify"), llm.count("verify")) == (1, 1, 1)


def fmt(s):
    ip, _, fp = s.partition(".")
    return f"{int(ip):,}.{fp}"


def test_unreadable_answer_is_asked_again_with_the_reason(db):
    agent, _ = make_agent(tshirt_llm(understand=understand(goods_description="men's cotton T-shirts", **IMPORTER_FULL)), db)
    t1 = agent.ask(TSHIRT_MSG.replace("value PKR 1,000,000, ", ""), as_of_date=D15)
    assert set(questions(t1)) == {"assessable_value_pkr"}
    t2 = agent.resume(t1.thread_id, "lots of money")
    assert t2.interrupt and "assessable_value_pkr" in questions(t2) and "could not find an amount" in questions(t2)["assessable_value_pkr"]["error"]
    t3 = agent.resume(t2.thread_id, "Rs 10 lakh")
    assert t3.final["status"] == "answer" and "1,000,000.00" in t3.final["text"]


def test_classification_questions_come_from_the_classifier_and_reach_search_and_prompt(db):
    llm = FakeLLM({"understand": understand(goods_description="T-shirts", value_text="PKR 1,000,000", **IMPORTER_FULL),
                   "classify": [classify(cand("6109.1000", 0.55), cand("6109.9090", 0.4), ambiguous=True, questions=["Are the T-shirts made of cotton or of another material?"],
                                         deciding="the material decides between 6109.1000 and 6109.9090"),
                                classify(cand("6109.1000", 0.93), cand("6109.9090", 0.04))],
                   "verify": verify()})
    stub = StubRetriever()
    agent, _ = make_agent(llm, db, retriever=stub)
    t1 = agent.ask("T-shirts, value PKR 1,000,000, registered importer, commercial importer, filer", as_of_date=D15)
    assert t1.interrupt["kind"] == "classification" and "cotton" in t1.interrupt["questions"][0]["question"]
    t2 = agent.resume(t1.thread_id, "100% cotton")
    assert t2.final["status"] == "answer" and t2.final["code"] == "6109.1000"
    second_prompt = [c for c in llm.calls if c["task"] == "classify"][1]["prompt"]
    assert "100% cotton" in second_prompt and "ALREADY ASKED" in second_prompt
    assert any("100% cotton" in q for i, q in stub.calls if i == "tariff")                    # the answer joined the search query
    assert t2.state["retries"] == 0                                                           # a clarification is not a retry


def test_no_candidate_but_questions_asks_instead_of_retrying(db):
    """Real Gemini behaviour for 'I want to import a car': no candidate yet, ambiguous, two questions that would decide it."""
    llm = FakeLLM({"understand": understand(goods_description="a car"),
                   "classify": [classify(ambiguous=True, questions=["What is the engine type and cylinder capacity of the car?", "Is it a snow vehicle or golf car?"],
                                         deciding="engine type and capacity decide the sub-heading", refined=["motor cars"]),
                                classify(cand("8703.2113", 0.9))]})
    stub = StubRetriever()
    agent, _ = make_agent(llm, db, retriever=stub)
    t1 = agent.ask("I want to import a car", as_of_date=D15)
    assert t1.interrupt["kind"] == "classification" and len(t1.interrupt["questions"]) == 2 and "engine type" in t1.interrupt["questions"][0]["question"]
    assert t1.state["retries"] == 0 and llm.count("classify") == 1                       # asked, did not burn a retry
    t2 = agent.resume(t1.thread_id, {"answers": {"q1": "petrol, 800cc", "q2": "no"}})
    assert t2.interrupt["kind"] == "duty_input" and "goods.vehicle_form" in {q["id"] for q in t2.interrupt["questions"]}
    assert "petrol, 800cc" in [c for c in llm.calls if c["task"] == "classify"][1]["prompt"]
    tariff_queries = [q for i, q in stub.calls if i == "tariff"]
    assert any("petrol, 800cc" in q for q in tariff_queries) and not any(q.endswith(" no") for q in tariff_queries)     # the bare "no" is not searched for


def test_the_question_budget_ends_in_not_sure_instead_of_asking_forever(db):
    ask = classify(ambiguous=True, questions=["More detail please?"])
    llm = FakeLLM({"understand": understand(goods_description="a car"), "classify": ask})
    agent, _ = make_agent(llm, db, cfg=Config(max_clarify_rounds=2))
    t = agent.ask("a car", as_of_date=D15)
    rounds = 0
    while t.interrupt:
        rounds += 1
        assert rounds <= 2
        t = agent.resume(t.thread_id, {"answers": {k["id"]: "no idea what else to say" for k in t.interrupt["questions"]}})
    assert t.final["status"] == "not_sure" and rounds == 2


# ===================================================================== Verify retries, then "not sure"
def test_not_sure_mode_after_two_failed_verifications(db):
    llm = tshirt_llm(verify=verify(fits=False, conf=0.3, problems=["the goods are not clearly made of cotton"], hint="knitted t-shirts of man-made fibres"))
    stub = StubRetriever()
    agent, _ = make_agent(llm, db, retriever=stub)
    turn = agent.ask(TSHIRT_MSG, as_of_date=D15)
    assert turn.interrupt is None
    assert turn.state["retries"] == 2 and llm.count("verify") == 3 and llm.count("classify") == 3          # first try + 2 retries
    assert turn.path.count("search") == 3 and turn.path[-2:] == ["verify", "respond"]
    f = turn.final
    assert f["status"] == "not_sure" and "I'm not sure" in f["text"] and f["bill"] is None and "PKR" not in f["text"].split("Top candidates")[0].split("Why I stopped")[0]
    assert [c["code"] for c in f["candidates"]] == ["6109.1000", "6109.9090", "6105.1000"]                  # top 3 with reasons
    assert all(c["reasons"] for c in f["candidates"]) and "Why:" in f["text"] and "What would help me decide" in f["text"]
    assert "check with Pakistan Customs" in f["text"] or "Please check with Pakistan Customs" in f["text"]
    assert not any(re.search(r"TOTAL PAYABLE", f["text"]) for _ in [0])                                    # no bill
    assert any("knitted t-shirts of man-made fibres" in q for i, q in stub.calls if i == "tariff")         # the auditor's hint refined the retry search
    assert "Your choice 6109.1000 was rejected" in [c for c in llm.calls if c["task"] == "classify"][1]["prompt"]


def test_one_failed_verification_then_success_counts_one_retry(db):
    llm = tshirt_llm(verify=[verify(fits=False, conf=0.2, problems=["material unclear"]), verify()])
    agent, _ = make_agent(llm, db)
    turn = agent.ask(TSHIRT_MSG, as_of_date=D15)
    assert turn.final["status"] == "answer" and turn.state["retries"] == 1 and llm.count("verify") == 2


def test_low_confidence_retries_then_says_not_sure_without_calling_verify(db):
    llm = tshirt_llm(classify=classify(cand("6109.1000", 0.4), cand("6105.1000", 0.35)))
    agent, tools = make_agent(llm, db)
    turn = agent.ask(TSHIRT_MSG, as_of_date=D15)
    assert turn.final["status"] == "not_sure" and turn.state["retries"] == 2 and llm.count("verify") == 0
    assert "low confidence" in turn.final["text"] and "compute_duty" not in tools.calls


def test_legal_note_contradiction_fails_verification_but_invented_note_labels_are_ignored(db):
    llm = tshirt_llm(verify=[verify(notes=("N1",), conf=0.9), verify()])      # N1 = Chapter 61 note 1 in the stub evidence
    agent, _ = make_agent(llm, db)
    turn = agent.ask(TSHIRT_MSG, as_of_date=D15)
    assert turn.state["retries"] == 1 and turn.final["status"] == "answer"
    assert "Chapter 61 note 1 may contradict" in json.dumps(turn.state["attempts"])
    llm2 = tshirt_llm(verify=verify(notes=("N99",)))
    agent2, _ = make_agent(llm2, db)
    t2 = agent2.ask(TSHIRT_MSG, as_of_date=D15)
    assert t2.final["status"] == "answer" and t2.state["retries"] == 0
    assert any("do not exist (N99)" in w for w in t2.final["verification"]["warnings"])


def test_verification_warnings_are_shown_and_auditor_text_is_sanitised(db):
    llm = tshirt_llm(verify=verify(problems=["the fabric weight was not stated"], unsupported=["Duty is 55% under SRO 9999(I)/2030, page 4321"]))
    agent, _ = make_agent(llm, db)
    f = agent.ask(TSHIRT_MSG, as_of_date=D15).final
    assert f["status"] == "answer"                                           # the guard did not trip: the invented figures never got in
    assert "warning: unchecked: the fabric weight was not stated" in f["text"]
    assert "warning: unsupported claim: (text withheld" in f["text"]
    for fake in ("55%", "9999(I)/2030", "4321"):
        assert fake not in f["text"]


# ===================================================================== codes: the LLM can never put an invalid code in an answer
def test_invalid_llm_codes_are_rejected_and_never_shown(db):
    # 9999.9999 is not in the tariff; 6110.2000 is a real tariff line that was NOT among the retrieved candidates
    bad = classify(cand("9999.9999", 0.97), cand("6110.2000", 0.9))
    llm = tshirt_llm(classify=bad)
    agent, tools = make_agent(llm, db)
    turn = agent.ask(TSHIRT_MSG, as_of_date=D15)
    assert turn.final["status"] == "not_sure" and turn.final["candidates"] == []
    for code in ("9999.9999", "6110.2000"):
        assert code not in turn.final["text"]
    reasons = {r["code"]: r["reason"] for r in turn.state["rejected_codes"]}
    assert "not among the retrieved candidate lines" in reasons["6110.2000"] and "not among" in reasons["9999.9999"]
    assert "compute_duty" not in tools.calls and llm.count("verify") == 0       # nothing invalid ever reaches the calculator or the auditor


def test_invalid_code_then_valid_code_on_retry_gives_an_answer(db):
    llm = tshirt_llm(classify=[classify(cand("9999.9999", 0.97)), classify(cand("6109.1000", 0.9))])
    agent, _ = make_agent(llm, db)
    turn = agent.ask(TSHIRT_MSG, as_of_date=D15)
    assert turn.final["status"] == "answer" and turn.final["code"] == "6109.1000" and turn.state["retries"] == 1
    assert "9999.9999" not in turn.final["text"]


def test_validate_candidates_checks_digits_offer_and_tariff(db):
    ev = gather(StubRetriever(), no_notes, query="T-shirts", as_of_date=D15)
    tools = RecordingTools(db)
    raw = [cand("61091000", 0.9), cand("6109.1000", 0.8), cand("6109", 0.7), cand("84713010", 0.6), cand("6109.9090", 0.2)]
    valid, rejected = validate_candidates(raw, ev, tools, D15)
    assert [v["code"] for v in valid] == ["6109.1000", "6109.9090"]                  # sorted, duplicates dropped, 8-digit only
    assert {r["code"]: r["reason"] for r in rejected}["6109"] == "not an eight-digit code"
    assert "not among the retrieved" in {r["code"]: r["reason"] for r in rejected}["8471.3010"]
    # a retrieved line that does not exist on the date is also rejected (FY mismatch)
    old = [{**LINES[0], "code": "01012199", "id": "x", "text": "0101.2199 made up", "heading": "01.01"}]
    ev2 = gather(StubRetriever(lines=old), no_notes, query="made up", as_of_date=D15)
    v2, r2 = validate_candidates([cand("0101.2199", 0.9)], ev2, tools, D15)
    assert v2 == [] and "not a valid tariff line" in r2[0]["reason"]


# ===================================================================== numbers: amounts come from the tool, nothing else
def test_answer_numbers_equal_tool_output_and_invented_figures_are_blocked(db):
    invented = "Fits heading 61.09. Regulatory duty of 99% applies under SRO 1234(I)/2026 (page 77), Rs 5,555.55 per piece."
    llm = tshirt_llm(classify=classify(cand("6109.1000", 0.92, reasons=invented), cand("6109.9090", 0.05)))
    agent, _ = make_agent(llm, db)
    turn = agent.ask(TSHIRT_MSG, as_of_date=D15)
    f = turn.final
    assert f["status"] == "answer"
    direct = compute_duty("6109.1000", 1000000, D15, importer=IMP_RC, db_path=db)
    direct_numbers = set(re.findall(r"\d+\.\d{2}\b", json.dumps(direct)))
    shown = money(f["text"])
    assert shown <= direct_numbers, shown - direct_numbers                                 # every amount in the answer is in the tool output
    for ln in direct["lines"]:
        assert ln["amount_pkr"] in shown                                                    # and every line amount of the bill is shown
    for k, v in direct["totals"].items():
        if re.fullmatch(r"\d+\.\d{2}", str(v)):
            assert v in shown, k
    assert f["bill"]["totals"] == direct["totals"] and f["bill"]["lines"] == direct["lines"]
    for fake in ("99%", "1234(I)/2026", "5,555.55", "page 77"):
        assert fake not in f["text"]
    assert "text withheld" in f["text"] and any("unsupported rate 99%" in r["reason"] for r in turn.state["rejected_codes"])


def test_bill_checks_catch_a_wrong_total(db):
    duty = compute_duty("6109.1000", 1000000, D15, importer=IMP_RC, db_path=db)
    lookup = RecordingTools(db).lookup_code("6109.1000", D15)
    ok, issues = bill_checks(duty, lookup, D15)
    assert all(ok.values()) and not issues
    bad = json.loads(json.dumps(duty))
    bad["totals"]["total_payable_pkr"] = "667381.00"
    checks, issues = bill_checks(bad, lookup, D15)
    assert checks["bill_arithmetic"] is False and "do not equal the sum" in issues[0]
    nocite = json.loads(json.dumps(duty))
    nocite["lines"][0]["page"] = None
    assert bill_checks(nocite, lookup, D15)[0]["citations_complete"] is False
    assert bill_checks(duty, lookup, "2024-01-01")[0]["code_exists_on_date"] is False


def test_ground_check_flags_every_kind_of_invented_citation(db):
    duty = compute_duty("6109.1000", 1000000, D15, importer=IMP_RC, db_path=db)
    ev = gather(StubRetriever(), no_notes, query="T-shirts", as_of_date=D15)
    corpus = Corpus(duty, ev, "men's T-shirts value PKR 1,000,000")
    assert check_text("RD is 8% under SRO 1064(I)/2026 S.No 290, p.14, PKR 80,000.00 on 6109.1000; Chapter 61 note 5 applies.", corpus) == []
    kinds = {i["type"] for i in check_text("RD 77% SRO 1111(I)/2026 p.999 PKR 123,456.78 code 6110.2000 Chapter 61 note 9 S.No 7777", corpus)}
    assert kinds == {"rate", "sro_number", "page", "amount", "code", "note", "serial"}
    text, issues = clean_llm_text("a 77% duty", corpus)
    assert issues and "withheld" in text
    assert clean_llm_text("  plain   words\nonly ", corpus) == ("plain words only", [])


# ===================================================================== missing inputs: ask, never guess a number
def test_missing_inputs_trigger_clarify_instead_of_a_number(db):
    llm = FakeLLM({"understand": understand(value_text="2 million", codes_text=["8703.2113"])})      # a code was given: no classify / verify calls expected... until verify
    llm.script["verify"] = verify()          # (only the description-less path skips it; kept to catch an unexpected call)
    agent, tools = make_agent(llm, db)
    t1 = agent.ask("duty on 8703.2113, value PKR 2 million", as_of_date=D15)
    assert t1.final is None and t1.interrupt["kind"] == "duty_input"
    q = questions(t1)
    # all stages of the rules are asked in ONE round (the income-tax question only shows up after the vehicle ones are answered)
    assert set(q) == {"importer.registration_status", "importer.commercial_importer", "importer.active_taxpayer", "goods.vehicle_form", "goods.engine_cc", "goods.used_vehicle_commercial_import_ipo"}
    assert "assessable_value_pkr" not in q                                      # the value was given and is not asked again
    assert q["goods.vehicle_form"]["allowed"] == ["CKD", "CBU"] and "Engine capacity" in q["goods.engine_cc"]["question"]
    assert t1.state.get("duty") is None and t1.state.get("final") is None       # no number of any kind yet
    assert not re.search(r"\d+\.\d{2}", json.dumps(t1.interrupt))
    t2 = agent.resume(t1.thread_id, {"answers": {"importer.registration_status": "registered", "importer.commercial_importer": "yes", "importer.active_taxpayer": "yes", "goods.vehicle_form": "CBU",
                                                 "goods.engine_cc": "1300cc", "goods.used_vehicle_commercial_import_ipo": "no"}})
    assert t2.final["status"] == "answer"
    direct = compute_duty("8703.2113", 2000000, D15, importer=IMP_RC, goods={"vehicle_form": "CBU", "engine_cc": "1300", "used_vehicle_commercial_import_ipo": False}, db_path=db)
    assert direct["status"] == "computed" and f"{int(float(direct['totals']['total_payable_pkr'])):,}" in t2.final["text"]
    # changed expectation (A6): this car (1300 cc, CBU) now carries FED (Table I S.No 55(b)), so the old "FED is NOT in this bill" wording is gone
    assert "Federal excise duty is NOT in this bill" not in t2.final["text"] and "[FED]" in t2.final["text"]
    assert any(ln["tax"] == "FED" for ln in t2.final["bill"]["lines"])
    assert "The code was given by you" in t2.final["text"] and llm.count("classify") == 0 and llm.count("verify") == 0


def test_hallucinated_value_without_a_quote_in_the_message_is_dropped(db):
    llm = tshirt_llm(understand=understand(goods_description="men's cotton T-shirts", value_text="PKR 9,999,999", **IMPORTER_FULL))
    agent, _ = make_agent(llm, db)
    t1 = agent.ask("men's cotton T-shirts, registered importer, commercial importer, filer", as_of_date=D15)
    assert t1.interrupt and set(questions(t1)) == {"assessable_value_pkr"}
    assert "dropped unquoted facts: value" in " ".join(t1.trace)


def test_value_in_dollars_is_asked_in_rupees_not_converted(db):
    llm = tshirt_llm(understand=understand(goods_description="men's cotton T-shirts", value_text="$10,000", **IMPORTER_FULL))
    agent, _ = make_agent(llm, db)
    t1 = agent.ask("men's cotton T-shirts worth $10,000, registered importer, commercial importer, filer", as_of_date=D15)
    assert set(questions(t1)) == {"assessable_value_pkr"}
    qt = questions(t1)["assessable_value_pkr"]["question"]
    assert "USD" in qt and "do not convert currencies" in qt


def test_i_dont_know_ends_in_needs_input_with_no_bill(db):
    llm = tshirt_llm(understand=understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000"))
    agent, tools = make_agent(llm, db)
    t1 = agent.ask("men's cotton T-shirts, value PKR 1,000,000", as_of_date=D15)
    assert set(questions(t1)) == {"importer.registration_status", "importer.commercial_importer", "importer.active_taxpayer"}
    t2 = agent.resume(t1.thread_id, {"importer.registration_status": "I don't know", "importer.commercial_importer": "yes", "importer.active_taxpayer": "yes"})
    assert t2.final["status"] == "needs_input" and t2.final["bill"] is None
    assert "registered" in t2.final["text"] and not re.search(r"TOTAL PAYABLE", t2.final["text"]) and llm.count("verify") == 0


def test_free_text_reply_to_several_questions_is_mapped_by_the_llm_then_read_by_code(db):
    llm = tshirt_llm(understand=understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000"))
    llm.script["map_answers"] = {"answers": {"importer.registration_status": "we are not registered", "importer.commercial_importer": "yes, we sell as is", "importer.active_taxpayer": "yes we are a filer"}}
    agent, _ = make_agent(llm, db)
    t1 = agent.ask("men's cotton T-shirts, value PKR 1,000,000", as_of_date=D15)
    t2 = agent.resume(t1.thread_id, "We are not registered, but yes we sell them as they are, and we are a filer")
    assert t2.final["status"] == "answer" and llm.count("map_answers") == 1
    assert t2.final["bill"]["totals"]["total_payable_pkr"] == compute_duty("6109.1000", 1000000, D15, importer={"registration_status": "unregistered", "commercial_importer": True, "active_taxpayer": True}, db_path=db)["totals"]["total_payable_pkr"]
    assert any(ln["tax"] == "FURTHER_TAX" for ln in t2.final["bill"]["lines"])      # unregistered at the 18% rate: further tax is added (seen on real assessed GDs)


def code_only_llm(value_text, code, **extra):
    return FakeLLM({"understand": understand(value_text=value_text, codes_text=[code], **extra)})


def test_specific_duty_asks_for_the_quantity_in_the_tariff_unit_and_never_converts(db):
    agent, _ = make_agent(code_only_llm("PKR 1,000,000", "1507.1000", **IMPORTER_FULL), db)
    t1 = agent.ask("duty on 1507.1000, value PKR 1,000,000, registered importer, commercial importer, filer", as_of_date=D15)
    q = questions(t1)
    assert set(q) == {"quantity"} and q["quantity"]["unit"] == "MT" and "MT" in q["quantity"]["question"]
    t2 = agent.resume(t1.thread_id, "2000 kg")                          # wrong unit: refused, not converted
    assert t2.interrupt and "do not convert units" in questions(t2)["quantity"]["error"]
    t3 = agent.resume(t2.thread_id, "2 MT")
    assert t3.final["status"] == "answer" and "303,821.59" in t3.final["text"]          # hand case 6 in tests/test_tools.py
    assert "Rs 10,550 per MT x 2 MT" in t3.final["text"] and "needs_review" in t3.final["text"]   # rotated-cell rate is flagged, not hidden


def test_film_running_time_is_asked_as_a_number(db):
    agent, _ = make_agent(code_only_llm("PKR 1,000,000", "3706.1000", **IMPORTER_FULL), db)
    t1 = agent.ask("duty on 3706.1000, value PKR 1,000,000, registered importer, commercial importer, filer", as_of_date=D15)
    assert "goods.running_time_minutes" in questions(t1) and questions(t1)["goods.running_time_minutes"]["type"] == "number"
    t2 = agent.resume(t1.thread_id, {"answers": {k: ("90 minutes" if k == "goods.running_time_minutes" else "1000 metres" if k == "quantity" else "no") for k in questions(t1)}})
    assert t2.interrupt is None or t2.interrupt["kind"] == "duty_input"


def test_mobile_phone_gives_a_partial_bill_and_no_total(db):
    agent, _ = make_agent(code_only_llm("PKR 1,000,000", "8517.1390", quantity_text="10 sets", **IMPORTER_FULL), db)
    t1 = agent.ask("duty on 8517.1390, 10 sets, value PKR 1,000,000, registered importer, commercial importer, filer", as_of_date=D15)
    answers = {"goods.c_and_f_value_usd_per_unit": "150", "goods.plant_machinery_for_manufacturing": "no"}
    t2 = agent.resume(t1.thread_id, {"answers": {k: answers[k] for k in questions(t1) if k in answers}})
    f = t2.final
    assert f["status"] == "cannot_compute" and f["bill"]["totals"] is None and "NO TOTAL IS GIVEN" in f["text"] and "TOTAL PAYABLE" not in f["text"]
    assert "60,000.00" in f["text"] and "sales tax" in f["text"] and "NOT the amount payable" in f["text"]


def test_a_fiscal_year_without_a_date_is_asked_for_an_exact_date(db):
    llm = tshirt_llm(understand=understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000", **IMPORTER_FULL))
    agent, _ = make_agent(llm, db)
    t = agent.ask(TSHIRT_MSG + " in FY2026-27")
    assert t.interrupt and "need an exact date" in questions(t)["as_of_date"]["question"]


# ===================================================================== dates
def test_unsupported_date_is_refused_before_any_search_or_calculation(db):
    llm = FakeLLM({})                        # any LLM call would raise AssertionError
    stub = StubRetriever()
    agent, tools = make_agent(llm, db, retriever=stub)
    turn = agent.ask("laptops", as_of_date="2024-03-01")
    f = turn.final
    assert f["status"] == "refused" and "2024-03-01" in f["text"] and "2025-07-01" in f["text"] and "2027-06-30" in f["text"]
    assert llm.calls == [] and tools.calls == [] and stub.calls == [] and f["bill"] is None
    for bad in ("2025-06-30", "2027-07-01"):                     # one day outside either end
        assert agent.ask("laptops", as_of_date=bad).final["status"] == "refused"
    for ok in ("2025-07-01", "2027-06-30"):                      # the edges are inside: the agent carries on and asks what the product is
        a2, _ = make_agent(FakeLLM({"understand": understand()}), db)
        t = a2.ask("hello", as_of_date=ok)
        assert t.final is None and t.interrupt["questions"][0]["id"] == "goods_description" and t.state["as_of_date"] == ok


def test_unsupported_fiscal_year_in_the_text_is_refused_without_the_llm(db):
    llm = FakeLLM({})
    agent, tools = make_agent(llm, db)
    f = agent.ask("What was the duty on laptops in FY2023-24?").final
    assert f["status"] == "refused" and "2023-24" in f["text"] and llm.calls == [] and tools.calls == []


def test_date_found_by_the_llm_in_the_message_is_checked_in_code(db):
    llm = FakeLLM({"understand": understand(goods_description="laptops", date_text="1 March 2024")})
    agent, tools = make_agent(llm, db)
    f = agent.ask("laptops on 1 March 2024").final
    assert f["status"] == "refused" and "2024-03-01" in f["text"] and tools.calls == []
    # a date the LLM claims but the user never wrote is ignored: the agent asks instead of assuming
    llm2 = FakeLLM({"understand": understand(goods_description="laptops", date_text="15 July 2026")})
    agent2, tools2 = make_agent(llm2, db)
    t = agent2.ask("laptops")
    assert t.interrupt and "as_of_date" in questions(t)


def test_missing_date_is_asked_never_assumed_to_be_today(db):
    llm = tshirt_llm(understand=understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000", **IMPORTER_FULL))
    agent, tools = make_agent(llm, db, today=lambda: __import__("datetime").date(2026, 10, 14))
    t = agent.ask(TSHIRT_MSG)
    assert t.interrupt and list(questions(t)) == ["as_of_date"] and t.state.get("as_of_date") is None and tools.calls == []
    # an answer that is not a full date is asked again, a fiscal year alone is not a date
    t2 = agent.resume(t.thread_id, "FY2026-27")
    assert t2.interrupt and "could not read a full date" in questions(t2)["as_of_date"]["error"]
    t3 = agent.resume(t2.thread_id, "2026-07-15")
    assert t3.final["status"] == "answer" and t3.final["as_of_date"] == "2026-07-15"
    # "today" is accepted only when the user writes it, and the answer says so
    llm4 = tshirt_llm(understand=understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000", date_text="today", **IMPORTER_FULL))
    agent4, _ = make_agent(llm4, db, today=lambda: __import__("datetime").date(2026, 7, 15))
    f = agent4.ask(TSHIRT_MSG + ", today").final
    assert f["status"] == "answer" and f["as_of_date"] == "2026-07-15" and "you wrote 'today'" in f["text"]


def test_the_two_fiscal_years_use_their_own_rules(db):
    for d, rd_sro, acd_sro in (("2026-06-30", "1152(I)/2025", "1151(I)/2025"), ("2026-07-01", "1064(I)/2026", "1063(I)/2026")):
        agent, _ = make_agent(tshirt_llm(), db)
        t = agent.ask(TSHIRT_MSG, as_of_date=d).final["text"]
        assert rd_sro in t and acd_sro in t


# ===================================================================== LLM problems are reported, not crashed on
def test_quota_error_is_a_clear_final_message_not_a_stack_trace(db):
    llm = FakeLLM({"understand": LLMRateLimited("The Gemini free tier is out of quota for every configured model (HTTP 429). Nothing was computed.")})
    agent, tools = make_agent(llm, db)
    f = agent.ask(TSHIRT_MSG, as_of_date=D15).final
    assert f["status"] == "error" and "out of quota" in f["text"] and "Traceback" not in f["text"] and tools.calls == []
    assert "Nothing was computed" in f["text"] and f["bill"] is None


def test_quota_error_during_verify_does_not_show_an_unverified_bill(db):
    llm = tshirt_llm(verify=LLMRateLimited("out of quota"))
    agent, _ = make_agent(llm, db)
    f = agent.ask(TSHIRT_MSG, as_of_date=D15).final
    assert f["status"] == "error" and f["bill"] is None and "NOT verified" in f["text"] and "6109.1000" in f["text"]
    assert "TOTAL PAYABLE" not in f["text"]


def test_unreadable_llm_output_is_handled(db):
    llm = tshirt_llm(classify={"candidates": "not a list"})
    agent, _ = make_agent(llm, db)
    f = agent.ask(TSHIRT_MSG, as_of_date=D15).final
    assert f["status"] == "not_sure"       # a failed classification is retried twice, then "not sure"


def test_no_matching_lines_means_no_llm_classification_and_a_not_sure_answer(db):
    llm = FakeLLM({"understand": understand(goods_description="zzz qqq", value_text="PKR 1")})
    agent, _ = make_agent(llm, db, retriever=StubRetriever(lines=[]))
    f = agent.ask("zzz qqq PKR 1", as_of_date=D15).final
    assert f["status"] == "not_sure" and "No tariff line matched" in f["text"] and llm.count("classify") == 0


# ===================================================================== codes written by the user
def test_a_code_alone_skips_classify_and_the_llm_fit_check(db):
    llm = FakeLLM({"understand": understand(value_text="PKR 1,000,000", codes_text=["6109.1000"], **IMPORTER_FULL)})
    agent, _ = make_agent(llm, db)
    f = agent.ask("duty on 6109.1000, value PKR 1,000,000, registered importer, commercial importer, filer", as_of_date=D15).final
    assert f["status"] == "answer" and "667,380.00" in f["text"] and "language-model fit check was skipped" in json.dumps(f["verification"])
    assert llm.count("classify") == 0 and llm.count("verify") == 0


def test_a_code_that_is_not_in_the_tariff_is_reported_and_ignored(db):
    llm = FakeLLM({"understand": understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000", codes_text=["6109.9999"], **IMPORTER_FULL),
                   "classify": classify(cand("6109.1000", 0.92)), "verify": verify()})
    agent, _ = make_agent(llm, db)
    f = agent.ask("men's cotton T-shirts code 6109.9999, value PKR 1,000,000, registered importer, commercial importer, filer", as_of_date=D15).final
    assert f["status"] == "answer" and "6109.9999" in f["text"] and "not a line of the tariff" in f["text"] and f["code"] == "6109.1000"


def test_a_raw_eight_digit_amount_is_not_mistaken_for_a_code(db):
    llm = tshirt_llm(understand=understand(goods_description="men's cotton T-shirts", value_text="PKR 10000000", **IMPORTER_FULL))
    agent, _ = make_agent(llm, db)
    t = agent.ask("men's cotton T-shirts, value PKR 10000000, registered importer, commercial importer, filer", as_of_date=D15)
    assert t.state["user_codes"] == [] and t.final["status"] == "answer" and "10,000,000.00" in t.final["text"]


def test_more_than_one_product_asks_which_one(db):
    llm = FakeLLM({"understand": understand(goods_description="laptops and phones", multiple_products=True)})
    agent, _ = make_agent(llm, db)
    t = agent.ask("laptops and phones", as_of_date=D15)
    assert t.interrupt and "one product at a time" in questions(t)["goods_description"]["question"]


# ===================================================================== persistence
def test_sqlite_checkpointer_lets_a_paused_conversation_survive_a_restart(db, tmp_path):
    from langgraph.checkpoint.sqlite import SqliteSaver

    path = tmp_path / "checkpoints.sqlite"
    conn = sqlite3.connect(path, check_same_thread=False)
    agent1, _ = make_agent(FakeLLM({"understand": understand(goods_description="laptop computers")}), db, checkpointer=SqliteSaver(conn))
    t1 = agent1.ask("laptop computers")
    assert t1.interrupt["kind"] == "request"
    conn.close()
    conn2 = sqlite3.connect(path, check_same_thread=False)                         # "a new process"
    llm2 = FakeLLM({"classify": classify(cand("8471.3010", 0.9)), "verify": verify()})
    agent2, _ = make_agent(llm2, db, checkpointer=SqliteSaver(conn2))
    assert agent2.pending(t1.thread_id)["questions"][0]["id"] == "as_of_date"
    t2 = agent2.resume(t1.thread_id, "2026-07-15")
    assert t2.interrupt["kind"] == "duty_input"
    t3 = agent2.resume(t2.thread_id, {"assessable_value_pkr": "1000000", "importer.registration_status": "registered", "importer.commercial_importer": "yes", "importer.active_taxpayer": "yes",
                                      "importer.manufacturer_in_house_use": "no"})
    assert t3.final["status"] == "answer" and "197,800.00" in t3.final["text"]
    conn2.close()


def test_thread_misuse_is_reported_clearly(db):
    llm = tshirt_llm()
    agent, _ = make_agent(llm, db)
    f = agent.ask(TSHIRT_MSG, as_of_date=D15, thread_id="done1")
    assert f.final["status"] == "answer"
    with pytest.raises(ValueError, match="already exists"):
        agent.ask("something else", thread_id="done1")                  # no silent reuse of old state
    with pytest.raises(ValueError, match="no pending questions"):
        agent.resume("done1", "yes")
    with pytest.raises(ValueError, match="no pending questions"):
        agent.resume("never-existed", "yes")


def test_unrecognised_resume_payload_is_asked_again_without_an_llm_call(db):
    llm = tshirt_llm(understand=understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000"))
    agent, _ = make_agent(llm, db)
    t1 = agent.ask("men's cotton T-shirts, value PKR 1,000,000", as_of_date=D15)
    t2 = agent.resume(t1.thread_id, {"unrelated": "x"})
    assert t2.interrupt and all(q.get("error") for q in t2.interrupt["questions"]) and llm.count("map_answers") == 0


def test_structured_answers_may_be_real_booleans(db):
    agent, _ = make_agent(tshirt_llm(understand=understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000")), db)
    t1 = agent.ask("men's cotton T-shirts, value PKR 1,000,000", as_of_date=D15)
    t2 = agent.resume(t1.thread_id, {"answers": {"importer.registration_status": "registered", "importer.commercial_importer": True, "importer.active_taxpayer": True}})
    assert t2.final["status"] == "answer"


# ===================================================================== retrieval rules
def test_score_floors_drop_irrelevant_hits_but_keep_exact_code_hits():
    class R(StubRetriever):
        def __call__(self, query, index, as_of_date, k):
            hits = super().__call__(query, index, as_of_date, k)
            if index == "rulings":
                return [{"id": "ruling:x", "ruling": "Chlorinated paraffin wax", "text": "unrelated", "page": 1, "source_file": "r.pdf", "rerank_score": -11.3, "method": "hybrid+rerank"},
                        {"id": "ruling:y", "ruling": "Massage chairs", "text": "relevant", "page": 2, "source_file": "r.pdf", "rerank_score": 7.1, "method": "hybrid+rerank"}]
            if index == "tariff" and "weather" in query:
                return [dict(LINES[0], rerank_score=-10.5, method="hybrid+rerank")]
            return hits

    ev = gather(R(), no_notes, query="massage chair", as_of_date=D15)
    assert [r["ruling"] for r in ev["rulings"]] == ["Massage chairs"] and ev["dropped"]["rulings"] == 1
    assert gather(R(), no_notes, query="how is the weather", as_of_date=D15)["lines"] == []
    exact = gather(R(), no_notes, query="", user_codes=["61091000"], as_of_date=D15)
    assert [ln["code"] for ln in exact["lines"]][0] == "6109.1000"


def test_codes_quoted_in_a_relevant_ruling_join_the_candidate_pool():
    class R(StubRetriever):
        def __call__(self, query, index, as_of_date, k):
            if index == "rulings":
                return [{"id": "ruling:pn", "ruling": "Public Notice 60/2026", "text": "classified under 6105.1000 not 6109.1000", "page": 3, "source_file": "pn.pdf", "rerank_score": 6.0, "method": "hybrid+rerank"}]
            return super().__call__(query, index, as_of_date, k)

    stub = R(lines=[LINES[0], LINES[2]])
    ev = gather(stub, no_notes, query="T-shirt", as_of_date=D15, k_tariff=1)
    assert any(ln.get("from_ruling") == "R1" for ln in ev["lines"]) or {ln["code"] for ln in ev["lines"]} >= {"6109.1000", "6105.1000"}


# ===================================================================== real search index (skipped when it is not built)
INDEX = Path("data/processed/search_index/tariff/emb.npy")


@pytest.mark.skipif(not INDEX.exists(), reason="search index not built (python -m src.search.build)")
def test_real_search_feeds_the_classifier_with_notes_and_the_right_candidate(db):
    seen = {}

    def classifier(prompt, n):
        seen["prompt"] = prompt
        return classify(cand("6109.1000", 0.9, reasons="T-shirts of cotton, knitted: heading 61.09.", evidence=("T1",)))

    llm = FakeLLM({"understand": understand(goods_description="men's knitted cotton t-shirts", value_text="PKR 1,000,000", **IMPORTER_FULL), "classify": classifier, "verify": verify()})
    agent = CustomsAgent(llm, tools=RecordingTools(db))                       # real retriever, real notes loader, real tools
    turn = agent.ask("men's knitted cotton t-shirts, value PKR 1,000,000, registered importer, commercial importer, filer", as_of_date=D15)
    p = seen["prompt"]
    assert "6109.1000" in p and "Chapter 61 note" in p and "GRI rule 1" in p
    assert turn.final["status"] == "answer" and "667,380.00" in turn.final["text"]
    ev = turn.state["evidence"]
    assert ev["rulings"] == [] and all(n["source_file"] and n["page"] for n in ev["notes"])      # an irrelevant ruling never shows up
