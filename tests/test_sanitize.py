"""User-facing text must carry legal citations only, never internal repo paths or file names."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.sanitize import clean_text, scrub
from src.api.security import RateLimiter
from src.api.service import AgentService, FeedbackStore

INTERNAL = re.compile(r"(docs|src)/|data/(raw|processed|ground_truth)|\w\.(md|csv|jsonl?|sqlite|py)\b")


@pytest.mark.parametrize("raw, want", [
    ("Sales Tax Act s.3(1A): further tax applies to unregistered persons (docs/duty_formula.md step 7).",
     "Sales Tax Act s.3(1A): further tax applies to unregistered persons."),
    ("Part III 5.5% or 6% (docs/duty_formula.md OPEN-7).", "Part III 5.5% or 6%."),
    ("so it is added (OPEN-4, docs/gd_findings.md).", "so it is added."),
    ("matched through the mapping (a6_fed_mapping.csv); others are not", "matched through the mapping; others are not"),
    ("no notification in data/raw, OQ-A6-5", "no notification in,"),
    ("see src/tools/compute.py for details", "see for details"),
])
def test_clean_text_removes_internal_refs(raw, want):
    assert clean_text(raw) == want


@pytest.mark.parametrize("keep", [
    "SRO 1064(I)/2026 para 2, Sales Tax Act s.3(1A), First Schedule Part II",
    "Tariff page 412, 20268251181330180Tariff-2026-27.pdf",   # FBR source PDF names are citations
    "the docs and data/information the importer keeps", "Rs. 117.00/MT", "8471.3010",
])
def test_clean_text_keeps_legal_citations(keep):
    assert clean_text(keep) == keep


def test_scrub_walks_nested_values_and_keeps_non_strings():
    obj = {"why": "x (docs/a.md)", "lines": [{"note": "y (b.csv)", "amount": 12.5, "ok": True, "n": None}], "t": ("z src/x.py",)}
    assert scrub(obj) == {"why": "x", "lines": [{"note": "y", "amount": 12.5, "ok": True, "n": None}], "t": ["z"]}


def test_tool_strings_have_no_internal_paths():
    """The bill and rule texts the tools can return are written clean at the source."""
    for f in ("src/tools/compute.py", "src/tools/fed.py", "src/tools/rules.py"):
        for lit in re.findall(r'"((?:[^"\\\n]|\\.){20,})"', Path(f).read_text(encoding="utf-8")):
            if " " in lit and "TAX_TOTAL_BUCKET" not in lit:   # developer error message, never sent to users
                assert not INTERNAL.search(lit), (f, lit)


def test_api_replies_are_scrubbed(tmp_path):
    q = {"message": "I need more information (docs/agent.md).", "notes": ["see data/processed/x.csv"],
         "questions": [{"id": "importer.registration_status", "question": "Registered?", "type": "choice",
                        "why": "Sales Tax Act s.3(1A): further tax applies to unregistered persons (docs/duty_formula.md step 7)."}]}

    class Agent:
        def ask(self, question, as_of_date=None, thread_id=None):
            from src.agent.runner import TurnResult
            return TurnResult(thread_id="a" * 32, interrupt=q, final=None, state={})

    bill = {"status": "needs_input", "missing_inputs": [{"why": "Part III 5.5% or 6% (docs/duty_formula.md OPEN-7)."}],
            "assumptions": ["not in data/raw (OQ-A6-9)"], "lines": [{"source_file": "202663017637155381064-2026.pdf", "page": 3}]}
    lim = {k: (100, 60) for k in ("agent", "agent_hour", "lookup", "bill", "feedback")}
    c = TestClient(create_app(AgentService(agent=Agent()), RateLimiter(lim), FeedbackStore(tmp_path / "f.sqlite"),
                              lookup_fn=lambda *a: {"hits": [{"note": "x (docs/a.md)"}]}, bill_fn=lambda *a, **k: bill))
    for r in (c.post("/api/agent/ask", json={"question": "laptops"}),
              c.post("/api/bill", json={"code": "84713010", "value_pkr": 1000}),
              c.post("/api/lookup", json={"query": "laptop"})):
        assert r.status_code == 200 and not INTERNAL.search(r.text.replace(".pdf", "")), r.text
    j = c.post("/api/bill", json={"code": "84713010", "value_pkr": 1000}).json()
    assert j["lines"][0]["source_file"] == "202663017637155381064-2026.pdf"
    assert j["missing_inputs"][0]["why"] == "Part III 5.5% or 6%."


@pytest.mark.parametrize("raw, want", [
    ("Part III 5.5% or 6% (OPEN-7).", "Part III 5.5% or 6%."),
    ("No source document states a rounding rule (OPEN-5). Each line is rounded half-up.", "No source document states a rounding rule. Each line is rounded half-up."),
    ("not collected (OQ-A6-9); electric vehicles are not computed (OQ-A6-1).", "not collected; electric vehicles are not computed."),
    ("so it is added (OPEN-4, docs/gd_findings.md).", "so it is added."),
    ("Sales Tax Act s.3(1A) and the OPENING stock", "Sales Tax Act s.3(1A) and the OPENING stock"),
])
def test_internal_open_question_tags_are_removed(raw, want):
    assert clean_text(raw) == want
