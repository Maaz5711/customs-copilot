# Plan: Fifth Schedule and China FTA concessions (new scope, approved by the owner 2026-10-16)

Why: for machinery importers (Fifth Schedule) and for goods from China (CPFTA Phase II) the real customs duty is often lower than the First Schedule CD that `compute_duty` applies today. The tools currently warn only ("concessions not in the store").

## What exists (verified 2026-10-16)
| Item | File | State |
|---|---|---|
| Fifth Schedule to the Customs Act, updated 30 Jun 2026 (59 pages) | `data/raw/2026825118858478FifthSchedule2026-27.pdf` | Text layer present but columns are scattered (table cells come out in separate lines). Needs coordinate-based parsing (pymupdf `get_text("words")` or blocks) plus page-image checks. |
| Same Schedule, older consolidation | inside `data/raw/20258121285942396CustomsAct1969(June2025)-(12.8.25).pdf` (pages 278-279 mention it) and `20268241784853463Customs-Act-1969.pdf` (page 281) | Use for FY2025-26 vs FY2026-27 differences. Check which version is valid when (the 2026-27 file says "Updated 30th June, 2026"). |
| China-Pakistan FTA Phase II: SRO 1640(I)/2019 dated 31 Dec 2019, effective 1 Jan 2020 | `data/raw/cpfta/2020111213219376SRO1640(I)2019dated31.12.2019.pdf` (30 MB, 177 pages) | **Scan with NO text layer.** Needs page images read by a vision model, then validation. Downloaded from FBR on 2026-10-16 with the owner's approval. |
| Amendments to SRO 1640(I)/2019 | not collected | FBR's "Active SROs Import" page (https://www.fbr.gov.pk/Activesrosimport, row 26) says "Amending SROs of 1640(I)/2019". Find them (FBR SRO search, or ask the owner). HS 2017 to HS 2022 code changes may be handled there. Do not assume. |
| FBR explanation of Phase II | https://fbr.gov.pk/fbr-issues-sro-to-launch-phaseii-of-pakchina-fta-/132214 | Categories: A0 (duty eliminated from 1 Jan 2020, 3,251 lines), A07 (tapered to zero, year 2 to 7), A15 (tapered, year 4 to 15), MOP1 (duty reduced by 20% of the base rate when the protocol entered into force), MOP2 (reduced by 20% in two years), C1 (base rate), C2 (no concession). Use as a cross-check of the parse, not as a source of rates. |
| Rules of origin / certificate | https://www.commerce.gov.pk/wp-content/uploads/pdf/Annex-II_PK-CN_FTA.pdf ; FBR procedure http://o.fbr.gov.pk/newcu/pta/files/ChinaProcedures.pdf | Preferential rate needs Chinese origin proved by a Certificate of Origin (Form E). The agent must ASK, never assume. |
| Other FTAs/PTAs in force (Malaysia, Indonesia, Sri Lanka, SAFTA, Iran, Mauritius, Uzbekistan, Afghanistan) | listed on the Active SROs page | Out of scope now. Mention in docs. |

## Rules that apply (CLAUDE.md hard rules)
1. Every fact row: `valid_from`, `valid_to`, `source_file`, `page`. Never write a rate from memory; every rate is parsed from the document with its page and clause/serial.
2. Arithmetic and "which rule applied on date X" are exact code (Decimal), not the LLM.
3. Vision-model reading of a scan is labelled "AI reading"; validate (code is a line of the tariff of that year, serial continuity, one-decimal rule because OCR drops decimal points, row counts against the FBR summary above, two-reader diff where possible). Log every validator failure; do not silently fix. Produce a spot-check CSV (at least 10% of rows) for the owner. Nothing is `verified` without the owner.
4. Do not edit `data/raw`. Write to `data/processed/`. Keep `.env` out of git.
5. Commit small and often; end commits with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
6. Owner questions go to `docs/owner_questions.md` in plain language with page numbers; manual tasks are HTML task pages (see `src/ingest/review_pages.py`, `docs/PROJECT_STATE.md`).

## How the concessions work (to be confirmed from the documents, with citations)
* **Fifth Schedule Part I (plant, machinery, capital goods)**: the entry gives a concessionary customs duty rate, but Explanations I to IV in the Schedule make the rate depend on the First Schedule slab of the code (for example a "3%/5%" entry gives 3% only to goods already at 3%, and 5% to higher slabs; "0%, 3%, 10%" gives 10% to higher slabs). Entries carry conditions (not locally manufactured per the CGO list or Engineering Development Board; chief-executive certificate; sector certificates; no sale without FBR approval). Conditions the system cannot check become questions to the importer (`claimed_rules` mechanism in `compute_duty`, see `docs/tools.md`). Other Parts and Tables cover sector inputs (pharma, poultry, etc.); parse all parts, mark rows by Part/Table/S.No.
* **CPFTA Phase II**: preferential CD per tariff line and per calendar year (tapering), only for goods of Chinese origin with a Form E certificate. Rates change every 1 January, so rows are dated by calendar year; FY2025-26 spans two rates (Jul-Dec 2025 and Jan-Jun 2026). Check what happens to ACD, RD, sales tax and income tax (they are NOT reduced by the FTA unless an SRO says so; verify in the SRO text and docs/duty_formula.md).
* How a concessionary CD changes the other taxes: ACD slab tests, sales-tax base, income tax base all depend on the CD actually paid. Read `docs/duty_formula.md` and `src/tools/compute.py` before changing anything; keep the old behaviour when no concession is claimed.

## Deliverables (in order, commit after each)
1. `docs/concessions_findings.md`: structure of both documents, what each column means, edge cases (cite pages).
2. Fifth Schedule parser `src/ingest/a7_fifth.py` -> `data/processed/a7_fifth_rules.csv/json` with validators + failures report + spot-check CSV + tests. FY2025-26 vs FY2026-27 validity decided from the two consolidations; note unresolved differences.
3. CPFTA reader: render pages (`data/processed/page_images/cpfta/`), vision read to `data/processed/cpfta_vision/` (use DeepSeek flash vision if it works, else Gemini; test on 3 pages first; keep live calls and cost small and report them), parse to `data/processed/a8_cpfta_rules.csv/json`, validators, spot-check CSV, tests.
4. Store tables `fifth_schedule_rules`, `fta_rules` (+ loaders, schema doc `docs/store_schema.md`), rebuild the store, tests.
5. `compute_duty` / `get_applicable_sros`: new optional inputs `goods.origin_country` ('CN'), `goods.has_certificate_of_origin`, plus Fifth Schedule claim inputs; the agent asks the importer when a concession could apply (machinery chapters 84/85 and goods of Chinese origin), shows the bill WITH and WITHOUT the concession and says which conditions are unchecked. Never silently apply a concession. Hand-computed test cases with page citations (at least 3 per concession) in `tests/test_tools.py` style and in `data/ground_truth/duty_cases.csv`.
6. Agent: ask about origin and certificate when the goods could qualify; update `docs/agent.md`, `docs/tools.md`, `docs/duty_formula.md`, `docs/PROJECT_STATE.md`.
7. Run the full test suite; do not re-run the paid evaluation (the DeepSeek balance is small).

## Limits to state openly
* Concession eligibility depends on facts the system cannot verify (certificates, local manufacture lists). The tool shows both bills and the conditions.
* Rates from a scan are an AI reading until the owner checks the spot-check sheet.
