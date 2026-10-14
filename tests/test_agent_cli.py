"""CLI (python -m src.agent) and the MCP-backed toolbox. FakeLLM + stub retrieval + the real exact tools."""
import io
import re
from pathlib import Path

import pytest

import src.agent.__main__ as cli
from src.agent import CustomsAgent, FakeLLM
from src.agent.toolbox import McpToolBox, ToolBox
from src.store.build import build

from tests.agent_fakes import IMPORTER_FULL, RecordingTools, StubRetriever, cand, classify, no_notes, understand, verify

PROC = Path("data/processed")
pytestmark = pytest.mark.skipif(not (PROC / "a3_acd_rules.csv").exists(), reason="processed data not present")


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("agentcli") / "store.sqlite"
    build(path)
    return str(path)


def laptop_llm():
    return FakeLLM({"understand": understand(goods_description="laptop computers"), "classify": classify(cand("8471.3010", 0.9)), "verify": verify()})


def kwargs(db):
    return {"retriever": StubRetriever(), "notes_loader": no_notes, "tools": RecordingTools(db)}


def scripted_input(answers: dict, log: list):
    """input() stand-in: answers a prompt like 'your answer to [importer.registration_status]> ' from a dict."""
    def fn(prompt=""):
        log.append(prompt)
        m = re.search(r"\[([^\]]+)\]>", prompt)
        return answers[m.group(1)] if m else ""
    return fn


ALL_ANSWERS = {"assessable_value_pkr": "1,000,000", "importer.registration_status": "registered", "importer.commercial_importer": "yes", "importer.manufacturer_in_house_use": "no"}


def test_cli_interactive_asks_the_questions_and_prints_the_answer(db):
    out, log = io.StringIO(), []
    code = cli.main(["laptop computers", "--date", "2026-07-15"], input_fn=scripted_input(ALL_ANSWERS, log), out=out, llm=laptop_llm(), agent_kwargs=kwargs(db))
    text = out.getvalue()
    assert code == 0
    assert "To calculate the duties I need these details" in text and "[1/4]" in text and "answer yes or no" in text and "type 'I don't know'" in text
    assert "TOTAL PAYABLE: PKR 197,800.00" in text and "decision support, not legal advice" in text
    assert len(log) == 4                                                           # one prompt per question, nothing else asked


def test_cli_debug_prints_the_node_path_and_llm_usage(db):
    out = io.StringIO()
    cli.main(["laptop computers", "--date", "2026-07-15", "--debug"], input_fn=scripted_input(ALL_ANSWERS, []), out=out, llm=laptop_llm(), agent_kwargs=kwargs(db))
    t = out.getvalue()
    assert "path: understand > search > classify > calculate > clarify > understand > calculate > verify > respond" in t


def test_cli_without_terminal_stops_with_the_questions_and_continues_from_a_checkpoint_file(db, tmp_path):
    ck = str(tmp_path / "threads.sqlite")
    out1 = io.StringIO()
    code1 = cli.main(["laptop computers", "--date", "2026-07-15", "--db", ck, "--thread", "demo1"], out=out1, llm=laptop_llm(), agent_kwargs=kwargs(db))
    t1 = out1.getvalue()
    assert code1 == 2 and "Not a terminal" in t1 and "--thread demo1" in t1 and "--answer assessable_value_pkr=..." in t1 and "TOTAL PAYABLE" not in t1
    # a second run (a new process in real life) answers from the command line
    out2 = io.StringIO()
    args = ["--db", ck, "--thread", "demo1"] + [f"--answer={k}={v}" for k, v in ALL_ANSWERS.items()]
    code2 = cli.main(args, out=out2, llm=laptop_llm(), agent_kwargs=kwargs(db))
    assert code2 == 0 and "TOTAL PAYABLE: PKR 197,800.00" in out2.getvalue()
    # the finished thread has nothing pending any more
    out3 = io.StringIO()
    assert cli.main(["--db", ck, "--thread", "demo1", "--answer", "x=1"], out=out3, llm=laptop_llm(), agent_kwargs=kwargs(db)) == 1
    assert "no pending questions" in out3.getvalue()


