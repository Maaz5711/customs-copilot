# Agent notes (C1): calibration, live smoke test, problems found

Design and usage: `docs/agent.md`. Observations only; no accuracy numbers (that is C2). Dates are 2026-10-14 (the day of the live test).

## 1. Search score floors (how they were chosen)
`src.search` returns a cross-encoder `rerank_score` per hit. Irrelevant hits sit at about -8 to -11 on every index; the merged search always returns a chlorinated-paraffin-wax ruling chunk because it is the least bad. I ran 9 queries per index (as of 2026-07-15, rulings as of 2026-10-14 so the 2026 rulings are valid) and looked at the scores.

| Index | Relevant hits seen | Irrelevant hits seen | Floor used |
|---|---|---|---|
| tariff | frozen chicken -0.9 to -1.9; laptop 8471.3010 -1.0 (parts -6.7 to -7.8); cotton T-shirt +5.1 to -0.1; massage chair 9019.1000 -4.7; curing chamber -6.3 to -7.8 | "how is the weather in Karachi" -10.2 to -11.1 | -9.0 |
| notes | Ch 85 note 5 (smartphone) +5.7; GRI query -1.4 to +5.6; laptop notes -7.8 and -10.1 (relevant but low) | frozen chicken -10.5 to -11.3 | -4.0, and chapter notes of the best chapters are fetched by exact code regardless of score |
| sro | T-shirt S.No 286/290 +3.4 / +1.9; "regulatory duty used vehicles" +5.8 to +7.1; CKD query -0.15 to -1.7 | frozen chicken: vegetables, eggs, fish -8.2 to -10.1 | -3.0 |
| rulings | massage chair valuation +6.8 to +7.6; curing chamber +6.4 to +7.7; chlorinated paraffin +5.5 to +7.1; "massage chair for home use" +0.7 | every other query -8.4 to -11.4 | 0.0 |

Effect in the real pipeline (`gather`, 3 to 5 s per question after warm start): T-shirt question 9 lines / 18 notes / 5 SRO / 0 rulings (the irrelevant ruling is gone); "weather" 0 lines; "massage chair for home use" as of 2026-10-14 keeps VR 2110 (+0.7); "curing chamber" keeps Public Notice 60/2026 and adds 8419.8990 (quoted in the notice, not in the hybrid top 10) to the candidate pool. The floors are a judgement from 9 queries, not a tuned value; C2 should re-check them on the evaluation set.

Hybrid ranking alone put men's shirts (6105.1000) above T-shirts (6109.1000) for "men's knitted cotton T-shirts". The classifier, with Chapter 61 notes and GRI in the prompt, chose 6109.1000 in the live run. That is the case the Classify step exists for.

## 2. Live smoke test with Gemini (free tier)
Budget set by the owner: about 5 live calls. Used: **5 successful generation calls**, plus 27 failed requests (503 overload, one 404) that cost no quota, plus 2 `ListModels` requests (not generation). The cap was enforced in code (`--max-llm-calls`).

| Run | Command (abridged) | Result |
|---|---|---|
| 0 | T-shirt question, `--models gemini-3.5-flash,gemini-3-flash-preview` | **Failed, 0 calls used.** Both models answered HTTP 503 ("high demand") twice each (4 failed requests). The agent retried once per model, then showed a clear error ("No Gemini model could answer. Details: ...") and "Nothing was computed". |
| a | same question, full default chain | **Worked.** 12 failed requests (503 on gemini-3.5-flash, 3-flash-preview, 3.6-flash, 3.7-flash at that moment), then Understand and Classify answered on `gemini-3-flash-preview`, Verify on `gemini-3.8-flash` (3 live calls). Path: understand > search > classify > calculate > verify > respond. Result: 6109.1000, total payable PKR 1,668,450.00, which equals my hand calculation (CD 500,000 + RD 200,000 + ACD 50,000 + ST 585,000 + VAT 97,500 + IT 235,950). The date, value (PKR 2,500,000), quantity (10,000 pieces), "registered" and "commercial importer" were all read correctly from one sentence, each backed by a quote. The auditor passed it with a useful warning: it could not check Chapter 61 note 5 (no drawstring or ribbed waistband for heading 61.09) from the description. |
| b | "I want to import a car", `--date 2026-07-15`, `--max-llm-calls 2` | 11 failed requests (503 on 5 models; `gemini-2.5-flash` answered 404 "no longer available to new users"). Understand and Classify answered on `gemini-3.5-flash-lite` (2 live calls). The classifier returned **no candidate, `ambiguous: true` and two questions** (engine type and cylinder capacity; snow vehicle or golf car). That is the right behaviour, but **my router ignored the questions** (it checked "no valid candidate" first), retried the search and then hit the call cap. Fixed (section 3, item 5). After the fix the same cached answers now give the two questions at zero cost. |

Replays: because every answer is cached on disk, `--max-llm-calls 0` replayed runs a and b with 0 live calls (3 and 2 cache hits). A cache miss fails before sending, so a replay cannot spend quota.

