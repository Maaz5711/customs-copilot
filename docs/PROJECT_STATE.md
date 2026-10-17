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
| Tariffs FY25-26, FY26-27 | src/ingest/tariff.py, data/processed/tariff_*.json | done; sub-group header description bug fixed 2026-10-15 (new fields own_description, parent_chain, full_description) |
| RD, ACD, used-vehicle SROs | a2/a3 files, docs/a2_sro_findings.md | done; owner checked about 230 rows, 0 errors |
| Sales tax, income tax | docs/a3_findings.md | done; mobile phones, sugar, formula rates, Chapter 99 cannot be computed |
| FED | docs/a6_fed_findings.md, src/tools/fed.py | loaded (174 rows + 34 mapped-by-description rows); applied in compute_duty; EV, 3001 cc, CKD refused; owner checked 15 cards 2026-10-15: 16 rows verified, S.No 8/55/55A/IA stay needs_review (legal reading open) |
| Legal notes (HS 2022) | docs/a4_findings.md | done, applicability assumed |
| Dated store | src/store, docs/store_schema.md | done; every fact row has valid_from, valid_to, source_file, page |
| Search (BM25 + dense + rerank) | src/search, docs/search_notes.md | done, 4 indexes |
| Tools | src/tools, docs/tools.md | done: lookup_code, get_applicable_sros, compute_duty (MCP) |
| LangGraph agent | src/agent, docs/agent.md, docs/agent_notes.md | works live with Gemini free tier; retrieval for big headings weak |
| Ground truth | data/ground_truth (README) | 79 real (+5 out of scope), 60 synthetic (unverified); owner reviewed 20 |
| Concessions (A7/A8, added 2026-10-16) | src/ingest/a7_fifth*.py, a8_cpfta*.py, src/tools/concessions.py, docs/concessions_findings.md, a8_cpfta_findings.md, gd_concession_check.md | Fifth Schedule FY2025-26 (FBR file, 1,519 rules) and FY2026-27 (1,349) and China FTA Phase II (6,778 of 6,786 SRO lines, OCR + pattern fit) in the store; compute_duty / get_applicable_sros offer them (bill with and without, never applied unless claimed); agent asks about conditions and origin/Form E. Against real GD lines: 98.4% of China FTA lines whose code is in our table match the CD charged; 21% of FTA lines have HS 2022 codes missing from the 2019 table (amendments not collected, OQ-A8-1). Owner spot checks pending (OQ-A7-5, OQ-A8-4) |
| Evaluation (C2) | src/eval, docs/eval.md, docs/eval_versions.md | DONE for v0-v4 on DeepSeek flash (key in .env). Full agent real cases: exact 8-digit line top-1 38/70 (54%), right line in top 3 51/70 (73%); plain LLM 18/70, LLM+search 24/70. TariffAI baseline run (6-digit only). All numbers in docs/eval_versions.md with intervals |
| UI/API, README results | - | NOT started |

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

## Owner decisions so far (do not re-ask)
- Gemini FREE tier is the LLM (key in .env). Keep live calls tiny; answers are cached on disk.
- FED: included in compute_duty (done). EV cars, 3001 cc, CKD vehicles are refused rather than guessed until the owner/consultant answers OQ-A6-1/2/4.
- CKD vs CBU: the agent asks the importer at runtime.
- Legal notes are labelled "HS 2022 edition, applicability to FY2025-26 and FY2026-27 assumed, not proven". Chapter 99 sub-chapter conditions (tariff pp.586-602) are out of scope.
- Fifth Schedule and China FTA Phase II concessions: added 2026-10-16 (approved by the owner). Other FTAs/PTAs and sugar/mobile-phone tax tables: out of scope (tools warn / cannot_compute).
- No time estimates (CLAUDE.md). Work is ordered by dependency.
- Owner style: every manual task is an HTML task page (scan + instructions + answer boxes + Save CSV). Minimise his work; AI second readers do the rest and are labelled as such.

## Owner items still pending
1. Optional: tariff 2026-27 pp.236, 237, 271 (header printed at same depth as first row: confirm parent headings read sensibly).
2. Optional: a customs expert/clearing agent to check two FED mappings (e-liquid 2404.1900, nicotine pouches 2404.9100: data/processed/a6_fed_mapping.csv) and OQ-A6-1/2/4; one real Goods Declaration of a car would also settle OQ-OPEN10 (3% value-addition base), rounding and EV serial.
3. docs/owner_questions.md lists all other open legal questions (sugar window, S.No 84(i), etc.). None blocks the next phase.
4. Baseline: clone Danial's TariffAI (MIT, reference only) so it can be run on the same cases at 6 digits.

