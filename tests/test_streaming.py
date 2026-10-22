"""Live progress ("thinking") stream: the API sends one JSON line per agent step, then the same reply the normal endpoint gives.
No network: a stub agent for the API tests, a scripted FakeLLM for the real graph."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.agent import CustomsAgent, FakeLLM
from src.agent.nodes import Config
from src.agent.runner import TurnResult
from src.api.app import create_app
from src.api.security import RateLimiter
from src.api.service import AgentService, FeedbackStore
from src.store.build import build
from tests.agent_fakes import IMPORTER_FULL, RecordingTools, StubRetriever, cand, classify, no_notes, understand, verify

TID = "b" * 32
LIMITS = {"agent": (100, 60), "agent_hour": (1000, 3600), "lookup": (100, 60), "bill": (100, 60), "feedback": (100, 60)}
PROC = Path("data/processed")


class StreamStub:
    def __init__(self):
        self.waiting, self.boom = set(), None

    def stream_ask(self, question, as_of_date=None, thread_id=None):
        yield {"type": "step", "node": "understand", "text": "understand: facts extracted by x"}
        yield {"type": "step", "node": "search", "text": "search: 12 lines, 3 notes, 0 SRO excerpts, 1 rulings (see docs/duty_formula.md)"}
        if self.boom:
            raise self.boom
        self.waiting.add(TID)
        yield {"type": "turn", "turn": TurnResult(thread_id=TID, interrupt={"message": "More info", "notes": [], "questions": [{"id": "q1", "question": "Material?", "type": "text"}]}, final=None, state={})}

    def pending(self, tid):
        return {"questions": []} if tid in self.waiting else None

    def stream_resume(self, tid, answer):
        self.waiting.discard(tid)
        yield {"type": "step", "node": "classify", "text": "classify: top 6109.1000 confidence 90%"}
        yield {"type": "turn", "turn": TurnResult(thread_id=tid, interrupt=None, final={"status": "answer", "code": "61091000", "text": "t"}, state={})}


@pytest.fixture
def stub():
    return StreamStub()


@pytest.fixture
def client(stub, tmp_path):
    return TestClient(create_app(AgentService(agent=stub), RateLimiter(LIMITS), FeedbackStore(tmp_path / "f.sqlite")))


def lines(resp):
    return [json.loads(x) for x in resp.text.splitlines() if x.strip()]


def test_ask_stream_sends_steps_then_the_same_payload_as_the_normal_endpoint(client):
    r = client.post("/api/agent/ask/stream", json={"question": "cotton t-shirts"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson") and r.headers["cache-control"] == "no-store"
    ev = lines(r)
    assert [e["type"] for e in ev] == ["step", "step", "done"]
    assert ev[0]["text"].startswith("understand:") and ev[2]["reply"]["status"] == "questions" and ev[2]["reply"]["thread_id"] == TID


def test_internal_file_names_never_reach_the_stream(client):
    ev = lines(client.post("/api/agent/ask/stream", json={"question": "cotton t-shirts"}))
    assert "docs/" not in json.dumps(ev) and "duty_formula" not in json.dumps(ev)


def test_answer_stream_resumes_the_conversation(client):
    client.post("/api/agent/ask/stream", json={"question": "cotton t-shirts"})
    ev = lines(client.post("/api/agent/answer/stream", json={"thread_id": TID, "answers": {"q1": "cotton"}}))
    assert ev[-1]["type"] == "done" and ev[-1]["reply"]["status"] == "answer" and ev[0]["text"].startswith("classify:")


def test_unknown_thread_is_reported_inside_the_stream(client):
    ev = lines(client.post("/api/agent/answer/stream", json={"thread_id": "c" * 32, "answers": {"q1": "x"}}))
    assert ev == [{"type": "error", "status": 404, "message": "This conversation has expired. Please start again."}]


def test_a_failure_during_the_stream_becomes_a_safe_error_event(client, stub):
    stub.boom = RuntimeError("secret details about the user's goods")
    ev = lines(client.post("/api/agent/ask/stream", json={"question": "cotton t-shirts"}))
    assert ev[-1]["type"] == "error" and ev[-1]["status"] == 500 and "secret" not in json.dumps(ev[-1]) and "reference" in ev[-1]["message"]


def test_validation_and_rate_limit_still_apply_to_the_stream(stub, tmp_path):
    assert TestClient(create_app(AgentService(agent=stub), RateLimiter(LIMITS), FeedbackStore(tmp_path / "f.sqlite"))).post("/api/agent/ask/stream", json={"question": ""}).status_code == 422
    c = TestClient(create_app(AgentService(agent=stub), RateLimiter({**LIMITS, "agent": (1, 60)}), FeedbackStore(tmp_path / "g.sqlite")))
    assert c.post("/api/agent/ask/stream", json={"question": "a b c"}).status_code == 200
    assert c.post("/api/agent/ask/stream", json={"question": "a b c"}).status_code == 429


@pytest.mark.skipif(not (PROC / "a3_acd_rules.csv").exists(), reason="processed data not present")
def test_real_graph_streams_each_node_in_order_then_the_turn(tmp_path):
    path = tmp_path / "store.sqlite"
    build(path)
    llm = FakeLLM({"understand": understand(goods_description="men's cotton T-shirts", value_text="PKR 1,000,000", **IMPORTER_FULL),
                   "classify": classify(cand("6109.1000", 0.92)), "verify": verify()})
    agent = CustomsAgent(llm, retriever=StubRetriever(), notes_loader=no_notes, tools=RecordingTools(str(path)), cfg=Config(use_hints=False, explore_steps=0))
    ev = list(agent.stream_ask("men's cotton T-shirts, value PKR 1,000,000, registered importer, commercial importer, filer", as_of_date="2026-07-15"))
    steps = [e["node"] for e in ev if e["type"] == "step"]
    assert steps.index("understand") < steps.index("search") < steps.index("classify") < steps.index("verify") and steps[-1] == "respond"
    assert ev[-1]["type"] == "turn" and ev[-1]["turn"].final["status"] == "answer" and ev[-1]["turn"].final["code"] == "6109.1000"
