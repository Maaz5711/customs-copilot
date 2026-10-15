"""The seven nodes of the agent graph (C1): Understand, Clarify, Search, Classify, Calculate Duty, Verify, Respond.

Division of labour (hard rules from CLAUDE.md):
* The LLM reads language: it extracts facts (as quotes), picks among retrieved candidate lines, and audits the choice.
* Code does everything else: dates, numbers, units, code validation, retrieval, duty arithmetic (src.tools), grounding checks, the answer text.
* Every node returns a plain dict update. `route` tells the graph where to go next; `trace` records what happened.
"""
from __future__ import annotations

import copy
import operator
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Any, Callable, TypedDict

from langgraph.types import interrupt

from . import prompts
from .facts import apply_value, coerce, spec_for, tool_args
from .ground import Corpus, check_text, clean_llm_text
from .llm import LLM, LLMBadResponse, LLMError
from .parsing import (
    display_code, find_pct_codes, is_bare_yes_no, is_unknown, parse_date_text, parse_number, parse_quantity, parse_registration, parse_vehicle_form,
    quote_in, says_today, unsupported_fiscal_year,
)
from .respond import conf_text, render_answer, render_error, render_needs_input, render_not_sure, render_refusal
from .retrieval import DEFAULT_FLOORS, NotesLoader, Retriever, default_notes_loader, default_retriever, evidence_text, gather, note_body, offered_codes
from .schemas import SchemaError, validate_classify, validate_map, validate_understand, validate_verify
from .toolbox import ToolBox

GOODS_Q = "What product do you want to import? Describe it in a sentence: what it is, what it is made of, and what it is used for."
DATE_Q = ("On which date should the rules apply? Please give a full date such as 2026-07-15. I do not assume today's date, "
          "and I only cover {lo} to {hi} (FY2025-26 and FY2026-27).")
WHICH_Q = "Your message mentions more than one product. Which one should I work on first? I handle one product at a time."
VALUE_Q = "What is the assessable (customs) value of the goods in PKR? I do not convert currencies."


# --------------------------------------------------------------------------------------------- state and deps
class AgentState(TypedDict, total=False):
    question: str
    date_arg: str | None
    facts: dict
    inputs: dict
    as_of_date: str | None
    date_source: str | None
    user_codes: list
    user_code_only: bool
    notes_to_user: list
    clarifications: list
    pending_questions: list
    pending_answer: Any
    clarify_kind: str | None
    clarify_rounds: int
    reask: dict
    unknown_fields: list
    unresolved: list
    evidence: dict
    offered_codes: list
    retry_pending: bool
    hint_headings: list
    hint_query: str
    extra_queries: list
    candidates: list
    rejected_codes: list
    deciding_info: str | None
    chosen_code: str | None
    lookup: dict | None
    duty: dict | None
    rules_in_force: dict | None
    verification: dict | None
    retries: int
    feedback: str | None
    attempts: list
    route: str
    mode: str
    not_sure_reason: str | None
    refusal: dict | None
    error: dict | None
    final: dict | None
    trace: Annotated[list, operator.add]
    llm_log: Annotated[list, operator.add]


@dataclass
class Config:
    confidence_threshold: float = 0.6       # below this the top candidate is "low confidence"
    verify_threshold: float = 0.5           # minimum fit_confidence from the auditor
    max_retries: int = 2                    # Verify / low-confidence retries before "not sure" mode
    max_clarify_rounds: int = 4
    max_reask: int = 2                      # times one unreadable answer is asked again
    k_tariff: int = 10
    # one small LLM call proposes 4-digit headings; they only widen the candidate pool. AGENT_USE_HINTS=0 switches it off (the unit tests do).
    use_hints: bool = field(default_factory=lambda: os.environ.get("AGENT_USE_HINTS", "1") != "0")
    floors: dict = field(default_factory=lambda: dict(DEFAULT_FLOORS))


@dataclass
class Deps:
    llm: LLM
    retriever: Retriever = default_retriever
    notes_loader: NotesLoader = default_notes_loader
    tools: ToolBox = field(default_factory=ToolBox)
    cfg: Config = field(default_factory=Config)
    today: Callable[[], date] = date.today


# --------------------------------------------------------------------------------------------- small helpers
def _err_update(e: Exception) -> dict:
    return {"mode": "error", "error": {"type": type(e).__name__, "message": str(e)}, "route": "respond", "trace": [f"error: {type(e).__name__}"]}


def _q(qid: str, kind: str, question: str, why: str | None = None, allowed=None, unit: str | None = None, fld: str | None = None) -> dict:
    f = fld or qid
    return {"id": qid, "field": f, "kind": kind, "question": question, "why": why, "allowed": allowed, "unit": unit, "type": spec_for(f, allowed)["type"]}


def _call(deps: Deps, task: str, system: str, prompt: str):
    res = deps.llm.complete_json(task=task, system=system, prompt=prompt)
    return res, f"{task}:{res.model}:{'cached' if res.cached else 'live'}"


def user_text(state: dict) -> str:
    parts = [state.get("question", "")] + [str(c.get("answer", "")) for c in state.get("clarifications", [])]
    return " ".join(p for p in parts if p)


def build_query(facts: dict, clar: list) -> str:
    desc = facts.get("goods_description") or ""
    parts = [desc]
    for k in ("material", "intended_use"):
        v = facts.get(k)
        if v and v.lower() not in desc.lower():
            parts.append(v)
    for c in clar:
        # a bare yes/no says nothing about the goods and only adds noise to the search query (it stays in the Classify prompt as Q and A)
        if c.get("kind") == "classification" and not c.get("unknown") and c.get("answer") and not is_bare_yes_no(str(c["answer"])):
            parts.append(str(c["answer"]))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()[:400]


