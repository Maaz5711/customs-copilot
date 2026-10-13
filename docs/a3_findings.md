# A3 findings: ACD, sales tax, income tax, legal notes, and what changed in this pass

Everything here was read from files in `data/raw/` (page images or text layers). Rates in this file are quoted from the A3 CSVs, never from memory.
Page numbers are the PDF page index. SRO scans were read by Claude (a vision model) and checked by code; AI readings are NOT owner verification.

## 1. What is in the store now (`python -m src.store.build`, 81 tests pass, 13 skipped = search index of the other track)

| Table | Rows | needs_review | Source files (extractor) |
|---|---|---|---|
| `tariff_headings` | 1,228 per FY (1,017 printed + 211 derived from codes) | 0 | A1 `src/ingest/tariff.py` |
| `tariff_lines` | 7,605 + 56 (FY2026-27), 7,590 (FY2025-26) | 103 | A1 |
| `sros` | 19 (6 RD/ACD + 13 sales tax / income tax / customs notifications) | 12 | `loaders.py`, `a3_instruments.csv` |
| `rd_rules` | 1,402 | 52 | A2 |
| `acd_rules` | 314 (1063: 184, 1151: 130) | 8 | `src/ingest/a3_acd.py` |
| `sales_tax_rules` | 906 | 76 | `a3_st_*`, `a3_sro_rules.py`, merged by `a3_build_rules.py` |
| `income_tax_rules` | 652 | 63 | `a3_it.py` (Twelfth Schedule, First Schedule Part II, s.148, Second Schedule) |
| `legal_notes` | 484 (chapter 355, subheading 76, section 45, general rules 8) | 6 | A4, mapped by `loaders.legal_notes_rows()` into `legal_notes_store.json` |

Lookups: `get_rule_on_date(conn, table, code, date)` (documented in `docs/store_schema.md`); hand-checked cases are in `tests/test_a3_store.py`.

## 2. A1 bug fixed: headings

Heading 11.03 is not in the tariff PDF text layer, and 02.05 / 04.09 / 05.01 ... are printed as a single code line with no heading line, so the parser
kept the previous heading for 216 codes in each year (for example 1103.1100 carried 11.02). Fix: a code's heading is its own first four digits; a missing heading
is added as a derived entry (`derived_from_code: true`, text taken from the code row for single-code headings, empty for 11.03). Result: **heading count 1,017 to 1,228
in both tariffs** (211 derived; 1,228 is the number of headings in HS 2022, which supports it). 0 codes now disagree with their heading.
Code counts unchanged (7,605 unique codes FY2026-27; 7,590 FY2025-26). Tests: `test_heading_matches_code`, `test_tariff_heading_for_1103`.
The same bug was present in FY2025-26 (same 216 rows) and is fixed the same way.

## 3. ACD (`a3_acd_rules.csv`, 314 rows)

Rules are **by tariff slab**, so the row says which slab it needs (`condition_text` starts `SLAB_EQ n` or `SLAB_GE n`) and the caller compares it to the code's tariff CD.
Validators (all passed): every listed code is in the tariff of its fiscal year; the code lists in the page text equal the lists read from the image; each exception-list
code really sits in the slab the SRO names (36/36 at 20% for 1063 (i)(a); 17/17 at 90% for (ii)(a); 14/14 specific-rate lines for (ii)(b)(i) and 1151 (iv)(a)).

| SRO | Dates | Rule (page) |
|---|---|---|
| 1151(I)/2025 | 1 Jul 2025 to 30 Jun 2026 (para 4, p.2; ends because 1063 supersedes it) | 2% slab 15%; 2% for 95 listed codes; 4% slab 20%; 6% slab 30%+ and specific-rate slabs except 14 listed codes at 2% (p.1); same for CKD vehicles at 2% (p.2); para 3 not levied (p.2) |
| 1063(I)/2026 | from 1 Jul 2026 (para 4, p.2); "in supersession of S.R.O. 1151(I)/2025" (p.1) | 2% slab 20% except 36 listed codes at 4%; 2% for 97 listed codes (p.1); 4% slab 25%+ and specific-rate slabs except 17 codes at 6%, 14 codes at 2% and CKD vehicles at 2% (p.2); para 3 not levied (p.2) |

