# Search notes (B2)

Package: `src/search/`. Build: `.venv/Scripts/python -m src.search.build` (about 10 minutes on CPU, mostly the 17.7k tariff rows). Try: `python -m src.search "plums" --date 2026-07-15 -k 5`. Tests: `pytest tests/test_search.py` (13 pass, 0 skipped, index must be built first). Indexes are written to `data/processed/search_index/` (gitignored, rebuildable).

## Design
- Four indexes: tariff (17,707 docs: headings, lines with the parent heading chain, special/compound rows, both FYs), notes (484), sro (1,401: RD rows from 1064/1152 plus vision-read clause text of 1063, 1151, 1898, 1065), rulings (35 chunks from three PDFs).
- Order: exact code lookup first (own code, ancestors, descendants), then BM25 + dense (bge-small-en-v1.5, fastembed ONNX, local) fused by RRF, then a local cross-encoder rerank (ms-marco-MiniLM-L-6) fused back with first-stage rank. No API keys, no downloads failed, so no fallback was needed.
- `as_of_date` keeps rows with valid_from <= date <= valid_to (inclusive). Every hit has id, source_file, page, valid_from, valid_to; the build refuses rows without them.
- With no index named, results are top-k per index merged round-robin, so rulings and notes always appear (even when irrelevant).

## Sample queries (as of 2026-07-15, top hit per index). Observations only, no accuracy figures.
| query | tariff top hit | remarks |
|---|---|---|
| frozen chicken | 0207.1200 (poultry, fowls, not cut, frozen) | plausible; SRO hit was frozen vegetables (S.No 63), not poultry |
| mobile phone | 8517.1419 (smartphones) | Chapter 85 note 5 (smartphone definition) found in notes |
| used car 1800cc | 8703.2321 | right heading band; the engine does not know "used" is a separate rule |
| 8703.2115 | exact match | notes gave chapter 87 notes; SRO side returned a fuzzy RD row that mentions 8703.2115 only by text |
| plums | 0809.4000 | SRO 1064 S.No 686 "Plums (allocha)" RD 20% found |
| cinematographic film | Heading 37.06 | SRO 1064 S.No 687 found; rate stored as "Rs.2400/per minute%", a rate-text quirk in the stored data, not a search bug |
| massage chair | 9019.1000 | VR 2110 is valid from 2026-10-01, so it is correctly filtered out at this date; searching the rulings index finds it |
| regulatory duty on live poultry | 0105.9900 | SRO 1064 S.No 2 (PCT 01.05) found |
| chapter note on parts of machines | Heading 90.33 | Section XVI note 2 is first in the notes index |
| curing chamber classification | 8413.9120 (wrong, a pump part) | failure: Public Notice 60/2026 (8419.3900 vs 8419.8990) is in the rulings index, valid 2026-09-01, so also filtered at this date; in the rulings index alone it ranks first |

## Problems seen
- Rulings text comes from the PDF text layer of scans: noisy (garbled words, wrong characters). Ruling numbers: only VR 2110/2026 and PN 60/2026 are legible; the valuation ruling PDF has no legible number (labelled "number illegible"). Validity dates are printed badly in the scans (read as 4 Jul 2025, 1 Oct 2026, 1 Sep 2026, the last with an assumed day). A person should check them against the page images.
- Notes carry no dates in the source; assumed valid 2025-07-01 onward (recorded in `date_basis`).
- SRO clause text is vision-model output from scans: verify against the page image.
- Round-robin merge puts an irrelevant ruling chunk (chlorinated paraffin wax) in every all-index search. The agent should search indexes separately or apply a score floor.
- Ruling dates after the as_of date hide them, which is correct behaviour but surprising in a demo.
- Natural-language queries do not understand "used" or specific engine bands as filters; the agent's Classify step must do that.
- Duplicate tariff codes (the 6 vehicle codes) are kept as separate rows (id includes page).
- Another agent was changing data in `data/processed` during the work; the index reflects the files as read at the last build and must be rebuilt if they change.