def normalize_reply(reply: Any, questions: list) -> tuple[dict, str | None]:
    """The resume value -> ({question id: raw answer}, free text). Accepts a string, {'answers': {...}}, {id: value}, {'text': ...} or a list."""
    ids = [q["id"] for q in questions]
    if reply is None:
        return {}, None
    if isinstance(reply, str):
        return ({ids[0]: reply}, reply) if len(ids) == 1 else ({}, reply)
    if isinstance(reply, (list, tuple)):
        return {i: v for i, v in zip(ids, reply)}, None
    if isinstance(reply, dict):
        if isinstance(reply.get("answers"), dict):
            return {k: v for k, v in reply["answers"].items() if k in ids}, reply.get("text")
        direct = {k: v for k, v in reply.items() if k in ids}
        if direct:
            return direct, reply.get("text")
        if "text" in reply:
            t = str(reply["text"])
            return ({ids[0]: t}, t) if len(ids) == 1 else ({}, t)
        return {}, None
    return {}, str(reply)


def _grounded_description(desc: str | None, message: str) -> str | None:
    """The LLM's description must share at least one real word with the message; otherwise use the message itself."""
    if not desc:
        return None
    words = {w for w in re.findall(r"[a-z]{4,}", desc.lower())}
    msg = set(re.findall(r"[a-z]{4,}", message.lower()))
    if words and not (words & msg):
        return re.sub(r"\s+", " ", message).strip()[:300]
    return desc


def facts_from_understand(u: dict, message: str, deps: Deps) -> tuple[dict, dict, list]:
    """Facts and compute_duty inputs from the LLM's extraction. Every fact needs a quote that really is in the message;
    numbers and units are then read by code (parsing.py), never taken from the LLM."""
    facts: dict = {"goods_description": _grounded_description(u["goods_description"], message), "intended_use": u["intended_use"], "material": u["material"]}
    inputs: dict = {}
    dropped: list[str] = []

    def keep(name: str, quote: str | None) -> bool:
        if quote_in(quote, message):
            return True
        dropped.append(name)
        return False

    if u["condition"] and keep("condition", u["condition_quote"]):
        facts["condition"] = u["condition"]
    if u["vehicle_form"] and keep("vehicle_form", u["vehicle_form_quote"]) and parse_vehicle_form(u["vehicle_form_quote"]) == u["vehicle_form"]:
        inputs.setdefault("goods", {})["vehicle_form"] = u["vehicle_form"]
        facts["vehicle_form"] = u["vehicle_form"]
    if u["engine_text"] and keep("engine", u["engine_text"]):
        c = coerce("goods.engine_cc", u["engine_text"])
        if c.ok:
            inputs.setdefault("goods", {})["engine_cc"] = c.value
            facts["engine_cc"] = c.value
        else:
            facts["engine_issue"] = f"engine size '{u['engine_text']}': {c.error}"
    if u["value_text"] and keep("value", u["value_text"]):
        c = coerce("assessable_value_pkr", u["value_text"])
        if c.ok:
            inputs["assessable_value_pkr"] = c.value
            facts["value_text"] = u["value_text"]
        else:
            facts["value_issue"] = f"you wrote '{u['value_text']}': {c.error}"
    if u["quantity_text"] and keep("quantity", u["quantity_text"]):
        n, unit = parse_quantity(u["quantity_text"])
        if n is not None and n > 0:
            inputs["quantity"] = format(n.normalize(), "f")
            if unit:
                inputs["quantity_unit"] = unit
            facts["quantity_text"] = u["quantity_text"]
    if u["registration_status"] and keep("registration", u["registration_quote"]) and parse_registration(u["registration_quote"]) == u["registration_status"]:
        inputs.setdefault("importer", {})["registration_status"] = u["registration_status"]
    if u["commercial_importer"] is not None and keep("commercial_importer", u["commercial_quote"]):
        inputs.setdefault("importer", {})["commercial_importer"] = u["commercial_importer"]
    if u["manufacturer_in_house_use"] is not None and keep("manufacturer_in_house_use", u["manufacturer_quote"]):
        inputs.setdefault("importer", {})["manufacturer_in_house_use"] = u["manufacturer_in_house_use"]
    return facts, inputs, dropped


def _refuse(reason: str, deps: Deps, trace: str, kind: str = "date") -> dict:
    lo, hi = deps.tools.supported_range()
    return {"mode": "refused", "refusal": {"reason": reason, "supported": [lo, hi], "kind": kind}, "route": "respond", "trace": [trace]}


