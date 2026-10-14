"""A small API around the graph (C1): ask a question, answer the agent's clarifying questions, read the result.

    agent = CustomsAgent(GeminiLLM())
    turn = agent.ask("men's cotton T-shirts, value PKR 2,500,000", as_of_date="2026-07-15")
    while turn.interrupt:                      # the agent needs more information
        turn = agent.resume(turn.thread_id, {"answers": {...}})    # or a plain string for a single question
    print(turn.final["text"])
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable

from langgraph.types import Command

from .graph import build_graph
from .llm import LLM
from .nodes import Config, Deps
from .retrieval import NotesLoader, Retriever, default_notes_loader, default_retriever
from .toolbox import ToolBox


@dataclass
class TurnResult:
    thread_id: str
    interrupt: dict | None          # the clarifying questions, when the graph is paused
    final: dict | None              # the answer (any status), when the graph has finished
    state: dict                     # the full graph state (trace, candidates, duty, ...)

    @property
    def trace(self) -> list:
        return list(self.state.get("trace", []))

    @property
    def path(self) -> list:
        """Node names visited, in order (for tests and debugging)."""
        return [t.split(":")[0] for t in self.trace]


class CustomsAgent:
    def __init__(self, llm: LLM, *, retriever: Retriever | None = None, notes_loader: NotesLoader | None = None, tools: ToolBox | None = None,
                 cfg: Config | None = None, checkpointer=None, today: Callable | None = None):
        kw: dict[str, Any] = {}
        if today is not None:
            kw["today"] = today
        self.deps = Deps(llm=llm, retriever=retriever or default_retriever, notes_loader=notes_loader or default_notes_loader,
                         tools=tools or ToolBox(), cfg=cfg or Config(), **kw)
        self.graph = build_graph(self.deps, checkpointer)

    @staticmethod
    def _cfg(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": 120}

    def _result(self, thread_id: str, out: dict) -> TurnResult:
        snap = self.graph.get_state(self._cfg(thread_id))
        state = dict(snap.values or {})
        intr = None
        for t in snap.tasks:
            if t.interrupts:
                intr = t.interrupts[0].value
                break
        return TurnResult(thread_id=thread_id, interrupt=intr, final=None if intr else state.get("final"), state=state)

    def ask(self, question: str, as_of_date: str | None = None, thread_id: str | None = None) -> TurnResult:
        """Start a new conversation. `as_of_date` is an explicit date (never assumed). Returns either questions or a final answer."""
        tid = thread_id or uuid.uuid4().hex
        out = self.graph.invoke({"question": question, "date_arg": as_of_date}, self._cfg(tid))
        return self._result(tid, out)

    def resume(self, thread_id: str, answer: Any) -> TurnResult:
        """Answer the pending questions. `answer`: a string, {'answers': {question id: text}} or {question id: text}."""
        out = self.graph.invoke(Command(resume=answer), self._cfg(thread_id))
        return self._result(thread_id, out)

    def pending(self, thread_id: str) -> dict | None:
        """The clarifying questions the thread is waiting on, if any (works after a restart with a SQLite checkpointer)."""
        snap = self.graph.get_state(self._cfg(thread_id))
        for t in snap.tasks:
            if t.interrupts:
                return t.interrupts[0].value
        return None
