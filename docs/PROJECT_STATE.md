# PROJECT_STATE.md - read this FIRST (saves agents from re-reading ten docs)

Customs Copilot (Pakistan): an agent that picks the 8-digit PCT code and computes the full duty bill (CD, RD, ACD, sales tax, income tax, FED) for FY2025-26 and FY2026-27 only, with a citation behind every number. Owner: Maaz Ahmed (beginner). Rules: CLAUDE.md (hard rules 1-8). Spec: SPEC.md.

## How to run things
- Python: `.venv/Scripts/python` (a harmless pywin32.pth warning prints at startup; use `PYTHONIOENCODING=utf-8`).
- All tests: `.venv/Scripts/python -m pytest -q` (about 300 tests, about 80 s).
- Rebuild the store: `python -m src.store.build` (data/processed/legal_store.sqlite). Rebuild search index: `python -m src.search.build` (about 10 min).
- Agent CLI: `python -m src.agent`. MCP tools: `python -m src.tools.mcp_server`.
- Review pages for the owner: src/ingest/review_pages.py, owner_tasks.py; results CSVs go to data/processed/review_results/.

## What exists (status 2026-10-15)
| Area | Where | State |
|---|---|---|
| Tariffs FY25-26, FY26-27 | src/ingest/tariff.py, data/processed/tariff_*.json | done; description bug being fixed (sub-group headers attached to the row above) |
| RD, ACD, used-vehicle SROs | a2/a3 files, docs/a2_sro_findings.md | done; owner checked about 230 rows, 0 errors |
| Sales tax, income tax | docs/a3_findings.md | done; mobile phones, sugar, formula rates, Chapter 99 cannot be computed |
| FED | docs/a6_fed_findings.md | loaded (174 rows); not yet applied in compute_duty (spec in section 6) |
| Legal notes (HS 2022) | docs/a4_findings.md | done, applicability assumed |
| Dated store | src/store, docs/store_schema.md | done; every fact row has valid_from, valid_to, source_file, page |
| Search (BM25 + dense + rerank) | src/search, docs/search_notes.md | done, 4 indexes |
| Tools | src/tools, docs/tools.md | done: lookup_code, get_applicable_sros, compute_duty (MCP) |
| LangGraph agent | src/agent, docs/agent.md, docs/agent_notes.md | works live with Gemini free tier; retrieval for big headings weak |
| Ground truth | data/ground_truth (README) | 79 real (+5 out of scope), 60 synthetic (unverified); owner reviewed 20 |
| Evaluation harness, UI/API, README results | - | NOT started |

## Conventions that matter
- Never write a rate from memory; every rate comes from a source document with page and clause.
- Duty arithmetic and date rules are exact code (Decimal), never the LLM.
- Nothing is `verified` unless the owner checked it. AI second reads are labelled "AI second reader, not owner verification".
- Never edit data/raw or data/processed/review_results. Never print or commit .env (Gemini key).
- Gemini free tier: about 20 requests per model per day; answers are cached on disk; keep live calls tiny.
- Owner questions go to docs/owner_questions.md in plain language with page numbers; the owner gets them as an HTML task page, never as a vague list.
- Commit messages end with: Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>

## Token-saving rules for agents
- Read only the docs your task needs (this file, plus at most 2-3 others). Do not re-read whole PDFs; search them with pymupdf.
- Render page images only when a number must be confirmed visually; prefer the text layer.
- One agent per task; do not spawn sub-agents. Stop and report if blocked.