# --------------------------------------------------------------------------------------------- Understand
def make_understand(deps: Deps):
    cfg = deps.cfg

    def needs_questions(facts: dict, codes: list, date_iso: str | None, problem: str | None, multiple: bool) -> list:
        lo, hi = deps.tools.supported_range()
        if multiple:
            return [_q("goods_description", "request", WHICH_Q)]
        qs = []
        if not facts.get("goods_description") and not codes:
            qs.append(_q("goods_description", "request", GOODS_Q))
        if not date_iso:
            text = DATE_Q.format(lo=lo, hi=hi)
            if problem:
                text = f"{problem} " + text
            qs.append(_q("as_of_date", "request", text, why="Rates, SROs and tax rules change on 1 July and sometimes in between."))
        return qs

    def extract(message: str):
        """One Understand LLM call on `message`; facts and inputs are kept only with a quote found in the message. Raises LLMError."""
        try:
            res, log = _call(deps, "understand", prompts.UNDERSTAND_SYSTEM, prompts.understand_prompt(message))
            u = validate_understand(res.data)
        except SchemaError as e:
            raise LLMBadResponse(f"The language model's answer to the Understand step could not be read ({e}).")
        facts, inputs, dropped = facts_from_understand(u, message, deps)
        return u, facts, inputs, dropped, log, res.model

    def first_pass(state: AgentState) -> dict:
        q = (state.get("question") or "").strip()
        lo, hi = deps.tools.supported_range()
        date_iso, source, problem = None, None, None
        arg = state.get("date_arg")
        if arg:
            d = parse_date_text(arg)
            if d:
                date_iso, source = d.isoformat(), "date given with the question"
            else:
                problem = f"I could not read the date '{arg}'."
        fy = unsupported_fiscal_year(q)
        if fy:
            return _refuse(f"you asked about fiscal year {fy}, which I do not cover", deps, f"understand: refused (fiscal year {fy})")
        if date_iso and not (lo <= date_iso <= hi):
            return _refuse(f"the date {date_iso} is outside the supported range", deps, f"understand: refused (date {date_iso})")
        if not q:
            return {"facts": {}, "inputs": {}, "as_of_date": date_iso, "date_source": source, "user_codes": [], "pending_questions": needs_questions({}, [], date_iso, problem, False),
                    "clarify_kind": "request", "route": "clarify", "trace": ["understand: empty question"]}
        try:
            u, facts, inputs, dropped, log, model = extract(q)
        except LLMError as e:
            return _err_update(e)
        # refusals that need no search: misdeclaration (the user states the intent in their own words) and questions that are not about imports
        if u.get("misdeclaration_intent") and u.get("misdeclaration_quote") and quote_in(u["misdeclaration_quote"], q):
            return _refuse("you asked how to describe or declare the goods as something other than what they are in order to pay less duty or tax. "
                           "That is misdeclaration, and I will not help with it. I can classify the goods as they really are and calculate the lawful duty.",
                           deps, "understand: refused (misdeclaration)", "misdeclaration")
        if u.get("off_topic") and not u.get("goods_description") and not find_pct_codes(q):
            return _refuse("this is not a question about the customs classification or duty of goods imported into Pakistan.", deps,
                           "understand: refused (off topic)", "off_topic")
        # date from the message (only when the user wrote one; never today's date unless the user wrote "today")
        if not date_iso and u["date_text"] and quote_in(u["date_text"], q):
            if says_today(u["date_text"]):
                date_iso, source = deps.today().isoformat(), "you wrote 'today'; the system date was used"
            else:
                d = parse_date_text(u["date_text"])
                if d:
                    date_iso, source = d.isoformat(), f"from your message ('{u['date_text']}')"
                else:
                    problem = f"I could not read a full date from '{u['date_text']}'."
        if not date_iso and not problem:
            m = re.search(r"\b(?:fy|fiscal year|financial year)\s*'?\s*(\d{2,4})\s*[-/]\s*(\d{2,4})", q, re.I)
            if m:
                problem = "You gave a fiscal year, but rules can change during a year, so I need an exact date."
        if date_iso and not (lo <= date_iso <= hi):
            return _refuse(f"the date {date_iso} is outside the supported range", deps, f"understand: refused (date {date_iso})")
        codes: list[str] = []
        for c in find_pct_codes(q) + [c for t in u["codes_text"] if quote_in(t, q) for c in find_pct_codes(t)]:
            if c["code"] not in codes and (c["trusted"] or deps.tools.code_in_tariff(c["code"])):
                codes.append(c["code"])
        qs = needs_questions(facts, codes, date_iso, problem, u["multiple_products"])
        out = {"facts": facts, "inputs": inputs, "as_of_date": date_iso, "date_source": source, "user_codes": codes, "clarifications": [], "clarify_rounds": 0,
               "retries": 0, "attempts": [], "reask": {}, "unknown_fields": [], "notes_to_user": [], "llm_log": [log],
               "trace": [f"understand: facts extracted by {model}" + (f" (dropped unquoted facts: {', '.join(dropped)})" if dropped else "")]}
        if qs:
            out.update({"pending_questions": qs, "clarify_kind": "request", "route": "clarify"})
        else:
            out.update({"pending_questions": [], "route": "search"})
        return out

    def map_free_text(questions: list, text: str) -> tuple[dict, list]:
        res, log = _call(deps, "map_answers", prompts.MAP_SYSTEM, prompts.map_prompt(questions, text))
        return validate_map(res.data, [q["id"] for q in questions]), [log]

    def apply_clarification(state: AgentState) -> dict:
        qs = list(state.get("pending_questions") or [])
        kind = state.get("clarify_kind")
        facts, inputs = copy.deepcopy(state.get("facts") or {}), copy.deepcopy(state.get("inputs") or {})
        clar = list(state.get("clarifications") or [])
        answers, free = normalize_reply(state.get("pending_answer"), qs)
        mapped, logs = {}, []
        if free and len(qs) > 1 and any(answers.get(q["id"]) in (None, "") for q in qs):
            try:
                mapped, logs = map_free_text([q for q in qs if answers.get(q["id"]) in (None, "")], free)
            except LLMError as e:
                return _err_update(e)
            except SchemaError:
                mapped = {}
        date_iso, source = state.get("as_of_date"), state.get("date_source")
        codes = list(state.get("user_codes") or [])
        unknown = list(state.get("unknown_fields") or [])
        reask = dict(state.get("reask") or {})
        failed: list[dict] = []
        gave_up: list[dict] = []
        for q in qs:
            raw = answers.get(q["id"])
            if raw in (None, ""):
                raw = mapped.get(q["id"])
            err = None
            if raw in (None, ""):
                err = "I did not get an answer to this question."
            elif q["kind"] == "classification":
                clar.append({"question": q["question"], "answer": str(raw), "kind": "classification", "unknown": is_unknown(str(raw))})
            elif q["id"] == "as_of_date":
                c = coerce("as_of_date", raw, today=deps.today())
                if c.ok:
                    date_iso, source = c.value, f"your answer ('{raw}')"
                else:
                    err = c.error
            elif q["id"] == "goods_description":
                text = re.sub(r"\s+", " ", str(raw)).strip()
                if is_unknown(text):
                    err = "you said you do not know"
                else:
                    # loop back through Understand: facts in the answer (value, quantity, importer status, a date) are read like in a first message
                    try:
                        u, f2, i2, dropped, lg, _model = extract(text)
                        logs = logs + [lg]
                    except LLMError as e:
                        return _err_update(e)
                    facts.update({k: v for k, v in f2.items() if v})
                    if not f2.get("goods_description"):
                        facts["goods_description"] = text[:300]
                    for k, v in i2.items():
                        if isinstance(v, dict):
                            inputs.setdefault(k, {})
                            for kk, vv in v.items():
                                inputs[k].setdefault(kk, vv)
                        else:
                            inputs.setdefault(k, v)
                    if not date_iso and u["date_text"] and quote_in(u["date_text"], text):
                        d = deps.today() if says_today(u["date_text"]) else parse_date_text(u["date_text"])
                        if d:
                            date_iso, source = d.isoformat(), f"from your answer ('{u['date_text']}')"
                    for c in find_pct_codes(text):
                        if c["code"] not in codes and (c["trusted"] or deps.tools.code_in_tariff(c["code"])):
                            codes.append(c["code"])
            else:       # duty input from compute_duty.missing_inputs (or the value question)
                c = coerce(q["field"], raw, allowed=q.get("allowed"), unit=q.get("unit"), today=deps.today())
                if c.ok:
                    apply_value(inputs, q["field"], c.value)
                    if q["field"] in unknown:
                        unknown.remove(q["field"])
                elif c.unknown:
                    if q["field"] not in unknown:
                        unknown.append(q["field"])
                else:
                    err = c.error
            if err:
                reask[q["id"]] = reask.get(q["id"], 0) + 1
                if reask[q["id"]] > cfg.max_reask or "do not know" in err:
                    if q["kind"] == "duty_input" and q["field"] not in unknown:
                        unknown.append(q["field"])
                    elif q["kind"] == "classification":
                        clar.append({"question": q["question"], "answer": "(no usable answer)", "kind": "classification", "unknown": True})
                    else:
                        gave_up.append({**q, "error": err})
                else:
                    failed.append({**q, "error": err})
        base = {"facts": facts, "inputs": inputs, "clarifications": clar, "as_of_date": date_iso, "date_source": source, "user_codes": codes, "unknown_fields": unknown,
                "reask": reask, "pending_answer": None, "llm_log": logs, "trace": [f"understand: applied answers ({kind}), {len(failed)} unreadable"]}
        lo, hi = deps.tools.supported_range()
        if date_iso and not (lo <= date_iso <= hi):
            return {**base, **_refuse(f"the date {date_iso} is outside the supported range", deps, f"understand: refused (date {date_iso})"), "pending_questions": []}
        if gave_up:
            return {**base, "mode": "needs_input", "unresolved": [{"question": g["question"], "why": g.get("why")} for g in gave_up], "pending_questions": [], "route": "respond"}
        if failed:
            return {**base, "pending_questions": failed, "route": "clarify"}
        base["pending_questions"] = []
        if kind == "request":
            more = needs_questions(facts, codes, date_iso, None, False)
            if more:
                return {**base, "pending_questions": more, "clarify_kind": "request", "route": "clarify"}
            return {**base, "route": "search"}
        if kind == "duty_input":
            return {**base, "route": "calculate"}
        return {**base, "route": "search"}

    def understand(state: AgentState) -> dict:
        if state.get("pending_answer") is not None or (state.get("pending_questions") and state.get("facts") is not None and state.get("clarify_kind")):
            return apply_clarification(state)
        return first_pass(state)

    return understand


