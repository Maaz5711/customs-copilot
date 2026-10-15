"""Run the ablation (C2): plain LLM vs LLM + RAG vs full graph, over the ground-truth cases, resumable, quota-aware.

    python -m src.eval.run --systems plain_llm llm_rag full_graph --kinds real synthetic --max-llm-calls 120
    python -m src.eval.run --sample 20 --seed 1 --systems full_graph       # a fixed random subset (same cases every time)
    python -m src.eval.run --report                                        # only rebuild docs/eval_report.md from the saved results

Results go to data/processed/eval/results_<system>.jsonl, one line per (case, system). A case already in the file is skipped, so
the run can be repeated every day after the Gemini free quota resets. A quota or budget stop is saved as progress, not as a failure.
Errors that are not quota (a crash) are saved with behavior 'error' and counted as wrong; --rerun-errors tries them again.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from src.agent.llm import LLMBudgetExceeded, LLMRateLimited

from .cases import Case, load_cases, load_duty_cases
from .systems import RUNNERS, SYSTEMS

OUT = Path("data/processed/eval")
STOP = (LLMRateLimited, LLMBudgetExceeded)


def results_path(system: str, out: Path = OUT) -> Path:
    return out / f"results_{system}.jsonl"


def load_results(system: str, out: Path = OUT) -> dict[str, dict]:
    p = results_path(system, out)
    if not p.exists():
        return {}
    rows = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["case_id"]] = r
    return rows


def _save(system: str, rec: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows = load_results(system, out)
    rows[rec["case_id"]] = rec
    tmp = results_path(system, out).with_suffix(".tmp")
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows.values()) + "\n", encoding="utf-8")
    tmp.replace(results_path(system, out))


def select(cases: list[Case], sample: int | None, seed: int, ids: list[str] | None) -> list[Case]:
    if ids:
        return [c for c in cases if c.id in set(ids)]
    if sample:
        by_kind: dict[str, list[Case]] = {}
        for c in cases:
            by_kind.setdefault(c.kind, []).append(c)
        rng = random.Random(seed)
        picked = []
        for kind in sorted(by_kind):
            lst = by_kind[kind]
            picked += rng.sample(lst, min(sample, len(lst)))
        return picked
    return cases


def run_case(system: str, case: Case, llm, **kw) -> dict:
    t0 = time.time()
    pred = RUNNERS[system](case, llm, **kw)
    return dict(case_id=case.id, kind=case.kind, system=system, as_of_date=case.as_of_date, expected=case.expected,
                expected_behavior=case.behavior, pred=pred, seconds=round(time.time() - t0, 1))


def run(systems, cases, llm, out: Path = OUT, rerun_errors: bool = False, log=print, **kw) -> dict:
    """Returns {'done': n, 'skipped': n, 'stopped': reason or None}."""
    done = skipped = 0
    for system in systems:
        have = load_results(system, out)
        for case in cases:
            old = have.get(case.id)
            if old and not (rerun_errors and old["pred"].get("behavior") == "error"):
                skipped += 1
                continue
            try:
                rec = run_case(system, case, llm, **kw)
            except STOP as e:
                log(f"STOP at {system} {case.id}: {e}")
                return dict(done=done, skipped=skipped, stopped=str(e))
            except Exception as e:      # a crash is a result, not a reason to stop the run
                rec = dict(case_id=case.id, kind=case.kind, system=system, as_of_date=case.as_of_date, expected=case.expected,
                           expected_behavior=case.behavior, pred=dict(behavior="error", codes=[], status="crash", citations=[], bill_totals=None,
                                                                      note=f"{type(e).__name__}: {str(e)[:200]}"), seconds=0)
            if rec["pred"].get("error_type") in {t.__name__ for t in STOP}:
                log(f"STOP at {system} {case.id}: LLM budget/quota ({rec['pred'].get('note')})")
                return dict(done=done, skipped=skipped, stopped=rec["pred"].get("note") or "llm quota")
            _save(system, rec, out)
            done += 1
            log(f"{system:10s} {case.id:5s} {rec['pred']['behavior']:20s} {rec['pred']['codes'][:2]}  expected {case.expected or case.behavior}")
    return dict(done=done, skipped=skipped, stopped=None)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--systems", nargs="+", default=list(SYSTEMS), choices=SYSTEMS)
    ap.add_argument("--kinds", nargs="+", default=["real", "synthetic"], choices=["real", "synthetic", "duty"])
    ap.add_argument("--ids", nargs="+")
    ap.add_argument("--sample", type=int, help="N cases per kind, fixed random subset")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-llm-calls", type=int, default=100, help="cap on LIVE Gemini calls in this process (cache hits are free)")
    ap.add_argument("--rerun-errors", action="store_true")
    ap.add_argument("--report", action="store_true", help="only rebuild the report")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    if not a.report:
        from src.agent import GeminiLLM

        llm = GeminiLLM(max_calls=a.max_llm_calls)
        cases = select(load_cases(tuple(k for k in a.kinds if k != "duty")) + (load_duty_cases() if "duty" in a.kinds else []), a.sample, a.seed, a.ids)
        res = run(a.systems, cases, llm, a.out, a.rerun_errors)
        print(res, "| live calls:", llm.stats["live_calls"], "cache hits:", llm.stats["cache_hits"])
    from .report import write_report

    write_report(a.out)


if __name__ == "__main__":
    main()
