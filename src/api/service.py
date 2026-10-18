"""The agent behind the API: conversations in memory with an expiry, a cap on open conversations, and a feedback store.

Privacy choices (docs/security.md):
* Conversations are kept in memory only (LangGraph MemorySaver) and deleted after `ttl` seconds; a restart forgets them. No product text reaches a disk checkpoint.
* The LLM response cache is switched off for the API (its files would hold users' product descriptions in clear text).
* Feedback stores the rating and, only when the user ticks the consent box, the code they say is right and a short note.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FEEDBACK_DB = ROOT / "data" / "processed" / "feedback" / "feedback.sqlite"
QUESTION_KEYS = ("id", "question", "why", "type", "allowed", "unit", "error")


class Busy(Exception):
    """Too many open conversations, or the model budget is used up."""


def build_default_agent(checkpointer):
    from src.agent import CustomsAgent, DeepSeekLLM, FireworksLLM, GeminiLLM

    provider = os.environ.get("LLM_PROVIDER", "deepseek").lower()
    budget = int(os.environ.get("API_MAX_LLM_CALLS", "3000"))
    if provider == "deepseek":
        llm = DeepSeekLLM(max_calls=budget, cache=False, overrides={"classify": {"thinking": "enabled"}})
    elif provider == "fireworks":
        llm = FireworksLLM(max_calls=budget, cache=False)
    elif provider == "gemini":
        llm = GeminiLLM(max_calls=budget, cache=False)
    else:
        raise RuntimeError(f"unknown LLM_PROVIDER '{provider}'")
    return CustomsAgent(llm, checkpointer=checkpointer)


def payload(turn) -> dict:
    """What the browser gets: either the questions the agent needs answered, or the finished answer."""
    if turn.interrupt:
        intr = turn.interrupt
        return {"status": "questions", "thread_id": turn.thread_id, "message": intr.get("message"), "notes": list(intr.get("notes") or []),
                "questions": [{k: q.get(k) for k in QUESTION_KEYS} for q in intr.get("questions", [])]}
    final = turn.final or {}
    return {"status": final.get("status", "error"), "thread_id": turn.thread_id, "result": final}


class AgentService:
    def __init__(self, agent=None, *, checkpointer=None, ttl: int = 3600, max_threads: int = 300, clock=time.time):
        from langgraph.checkpoint.memory import MemorySaver

        self.cp = checkpointer if checkpointer is not None else MemorySaver()
        self._agent, self.ttl, self.max_threads, self.clock = agent, ttl, max_threads, clock
        self.created: dict[str, float] = {}
        self.locks: dict[str, threading.Lock] = {}
        self.guard = threading.Lock()

    @property
    def agent(self):
        with self.guard:
            if self._agent is None:
                self._agent = build_default_agent(self.cp)
            return self._agent

    def purge(self) -> int:
        now, gone = self.clock(), 0
        with self.guard:
            old = [t for t, c in self.created.items() if now - c > self.ttl]
        for t in old:
            try:
                self.cp.delete_thread(t)
            except Exception:
                pass
            with self.guard:
                self.created.pop(t, None)
                self.locks.pop(t, None)
            gone += 1
        return gone

    def ask(self, question: str, as_of_date: str | None) -> dict:
        self.purge()
        with self.guard:
            if len(self.created) >= self.max_threads:
                raise Busy("The service is busy. Please try again in a few minutes.")
        turn = self.agent.ask(question, as_of_date=as_of_date)
        with self.guard:
            self.created[turn.thread_id] = self.clock()
        return payload(turn)

    def answer(self, thread_id: str, answers: dict, reply: str | None) -> dict:
        self.purge()
        with self.guard:
            if thread_id not in self.created:
                raise KeyError(thread_id)
            lock = self.locks.setdefault(thread_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise Busy("This conversation is still working on your last answer.")
        try:
            if self.agent.pending(thread_id) is None:
                raise KeyError(thread_id)
            resume = {"answers": answers} if answers else (reply or "")
            return payload(self.agent.resume(thread_id, resume))
        finally:
            lock.release()


class FeedbackStore:
    def __init__(self, path: Path | str = FEEDBACK_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY, created TEXT, thread_id TEXT, helpful INTEGER, code TEXT, note TEXT)")

    def _conn(self):
        return sqlite3.connect(self.path)

    def add(self, helpful: bool, thread_id: str | None, code: str | None, note: str | None, consent: bool) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO feedback (created, thread_id, helpful, code, note) VALUES (datetime('now'), ?, ?, ?, ?)",
                      (thread_id if consent else None, int(helpful), code if consent else None, (note or "")[:500] if consent else None))