## Duty-side verification (2026-10-16)
* Official WeBOC duty calculator used as an independent oracle: 49 FY2026-27 codes captured (`data/ground_truth/weboc_calculator_2026-10-16.json`), compared by `python -m src.eval.weboc_compare` -> `docs/weboc_comparison.md`. Result: of 33 codes our tool can compute on these inputs, CD/RD/ACD/ST(/FED) match WeBOC to the rupee on 30; 3 vehicle-part codes differ (WeBOC ACD 11%, OQ-W1). Income tax: found and fixed a real gap (non-filer doubling, ITO Tenth Schedule rule 1; tool now asks `importer.active_taxpayer`). WeBOC flat 12% IT and no 3% VAT are WeBOC simplifications (OQ-W2, OQ-W3).
* The WeBOC form is a plain ASP.NET page; a short in-browser script (fields txtHSCode, txtQuantity, txtUnitValue, btnSaveBottom) reads it. Keep use light (about 150 requests so far, 1.2 s apart).

## Status 2026-10-16 evening
* Concessions (Fifth Schedule both years, China FTA SRO 1640(I)/2019) built, committed, 457 tests pass. Agent asks origin and claim questions, shows both bills. Real-data check: docs/gd_concession_check.md (China FTA 98.4% match where the code is in the 2019 table; 21% of FTA lines carry HS 2022 codes missing from it: amendments to SRO 1640 are not in data/raw, OQ-A8-1).
* Further tax for unregistered importers (4% at the 18% rate) is now added and included in the income-tax base (real assessed GDs, docs/gd_findings.md); non-filer income tax doubled (Tenth Schedule rule 1).
* Importer classification (DeepSeek flash): 150 cases for all three systems (11% / 24% / 42% exact line) and the full agent on 276 cases (44%). Stopped: DeepSeek balance is $0 (HTTP 402). Resume only after a top-up, off-peak: three shards `python -m src.eval.run --llm deepseek --tag importer_s{i} --kinds importer --classify-thinking enabled --systems full_graph --shard i/3 --skip-done-in data/processed/eval/deepseek_importer --max-llm-calls 450`, then `--merge-from` the shard folders (about 680 cases, about 2.2 USD).

## Status 2026-10-17 (duty and concession wrap-up, 469 tests pass)
* Plain-rate importer lines matching Customs on every tax: 88% (678 of 770), up from 84%.
* Further tax for unregistered importers now also at non-18% rates (7/18 of sales tax less the 3% line, flagged OPEN4_OBSERVED). Observed ACD 11% on 11 codes: warning only (OQ-W1). Part III raw-material proviso: offered as a possible rule, never applied (OQ-W5). China FTA family rates: information only (75% reliable, never applied). Phones: still cannot_compute (OQ-W4). Details: docs/gd_findings.md section 4d.
* Single source of truth for which tax goes into which total: TAX_TOTAL_BUCKET in src/tools/compute.py (guard test).
* Open for the owner: spot-check sheets (Fifth Schedule, China FTA), OQ-A7-1, OQ-A8-1, sending the FBR email and clearing-agent message, DeepSeek top-up.

## NEXT STEPS (in order)
1. Real answer key: owner is asking a friend (textile/electronics importer from China) for 30-50 products with the final accepted 8-digit code (kit in docs/case_collection/). When it arrives: add as a third case file (kind 'importer'), report separately, check for disputes vs clean cases. Real test set is mostly contested goods (66 of 79 are disputes), so scores are pessimistic for everyday goods.
2. FBR email (docs/case_collection/email_draft.md) is for the owner to send: asks permission to use published documents in a free public tool, data files, a validation reviewer, and 5 legal questions. Legal note: FBR website terms allow copying unmodified single pages for sharing; our derived data should not be republished until permission arrives.
3. Accuracy levers still open: tune Classify (thinking is on in v4: +2 cases, within noise, cost about 0.004 USD per query); more precedents as FBR publishes; WCO Explanatory Notes cannot be copied (hard rule 6), cite by reference only; ask-and-answer loop with real users (the simulated importer did not help).
4. More hand-computed duty cases in data/ground_truth/duty_cases.csv (only 2 exist).
5. C3: FastAPI + simple UI (answer, bill, sources, alternatives, date stamp, 'not FBR' notice, privacy notice for the LLM provider), README with docs/eval_versions.md numbers. Competitors (clearagent.io, taxtoday.pk) are keyword lookups with customs duty only; our edge is described-in-words classification plus the full cited bill by date.
6. Eval LLM: DeepSeek flash (DEEPSEEK_API_KEY). Spend so far about 4.4M input and 0.9M output tokens: 1.2 to 2.4 USD depending on peak/off-peak. Check the DeepSeek balance before large runs. Gemini adapter still works (free tier, 20 req/model/day).

## Housekeeping notes
- Local-only (gitignored): data/raw (originals), legal_store.sqlite, search_index/, .env. Rebuild commands are at the top.
- Untracked leftovers: data/processed/sro_vision/ (vision outputs), and duplicate PDFs in the repo root (copies of files in data/raw; safe to delete by the owner).
- Remote Control (phone) was turned on for the old session; enable it for the new session from the toolbar.
- Token use: the Pro plan 5-hour window is the bottleneck. Run at most one or two agents at once; check usage first (ccd_session_mgmt get_usage); do small jobs inline.
