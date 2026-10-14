"""The LangGraph for the customs agent (C1). Diagram and state fields: docs/agent.md.

    START -> understand -> (clarify | search | calculate | respond)
    clarify -> understand                      (interrupt() pauses here; Command(resume=...) continues)
    search -> (classify | clarify | respond)
    classify -> (calculate | clarify | search | respond)
    calculate -> (verify | clarify | respond)
    verify -> (respond | search)               (search = a retry; at most 2, then "not sure" mode)
    respond -> END

Every node sets `route` itself, so the edges below are only a lookup table.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import (
    AgentState, Deps, make_calculate, make_clarify, make_classify, make_respond, make_search, make_understand, make_verify,
)

NODES = ("understand", "clarify", "search", "classify", "calculate", "verify", "respond")


def _route(state: dict) -> str:
    return state["route"]


def build_graph(deps: Deps, checkpointer=None):
    g = StateGraph(AgentState)
    g.add_node("understand", make_understand(deps))
    g.add_node("clarify", make_clarify(deps))
    g.add_node("search", make_search(deps))
    g.add_node("classify", make_classify(deps))
    g.add_node("calculate", make_calculate(deps))
    g.add_node("verify", make_verify(deps))
    g.add_node("respond", make_respond(deps))
    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", _route, {"clarify": "clarify", "search": "search", "calculate": "calculate", "respond": "respond"})
    g.add_edge("clarify", "understand")
    g.add_conditional_edges("search", _route, {"classify": "classify", "clarify": "clarify", "respond": "respond"})
    g.add_conditional_edges("classify", _route, {"calculate": "calculate", "clarify": "clarify", "search": "search", "respond": "respond"})
    g.add_conditional_edges("calculate", _route, {"verify": "verify", "clarify": "clarify", "respond": "respond"})
    g.add_conditional_edges("verify", _route, {"respond": "respond", "search": "search"})
    g.add_edge("respond", END)
    return g.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())