# --------------------------------------------------------------------------------------------- Clarify
def make_clarify(deps: Deps):
    def clarify(state: AgentState) -> dict:
        qs = state.get("pending_questions") or []
        kind = state.get("clarify_kind") or "request"
        rnd = state.get("clarify_rounds", 0) + 1
        intro = {"request": "I need a little more before I can start.",
                 "classification": "To choose the right tariff line I need to know a bit more about the goods.",
                 "duty_input": "To calculate the duties I need these details. The rules cannot be applied without them."}.get(kind, "I need more information.")
        reply = interrupt({"type": "clarify", "kind": kind, "round": rnd, "message": intro, "questions": qs, "notes": state.get("notes_to_user", [])})
        return {"pending_answer": reply, "clarify_rounds": rnd, "trace": [f"clarify: answered round {rnd} ({kind}, {len(qs)} question(s))"]}

    return clarify


# --------------------------------------------------------------------------------------------- Search
def make_search(deps: Deps):
    cfg = deps.cfg

    def search(state: AgentState) -> dict:
        date_iso = state["as_of_date"]
        facts, clar = state.get("facts") or {}, state.get("clarifications") or []
        notes = list(state.get("notes_to_user") or [])
        good: list[str] = []
        for c in state.get("user_codes") or []:
            lk = deps.tools.lookup_code(c, date_iso)
            if lk.get("status") in ("found", "not_a_full_code"):
                good.append(c)
            else:
                other = f" (it exists in {', '.join(lk['exists_in_other_fy'])})" if lk.get("exists_in_other_fy") else ""
                msg = f"The code {display_code(c)} that you wrote is not a line of the tariff on {date_iso}{other}, so I ignored it."
                if msg not in notes:
                    notes.append(msg)
        has_desc = bool(facts.get("goods_description"))
        full = [c for c in good if len(c) == 8]
        if not has_desc and not full:
            if state.get("clarify_rounds", 0) >= cfg.max_clarify_rounds:
                return {"mode": "needs_input", "unresolved": [{"question": GOODS_Q}], "route": "respond", "notes_to_user": notes, "trace": ["search: no goods description"]}
            q = _q("goods_description", "request", GOODS_Q + (" " + " ".join(notes) if notes else "") + (" (A 4 or 6 digit heading code alone is not enough to pick a line.)" if good else ""))
            return {"pending_questions": [q], "clarify_kind": "request", "route": "clarify", "user_codes": good, "notes_to_user": notes, "trace": ["search: needs a description"]}
        code_only = (not has_desc) and len(full) == 1
        retry = bool(state.get("retry_pending"))
        k = cfg.k_tariff + (5 if state.get("retries", 0) >= 2 else 0)
        query_text = "" if code_only else build_query(facts, clar)
        hints, hint_log = list(state.get("hint_headings") or []), []
        if cfg.use_hints and query_text and state.get("hint_query") != query_text:
            try:
                res, hlog = _call(deps, "hint_headings", prompts.HINT_SYSTEM, prompts.hint_prompt(query_text))
                hint_log = [hlog]
                raw_h = (res.data.get("headings") if isinstance(res.data, dict) else None) or []
                hints = [h for h in (re.sub(r"\D", "", str(x))[:4] for x in raw_h) if len(h) == 4][:4]
            except LLMBadResponse:
                hints = []                      # a bad hint answer only means plain search; it never stops the question
            except LLMError as e:
                return _err_update(e)
        try:
            ev = gather(deps.retriever, deps.notes_loader, query=query_text, extra_queries=list(state.get("extra_queries") or []) if retry else [],
                        user_codes=good, as_of_date=date_iso, floors=cfg.floors, k_tariff=k, hint_headings=hints)
        except FileNotFoundError as e:
            return _err_update(RuntimeError(f"The search index is missing ({e}). Build it with: python -m src.search.build"))
        except Exception as e:      # an index or model problem must end in a clear message, not a stack trace
            return _err_update(RuntimeError(f"Search failed: {type(e).__name__}: {e}"))
        return {"evidence": ev, "offered_codes": offered_codes(ev), "user_codes": good, "user_code_only": code_only, "notes_to_user": notes, "retry_pending": False, "route": "classify", "hint_headings": hints, "hint_query": query_text, "llm_log": hint_log,
                "trace": [f"search: {len(ev['lines'])} lines, {len(ev['notes'])} notes, {len(ev['sro'])} SRO excerpts, {len(ev['rulings'])} rulings"
                          + (f" (retry {state.get('retries', 0)})" if retry else "") + (f", dropped below floor {ev['dropped']}" if any(ev["dropped"].values()) else "")]}

    return search


