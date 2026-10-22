# Catalogue test set and retrieval-only evaluation (2026-10-22)

## Why this exists
The 79 real cases are mostly disputes and the 60 synthetic ones were hand-picked. Real office cases are not available yet, so a **catalogue set** walks the whole tariff by category: one everyday description per randomly sampled tariff line. One number then says how the agent does on ordinary goods in every chapter, not only on contested ones.

## How it was made (reproducible, no LLM in the sampling)
1. `python -m src.eval.catalog_sample --total 420` draws real 8-digit lines of the FY2026-27 tariff, balanced by chapter (quota proportional to the square root of the chapter's size, at least 2, never two from one 6-digit sub-heading, fixed seed). 421 candidates in 96 chapters.
2. Claude wrote what an importer or clearing agent would type for each line (`data/ground_truth/catalog_descriptions.tsv`). Lines that only say "Other > Other" were skipped because their meaning depends on sibling lines, and a few were skipped because no natural product exists (for example electrical energy). 279 lines were kept, in 93 chapters.
3. `python -m src.eval.catalog_build` checks every code against the store and writes `data/ground_truth/cases_catalog.csv` with the tariff wording as `basis`, the tariff page, a `label_confidence` (H = the writer is sure, M = a sibling line might also fit) and a split.
4. **Dev / test split by 4-digit heading (hash)**: 193 dev cases, 86 test cases, and no heading is in both. Tune on dev. Report test once per version and never tune on it.

## Limits (state them whenever a number is quoted)
* Labels are **AI-written and unverified** (`verified=false`). 88 of 279 labels are marked M. A person who knows the tariff should check a sample.
* The writer knew the tariff wording, so descriptions are cleaner than real importer text (the real Goods Declaration lines are terser and noisier). Expect lower scores on real input.
* A uniform sample of tariff lines contains many technical and chemical lines. It is a coverage benchmark, not a picture of what Pakistani importers import most.
* Intervals are 95% Wilson. With n=86 an interval is about plus or minus 6 to 8 points.

## Retrieval-only result (no LLM, no cost): does the right line reach the shortlist?
`python -m src.eval.retrieval_eval --split dev|test`. The shortlist is what the Classify step sees (about 11 to 13 lines). If the line is not in it, the agent cannot choose it.

| Version | Split | Exact line offered | Right 4-digit heading offered | Line in the first 10 |
|---|---|---|---|---|
| base (hybrid search, no rulings from FBR valuation list) | dev (193) | 174 (90%, CI 85-94) | 175 (91%) | 170 (88%) |
| base | test (86) | 78 (91%, CI 83-95) | 80 (93%) | 76 (88%) |
| + 349 FBR valuation rulings in the rulings index | dev | 174 (90%) | 175 (91%) | 170 (88%) |
| + 349 FBR valuation rulings | test | 78 (91%) | 80 (93%) | 76 (88%) |

Reading: adding the valuation rulings did **not** change shortlist recall. 31 of the 279 cases (11%) have their code in a ruling, and for those the line was already in the shortlist. Their possible value is in how the model picks, which needs LLM runs. The misses are whole-heading misses (butter, canned mackerel, pectin, sausage casings): the cases the autonomous research step (`src/agent/explore.py`) is meant to rescue.

## FBR valuation rulings (new source)
* `python -m src.ingest.fbr_vr_download` reads FBR's public Customs Valuation list (one read-only call, `POST /Home/LoadVALUATIONs`, department Customs: 939 entries) and saves the originals of the rulings dated 2022 or later: 383 PDFs, 756 MB, 10 links were dead (HTTP 404). One request at a time, 1.5 s apart. FBR publishes no robots.txt; its terms allow copying single pages for sharing, so the derived data stays in the private repo until FBR answers the permission email.
* `python -m src.ingest.vr_parse` turns each ruling into one search document: the goods name from the listing title and the PCT codes the ruling prints "for illustrative purposes". 349 rulings, 1,170 codes. A code is kept only if it exists in the tariff; 41 were repaired from scan look-alikes (`15r3.r900` to `1513.1900`); 33 rulings showed no valid code and 1 had no text layer. Nothing is fixed silently: `data/processed/vr/parse_report.json`.
* The classifier is told that a valuation ruling is supporting evidence only, never proof.

## Other websites (TaxFlow and similar)
No site called TaxFlow turned up for Pakistan. The Pakistani lookup sites found (LawPoint Classifactor, TradeInt, similar) are keyword lookups over the same FBR tariff the project already holds, so they add no new classification knowledge, and bulk-copying a commercial site's compiled database raises terms-of-use and copyright problems that would hurt a pitch to FBR. They are not used as a data source. FBR's own rulings and public notices are.

## LLM results (DeepSeek flash, 2026-10-22; full agent with hints and Classify thinking on)
Dev sample = 60 random dev cases (seed 11, the same cases for every row). Test = all 86 held-out cases, run **once** for this version and never tuned on. Intervals are 95% Wilson. Labels are AI-written and unverified (see Limits above).

| System | Cases | Exact 8-digit line, first choice | Right 6-digit | Right 4-digit heading | Right line in top 5 |
|---|---|---|---|---|---|
| Plain LLM (no search) | dev 60 | 26 (43%, CI 32-56) | 36 (60%) | 50 (83%) | 29 (48%) |
| LLM + search (no agent graph) | dev 60 | 47 (78%, CI 66-87) | 49 (82%) | 51 (85%) | 50 (83%) |
| **Full agent** | dev 60 | **57 (95%, CI 86-98)** | 58 (97%) | 58 (97%) | 58 (97%) |
| Full agent, research step switched off | dev 60 | 57 (95%) | 58 (97%) | 58 (97%) | 58 (97%) |
| **Full agent, held-out test** | test 86 | **78 (91%, CI 83-95)** | 79 (92%) | 81 (94%) | 82 (95%) |

Cost: about 22 US cents in all for these runs (dev 60 and its baselines, the ablation, test 86), roughly 0.13 cents per question for the full agent.

Reading it honestly:
* The agent beats the plain model (43%) and model-plus-search (78%) on the same cases. The gap between 78% and 95% is the graph: grounded candidate checks, notes, the separate verification and the retry loop.
* **The autonomous research step made no difference on this set**: the first choice was identical in all 60 cases with it on and off (it answered "done after 0 actions" almost every time, because the first retrieval already held the line). It costs about one extra model call per question. Its value, if any, is on harder and noisier goods, which this set does not test. Keep it, but do not claim it improved accuracy.
* These descriptions are clean, written by an AI that knew the tariff wording. Real importer text is terser and noisier: on real cleared Goods Declaration lines the same agent scored 43.6% exact against the declared codes (which are themselves inconsistent), and 54% on the real-ruling set. Expect real use to land between the two.
* The 8 test misses: 3 asked or hedged with the right line second (C116, C118, C218), 1 returned nothing (C269, table-tennis equipment), and 4 chose a wrong line in the right area (for example 34051010 instead of 34051020, a sibling line). The first test run before any fix is the number above; nothing was tuned on test.
