# Evaluation harness (C2)

Code: `src/eval/` (`cases.py`, `systems.py`, `metrics.py`, `citations.py`, `run.py`, `report.py`). Tests: `tests/test_eval.py` (no network).
The numbers live in `docs/eval_report.md`, which is **generated** from `data/processed/eval/results_<system>.jsonl`. Nothing in this file is a result.

## Run
```
python -m src.eval.run --sample 5 --systems plain_llm llm_rag full_graph --max-llm-calls 60   # small fixed subset (5 real + 5 synthetic)
python -m src.eval.run --max-llm-calls 120                                                      # everything, resumable
python -m src.eval.run --kinds duty --systems full_graph                                        # hand-computed bills
python -m src.eval.run --report                                                                 # rebuild docs/eval_report.md only
```
Cases already in the results file are skipped, so repeat the command each day after the Gemini free quota resets. A quota or budget stop is saved
as progress. A crash is saved as `error` and counted wrong (`--rerun-errors` tries again). LLM answers are cached on disk, so a re-run costs nothing.

## The three systems (the ablation)
| System | What it has | What it lacks |
|---|---|---|
| `plain_llm` | the LLM and its own knowledge | retrieval, tools, checks. May invent codes (kept and scored) |
| `llm_rag` | tariff (15 lines) and ruling retrieval; picks only among offered lines | clarify, legal notes, verify, duty tools |
| `full_graph` | the whole LangGraph agent | nothing. Nobody answers its clarifying questions (see below) |

## Scoring rules
* **Code accuracy**: top-1 and top-5 at 4, 6 and 8 digits, prefix match against the expected code or an accepted alternative. A case whose expected code is shorter than the level is left out of that cell, so n differs per cell and is printed. The full graph returns at most 3 candidates, so its top-5 equals its top-3.
* **Behaviour** (synthetic only): expected `answer`, `not_sure_or_clarify` or `refuse`. For the full graph a run that pauses to ask about the classification counts as `not_sure_or_clarify`; one that only asks for duty inputs (value, importer status) counts as `answer`, because the code was already chosen. A "not sure" answer is also checked for showing the right heading among its candidates.
* **Citation correctness** (full graph): each citation must point at a real fact row (tariff line on the date with the same file and page, or a store row with that file and page). It checks the pointer, not the legal claim. Ruling citations are information only and are not scored.
* **Duty match**: the bill total equals a hand-computed total to the paisa. `data/ground_truth/duty_cases.csv` holds 2 cases (the T-shirt hand cases of `tests/test_tools.py`, 6109.1000, before and after 1 July 2026). That is far too few for a rate; the report prints n.
* **Intervals**: 95% Wilson. Real and synthetic are never averaged. Systems are compared only on cases every system has run.

## Leak control
Real cases come from FBR rulings that are also in the rulings search index. For a real case, hits from that case's own ruling file are removed from every ruling search (`leak_free`, tested). Synthetic cases have no source ruling.

## Limits
* Real part: 79 cases from public sources, mostly one Karachi classification committee, leaning to machinery, electronics and chemicals. Synthetic part: written by Claude, unverified; a mismatch may be the label's mistake.
* Gemini free tier is roughly 20 requests per model per day. The full graph uses several calls per case, so a full run takes several days. Partial results are reported as partial, with their n.
* The baseline (Danial's TariffAI at 6 digits) is not run. It needs the repository cloned and set up; MIT licence, reference only, no code copied.
