# Customs Copilot (Pakistan) — Design Spec v1

Owner: Maaz Ahmed. Status: DRAFT for approval. Date: 2026-10-08.

**Scope decision (owner, 2026-10-08):** v1 is the complete version: the full duty stack including sales tax and income tax, built as fast as quality allows. History covers at most the last 2 years (FY2025-26 and FY2026-27). No calendar timeline; the build order below is by dependency only.

## 1. Problem

Importers and clearing agents in Pakistan must choose an 8-digit PCT tariff code and work out the full duty bill. Today they rely on experience, WhatsApp groups and PDFs. The rules are spread across the Customs Tariff, legal notes, SROs that replace each other every year, and rulings. The tariff PDF shows only one duty (customs duty, CD). The real bill also needs regulatory duty (RD), additional customs duty (ACD), sales tax (including any further or extra tax), and income tax (advance tax collected at import). Which rule applies depends on the date and, for income tax, on the importer's status.

## 2. What we build

An AI agent. A user describes a product (and optionally a date). The agent asks for missing details, finds the candidate PCT codes, checks them against the legal notes, calculates the duty with exact tools for the given date, verifies its own answer, and replies with citations. If it is not confident, it says so and shows the top 3 candidates (decision made: "Option A").

**Not goals for v1:** valuation disputes, used-car special valuation rules, FTA/PTA preferential rates, other countries, filing declarations in WeBOC, legal advice.

## 3. Users and use

- Primary: importers, small traders, clearing-agent staff.
- Portfolio demo user: a recruiter or professor who types a product and sees the answer, the sources and the accuracy numbers.

## 4. Features (v1)

1. Product description to top-3 PCT codes with confidence.
2. Clarifying questions (new or used, material, engine size, use, etc.) before answering.
3. Full duty stack calculator for a chosen "as of" date: CD, RD, ACD, sales tax (standard rate, reduced rates, exemptions, further/extra tax for unregistered importers) and income tax (advance tax at import, by importer status). The user supplies or the agent asks for: assessable value, importer type (registered/filer status), date. Output is an itemised bill with the rule and source behind every line.
4. Citations on every claim: tariff page, SRO number and clause, legal note, ruling.
5. "Not sure" mode: low confidence after retries returns top 3 candidates plus a "check with customs" message.
6. Date picker: which rule applied on date X (SRO supersession history).
7. Evaluation dashboard: accuracy numbers and ablation table.
8. FastAPI endpoint and a simple web page.

## 5. Architecture

### 5.1 Job 1 — offline ingestion (not RAG)

Goal: turn PDFs into a dated legal store. Every fact has `valid_from`, `valid_to`, `source_file`, `page`.

- Tariff PDF (text layer is clean): parse with pdfplumber coordinates. Known results from a trial parse: 7,606 eight-digit code lines, 7,605 unique, 1,017 four-digit headings, 7,553 rows end in a plain CD value, 53 rows have specific or compound duties that plain text extraction scrambles, 6 vehicle codes appear twice (8703.2115, 8703.2193, 8703.3225, 8704.3130, 8704.3150, 8704.3190).
- SRO PDFs (scans, e.g. 1063(I)/2026 ACD, 1064(I)/2026 RD): render pages as images, read with a vision model, then run validators. A fresh Tesseract run was worse than the embedded OCR, so vision plus validators is the plan.
- Validators: code exists in the tariff, S.No continuity, rate in allowed range, one-decimal rule (OCR drops the decimal point, "40" can mean 4.0), row counts, two-tool diff, at least 10% manual spot check by the owner.
- SRO supersession: 1064(I)/2026 (RD, effective 1 Jul 2026) supersedes 1152(I)/2025; 1063(I)/2026 (ACD) supersedes 1151(I)/2025. Store these as chains.
- Legal notes: Pakistan's own General Rules for Interpretation, Section Notes and Chapter Notes come from the FBR FY2022-23 tariff PDF (HS 2022, same nomenclature as 2026-27). To verify: download it, confirm completeness, check for later amendments. WCO Explanatory Notes are paid, so cite by reference only and do not copy.
- Other inputs on hand: Fifth Schedule 2026-27, Public Notice 60/2026, Valuation Ruling 2110.
- **Sales tax sources (NOT yet in hand, must be obtained):** the Sales Tax Act 1990 schedules as amended by Finance Act 2026 (Third, Sixth, Eighth schedules: retail-price items, exemptions, reduced rates) plus the SROs that currently apply to imports, and the rules for further tax / extra tax on unregistered importers.
- **Income tax sources (NOT yet in hand, must be obtained):** the Income Tax Ordinance 2001 provision on advance tax at import (section 148) and the matching rates table in the First Schedule as amended by Finance Act 2026, which sets rates by category of goods and importer status.
- Do not write any rate from memory. Every rate in the database must come from a parsed source document and carry its page and clause.
- History scope: FY2026-27 (primary) and FY2025-26 (previous year: Tariff 2025-26 PDF and its SRO set, including the superseded 1151(I)/2025 and 1152(I)/2025). Nothing older.

### 5.2 Job 2 — question-time agent (LangGraph)

Nodes: Understand, Clarify, Search, Classify, Calculate Duty, Verify, Respond. Diagram: https://claude.ai/artifact/EM9xgvZYa5d9FPXk9zQ41i