Row groups: the slab rows and listed codes share the rule_group of the SRO; the "goods imported under SRO 655/656(I)/2006" row, the CKD vehicle rows and each para 3
not-levied clause have their own group, so they come back next to the slab row instead of hiding it. Supersession is checked in `sros`: 1151 is `superseded` by 1063.
On 30 Jun 2026 only 1151 rows are returned, on 1 Jul 2026 only 1063 rows (tests `test_acd_exception_list_code_on_boundary_dates`).
Open: CKD vehicle codes (OQ-A3-1, rows `needs_review`); SRO 1151 has no clause (iii) (OQ-A3-2). Issues file: `a3_acd_issues.csv`. Owner sheet: `spotcheck_a3_acd.csv`.
Differences between the two SROs worth knowing: 1151 para 3(iii) also excludes Part III serial 110 of the Fifth Schedule; 1063 does not.

## 4. A3 fixes from the AI second read

| Item | What was done |
|---|---|
| (a) SRO 1525(I)/2026 | The SRO prints no S.No or code rows. It only adds a proviso after Table-II of SRO 297(I)/2023: Table-II "shall not apply to locally manufactured hybrid electric vehicles with engine capacity upto 2000cc", effective at once, 13 Sep 2026 (p.1). The three Table-II rows from 13 Sep 2026 now cite SRO 297 Table-II (rate printed on SRO 370(I)/2024 p.1) and carry the carve-out in their condition; two exempt rows (87.03, 87.04) in group `ST-SRO297-T2-1525-HYBRID` cite SRO 1525 itself. It is a local-supply rule, not an import rule. |
| (b) Sugar chain | Rebuilt as dated windows, same for sales tax and income tax (customs has A and B only). **A** 8 Jul to 21 Sep 2025: SRO 1217 / 1216 / 1215 as issued, cut-off 30 Sep 2025 (accepted). **B** 22 Sep to 30 Nov 2025: SRO 1832 / 1833 / 1834 (22 Sep 2025) replace "September" by "November"; the day 30 is quoted by SRO 527/455 (accepted). **C** SRO 527 (19 Mar 2026) / 455 (5 Mar 2026) move the cut-off to 28 Feb 2026, a date before their own issue; window = issue date to 21 Apr 2026 (`needs_review`). **D** SRO 663 (22 Apr 2026) rescinds 527 and 455 "with immediate effect": from 22 Apr 2026 conditional row, "reverts to the 30 Nov 2025 cut-off" (`needs_review`). SRO 1216 date is 8 July 2025 (owner confirmed, `owner_answers.csv`). SRO 1834 is in `data/raw/` (the AI second read thought it was not): page image read, it substitutes "November" for "September" in SRO 1215 clause (iii). No customs extension after 30 Nov 2025 exists in `data/raw/`. The sugar rows name no PCT code, so a code lookup never returns them. Chain facts are in `sros` (527 and 455 `rescinded`, `valid_to` 2026-04-21, `superseded_by` 663(I)/2026). Open: OQ-A3-3. |
| (c) s.53A(1) | Wording fixed to the literal "by one percent" (not "up to 1 percentage point"); cited with its continuation (starts bottom of p.126, continues p.127). Meaning left to the owner (OQ-A3-7). |
| (d) S.No 133 | The page prints 11 "Respective headings" entries (footnotes 901-905, 907-912; 906 is a code). The sheet had 9: the two missing were "Ingredients for pesticides" with footnotes 904 and 905 on p.171. Cause: de-duplication keyed on text alone dropped repeats; now keyed on printed position too. Also fixed: all 67 rows cited p.169, the first page of the serial; rows now cite the page they are printed on (169 to 172). Serial 133 now has 69 rows. |
| (e) valid_to | Read from the text, checked by tests. Second Schedule 12B: 31 Dec 2021 ("ending on"); 12C: 30 Sep 2020; 12H: 3 months from 23 Jun 2020 (computed 22 Sep 2020); 12K: 3 months from 25 Dec 2020 (24 Mar 2021); 12M: 180 days from 14 May 2021 (9 Nov 2021); 123: 3 months from 1 Dec 2022 (28 Feb 2023); 124: "till 31 Dec 2022". All end before 1 Jul 2025, so they are history only and are not loaded (3 end dates are computed from "three months"/"180 days"). Sixth Schedule S.No 152: "till [30th June, 2026]" (p.176), loaded with `valid_to` 2026-06-30. Twelfth Schedule conditions (2)(xi) and (2)(xii): "till 30th June, 2026" (p.226), loaded with `valid_to` 2026-06-30. |
| (f) Serial label | Twelfth Schedule rows had `s_no` values such as `I-009`: parser counts, not legal serials. Column `s_no` is now empty for them and the count lives in `row_index`; the sheets show `row_index I-009`. Test `test_twelfth_schedule_rows_use_row_index_not_serial`. |
| (g) Specific duties | The store loads `cd_specific_amount` from the parsed amount and never from the digits of `cd_raw`; test compares all 54 specific rows in both years with the A1 JSON (Rs.11700/MT for 1507.9000). |

