"""Command line for the customs agent (C1).

    python -m src.agent                                   # interactive: type a product description
    python -m src.agent "men's cotton T-shirts, value PKR 2,500,000, registered commercial importer" --date 2026-07-15
    python -m src.agent --list-models                     # which Gemini models this key can use (does not use generation quota)

The agent never assumes today's date: give --date or it will ask. Free-tier Gemini keys have a small daily quota per model;
answers are cached on disk (data/processed/cache/llm/), so asking the same question again costs nothing.

To keep a paused conversation across runs use a checkpoint file:
    python -m src.agent "laptops" --db data/processed/cache/agent_threads.sqlite --thread demo1      # prints the questions and stops (not a terminal)
    python -m src.agent --db data/processed/cache/agent_threads.sqlite --thread demo1 --answer as_of_date=2026-07-15
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import uuid
from pathlib import Path

from .llm import GeminiLLM, LLMError
from .nodes import Config
from .runner import CustomsAgent, TurnResult

ROOT = Path(__file__).resolve().parents[2]


def _hint(q: dict) -> str:
    allowed = q.get("allowed")
    if allowed and all(isinstance(a, bool) for a in allowed):
        return "answer yes or no"
    if allowed:
        return "one of: " + " / ".join(map(str, allowed))
    return {"date": "a full date, for example 2026-07-15", "money_pkr": "an amount in PKR, for example 2500000 or 25 lakh", "number": "a number",
            "quantity": "a number" + (f" in {q['unit']}" if q.get("unit") else "")}.get(q.get("type"), "")


def show_questions(intr: dict, out) -> None:
    print("", file=out)
    print(intr.get("message", "I need more information."), file=out)
    for n in intr.get("notes") or []:
        print(f"  Note: {n}", file=out)
    qs = intr["questions"]
    for i, q in enumerate(qs, 1):
        print(f"  [{i}/{len(qs)}] {q['question']}", file=out)
        if q.get("error"):
            print(f"        (I could not use your last answer: {q['error']})", file=out)
        if q.get("why"):
            print(f"        why: {q['why']}", file=out)
        h = _hint(q)
        if h:
            print(f"        ({h}; type 'I don't know' if you do not know)", file=out)


def read_answers(intr: dict, input_fn) -> dict:
    """One prompt per question. Raises EOFError when there is no input (closed stdin)."""
    answers = {}
    for q in intr["questions"]:
        answers[q["id"]] = input_fn(f"  your answer to [{q['id']}]> ")
    return {"answers": answers}


def print_result(turn: TurnResult, out, debug: bool, llm) -> None:
    print("", file=out)
    print(turn.final["text"], file=out)
    if debug:
        print("\n--- debug ---", file=out)
        print("path: " + " > ".join(turn.path), file=out)
        for t in turn.trace:
            print("  " + t, file=out)
        st = getattr(llm, "stats", None)
        if st:
            print(f"LLM live calls: {st['live_calls']}  cache hits: {st['cache_hits']}  failed requests: {st['failed_requests']}  by model: {st['by_model']}", file=out)
            for line in st.get("log", []):
                print("  " + line, file=out)


def main(argv=None, *, input_fn=input, out=None, llm=None, agent_kwargs=None) -> int:
    out = out or sys.stdout
    try:
        out.reconfigure(encoding="utf-8", errors="replace")      # Windows consoles: never crash on a stray character in the tariff text
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="python -m src.agent", description="Pakistan customs copilot: tariff code and duty bill with citations (decision support, not legal advice).")
    ap.add_argument("question", nargs="?", help="what you want to import (leave out for an interactive session)")
    ap.add_argument("--date", help="date the rules apply (YYYY-MM-DD). Never assumed: if missing the agent asks.")
    ap.add_argument("--db", help="SQLite file that keeps paused conversations between runs")
    ap.add_argument("--thread", help="conversation id (with --db you can continue it later)")
    ap.add_argument("--answer", action="append", default=[], metavar="ID=TEXT", help="answer a pending question (repeatable)")
    ap.add_argument("--reply", help="free-text reply to the pending questions")
    ap.add_argument("--models", help="comma separated Gemini model names in order of preference (default: GEMINI_MODELS or the built-in list)")
    ap.add_argument("--max-llm-calls", type=int, default=None, help="stop after this many LIVE LLM calls (protects the free quota)")
    ap.add_argument("--no-cache", action="store_true", help="do not read or write the on-disk LLM response cache")
    ap.add_argument("--list-models", action="store_true", help="list the Gemini models this key can use and exit")
    ap.add_argument("--debug", action="store_true", help="print the node trace and LLM usage")
    ap.add_argument("--tools", choices=("inproc", "mcp"), default="inproc", help="call the exact tools in-process or through the MCP server (stdio)")
    a = ap.parse_args(argv)

    if llm is None:
        llm = GeminiLLM(models=[m.strip() for m in a.models.split(",")] if a.models else None, cache=not a.no_cache, max_calls=a.max_llm_calls)
    if a.list_models:
        try:
            avail = llm.available_models()
        except LLMError as e:
            print(f"Could not list models: {e}", file=out)
            return 1
        print("Configured order: " + ", ".join(llm.models), file=out)
        print("Available to this key (generateContent):", file=out)
        for m in avail:
            print(("  * " if m in llm.models else "    ") + m, file=out)
        print("(* = in the fallback chain. Listing does not use generation quota; whether a model still has free quota today is only known when it is called.)", file=out)
        return 0

    checkpointer, conn = None, None
    if a.db:
        from langgraph.checkpoint.sqlite import SqliteSaver

        Path(a.db).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(a.db, check_same_thread=False)
        checkpointer = SqliteSaver(conn)
    kw = dict(agent_kwargs or {})
    toolbox = None
    if a.tools == "mcp" and "tools" not in kw:
        from .toolbox import McpToolBox

        toolbox = McpToolBox()
        kw["tools"] = toolbox
    agent = CustomsAgent(llm, cfg=Config(), checkpointer=checkpointer, **kw)
    interactive = sys.stdin.isatty() if input_fn is input else True
    code = 0
    try:
        # ---- continue a stored conversation with scripted answers
        if a.thread and (a.answer or a.reply):
            if not agent.pending(a.thread):
                print(f"Thread {a.thread} has no pending questions.", file=out)
                return 1
            reply = {"answers": dict(x.split("=", 1) for x in a.answer)} if a.answer else a.reply
            turn = agent.resume(a.thread, reply)
            return _drive(agent, turn, input_fn, out, a, llm, interactive)
        first = a.question
        while True:
            if not first:
                if not interactive and input_fn is input:
                    print("Give a question, for example: python -m src.agent \"laptops\" --date 2026-07-15", file=out)
                    return 1
                try:
                    first = input_fn("\nWhat do you want to import? (empty line to quit)\n> ").strip()
                except (EOFError, KeyboardInterrupt):
                    return 0
                if not first:
                    return 0
            tid = a.thread or uuid.uuid4().hex[:12]
            if a.db:
                print(f"(conversation id: {tid})", file=out)
            try:
                turn = agent.ask(first, as_of_date=a.date, thread_id=tid)
            except ValueError as e:         # for example: --thread names a conversation that already exists
                print(f"{e}.", file=out)
                return 1
            code = _drive(agent, turn, input_fn, out, a, llm, interactive)
            if a.question:          # a question on the command line is a one-shot run
                return code
            first, a.thread = None, None
    except KeyboardInterrupt:
        print("\nStopped.", file=out)
        return 130
    finally:
        if toolbox is not None:
            toolbox.close()
        if conn is not None:
            conn.close()


def _drive(agent: CustomsAgent, turn: TurnResult, input_fn, out, a, llm, interactive: bool) -> int:
    while turn.interrupt:
        show_questions(turn.interrupt, out)
        if interactive:
            try:
                reply = read_answers(turn.interrupt, input_fn)
            except EOFError:                     # stdin is closed: behave like a non-interactive run
                print("", file=out)
                interactive = False
            else:
                turn = agent.resume(turn.thread_id, reply)
                continue
        ids = " ".join(f"--answer {q['id']}=..." for q in turn.interrupt["questions"])
        if a.db:
            print(f"\nNot a terminal, so I stopped here. Continue with:\n  python -m src.agent --db {a.db} --thread {turn.thread_id} {ids}", file=out)
        else:
            print("\nNot a terminal, so I stopped here. Add --db FILE (and --thread NAME) to your command to keep the conversation, then answer with --answer ID=TEXT.", file=out)
        return 2
    print_result(turn, out, a.debug, llm)
    return 1 if turn.final["status"] == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
