# Dated legal store: schema, loader contract, resolution order

Code: `src/store/` (`schema.py` DDL, `loaders.py`, `resolve.py`, `build.py`). Tests: `tests/test_store.py`.
Build: `.venv/Scripts/python -m src.store.build` creates `data/processed/legal_store.sqlite` (gitignored via `*.sqlite`) from the parsed files in `data/processed/`.
The raw PDFs are never touched.

## Hard rule, enforced by the database
Every fact table has `valid_from`, `valid_to`, `source_file`, `page`, all `NOT NULL`, with CHECKs:
valid dates in `YYYY-MM-DD` form (`date(x) = x`), `valid_to >= valid_from`, `source_file` not blank, `page` an integer >= 1.
Open-ended validity is the sentinel `9999-12-31`, never NULL. Both dates are inclusive. Tests insert rows without each field (and with bad values) and require `IntegrityError`.
Multi-branch CHECKs are wrapped in `COALESCE(..., 0)` because SQLite lets a NULL check result pass.

Shared columns: `status` in `accepted | needs_review | verified`.
`needs_review` = failed an upstream validator or is an unconfirmed inference. It is loaded, not dropped and not fixed. `verified` is reserved for rows the owner confirmed by hand.

## Tables
| Table | Key | Loaded now |
|---|---|---|
| `tariff_headings` | fy, heading | 1,228 per FY (1,017 printed + 211 derived from code, see A1 fix) |
| `tariff_lines` | fy, code, page | FY2026-27: 7,605 eight-digit + 56 Chapter 99 fragments; FY2025-26: 7,590 |
| `sros` | sro_number | 19 (6 RD/ACD SROs + 13 sales tax / income tax / customs notifications from `a3_instruments.csv`, incl. rescinded 455/527) |
| `rd_rules` | one row per (SRO, S.No, code) | 1064: 698 rows from 687 S.Nos; 1152: 704 rows from 693 S.Nos |
| `acd_rules` | one row per code or slab/regime clause | 314 (1063: 184, 1151: 130) |
| `sales_tax_rules`, `income_tax_rules` | see contract | 906 / 652 |
| `fed_rules` | one row per (serial, sub-clause, code) | 174 (FY2025-26: 80, FY2026-27: 94), A6 |
| `legal_notes` | note_kind, scope, note_no, valid_from | 484 (dates assumed, label in `hs_edition`) |

`tariff_lines`: `code` as printed, `code_norm` digits only, `level` 8 or 4 (Chapter 99), `cd_kind` `plain | specific | compound`, `cd_rate` (percent) or `cd_specific_amount` + `cd_specific_unit`, `cd_raw`, `rotated`, `note`.
`rd_rules`: `sro_number`, `s_no`, `raw_pct_code`, `description`, `issues`, hierarchical columns, rate columns.

### Hierarchical columns (rd, acd, sales tax, income tax)
- `code_norm`: digits only. `match_level` must agree with its length: `code8` (8), `code6` (6), `heading4` (4), `chapter2` (2), `all` (empty string, matches every code), `unmapped` (NULL: the source row names no code, for example "Respective Headings").
- `except_codes`: JSON array of digit strings (8-digit codes or 4-digit headings) carved out of this row.
- `unparsed_except_text`: 1 when the description has an except/excluding/other-than phrase that names no code (for example "other than swimwear"). The store cannot evaluate it; the row is flagged, not guessed.
- `rule_group`: rows that substitute for each other share a group (most specific wins inside it). Different groups are cumulative. For RD and ACD the group is the SRO number, so an "in addition" SRO (1898, 1065) never overrides 1064/1152.

### Rate columns
`rate_kind` `percent | specific | conditional | exempt`. `percent` needs `rate_pct` in 0..100. `specific` needs amount + unit (rupees per unit). `conditional` keeps the printed text only in `rate_raw` (for example "10% (5 to 10 years old) and 20% (Above 10 years old)") and is always `needs_review`. `rate_raw` always holds the rate exactly as the reader produced it.

## Loader contract for A3 (sales tax, income tax, ACD, legal notes)
`load_table_file(conn, table, path)` in `src/store/loaders.py` takes a CSV (header row) or a JSON list of objects (or `{"rows": [...]}`). All-or-nothing: any constraint violation rolls the whole file back. Unknown columns or missing required columns raise `ValueError`. Empty CSV cells become NULL, so an empty `page` fails.