def test_cli_refuses_an_unsupported_date_and_exits_cleanly(db):
    out = io.StringIO()
    code = cli.main(["laptops", "--date", "2023-01-01"], input_fn=lambda p="": "", out=out, llm=FakeLLM({}), agent_kwargs=kwargs(db))
    assert code == 0 and "I can't answer this question" in out.getvalue() and "2025-07-01" in out.getvalue()


def test_cli_reports_an_llm_error_with_exit_code_1(db):
    from src.agent.llm import LLMRateLimited

    out = io.StringIO()
    code = cli.main(["laptops", "--date", "2026-07-15"], input_fn=lambda p="": "", out=out, llm=FakeLLM({"understand": LLMRateLimited("out of quota, nothing was computed")}), agent_kwargs=kwargs(db))
    assert code == 1 and "out of quota" in out.getvalue() and "Traceback" not in out.getvalue()


def test_cli_passes_model_budget_and_cache_flags_to_gemini(monkeypatch, db):
    seen = {}

    class Spy(FakeLLM):
        def __init__(self, **kw):
            seen.update(kw)
            super().__init__({"understand": understand(goods_description="laptops")})

    monkeypatch.setattr(cli, "GeminiLLM", Spy)
    out = io.StringIO()
    # an unsupported date is refused before any LLM call, so only the constructor flags matter here
    cli.main(["laptops", "--date", "2023-01-01", "--models", "m-a, m-b", "--max-llm-calls", "5", "--no-cache"], input_fn=lambda p="": "", out=out, agent_kwargs=kwargs(db))
    assert seen == {"models": ["m-a", "m-b"], "cache": False, "max_calls": 5}


def test_cli_list_models_does_not_need_a_question():
    class L(FakeLLM):
        models = ["gemini-3.5-flash", "gemini-3-flash-preview"]

        def available_models(self):
            return ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3.5-flash"]

    out = io.StringIO()
    assert cli.main(["--list-models"], out=out, llm=L()) == 0
    t = out.getvalue()
    assert "  * gemini-3.5-flash" in t and "    gemini-2.5-flash" in t and "does not use generation quota" in t


def test_cli_with_no_question_and_no_terminal_explains_how_to_start(db):
    out = io.StringIO()
    assert cli.main([], out=out, llm=FakeLLM({}), agent_kwargs=kwargs(db)) == 1
    assert "Give a question" in out.getvalue()


# ===================================================================== MCP-backed tools
def test_mcp_toolbox_gives_the_same_results_as_in_process_tools_and_runs_the_agent(db):
    imp = {"registration_status": "registered", "commercial_importer": True}
    local = ToolBox(db)
    mcp = McpToolBox(db_path=db)
    try:
        assert mcp.lookup_code("6109.1000", "2026-07-15") == local.lookup_code("6109.1000", "2026-07-15")
        assert mcp.compute_duty("6109.1000", "1000000", "2026-07-15", importer=imp) == local.compute_duty("6109.1000", "1000000", "2026-07-15", importer=imp)
        assert mcp.get_applicable_sros("6109.1000", "2026-07-01") == local.get_applicable_sros("6109.1000", "2026-07-01")
        # a specific-rate duty with quantity goes through unchanged (string quantity)
        a = mcp.compute_duty("1507.1000", "1000000", "2026-07-15", importer=imp, quantity="2", quantity_unit="MT")
        assert a["totals"]["total_payable_pkr"] == "303821.59"                              # hand case 6 in tests/test_tools.py
        llm = FakeLLM({"understand": understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000", **IMPORTER_FULL),
                       "classify": classify(cand("6109.1000", 0.92)), "verify": verify()})
        agent = CustomsAgent(llm, retriever=StubRetriever(), notes_loader=no_notes, tools=mcp)
        f = agent.ask("men's cotton T-shirts, value PKR 1,000,000, registered importer, commercial importer", as_of_date="2026-07-15").final
        assert f["status"] == "answer" and "667,380.00" in f["text"]
    finally:
        mcp.close()
