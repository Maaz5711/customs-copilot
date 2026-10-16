"""The blind AI second reader (src/eval/adjudicate.py). FakeLLM, stub notes: no network."""
import random

from src.agent import FakeLLM
from src.eval.adjudicate import judge, summarize, _append, SYSTEM

WORDS = {"85361090": "Fuses: Other", "85351000": "Fuses for a voltage exceeding 1,000 V"}


def stub_retriever(q, index, date, k):
    return [{"id": "n1", "method": "exact_code", "scope": "Chapter 85", "note_number": "1", "text": "note text"}] if index == "notes" else []


def no_notes(date):
    return [{"id": "g1", "kind": "gri", "note_number": "1", "text": "GRI 1 text"}]


def seed_that(flips: bool) -> str:
    for i in range(100):
        if (random.Random(f"s{i}").random() < 0.5) == flips:
            return f"s{i}"
    raise AssertionError


def ask(pick, flips):
    llm = FakeLLM({"eval_adjudicate": {"better": pick, "confidence": 0.8, "reason": "r"}})
    res = judge(llm, "FUSE 6.3A 250V", "85351000", "85361090", "2026-02-10", WORDS, seed_that(flips), stub_retriever, no_notes)
    return llm, res


def test_the_prompt_is_blind_and_carries_wording_notes_and_rules():
    llm, _ = ask("A", False)
    p = llm.calls[0]["prompt"].lower()
    assert "declared" not in p and "agent" not in p and "our tool" not in p
    assert "fuses: other" in p and "exceeding 1,000 v" in p and "note text" in p and "gri 1 text" in p
    assert "declared" not in SYSTEM.lower() and "agent" not in SYSTEM.lower()


def test_verdict_is_mapped_back_to_the_original_codes_whatever_the_order_shown():
    # not flipped: A is x (85351000), B is y (85361090)
    assert ask("A", False)[1]["verdict"] == "x" and ask("B", False)[1]["verdict"] == "y"
    # flipped: A is y, B is x
    assert ask("A", True)[1]["verdict"] == "y" and ask("B", True)[1]["verdict"] == "x"
    assert ask("both", True)[1]["verdict"] == "both" and ask("neither", False)[1]["verdict"] == "neither"
    assert ask("banana", False)[1]["verdict"] == "unclear"


def test_the_order_is_deterministic_for_a_case_and_roughly_balanced_over_cases():
    flips = [random.Random(f"G{i:04d}").random() < 0.5 for i in range(400)]
    assert 140 < sum(flips) < 260
    assert [random.Random("G0001").random() for _ in range(2)] == [random.Random("G0001").random() for _ in range(2)]


def test_summary_counts_each_verdict(tmp_path):
    for i, v in enumerate(["x", "x", "y", "both", "neither", "unclear"]):
        _append(tmp_path / "calibrate.jsonl", {"case_id": f"C{i}", "x": "1", "y": "2", "verdict": v})
    s = summarize("calibrate", tmp_path)
    assert (s["n"], s["x"], s["y"], s["both"], s["neither"], s["unclear"]) == (6, 2, 1, 1, 1, 1)