- Understand: LLM extracts product facts into state.
- Clarify: `interrupt()` pauses the graph to ask the user; `Command(resume=...)` continues. Loop back to Understand.
- Search (RAG): hybrid BM25 + dense embeddings with reranking over four stores: tariff text, legal notes, SRO clauses, rulings.
- Classify: top 3 PCT codes, each checked against chapter notes, with a confidence score.
- Calculate Duty (MCP tools, exact): `lookup_code`, `get_applicable_sros(code, date)`, `get_sales_tax_rule(code, date, importer)`, `get_income_tax_rule(code, date, importer_status)`, `compute_duty(code, value, date, importer)`. The calculation order (what each tax is charged on, for example whether sales tax is on value plus duties) must follow the source documents and be written down in `docs/duty_formula.md` with citations before it is coded.
- Verify: separate LLM check that the code fits the description, the notes agree and the arithmetic holds. Below threshold: retry Search with a refined query, maximum 2 retries.
- Respond: answer, duty breakdown, citations, confidence. If still not confident: "I'm not sure" plus the top 3 candidates and a "check with customs" note.

State carries the conversation. Use a checkpointer for pause and resume, and a long-term store for facts the user confirms.

### 5.3 Stack (proposed, free where possible)

Python 3.11, pdfplumber, a vision model for scans (Gemini free tier to start, one paid model as cross-check), PaddleOCR or Docling on CPU as second opinion, SQLite or Postgres for the dated store, Qdrant or pgvector for vectors, BM25 via rank_bm25 or Postgres full text, an open reranker, LangGraph, an MCP server for the tools, FastAPI, a simple front end, pytest, GitHub Actions.

## 6. Evaluation

- Ground truth: about 85 real classification rulings (one Karachi office) plus about 150 synthetic cases, with the owner reviewing a sample.
- Metrics: top-1 and top-5 at 4, 6 and 8 digits; citation correctness; duty-calculation match against hand-computed answers; refusal quality (does it say "not sure" when it should).
- Ablation: plain LLM vs LLM + RAG vs full graph with verifier.
- Baseline: run Danial's TariffAI (MIT licence, read-only reference, do not copy code) on the same cases at 6 digits.
- Report numbers with sample sizes and confidence intervals. State the small test-set limit openly.

## 7. Build order (by dependency, no time estimates)

Work at full pace. Run independent tracks in parallel (for example with subagents). Do not wait for calendar gates; only wait for things that truly block (inputs Maaz must supply, his spot checks).

**Track A — data (can all start at once)**
- A1 Tariff 2026-27 and 2025-26: parse, fix 53 compound rows, explain 6 duplicates. Done when counts reproduce and tests pass.
- A2 Customs SROs (RD and ACD, both years, with supersession chains): vision extraction plus validators. Done when validators pass and the 10% spot check passes.
- A3 Sales tax rules (schedules and import SROs) and income tax rules (section 148 table): extract with the same validators. Done when every rate has a page and clause.
- A4 Legal notes from the FBR FY2022-23 tariff PDF. Done when General Rules, Section Notes and Chapter Notes are all indexed with page refs.
- A5 Fifth Schedule, Public Notice 60/2026, VR 2110: extract what affects duty.

**Track B — engine (starts once A1 has loaded)**
- B1 Dated store schema and loaders.
- B2 Hybrid search, rerank, and the four indexes.
- B3 Tools and `docs/duty_formula.md`, then `compute_duty`. Done when hand-computed cases match exactly.

**Track C — agent and proof (starts once B2 and B3 work)**
- C1 LangGraph agent with Clarify, Verify, retry and "not sure" mode.
- C2 Ground truth, metrics, ablation and TariffAI baseline.
- C3 FastAPI, simple UI, README with results, short write-up, demo video.

Finish when every success criterion in section 9 is met.

## 8. Risks

1. SRO 1063 code lists are garbled on the scan; extraction may need heavy manual checking.
1a. Sales tax and income tax are new scope and the source documents are not yet collected. This is now the largest data risk: the rules depend on importer status and category, may sit in several SROs, and the calculation order must be proven from the documents before coding.
2. Legal-notes completeness and any post-2022 amendments are unverified until the FY2022-23 PDF is downloaded and read.
3. Evidence of customer pain comes from blogs only; talk to 5 to 10 clearing agents before any monetisation.
4. FBR terms for automated reuse are unclear; keep the project non-commercial until checked.
5. Ground truth is small and from one office; report this limit.
6. A wrong duty can cost a user money; always show sources and the "verify with customs" notice.
7. Research findings so far come mostly from search summaries and need direct checking.

## 9. Success criteria

- A cold reader can run the demo, ask a question and see answer, duty and sources.
- Numbers for the three-way ablation are published in the README.
- Every duty figure traces to a page or SRO clause.
- The agent refuses (top-3 plus warning) on cases it gets wrong more often than it answers wrongly with confidence. Measure this.

## 10. Open items for the owner

- Download the FBR FY2022-23 tariff PDF and add it to `data/raw/`.
- Get a Gemini API key (free tier) to start.
- Download the Tariff 2025-26 PDF and the 2025-26 SRO set (including 1151(I)/2025 and 1152(I)/2025).
- Download the sales tax and income tax source documents listed in section 5.1 (Finance Act 2026 schedules and the SROs applying to imports). I can write a prompt for Claude in Chrome to collect them from the FBR site.
- Decide the repository name and licence.