Observed per call (Gemini `usageMetadata`): Understand about 800 prompt + 224 answer + 1,144 thinking tokens; Classify 3,546 + 167 + 812; Verify 2,944 + 93 + 287. The thinking tokens dominate; calls took from seconds to well over a minute when models were overloaded.
Models seen working today: gemini-3-flash-preview (2 calls), gemini-3.8-flash (1), gemini-3.5-flash-lite (2). Each of these answered 503 (overloaded) at some point during the test: gemini-3.5-flash, 3-flash-preview, 3.6-flash, 3.7-flash, 3.8-flash (3-flash-preview and 3.8-flash did answer in run a, 3.8-flash was overloaded in run b). Retired for new keys: gemini-2.5-flash (and therefore the 2.5 family was removed from the default chain). Not called: gemini-3.1-flash-lite. No 429 was seen, so the quota book and the daily/per-minute handling were tested only with a fake HTTP layer (`tests/test_agent_llm.py`, using a realistic 429 body), not live. Free quota used by this smoke test: 2, 1 and 2 requests on those three models (other work on the same key, if any, is not counted here).

JSON mode (`responseMimeType: application/json`) with `systemInstruction` and temperature 0 was accepted by all three models; all five answers parsed on the first try; no schema change was needed.

## 3. Problems found while building (all fixed unless marked open)
1. The grounding check flagged "p.27": the sales-tax clause text printed by the tool contains page references inside a string ("PDF pp. 28 and 25; FY2025-26 file p.27") that the page index (built from `page` fields) did not know. Without the check this would have been an unexplained failure; the corpus now reads page references inside text.
2. A model confidence printed as "0.92" looked like a money amount to the answer check and to a reader. It is now "92 out of 100", so every two-decimal number in an answer is a PKR amount from the tool.
3. `compute_duty` reports missing inputs stage by stage (for a car the income-tax question only appears after the vehicle questions), which forced two rounds of questions. Calculate now discovers all stages in one round with stand-in answers whose numbers are discarded (`discover_missing`).
4. Live: 503 overload made every LLM step retry the same dead models first (about 10 failed requests per step). Models that just failed are now tried last for 90 s. `gemini-2.5-flash` is retired for this key; removed from the default chain.
5. Live: the classifier asks questions when it has no candidate yet; questions now take priority over a retry (`test_no_candidate_but_questions_asks_instead_of_retrying`).
6. Live-environment: stdin looked like a terminal but was closed, so `input()` raised EOF and the CLI crashed with a traceback. EOF now falls back to "not a terminal, continue with --answer" (exit code 2).
7. Parsing: "1800cc" was read as 180 (a lookahead bug); a raw 8-digit amount such as 10000000 looks like a PCT code. Fixed; such numbers are only accepted as codes if the tariff has them (`test_a_raw_eight_digit_amount_is_not_mistaken_for_a_code`).
8. `load_dotenv()` without a path crashes when a script is run from stdin; the agent loads `.env` by explicit path.
9. The search index labelled the 2006 valuation ruling "number illegible"; updated from the owner's reading of the scans (`src/search/docs.py`, rulings index rebuilt, 10 s). No other search code was touched.

Open (not fixed, for C2/C3 or the owner):
* **Large headings.** 8703 has 103 lines; only about 10 are retrieved for "a car", mostly hybrid vehicles. After the user's answers join the query it gets better, but there is no sub-heading-first retrieval. A correct line that is not retrieved cannot be chosen, and the agent ends in "not sure". Worth testing on vehicles in C2.
* **Confidence is the model's own number** (the live classifier said 1.0 for the T-shirt). Thresholds 0.6 and 0.5 are placeholders.
* **Quota.** About 20 requests per model per day and heavy 503 overload make a free-tier demo unreliable; the cache makes repeated demo questions free. A paid key or a second provider (the interface allows it) would be needed for real use.
* **Auditor independence.** Verify is a separate call with its own prompt, but it may run on the same model family as Classify.
* The Understand step trusts the model to copy quotes; code checks that the quote is in the message, not that it was understood correctly (for example "value" vs "freight").
* FED is still not included (owner: include only if source data is good enough); every answer says so.

## 4. Tests
`tests/test_agent_llm.py` 26 (cache, 429 daily and per-minute, fallback, 503, bad key, budget, key never leaks, Pacific reset time, FakeLLM), `tests/test_agent_parsing.py` 45, `tests/test_agent.py` 46 (graph, real exact tools over a fresh store, stub retrieval with real codes; one test uses the real search index), `tests/test_agent_cli.py` 10 (CLI, MCP toolbox identical to in-process tools). Run: `.venv/Scripts/python -m pytest tests/test_agent*.py`.
Required cases: clarify interrupt/resume round trip; not-sure mode after 2 failed verifications; invalid LLM code rejected; answer numbers equal the tool output; missing_inputs trigger Clarify instead of a number; unsupported date refused. All covered (see the table in `docs/agent.md`).