# --------------------------------------------------------------------------------------------- Classify
def validate_candidates(raw: list, evidence: dict, tools: ToolBox, date_iso: str) -> tuple[list, list]:
    """Keep only candidates that (1) are eight-digit codes, (2) were offered to the model, (3) exist in the tariff on the date.
    Returns (valid, rejected). The LLM can never put a code into an answer that did not pass here."""
    offered = {ln["norm"]: ln for ln in evidence.get("lines", [])}
    labels = {x["label"] for k in ("lines", "notes", "sro", "rulings") for x in evidence.get(k, [])}
    valid, rejected, seen = [], [], set()
    for c in raw:
        digits = re.sub(r"\D", "", c["code"])
        shown = display_code(digits) if len(digits) == 8 else c["code"]
        if len(digits) != 8:
            rejected.append({"code": c["code"], "reason": "not an eight-digit code"})
            continue
        if digits in seen:
            continue
        seen.add(digits)
        if digits not in offered:
            rejected.append({"code": shown, "reason": "not among the retrieved candidate lines"})
            continue
        lk = tools.lookup_code(digits, date_iso)
        if lk.get("status") != "found" or lk.get("level") != 8:
            rejected.append({"code": shown, "reason": f"not a valid tariff line on {date_iso} ({lk.get('status')})"})
            continue
        ln = offered[digits]
        valid.append({"code": lk["code"], "norm": digits, "confidence": c["confidence"], "reasons": c["reasons"], "evidence": [e for e in c["evidence"] if e in labels],
                      "description": ln["description"], "page": lk["page"], "source_file": lk["source_file"], "fy": lk["fy"], "label": ln["label"]})
    valid.sort(key=lambda x: -x["confidence"])
    return valid[:3], rejected


def make_classify(deps: Deps):
    cfg = deps.cfg

    def fail_or_retry(state: AgentState, reason: str, extra: dict) -> dict:
        """A classification attempt that produced nothing usable: retry the search, or give up in 'not sure' mode."""
        retries = state.get("retries", 0)
        base = {**extra, "attempts": state.get("attempts", []) + [{"attempt": retries, "stage": "classify", "reason": reason, "candidates": extra.get("candidates", [])}]}
        if retries < cfg.max_retries:
            return {**base, "retries": retries + 1, "retry_pending": True, "feedback": reason, "route": "search", "trace": [f"classify: {reason} -> retry {retries + 1}"]}
        return {**base, "mode": "not_sure", "not_sure_reason": reason, "route": "respond", "trace": [f"classify: {reason} -> not sure"]}

    def classify(state: AgentState) -> dict:
        ev = state["evidence"]
        date_iso = state["as_of_date"]
        if state.get("user_code_only"):
            code = state["user_codes"][0]
            lk = deps.tools.lookup_code(code, date_iso)
            if lk.get("status") != "found" or lk.get("level") != 8:
                return fail_or_retry(state, f"the code you gave is not a valid tariff line on {date_iso}", {"candidates": []})
            ln = next((x for x in ev["lines"] if x["norm"] == code), None)
            cand = {"code": lk["code"], "norm": code, "confidence": 1.0, "reasons": "The code was given by you; I checked that it exists in the tariff on that date.", "evidence": [],
                    "description": (ln or {}).get("description") or lk["description"], "page": lk["page"], "source_file": lk["source_file"], "fy": lk["fy"], "label": (ln or {}).get("label")}
            return {"candidates": [cand], "chosen_code": code, "route": "calculate", "trace": [f"classify: code given by user {lk['code']}"]}
        if not ev.get("lines"):
            return fail_or_retry(state, "no tariff line matched the description closely enough", {"candidates": []})
        prompt = prompts.classify_prompt(state.get("facts") or {}, state.get("clarifications") or [], evidence_text(ev), state.get("feedback"), date_iso)
        try:
            res, log = _call(deps, "classify", prompts.CLASSIFY_SYSTEM, prompt)
            out = validate_classify(res.data)
        except LLMError as e:
            return _err_update(e)
        except SchemaError as e:
            return fail_or_retry(state, f"the classifier's answer could not be read ({e})", {"candidates": [], "llm_log": []})
        valid, rejected = validate_candidates(out["candidates"], ev, deps.tools, date_iso)
        corpus = Corpus(ev, state.get("facts"), state.get("inputs"), user_text(state))
        issues: list[dict] = []
        for c in valid:
            c["reasons"], iss = clean_llm_text(c["reasons"], corpus)
            issues += iss
        qs: list[dict] = []
        for q in out["questions"]:
            text, iss = clean_llm_text(q["question"], corpus, 300)
            issues += iss
            if not iss:
                qs.append(_q(f"q{len(state.get('clarifications', [])) + len(qs) + 1}", "classification", text, why=q.get("why")))
        deciding, iss = clean_llm_text(out["deciding_info"] or "", corpus, 400)
        issues += iss
        deciding = deciding if deciding and not iss else None
        base = {"candidates": valid, "rejected_codes": list(state.get("rejected_codes") or []) + rejected, "deciding_info": deciding, "llm_log": [log],
                "extra_queries": out["refined_queries"], "verification": None}
        if issues:
            base["rejected_codes"] = base["rejected_codes"] + [{"code": "(text)", "reason": f"unsupported {i['type']} {i['token']} in model text"} for i in issues]
        rounds_left = state.get("clarify_rounds", 0) < cfg.max_clarify_rounds
        if not valid:
            if qs and rounds_left and not rejected:
                # no line can be chosen yet but the classifier knows what would decide it (for example "a car": engine size and type): ask
                return {**base, "pending_questions": qs, "clarify_kind": "classification", "route": "clarify",
                        "trace": [f"classify: no candidate yet, asking {len(qs)} question(s)"]}
            why = "every code the classifier proposed failed the checks" if rejected else "the classifier found no fitting line among the candidates"
            return fail_or_retry(state, why, base)
        top = valid[0]
        if qs and rounds_left and (out["ambiguous"] or top["confidence"] < cfg.confidence_threshold):
            return {**base, "pending_questions": qs, "clarify_kind": "classification", "route": "clarify",
                    "trace": [f"classify: ambiguous (top {top['code']} {conf_text(top['confidence'])}), asking {len(qs)} question(s)"]}
        if top["confidence"] < cfg.confidence_threshold:
            return fail_or_retry(state, f"the best candidate {top['code']} has low confidence ({conf_text(top['confidence'])})", base)
        return {**base, "chosen_code": top["norm"], "route": "calculate", "trace": [f"classify: top {top['code']} confidence {conf_text(top['confidence'])}"
                                                                                  + (f"; rejected {len(rejected)} invalid code(s)" if rejected else "")]}

    return classify


