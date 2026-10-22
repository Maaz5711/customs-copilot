"""Daily test run on a free model. Default: Google Gemini free tier (several models, each with its own daily quota, already in .env).
Alternative: OpenRouter free models (50 requests a day in total; MiniMax M3.1 Flash stopped being free on 2026-10-22).

One command a day; it continues where yesterday stopped:

    python -m src.eval.daily_free                  # Gemini free tier, dev split
    python -m src.eval.daily_free --provider openrouter --model google/gemma-4-31b-it:free
    python -m src.eval.daily_free --split test     # only when a version is final: report test once, never tune on it

* Lean settings so a case costs about 4-6 calls (understand, up to 2 research steps, classify, verify): heading hints off,
  AGENT_EXPLORE_STEPS=2. Results are NOT comparable with runs that used other settings; the folder name carries the settings.
* Case order is a fixed random shuffle of the split, so any number of finished cases is an unbiased sample.
* A case is not started unless enough of today's call budget is left to finish it, so no calls are wasted on half-done cases.
* The free model may log prompts: only evaluation cases are sent, never users' questions.
* Needs the provider's key in .env (gitignored): GEMINI_API_KEY (Gemini) or OPENROUTER_API_KEY (OpenRouter), one line: NAME=your-key-here
"""
from __future__ import annotations

import argparse
import os
import random
from pathlib import Path

from .metrics import wilson


def summarize(results: dict, cases: dict) -> list[str]:
    from .metrics import hit_at

    rows = [(cases[cid], r) for cid, r in results.items() if cid in cases]
    n = len(rows)
    if not n:
        return ["no finished cases yet"]

    def frac(level: int, k: int) -> str:
        hits = sum(bool(hit_at(r["pred"]["codes"], [c.expected], level, k)) for c, r in rows)
        lo, hi = wilson(hits, n)
        return f"{hits}/{n} ({100 * hits / n:.0f}%, CI {100 * lo:.0f}-{100 * hi:.0f})"

    errs = sum(r["pred"]["behavior"] == "error" for _, r in rows)
    asked = sum(r["pred"]["behavior"] == "not_sure_or_clarify" for _, r in rows)
    return [f"finished cases: {n}   (errors {errs}, asked or not sure {asked})",
            f"  exact 8-digit line, first choice : {frac(8, 1)}",
            f"  right line among top 3           : {frac(8, 3)}",
            f"  right 4-digit heading, first     : {frac(4, 1)}",
            "  (small n: the interval is wide; labels are AI-written and unverified)"]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=("dev", "test"), default="dev")
    ap.add_argument("--provider", choices=("gemini", "openrouter"), default="gemini")
    ap.add_argument("--budget", type=int, default=None, help="LIVE calls to use in this run (default 120 for Gemini, 48 for OpenRouter whose free limit is 50 a day)")
    ap.add_argument("--steps", type=int, default=2, help="research steps per question (AGENT_EXPLORE_STEPS)")
    ap.add_argument("--reserve", type=int, default=6, help="calls a case may need; a case is not started below this")
    ap.add_argument("--model", help="OpenRouter model id (required with --provider openrouter)")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(".env")
    key_name = "GEMINI_API_KEY" if a.provider == "gemini" else "OPENROUTER_API_KEY"
    if not os.environ.get(key_name, "").strip():
        raise SystemExit(f"{key_name} is not in .env yet. " + (__doc__ or "").split("Needs", 1)[-1].strip())
    if a.provider == "openrouter" and not a.model:
        raise SystemExit("Give an OpenRouter model, for example --model google/gemma-4-31b-it:free")
    os.environ.setdefault("AGENT_USE_HINTS", "0")
    os.environ["AGENT_EXPLORE_STEPS"] = str(a.steps)

    from src.agent import GeminiLLM, OpenRouterLLM

    from .cases import load_cases
    from .report import write_report
    from .run import load_results, run

    cases = [c for c in load_cases(("catalog",)) if c.split == a.split]
    random.Random(a.seed).shuffle(cases)
    budget = a.budget or (120 if a.provider == "gemini" else 48)
    out = Path(f"data/processed/eval/{a.provider}_cat_free_{a.split}_s{a.steps}")
    llm = GeminiLLM(max_calls=budget) if a.provider == "gemini" else OpenRouterLLM(model=a.model, max_calls=budget)
    res = run(["full_graph"], cases, llm, out, reserve=a.reserve)
    print(res, "| live calls:", llm.stats["live_calls"])
    done = load_results("full_graph", out)
    print(f"Progress on the {a.split} split: {len(done)} of {len(cases)} cases finished ({a.provider}, {a.steps} research steps, hints off)")
    for line in summarize(done, {c.id: c for c in cases}):
        print(line)
    try:
        write_report(out, Path(f"docs/eval_report_{a.provider}_cat_free_{a.split}.md"), f"{a.provider} free tier, lean settings")
    except Exception as e:        # the report is a convenience; the results are already saved
        print("(report not written:", type(e).__name__, str(e)[:80], ")")


if __name__ == "__main__":
    main()
