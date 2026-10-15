"""The three systems compared in the ablation (C2). Each takes a Case and returns one normalised prediction dict:

    {behavior: answer|not_sure_or_clarify|refuse|error, codes: [8-digit strings, best first], status, citations, bill_totals, note}

* plain_llm : the LLM alone, no retrieval, no tools. It may invent codes; that is the point of the baseline.
* llm_rag   : tariff + ruling retrieval, the LLM picks among the offered lines. No clarify, verify, notes or duty tools.
* full_graph: the whole LangGraph agent (src/agent). Clarifying questions are NOT answered (nobody is there to answer): a paused run
  counts as 'not_sure_or_clarify' when it asks about the classification, and as 'answer' when it only asks for duty inputs
  (value, importer status) because the code was already chosen. The full graph shows at most 3 candidates, so its top-5 equals its top-3.

Leak control: for real cases the ruling the case came from is removed from every ruling search (`leak_free`), otherwise the answer
sits in the index.
"""
from __future__ import annotations

import re
from typing import Callable

from src.agent import CustomsAgent
from src.agent.llm import LLM
from src.agent.retrieval import default_retriever

from .cases import Case

SYSTEMS = ("plain_llm", "llm_rag", "full_graph")


def leak_free(retriever: Callable, case: Case) -> Callable:
    """Wrap a retriever so that hits from the case's own source ruling are dropped from the rulings index."""
    if not case.source_file:
        return retriever
    own = case.source_file.lower()
    stem = own.lstrip("0123456789")      # the FBR prefix digits differ between the case URL and the stored file name

    def wrapped(query, index, as_of_date, k):
        if index != "rulings":
            return retriever(query, index, as_of_date, k)
        hits = retriever(query, index, as_of_date, k + 6)
        keep = []
        for h in hits:
            f = (h.get("source_file") or "").lower().split("/")[-1]
            if f == own or (stem and f.lstrip("0123456789") == stem):
                continue
            keep.append(h)
        return keep[:k]
    return wrapped


def _codes(seq) -> list[str]:
    out, seen = [], set()
    for c in seq or []:
        d = re.sub(r"\D", "", str(c))
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


JSON_FORMAT = ('Return JSON only: {"behavior": "answer" | "not_sure" | "refuse", "codes": ["8-digit PCT codes, best first, at most 5"], '
               '"reason": "one sentence"}. Use "not_sure" if the description is too vague to choose one line, "refuse" if the question is not '
               'about classifying goods imported into Pakistan or the date is outside 1 July 2025 to 30 June 2027.')


def _behavior(raw) -> str:
    return {"answer": "answer", "not_sure": "not_sure_or_clarify", "refuse": "refuse"}.get(str(raw or "").lower(), "answer")


def run_plain_llm(case: Case, llm: LLM, **_) -> dict:
    system = ("You classify goods under the Pakistan Customs Tariff (PCT, HS 2022 based, 8-digit codes written 1234.5678). "
              "Answer from your own knowledge. " + JSON_FORMAT)
    prompt = f"Date of import: {case.as_of_date}\nGoods: {case.description}"
    r = llm.complete_json(task="eval_plain", system=system, prompt=prompt)
    d = r.data if isinstance(r.data, dict) else {}
    return dict(behavior=_behavior(d.get("behavior")), codes=_codes(d.get("codes"))[:5], status="plain", citations=[], bill_totals=None,
                note=str(d.get("reason", ""))[:300])


def run_llm_rag(case: Case, llm: LLM, retriever: Callable = default_retriever, k: int = 15, **_) -> dict:
    ret = leak_free(retriever, case)
    lines = ret(case.description, "tariff", case.as_of_date, k)
    rulings = ret(case.description, "rulings", case.as_of_date, 3)
    offered = {}
    for h in lines:
        c = re.sub(r"\D", "", h.get("code") or "")
        if len(c) == 8:
            offered[c] = (h.get("text") or "")[:260]
    ev = "\n".join(f"- {t}" for t in offered.values())
    rv = "\n".join(f"- {(h.get('text') or '')[:300]}" for h in rulings if h.get("rerank_score") is None or h["rerank_score"] > 0)
    system = "You classify goods under the Pakistan Customs Tariff. Choose ONLY codes that appear in the CANDIDATE LINES. " + JSON_FORMAT
    prompt = f"Date of import: {case.as_of_date}\nGoods: {case.description}\n\nCANDIDATE LINES\n{ev}\n\nRULINGS (information)\n{rv or '(none)'}"
    r = llm.complete_json(task="eval_rag", system=system, prompt=prompt)
    d = r.data if isinstance(r.data, dict) else {}
    said = _codes(d.get("codes"))
    chosen = [c for c in said if c in offered]
    return dict(behavior=_behavior(d.get("behavior")), codes=chosen[:5], status="rag", citations=[], bill_totals=None,
                note=f"{len(offered)} lines offered; {len(said) - len(chosen)} codes dropped (not offered)")


def run_full_graph(case: Case, llm: LLM, retriever: Callable = default_retriever, **_) -> dict:
    agent = CustomsAgent(llm, retriever=leak_free(retriever, case))
    turn = agent.ask(case.description, as_of_date=case.as_of_date)
    st = turn.state
    cands = [re.sub(r"\D", "", c.get("code", "")) for c in (st.get("candidates") or [])]
    if turn.interrupt:
        kind = turn.interrupt.get("kind")
        beh = "answer" if kind == "duty_input" else "not_sure_or_clarify"
        if kind == "duty_input" and st.get("chosen_code"):
            cands = [st["chosen_code"]] + cands
        qs = "; ".join(q.get("question", "")[:80] for q in turn.interrupt.get("questions", [])[:3])
        return dict(behavior=beh, codes=_codes(cands), status=f"paused:{kind}", citations=[], bill_totals=None, note="agent asked: " + qs)
    fin = turn.final or {}
    status = fin.get("status")
    beh = {"answer": "answer", "cannot_compute": "answer", "needs_input": "answer", "not_sure": "not_sure_or_clarify",
           "refused": "refuse", "error": "error"}.get(status, "error")
    codes = _codes(([fin["code"]] if fin.get("code") else []) + cands)
    return dict(behavior=beh, codes=codes, status=status, citations=fin.get("citations") or [],
                bill_totals=(fin.get("bill") or {}).get("totals"), error_type=(st.get("error") or {}).get("type"),
                note=(st.get("not_sure_reason") or (st.get("error") or {}).get("message") or "")[:300])


RUNNERS = {"plain_llm": run_plain_llm, "llm_rag": run_llm_rag, "full_graph": run_full_graph}
