# A2 findings: SRO extraction (read by Claude from page images, validated by code)

Method: each scan page was rendered to an image and read by Claude (subagents), copying text as printed and flagging doubts.
Validators (`src/ingest/sro_validate_claude.py`) then check every row. Nothing is auto-corrected. Gemini (free tier, 20 req/day/model)
read ~10 pages of SRO 1064 before the quota ran out and serves as an independent second reader for those rows.

| SRO | Rows | S.No continuity | Accepted | For review | Second reader |
|---|---|---|---|---|---|
| 1064(I)/2026 RD, eff. 1 Jul 2026 (FY2026-27) | 687 | 1..687, no gaps | 662 | 25 | Gemini: 379 row-comparisons, 0 disagreements |
| 1152(I)/2025 RD, 1 Jul 2025 to 30 Jun 2026 (FY2025-26) | 693 | 1..693, no gaps | 669 | 24 | none (embedded OCR text only, weak) |
| 1063(I)/2026 ACD (167 listed codes) | rule text | n/a | all 167 codes exist in tariff 2026-27 | 0 flagged | - |
| 1151(I)/2025 ACD (112 listed codes) | rule text | n/a | all 112 codes exist in tariff 2025-26 | 0 flagged | - |
| 1065(I)/2026 RD 30% used vehicles (supersedes 1898) | 1 clause | n/a | - | - | - |
| 1898(I)/2025 RD 40% used vehicles (in addition to 1152) | 1 clause | n/a | - | - | - |

## Facts the readers surfaced (to verify, not yet relied on)
- 1064 and 1152 both print specific rates for S.No 113 (betel leaves, 1404.9020): 1064 reads Rs.320/Kg, 1152 reads Rs.400/Kg; and rows ~550-559 have Rs./set rates.
- Both print S.No 109/110 with the same code 1102.9000 (Maida, Semolina). This code is not in the tariff 2026-27.
- Rows with pct_code "Respective headings" (S.No 686/687 in 1064, 692/693 in 1152) need manual mapping.
- SRO 1152 pages 38-39 and 1064 pages 29-30 hold clauses (effective date, validity) that the loader must read.
- ACD SRO 1063 para 3 contains a non-levy list; 1151's clause numbering skips (iii). Both are stored as printed.
- 1065 and 1898 are in addition to 1064 / 1152 respectively; neither prints an effective-date clause. The loader needs the date from the SRO's own date line.

## Needs the owner's eyes
`data/processed/sro_1064_rd_failures.csv`, `sro_1152_rd_failures.csv` (about 25 rows each, with the page image path), then the 10% spot-check sheets
`spotcheck_sro_1064_rd.csv`, `spotcheck_sro_1152_rd.csv`.
