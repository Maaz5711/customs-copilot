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

## Owner answers applied (owner_tasks-results.csv; tests in tests/test_owner_answers.py)
Source labels: "owner" = Maaz read the page; "Claude" = Claude read the page image. Nothing here is marked `verified` unless the owner said so.
- **SRO 1065(I)/2026** (owner): date line 30 June 2026, no start or end wording printed. Stored `valid_from` 2026-06-30, open end, `needs_review`, note "no effective-date clause printed; date line used". Para 1 says "in supersession of ... S.R.O. 1898(I)/2025 dated 1st October, 2025" and para 2 makes it "in addition to" 1064 (Claude, page image). Oddity kept visible: 1064 starts 1 Jul 2026, so on 30 Jun 2026 only 1152 plus 1065 apply.
- **SRO 1898(I)/2025** (owner): date line 1 October 2025, no start or end wording. `valid_from` 2025-10-01, `valid_to` 2026-06-29 (day before 1065, because 1065 supersedes it), `needs_review`.
- **Used-vehicle RD rules loaded** into `rd_rules`: 1898 = 40%, 1065 = 30%, one heading row each for 8702, 8703, 8704, 8711 (8 rows), own `rule_group` (they add to 1064/1152, never replace them), `needs_review`. The condition (commercial import of used vehicles under clause (xvi) of S.No.10, Appendix-C, Import Policy Order 2022) cannot be tested from the HS code, so the caller must ask. Rates come from the vision readings in `data/processed/sro_claude/*/p001.json`.
- **SRO 1064**: effective 1 Jul 2026, no end date printed (owner): `valid_to` stays 9999-12-31. **SRO 1152**: effective 1 Jul 2025, end 30 Jun 2026 as printed (owner): the store has exactly that.
- **"Respective headings" rows** (owner read the descriptions; Claude checked the rate cells on page images 1064 p.29 and 1152 p.38): S.No 686 (20.0%) and 692 (28%) = Plums (allocha) mapped to 0813.4050 (the only such line in both tariffs, checked by test). S.No 687 (Rs.2400 per minute) and 693 (Rs.3000 per minute) = Cinematographic film mapped to heading 37.06 (`heading4`). Rows are `accepted` with note "description read by owner, code mapped by description match to the tariff". The tariff itself prices 3706.1000/3706.9000 at Rs. 5 per meter, so "per minute" in the RD SROs is a different unit; `compute_duty` must ask for film length or running time.
- **Income tax Twelfth Schedule, p.827**: the table prints `[5403.2010` (typo); footnote 1 says PCT 5503.2010 was inserted through S.R.O. 1240(I)/2020 dated 20.11.2020; the row sits between 55.03 and 55.04; 5503.2010 is in the tariff. Stored as 5503.2010 (`src/ingest/a3_build_rules.py`, `CODE_CORRECTIONS`); the printed value is kept in the issues note and in `a3_it_twelfth_schedule.csv`. Footnote 2 (72.04 inserted by Finance Act 2022): the row is already 72.04. A scan of all `a3_*` footnotes found no other footnote-corrected code (the 3204.17xx and Sixth Schedule hits are footnotes that list several codes at once, not corrections).