Always required (all four): `valid_from, valid_to, source_file, page`.

| Table | Required | Optional |
|---|---|---|
| `acd_rules` | sro_number, clause, code_norm, match_level, rule_group, rate_kind | slab_pct, condition_text, except_codes, unparsed_except_text, rate_pct, rate_specific_amount, rate_specific_unit, rate_raw, status |
| `sales_tax_rules` | instrument, clause, tax_kind (`sales_tax|further_tax|extra_tax|withholding`), code_norm, match_level, rule_group, rate_kind | importer_status (`any|registered|unregistered`, default any), charged_on, condition_text, + the rate/except columns above, status |
| `income_tax_rules` | instrument, clause, code_norm, match_level, rule_group, rate_kind | importer_status (free text as printed, default `any`), importer_category, charged_on, condition_text, + rate/except columns, status |
| `legal_notes` | note_kind (`general_rule|section_note|chapter_note|subheading_note`), scope, note_no, text | hs_edition (default HS2022), status |

Rules for producers: `code_norm` is digits only (`"01012100"`, not `"0101.2100"`); for rules that apply to all goods use `match_level=all` with an empty `code_norm`; `except_codes` is a JSON array string such as `["01051100","0304"]`; `clause` cites the section/serial/clause; `charged_on` must cite where the base is defined (see `docs/duty_formula.md`); a rate read by OCR or a vision model that failed a validator gets `status=needs_review`. Rates come only from source documents, never from memory.

## SRO dates
`sros.valid_from/valid_to` are the dates the notification is in force, read from the SRO's own clauses:
- 1064(I)/2026: effect from 1 Jul 2026 (clause 6, page 30). No end date printed: `9999-12-31`.
- 1152(I)/2025: 1 Jul 2025 to 30 Jun 2026 (clause 6, page 39).
- 1063(I)/2026, 1151(I)/2025 (ACD): effect from 1 Jul 2026 / 1 Jul 2025 (page 2). 1151 end date is set to 30 Jun 2026 because 1063 supersedes it.
- 1898(I)/2025 and 1065(I)/2026 print no effective-date clause. `validity_basis='date_line'`, `status='needs_review'`: start = the SRO date line (1 Oct 2025; 30 Jun 2026). 1898 ends 29 Jun 2026 so the two do not overlap.
`superseded_by` and `sro_status` are derived from the `supersedes` chain. 928(I)/2024 and 929(I)/2024 appear only as `supersedes` text (out of scope: older than FY2025-26).

## Resolution order (`get_rule_on_date`)
`get_rule_on_date(conn, table, key, date, statuses=None) -> list[dict]`, pure SQL and Python, no LLM. Dates are inclusive on both ends; `date` is `datetime.date` or `YYYY-MM-DD` (impossible dates raise `ValueError`).
- `tariff_lines`: key = code (dotted or not). `tariff_headings`: heading. `sros`: SRO number (spacing/`(I)` variants normalised). `legal_notes`: scope.
- Rule tables: key = full 8-digit code. Steps:
  1. Rows valid on the date.
  2. Rows whose `code_norm` is a prefix of the 8-digit target (exact code, 6-digit, heading, chapter, `all`).
  3. Drop any row whose `except_codes` has a token that is a prefix of the target. The row does not apply to that code.
  4. Within each `rule_group`, keep only the longest prefix (exact code beats heading beats chapter beats `all`). If an excepted code has no row of its own, the group yields nothing for it (no rate levied by that SRO).
  5. Rows tied at the same specificity are all returned (for example the C&F-value tiers of 8517.1390); the caller must choose by condition.
- Each returned rule row has `_resolution` (`exact` or `prefix:<level>`) and `_flags`: `matched_by_prefix_not_exact_code`, `description_has_unparsed_exception_text`, `row_needs_review`, `rate_is_conditional_choose_manually`, `multiple_rows_same_specificity_choose_by_condition`. `statuses=['accepted','verified']` hides `needs_review` rows.

`except` tokens are read from the description text after the first `except / excepting / excluding / other than`: every 8-digit code and `NN.NN` heading printed after it.