# --------------------------------------------------------------------------------------------- Calculate Duty
def _missing_to_questions(missing: list, unknown: list) -> list:
    qs = []
    for m in missing:
        if m["field"] in unknown:
            continue
        unit = None
        if m["field"] == "quantity":
            mm = re.search(r"quantity_unit='([^']+)'", m.get("question", ""))
            unit = mm.group(1) if mm else None
        qs.append(_q(m["field"], "duty_input", m["question"], why=m.get("why"), allowed=m.get("allowed"), unit=unit))
    return qs


PROBE_VALUES = {"goods.engine_cc": "1500", "goods.age_years": "7"}


def _placeholder(m: dict):
    """A stand-in answer used ONLY to see which question the rules ask next. It is never used in a bill."""
    allowed = m.get("allowed")
    if allowed:
        return False if False in allowed else allowed[0]
    return PROBE_VALUES.get(m["field"], "1")


def _set_probe(probe: dict, m: dict, value) -> None:
    f = m["field"]
    if f == "quantity":
        probe["quantity"] = value
        mm = re.search(r"quantity_unit='([^']+)'", m.get("question", ""))
        probe["quantity_unit"] = mm.group(1) if mm else probe.get("quantity_unit")
        return
    head, _, tail = f.partition(".")
    if tail and head in ("importer", "goods"):
        probe[head] = dict(probe.get(head) or {})
        probe[head][tail] = value


def discover_missing(tools: ToolBox, code: str, date_iso: str, args: dict, value: str, seed: list | None = None, max_rounds: int = 5) -> list:
    """Every input the rules need, across all stages of compute_duty.

    compute_duty reports missing inputs stage by stage (for a car, the income-tax question only appears once the vehicle questions are
    answered), which would force several rounds of questions. Here the tool is called again with a stand-in answer for each missing field
    until it asks nothing new. The stand-in values are thrown away; only the list of questions is kept."""
    probe = copy.deepcopy(args)
    found: list = []
    seen: set[str] = set()
    missing = seed
    for _ in range(max_rounds):
        if missing is None:
            r = tools.compute_duty(code, value, date_iso, **probe)
            if r.get("status") != "needs_input":
                break
            missing = r.get("missing_inputs", [])
        new = [m for m in missing if m["field"] not in seen]
        if not new:
            break
        for m in new:
            seen.add(m["field"])
            found.append(m)
            _set_probe(probe, m, _placeholder(m))
        missing = None
    return found


def make_calculate(deps: Deps):
    cfg = deps.cfg

    def ask_or_stop(lookup: dict, missing: list, unknown: list, rounds_left: bool, with_value: str | None, label: str) -> dict:
        qs = _missing_to_questions(missing, unknown)
        if with_value is not None:
            qs = [_q("assessable_value_pkr", "duty_input", with_value, why="Customs duty, sales tax and income tax are percentages of the value (Customs Act s.25).")] + qs
        if not qs or not rounds_left:
            unresolved = ([{"question": VALUE_Q}] if with_value is not None else []) + [{"question": m["question"], "why": m.get("why")} for m in missing]
            return {"mode": "needs_input", "unresolved": unresolved, "lookup": lookup, "duty": None, "route": "respond", "trace": [f"calculate: {label}, cannot ask more"]}
        return {"lookup": lookup, "pending_questions": qs, "clarify_kind": "duty_input", "route": "clarify", "trace": [f"calculate: {label} -> asking {[q['field'] for q in qs]}"]}

    def calculate(state: AgentState) -> dict:
        code, date_iso = state["chosen_code"], state["as_of_date"]
        lookup = deps.tools.lookup_code(code, date_iso)
        inputs = state.get("inputs") or {}
        unknown = list(state.get("unknown_fields") or [])
        args = tool_args(inputs)
        value = args.pop("assessable_value_pkr")
        facts = state.get("facts") or {}
        rounds_left = state.get("clarify_rounds", 0) < cfg.max_clarify_rounds
        if value is None:
            # No value yet: ask for it together with everything else the rules need (discovered with a 1 PKR stand-in value whose numbers are discarded).
            missing = discover_missing(deps.tools, code, date_iso, args, "1")
            vq = VALUE_Q + (f" ({facts['value_issue']})" if facts.get("value_issue") else "")
            return ask_or_stop(lookup, missing, unknown, rounds_left, None if "assessable_value_pkr" in unknown else vq, "value missing")
        duty = deps.tools.compute_duty(code, value, date_iso, **args)
        if duty.get("status") == "needs_input":
            missing = discover_missing(deps.tools, code, date_iso, args, value, seed=duty["missing_inputs"])
            return ask_or_stop(lookup, missing, unknown, rounds_left, None, "needs_input")
        if duty.get("status") not in ("computed", "cannot_compute"):
            return {"lookup": lookup, "duty": duty, "route": "verify", "trace": [f"calculate: tool status {duty.get('status')}"]}
        rules = deps.tools.get_applicable_sros(code, date_iso)
        in_force: dict = {}
        for label, key in (("RD", "rd"), ("ACD", "acd"), ("sales tax", "sales_tax"), ("income tax", "income_tax")):
            blk = (rules.get(key) or {}).get("notifications", {}).get("in_force_on_date", [])
            in_force[label] = [n["sro_number"] for n in blk]
        return {"lookup": lookup, "duty": duty, "rules_in_force": in_force, "route": "verify", "trace": [f"calculate: {duty['status']}"
                + (f", total {duty['totals']['total_payable_pkr']}" if duty.get("totals") else "")]}

    return calculate


