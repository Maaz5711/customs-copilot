"""Retrieval-only evaluation (no LLM, no cost): does the right tariff line reach the shortlist the classifier sees?

For every catalogue case the same retrieval the agent uses (`gather`) is run on the description alone, with no LLM heading hints,
and we record whether the expected 8-digit line, its 6-digit sub-heading and its 4-digit heading are among the offered lines.
This is the ceiling for the Classify step: if the line is not offered, the agent cannot pick it.

    python -m src.eval.retrieval_eval --split dev                 # tune on this
    python -m src.eval.retrieval_eval --split test --tag v1       # report once per version
    python -m src.eval.retrieval_eval --split dev --misses 20     # show the first misses
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.agent.retrieval import default_notes_loader, default_retriever, gather, offered_codes

from .cases import load_cases
from .metrics import wilson


def run(cases, retriever=default_retriever, notes_loader=default_notes_loader, **kw) -> list[dict]:
    out = []
    for c in cases:
        t0 = time.time()
        ev = gather(retriever, notes_loader, query=c.description, as_of_date=c.as_of_date, **kw)
        offered = offered_codes(ev)
        exp = c.expected
        out.append({"id": c.id, "expected": exp, "description": c.description, "n_offered": len(offered), "secs": round(time.time() - t0, 2),
                    "hit8": exp in offered, "hit6": any(o[:6] == exp[:6] for o in offered), "hit4": any(o[:4] == exp[:4] for o in offered),
                    "rank8": offered.index(exp) + 1 if exp in offered else None, "offered": offered[:60], "split": c.split, "confidence": c.confidence})
    return out


def fmt(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({100 * k / n:.0f}%, {100 * lo:.0f}-{100 * hi:.0f})" if n else "n/a"


def summary(rows: list[dict]) -> dict:
    n = len(rows)
    return {"n": n, "line_offered": sum(r["hit8"] for r in rows), "subheading_offered": sum(r["hit6"] for r in rows), "heading_offered": sum(r["hit4"] for r in rows),
            "line_in_first_10": sum(1 for r in rows if r["rank8"] and r["rank8"] <= 10), "median_offered": sorted(r["n_offered"] for r in rows)[n // 2] if n else 0}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=("dev", "test", "all"), default="dev")
    ap.add_argument("--confidence", choices=("H", "all"), default="all")
    ap.add_argument("--tag", default="")
    ap.add_argument("--misses", type=int, default=0)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    cases = [c for c in load_cases(("catalog",)) if a.split == "all" or c.split == a.split]
    if a.confidence == "H":
        cases = [c for c in cases if c.confidence == "H"]
    cases = cases[: a.limit] if a.limit else cases
    rows = run(cases)
    s = summary(rows)
    print(f"retrieval-only, catalogue {a.split} split, confidence {a.confidence}, n={s['n']}")
    print("  exact line offered :", fmt(s["line_offered"], s["n"]))
    print("  6-digit offered    :", fmt(s["subheading_offered"], s["n"]))
    print("  4-digit offered    :", fmt(s["heading_offered"], s["n"]))
    print("  line in first 10   :", fmt(s["line_in_first_10"], s["n"]), "| median lines offered:", s["median_offered"])
    for r in [r for r in rows if not r["hit8"]][: a.misses]:
        print(f"  MISS {r['id']} {r['expected']} (4-digit {'ok' if r['hit4'] else 'MISSING'}): {r['description'][:90]}")
    if a.tag:
        d = Path("data/processed/eval/retrieval")
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{a.tag}_{a.split}.json").write_text(json.dumps({"summary": s, "rows": rows}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