## Uncertainties (not resolved, flagged in the data)
1. The except parser is text-based. A code listed after "except" is assumed to be an exclusion; phrases like "other than swimwear" are only flagged (`unparsed_except_text`: 14 rows in 1064, 17 in 1152). Spot-check some of the 73 / 65 rows with parsed except tokens.
2. "Respective Headings" rows are now mapped (owner read the descriptions): 686/692 Plums (allocha) -> 0813.4050, 687/693 Cinematographic film -> heading 3706; `accepted`.
3. 1102.9000 appears under S.No 109 and 110 in both RD SROs (Maida, Semolina) and is not in the 2026-27 tariff. Both rows are kept; lookups return both, flagged.
4. 1152 S.No 511 (8433.5100) has an age-conditional rate; stored as `conditional`.
5. Tariff specific duties from rotated cells (48 rows in each year) are `needs_review`: the scale (Rs.10550/MT) is reassembled from wrapped text. Chapter 99 entries with a blank or odd duty cell ("", "0 0"; 7 rows) are stored as `compound` with the printed text and `needs_review`.
6. Chapter 99 entries span pages; the parser produced 56 fragments for 42 codes, kept as one row per page (`UNIQUE(fy, code, page)`).
7. The 6 "duplicate" vehicle codes are not duplicates (A1 finding, re-checked by a test): one table row each; the other hits were mentions in notes.
8. 1065(I)/2026 has no effective-date wording (owner read it): date line 30 Jun 2026 is used, `needs_review`. It is "in addition to" 1064, which starts 1 Jul 2026.
9. An RD row with the same code in different SROs with overlapping dates is expected only for the "in addition" SROs (not yet loaded as rules). 1898/1065 rules are loaded (4 heading rows each) with their own `rule_group`.
10. Rows 25 (1064) and 24 (1152) listed in the `*_failures.csv` stay `needs_review` until the owner fills `owner_decision`; reloading after that is the intended path (the loader reads the CSV on each build).

## A3 additions (see docs/a3_findings.md)
- `acd_rules` slab convention: `condition_text` starts with `SLAB_EQ n` or `SLAB_GE n`; the caller compares n with the tariff CD of the code (a specific-rate line counts for `SLAB_GE`).
  Not-levied clauses (para 3 of 1063/1151) are `rate_kind='exempt'`, one `rule_group` each (`<SRO>#3(x)`), so they are returned next to the levy rows.
- Rows that name goods only by description are `match_level='unmapped'` (code_norm NULL): they never match a code lookup. `all` is only for true general rules.
- `sros` also holds the sales tax / income tax / customs notifications of the sugar and SRO 297 chains (`load_instruments`); `rescinded` ends the day before the rescinding notification.
- `legal_notes.hs_edition` carries the label "applicability to FY2025-26 and FY2026-27 assumed, not proven"; `valid_from` 2025-07-01, `valid_to` 9999-12-31.
- Tariff headings: 1,228 per FY; 211 are derived from codes (`tariff_headings.text` may be empty, e.g. 11.03).
- `legal_notes.table_json` (nullable, json_valid): structured table of a note whose flattened `text` is ambiguous (Chapter 11 note 2, Chapter 48 subheading notes 1 and 2); `text` is kept unchanged. Source: `data/processed/legal_notes_tables.json`.

## A6 additions: `fed_rules` (federal excise duty, see docs/a6_fed_findings.md)
Loaded from `data/processed/a6_fed_rules.csv` (`python -m src.ingest.a6_fed` writes it; `load_table_file(conn, 'fed_rules', ...)`). Same hard rule: `valid_from/valid_to/source_file/page` NOT NULL with CHECKs; `status` accepted | needs_review.
* Hierarchical columns as in the other rule tables; `HIER_TABLES` includes `fed_rules`, so `get_rule_on_date(conn, 'fed_rules', code8, date)` works. `rule_group`: `FED-T1` (Table I rates, longest prefix wins), `FED-T1A` (Table IA Special Excise Duty, cumulative with Table I), `FED-T3` (First Schedule Table III), `FED-3RD-SCHEDULE` (conditional exemptions).
* Rows whose heading column prints "Respective heading(s)" are `match_level='unmapped'` (code_norm NULL): they never match a code lookup.
* `rate_kind`: `percent` (+ `rate_basis` ad_valorem | retail_price), `specific` (amount + unit: kg, 1000 cigarettes, 100 m3, MMBTu, 100 MT, liter, fan, DOC), `compound` (`compound_rule='higher_of'`: percent part and specific part), `exempt` (Third Schedule, condition text in `condition_text`).
* Bands: `cc_ge`, `cc_gt`, `cc_le` (engine capacity in cc), `usd_gt`, `usd_le` (section 25 value in USD). `applies_to`: import_only | local_only | import_and_local | unclear. `amended_by` cites the Finance Act clause for rows that differ from the previous year.
* Helper `src.store.resolve.get_fed_on_date(conn, code8, date)` splits the result into applicable Table I / IA rows, local-only rows (never applied to imports) and possible exemptions (never applied by the store).
* FY2025-26 rows: 2025-07-01 to 2026-06-30 (FED25 snapshot); FY2026-27 rows: 2026-07-01 to 9999-12-31 (FED26). No mid-year notification is loaded.