# --------------------------------------------------------------------------------------------- Verify
def bill_checks(duty: dict | None, lookup: dict | None, date_iso: str) -> tuple[dict, list]:
    """Exact checks that need no LLM: (a) the code exists and is valid on the date, arithmetic of the bill, every line has a citation."""
    from decimal import Decimal

    checks, issues = {}, []
    ok_code = bool(lookup and lookup.get("status") == "found" and lookup.get("level") == 8 and lookup["valid_from"] <= date_iso <= lookup["valid_to"])
    checks["code_exists_on_date"] = ok_code
    if not ok_code:
        issues.append("the chosen code is not a valid tariff line on the date")
    if not duty or duty.get("status") not in ("computed", "cannot_compute"):
        checks["bill_arithmetic"] = checks["citations_complete"] = False
        issues.append(f"the calculation tool did not return a bill (status {duty.get('status') if duty else None})")
        return checks, issues
    lines = duty.get("lines", [])
    cites = all(ln.get("instrument") and ln.get("clause") and ln.get("source_file") and isinstance(ln.get("page"), int) and ln.get("valid_from") and ln.get("valid_to") for ln in lines)
    checks["citations_complete"] = bool(cites)
    if not cites:
        issues.append("a bill line has no complete citation (instrument, clause, file, page, dates)")
    if duty["status"] == "computed":
        tot = duty["totals"]
        s = {"customs_duties": Decimal(0), "federal_excise_duty": Decimal(0), "sales_tax": Decimal(0), "income_tax": Decimal(0)}
        for ln in lines:
            a = Decimal(ln["amount_pkr"])
            if ln["tax"] in ("CD", "RD", "RD_USED_VEHICLE", "ACD"):
                s["customs_duties"] += a
            elif ln["tax"] in ("FED", "SED"):
                s["federal_excise_duty"] += a
            elif ln["tax"] in ("ST", "VAT"):
                s["sales_tax"] += a
            elif ln["tax"] == "IT":
                s["income_tax"] += a
        ok = all(Decimal(tot[k]) == v for k, v in s.items()) and Decimal(tot["total_payable_pkr"]) == sum(s.values())
        checks["bill_arithmetic"] = ok
        if not ok:
            issues.append("the totals do not equal the sum of the bill lines")
    else:
        checks["bill_arithmetic"] = True      # no total is given for a partial bill
    return checks, issues


