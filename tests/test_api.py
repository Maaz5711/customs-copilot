"""Web API tests: validation, security headers, rate limits, privacy of feedback, error mapping. A stub agent stands in for the LLM (no network)."""
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from src.agent.llm import LLMBudgetExceeded
from src.agent.runner import TurnResult
from src.api.app import create_app
from src.api.security import RateLimiter
from src.api.service import AgentService, FeedbackStore

TID = "a" * 32
QUESTIONS = {"message": "I need more information.", "notes": ["n1"],
             "questions": [{"id": "material", "question": "What is it made of?", "why": "x", "type": "text", "secret_internal": "no"}]}
LIMITS = {"agent": (100, 60), "agent_hour": (1000, 3600), "lookup": (100, 60), "bill": (100, 60), "feedback": (100, 60)}


class StubAgent:
    def __init__(self):
        self.calls, self.fail = [], None
        self.waiting = set()

    def ask(self, question, as_of_date=None, thread_id=None):
        self.calls.append((question, as_of_date))
        if self.fail:
            raise self.fail
        self.waiting.add(TID)
        return TurnResult(thread_id=TID, interrupt=QUESTIONS, final=None, state={})

    def pending(self, tid):
        return QUESTIONS if tid in self.waiting else None

    def resume(self, tid, answer):
        self.waiting.discard(tid)
        return TurnResult(thread_id=tid, interrupt=None, final={"status": "answer", "code": "84713010", "text": "t"}, state={})


@pytest.fixture
def stub():
    return StubAgent()


@pytest.fixture
def client(stub, tmp_path):
    svc = AgentService(agent=stub)
    app = create_app(svc, RateLimiter(LIMITS), FeedbackStore(tmp_path / "f.sqlite"),
                     lookup_fn=lambda q, d, k, ch, cd: {"status": "ok", "q": q, "d": d, "k": k, "chapter": ch, "cd": cd},
                     bill_fn=lambda code, v, d, **kw: {"status": "computed", "code": code, "v": v, "d": d, **{k: x for k, x in kw.items() if x is not None}})
    return TestClient(app)


def test_security_headers_and_no_store(client):
    r = client.get("/api/meta")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store" and r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"] and r.headers["x-content-type-options"] == "nosniff"
    assert "not an FBR service" in r.json()["disclaimer"]


def test_docs_are_off_and_unknown_host_is_refused(client):
    assert client.get("/api/docs").status_code == 404 and client.get("/api/openapi.json").status_code == 404
    assert client.get("/api/meta", headers={"host": "evil.example"}).status_code == 400


def test_ask_then_answer_flow_maps_questions_without_internal_fields(client, stub):
    r = client.post("/api/agent/ask", json={"question": "men's cotton T-shirts", "date": "2026-10-18"})
    j = r.json()
    assert r.status_code == 200 and j["status"] == "questions" and j["thread_id"] == TID and "secret_internal" not in j["questions"][0]
    assert stub.calls == [("men's cotton T-shirts", "2026-10-18")]
    r = client.post("/api/agent/answer", json={"thread_id": TID, "answers": {"material": "cotton"}})
    assert r.status_code == 200 and r.json()["status"] == "answer" and r.json()["result"]["code"] == "84713010"
    assert client.post("/api/agent/answer", json={"thread_id": TID, "answers": {"material": "x"}}).status_code == 404       # nothing pending any more


def test_validation_is_strict_and_never_echoes_input(client):
    secret = "SECRET-PRODUCT-TEXT"
    for body in ({"question": "x"}, {"question": secret * 100}, {"question": secret, "date": "18-10-2026"}, {"question": secret, "extra": 1}):
        r = client.post("/api/agent/ask", json=body)
        assert r.status_code == 422 and secret not in r.text
    assert client.post("/api/agent/answer", json={"thread_id": "nothex", "answers": {"a": "b"}}).status_code == 422
    assert client.post("/api/agent/answer", json={"thread_id": TID, "answers": {"Bad Key!": "b"}}).status_code == 422
    assert client.post("/api/agent/answer", json={"thread_id": TID}).status_code == 422                                          # nothing answered
    assert client.post("/api/bill", json={"code": "84713010", "value_pkr": -5}).status_code == 422
    assert client.post("/api/bill", json={"code": "84713010", "value_pkr": 1e15}).status_code == 422
    assert client.post("/api/lookup", json={"query": "x", "k": 500}).status_code == 422