## A7 / A8 additions: customs-duty concessions (see docs/concessions_findings.md)
Same hard rule: `valid_from`, `valid_to`, `source_file`, `page` NOT NULL with the CHECKs above; `status` accepted | needs_review. Both tables are in `HIER_TABLES`, so `get_rule_on_date(conn, 'fifth_schedule_rules' | 'fta_rules', code8, date)` works (rows valid on the date, code prefix match; each Fifth Schedule serial is its own `rule_group`, so several serials that list the same code are all returned).

### `fifth_schedule_rules` (Fifth Schedule to the Customs Act 1969)
Loaded from `data/processed/a7_fifth_rules.csv` (FY2026-27 file, 1,349 rows, `valid_from 2026-07-01`, `valid_to 9999-12-31`) and `a7_fifth_rules_2025_26.csv` (FY2025-26 file, 1,519 rules, `2025-07-01` to `2026-06-30`) by `src.store.loaders.fifth_rows` (renames `table` to `table_no`, adds `rule_group = FIFTH-<part>-<table>-<s_no>`; blank code = `match_level 'unmapped'`, `code_norm` NULL).
* `part` I, II, III, IV, V(A), V(B), V(C), VI, VIII; `table_no` main, A to E (Part II) or I to III (Part V); `s_no` as printed ("8(a)", "15A"); `sub_ref` item label; `scope` (`plant_machinery_part_I`, `pharma_api` ... `border_markets`); `title`, `group_context`, `description`, `sub_items_text` (illustrative lists), `code_raw` (the PCT cell as read), `conditions` (the Conditions column, never evaluated), `part_conditions_ref` (which preamble notes also apply).
* `match_level` `code8` (almost all rows), `heading4` (a few) or `unmapped` (Respective Headings or a code named only in words; they never match a code lookup).
* `rate_kind`: `percent` (`rate_pcts` JSON list of the printed rates, ascending; several entries = slab rule of Part I note (iv)), `fraction_of_first_schedule` (`rate_fraction_pct` 50 = "50% of the prevailing rate"), `nil`, `other` (printed text such as "1% (notwithstanding ...)", kept in `rate_raw`), `none` (printed blank, e.g. Part II Table A S.No 325). `issues` lists `rate_inherited_from_heading_row`, `rate_inherited_from_earlier_row_of_same_serial`, `rate_carried_over_page_break` (information), `description_shared_by_several_codes`, `code_taken_from_description_text`; any issue other than information makes the row `needs_review`.
* The conditions are text for the importer; the store and tools never decide them.

### `fta_rules` (China-Pakistan FTA Phase II, SRO 1640(I)/2019)
Loaded from `data/processed/a8_cpfta_rules.csv`: one row per tariff line per calendar year **2025, 2026 and 2027** (columns Year 6, 7, 8 of the SRO; the other years are in `a8_cpfta_rows.csv`, outside the two fiscal years). `valid_from` = the column date (1 Jan), `valid_to` = 31 Dec of that year. `rate_pct` is the preferential duty printed for that year; the tool pays the lower of it and the normal tariff CD. `rate_source`: `ocr_fitted_to_taper_pattern` = AI reading (local OCR of the scan) fitted to the printed straight-line pattern (flat, then equal steps to 0); `cells_read` / `cells_agree` say how many of the 15 yearly cells were read and agreed. `category`: A0 (zero in all years), constant rate, A07, A15. `description_ocr` is context only. `status needs_review` = a validator failed (code read once more, Sr.No, pattern). The SRO is read as issued on 31 Dec 2019: its amendments are not in `data/raw` (OQ-A8-1), so codes renumbered since are listed in `a8_cpfta_failures.csv` and never matched. The `sros` table has the notification (`1640(I)/2019`, kind `CD`, from 2020-01-01, no end date printed).