def make_verify(deps: Deps):
    cfg = deps.cfg

    def verify_notes(state: AgentState, chosen: dict) -> list:
        """Notes for the chosen code's chapter (+ its section notes and the GRI), labelled. Uses retrieved notes; fetches the chapter if it was not retrieved."""
        ev = state["evidence"]
        chapter = chosen["norm"][:2]
        notes = [n for n in ev.get("notes", []) if n.get("chapter") == chapter or n.get("kind") in ("gri", "section_note")]
        if not any(n.get("chapter") == chapter for n in notes):
            extra = [h for h in deps.retriever(chapter + "00", "notes", state["as_of_date"], 40) if h.get("method") == "exact_code"][:8]
            for i, h in enumerate(extra, 1):
                notes.append({"label": f"V{i}", "id": h["id"], "kind": h.get("kind"), "scope": h.get("scope", ""), "number": str(h.get("note_number") or ""), "text": h.get("text", ""),
                              "page": h.get("page"), "source_file": h.get("source_file"), "chapter": chapter})
        return notes

    def verify(state: AgentState) -> dict:
        date_iso = state["as_of_date"]
        cands = state.get("candidates") or []
        top = cands[0]
        lookup, duty = state.get("lookup"), state.get("duty")
        checks, issues = bill_checks(duty, lookup, date_iso)
        warnings: list[str] = []
        # (b) every cited fact in the final text is in the tool output / retrieved evidence / user's words
        if duty and duty.get("status") in ("computed", "cannot_compute") and lookup and lookup.get("status") == "found":
            draft = render_answer({**state}, None)["text"]
            corpus = Corpus(lookup, duty, state.get("rules_in_force"), state.get("evidence"), user_text(state), state.get("facts"), state.get("inputs"), [c["code"] for c in cands])
            g = check_text(draft, corpus)
            checks["figures_grounded"] = not g
            if g:
                issues.append("figures in the answer that are not in the tool output or sources: " + ", ".join(f"{i['type']} {i['token']}" for i in g[:5]))
        else:
            checks["figures_grounded"] = False
        # (a)+(c) second LLM call: does the line fit the goods, do the notes agree
        llm_part, log = None, []
        has_desc = bool((state.get("facts") or {}).get("goods_description"))
        if state.get("user_code_only") or not has_desc:
            checks["llm_fit"] = checks["notes_agree"] = None
            warnings.append("no product description was given, so the language-model fit check was skipped")
        else:
            notes = verify_notes(state, top)
            block = "LEGAL NOTES (labels N1.. are the only valid labels)\n" + "\n".join(f"[{n['label']}] {n['scope']} note {n['number']} ({n['kind']}): {re.sub(chr(10), ' ', note_body(n['text']))[:700]}" for n in notes)
            prompt = prompts.verify_prompt(state.get("facts") or {}, state.get("clarifications") or [], top, [c for c in cands[1:3]], block, top.get("reasons", ""), date_iso)
            try:
                res, lg = _call(deps, "verify", prompts.VERIFY_SYSTEM, prompt)
                llm_part = validate_verify(res.data)
                log = [lg]
            except LLMError as e:
                return _err_update(e)
            except SchemaError as e:
                llm_part = {"fits": False, "fit_confidence": 0.0, "contradicting_notes": [], "unsupported_claims": [], "problems": [f"the auditor's answer could not be read ({e})"], "search_hint": None}
            gc = Corpus(state.get("evidence"), user_text(state), state.get("facts"), state.get("inputs"), lookup, duty)
            llm_part["problems"] = [clean_llm_text(x, gc, 300)[0] for x in llm_part["problems"]]
            llm_part["unsupported_claims"] = [clean_llm_text(x, gc, 300)[0] for x in llm_part["unsupported_claims"]]
            llm_part["contradicting_notes"] = [{"note": c["note"], "why": clean_llm_text(c["why"], gc, 300)[0]} for c in llm_part["contradicting_notes"]]
            labels = {n["label"]: n for n in notes}
            real = [c for c in llm_part["contradicting_notes"] if c["note"] in labels]
            ignored = [c for c in llm_part["contradicting_notes"] if c["note"] not in labels]
            if ignored:
                warnings.append("the auditor cited note labels that do not exist (" + ", ".join(c["note"] for c in ignored) + "); ignored")
            fit_ok = llm_part["fits"] and llm_part["fit_confidence"] >= cfg.verify_threshold
            checks["llm_fit"] = fit_ok
            checks["notes_agree"] = not real
            if not llm_part["fits"] or llm_part["fit_confidence"] < cfg.verify_threshold:
                issues.append("the independent check says the line does not fit the goods" if not llm_part["fits"] else f"the independent check is not confident the line fits ({conf_text(llm_part['fit_confidence'])})")
            for c in real:
                n = labels[c["note"]]
                issues.append(f"{n['scope']} note {n['number']} may contradict this choice: {c['why']}")
            issues += [p for p in llm_part["problems"] if not llm_part["fits"]]
            warnings += [f"unsupported claim: {u}" for u in llm_part["unsupported_claims"]]
            if llm_part["fits"]:
                warnings += [f"unchecked: {p}" for p in llm_part["problems"]]
        passed = not issues
        summary_bits = ["exact checks " + ("passed" if all(v for k, v in checks.items() if k not in ("llm_fit", "notes_agree") and v is not None) else "FAILED")
                        + " (code exists on the date, bill adds up, every line cited, every figure found in the tool output)"]
        if checks.get("llm_fit") is not None:
            summary_bits.append(f"second AI call: line {'fits' if checks['llm_fit'] else 'does NOT fit'}, legal notes {'agree' if checks['notes_agree'] else 'DISAGREE'}")
        verification = {"passed": passed, "checks": checks, "issues": issues, "warnings": warnings, "llm": llm_part, "summary": "; ".join(summary_bits) + "."}
        retries = state.get("retries", 0)
        attempts = state.get("attempts", []) + [{"attempt": retries, "stage": "verify", "code": top["code"], "passed": passed, "issues": issues}]
        if passed:
            return {"verification": verification, "attempts": attempts, "mode": "answer" if duty["status"] == "computed" else "cannot_compute", "route": "respond", "llm_log": log,
                    "trace": ["verify: passed" + (f" ({len(warnings)} warning(s))" if warnings else "")]}
        queries = ([llm_part["search_hint"]] if llm_part and llm_part.get("search_hint") else []) + list(state.get("extra_queries") or [])
        if retries < cfg.max_retries:
            fb = f"Your choice {top['code']} was rejected by an independent check: " + "; ".join(issues[:4]) + "."
            return {"verification": verification, "attempts": attempts, "retries": retries + 1, "retry_pending": True, "feedback": fb, "extra_queries": queries, "route": "search", "llm_log": log,
                    "trace": [f"verify: failed ({'; '.join(issues[:2])}) -> retry {retries + 1}"]}
        return {"verification": verification, "attempts": attempts, "mode": "not_sure", "not_sure_reason": "an independent check kept failing: " + "; ".join(issues[:3]),
                "route": "respond", "llm_log": log, "trace": [f"verify: failed ({'; '.join(issues[:2])}) -> not sure after {retries} retries"]}

    return verify


# --------------------------------------------------------------------------------------------- Respond
def make_respond(deps: Deps):
    def respond(state: AgentState) -> dict:
        mode = state.get("mode") or "answer"
        if mode == "refused":
            final = render_refusal(state)
        elif mode == "error":
            final = render_error(state)
        elif mode == "needs_input":
            final = render_needs_input(state)
        elif mode == "not_sure":
            final = render_not_sure(state)
        else:
            final = render_answer(state, state.get("verification"))
            # last line of defence: nothing may reach the user that the tool output / sources do not contain
            cands = state.get("candidates") or []
            corpus = Corpus(state["lookup"], state["duty"], state.get("rules_in_force"), state.get("evidence"), user_text(state), state.get("facts"), state.get("inputs"), [c["code"] for c in cands])
            bad = check_text(final["text"], corpus)
            if bad:
                final = render_error({**state, "error": {"type": "GroundingError", "message": "an internal consistency check failed (a figure was not found in the tool output): "
                                                         + ", ".join(f"{i['type']} {i['token']}" for i in bad[:4])}})
        if state.get("notes_to_user"):
            final["text"] = "NOTES ABOUT YOUR QUESTION:\n" + "\n".join(f"  - {n}" for n in state["notes_to_user"]) + "\n\n" + final["text"]
        final["trace"] = list(state.get("trace", []))
        return {"final": final, "trace": [f"respond: {final['status']}"]}

    return respond