def test_body_size_cap(client):
    r = client.post("/api/agent/ask", content=b'{"question": "' + b"a" * 20000 + b'"}', headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_lookup_and_bill_pass_clean_values(client):
    j = client.post("/api/lookup", json={"query": "  laptop  ", "chapter": "84", "cd_pct": "11", "k": 5}).json()
    assert j["q"] == "laptop" and j["k"] == 5 and j["chapter"] == "84" and j["d"]
    j = client.post("/api/bill", json={"code": "8471.3010", "value_pkr": 1000000, "date": "2026-10-18",
                                       "importer": {"registration_status": "registered", "commercial_importer": True}}).json()
    assert j["status"] == "computed" and j["importer"]["commercial_importer"] is True


def test_rate_limit_returns_429_with_retry_after(stub, tmp_path):
    lim = RateLimiter({**LIMITS, "agent": (2, 60)})
    c = TestClient(create_app(AgentService(agent=stub), lim, FeedbackStore(tmp_path / "f.sqlite")))
    codes = [c.post("/api/agent/ask", json={"question": "laptops"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = c.post("/api/agent/ask", json={"question": "laptops"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


def test_rate_limiter_window():
    t = [0.0]
    lim = RateLimiter({"b": (2, 10)}, clock=lambda: t[0])
    assert lim.check("ip", "b") is None and lim.check("ip", "b") is None and lim.check("ip", "b") >= 1
    assert lim.check("other", "b") is None
    t[0] = 11
    assert lim.check("ip", "b") is None


def test_errors_do_not_leak_details(client, stub):
    stub.fail = RuntimeError("boom with USER TEXT inside")
    r = client.post("/api/agent/ask", json={"question": "laptops"})
    assert r.status_code == 500 and "USER TEXT" not in r.text and "reference" in r.json()["message"]
    stub.fail = LLMBudgetExceeded("budget")
    r = client.post("/api/agent/ask", json={"question": "laptops"})
    assert r.status_code == 503 and r.headers["retry-after"] and "budget" not in r.text


def test_conversations_expire_and_are_capped():
    now = [1000.0]
    svc = AgentService(agent=StubAgent(), ttl=60, max_threads=1, clock=lambda: now[0])
    svc.ask("laptops", None)
    with pytest.raises(Exception, match="busy"):
        svc.ask("again", None)                       # cap of 1 open conversation
    now[0] += 61
    assert svc.purge() == 1 and not svc.created
    svc.ask("laptops", None)


def test_feedback_stores_nothing_free_text_without_consent(client, tmp_path):
    assert client.post("/api/feedback", json={"helpful": True, "code": "84713010", "note": "my private note", "thread_id": TID}).status_code == 204
    assert client.post("/api/feedback", json={"helpful": False, "code": "84713010", "note": "shared note", "consent_to_store_note": True}).status_code == 204
    rows = sqlite3.connect(tmp_path / "f.sqlite").execute("SELECT helpful, code, note, thread_id FROM feedback ORDER BY id").fetchall()
    assert rows == [(1, None, None, None), (0, "84713010", "shared note", None)]
    assert client.post("/api/feedback", json={"helpful": True, "code": "1234"}).status_code == 422


def test_one_answer_at_a_time_per_conversation(stub):
    svc = AgentService(agent=stub)
    svc.ask("laptops", None)
    lock = svc.locks.setdefault(TID, threading.Lock())
    lock.acquire()
    with pytest.raises(Exception, match="still working"):
        svc.answer(TID, {"material": "x"}, None)
    lock.release()