## 5. Another defect found while loading

The extractors marked many schedule rows that name goods only by words (Third, Sixth, Eighth Schedule, Twelfth Schedule exclusions) as `match_level = all`, which in the store
means "every code". A Sixth Schedule exemption for urine drainage bags would have been returned for any code. `a3_build_rules.py` now stores those 100+ rows as `unmapped`
(never matched by code, still searchable). General rules (Act s.3, s.148 text, Part II class rates, the Part III residual class) stay `all`. Test
`test_schedule_rows_without_code_cannot_match_every_code`. Rates were not touched.

## 6. Supersession and amendment chain (as stored in `sros`)

RD: 928(I)/2024 -> 1152(I)/2025 (to 30 Jun 2026) -> 1064(I)/2026; used vehicles 1898(I)/2025 (1 Oct 2025) -> 1065(I)/2026 (30 Jun 2026, start date open: OQ-A3-4).
ACD: 929(I)/2024 -> 1151(I)/2025 -> 1063(I)/2026. Sales tax: SRO 297(I)/2023 as substituted by 370(I)/2024 (Table-II) and amended by 1525(I)/2026;
sugar 1217 <- 1832 <- 527 (rescinded by 663). Income tax sugar 1216 <- 1833 <- 455 (rescinded by 663). Customs sugar 1215 <- 1834. Early Harvest (Afghanistan) 1386(I)/2025, 1 Aug 2025 to 31 Jul 2026 (out of scope for duty; rows are in `a3_customs_concessions.csv`, not loaded).
`sros` has no "amended" status: amended notifications stay `in_force`, with the amendment in `note`. 928/929(I)/2024 appear only as `supersedes` text (older than FY2025-26).

## 7. Things the tools must know (see `docs/duty_formula.md` for the formula and citations)

- Twelfth Schedule rows are `conditional` ("class: Part I/II/III"): they give the CLASS; the rate comes from the First Schedule Part II rows (1%, 2% or 3.5% commercial, 5.5% or 6% commercial).
- Mobile-phone rows are specific (Rs) by C&F value band and change on 1 Jul 2026 (tests `test_s148_class_rates_and_mobile_change`).
- ACD slab rows need the tariff CD; para 3 not-levied rows need the user's answer on the import regime.
- Legal notes are cited by reference. Their dates are an assumption written in `hs_edition`.

## 8. What still needs the owner

See `docs/owner_questions.md` (OQ-A3-1 to OQ-A3-11): CKD vehicle mapping, SRO 1151 numbering, sugar Dec 2025 to Feb 2026, SRO 1065 start date, Eighth Schedule 84(i) cell,
S.No 133 blank-code row, s.53A meaning, legal notes dates and HS 2027, the 5403/5503 footnote mismatch, FED, and the 10% spot checks (including the new ACD sheet).
Nothing is marked `verified`; that status is reserved for rows the owner confirms by hand.
