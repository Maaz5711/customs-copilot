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
| `sros` | sro_number | 6 (1064, 1152, 1063, 1151, 1898, 1065) |
| `rd_rules` | one row per (SRO, S.No, code) | 1064: 698 rows from 687 S.Nos; 1152: 704 rows from 693 S.Nos |
| `acd_rules`, `sales_tax_rules`, `income_tax_rules`, `legal_notes` | see contract | empty |

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
2. "Respective Headings" rows (1064 S.No 686/687, 1152 S.No 692/693) are loaded `unmapped` + `needs_review`; they match no code until mapped by hand.
3. 1102.9000 appears under S.No 109 and 110 in both RD SROs (Maida, Semolina) and is not in the 2026-27 tariff. Both rows are kept; lookups return both, flagged.
4. 1152 S.No 511 (8433.5100) has an age-conditional rate; stored as `conditional`.
5. Tariff specific duties from rotated cells (48 rows in each year) are `needs_review`: the scale (Rs.10550/MT) is reassembled from wrapped text. Chapter 99 entries with a blank or odd duty cell ("", "0 0"; 7 rows) are stored as `compound` with the printed text and `needs_review`.
6. Chapter 99 entries span pages; the parser produced 56 fragments for 42 codes, kept as one row per page (`UNIQUE(fy, code, page)`).
7. The 6 "duplicate" vehicle codes are not duplicates (A1 finding, re-checked by a test): one table row each; the other hits were mentions in notes.
8. 1065(I)/2026 effective date (date line 30 Jun 2026 vs the "in addition to 1064" which starts 1 Jul 2026) is an open question.
9. An RD row with the same code in different SROs with overlapping dates is expected only for the "in addition" SROs (not yet loaded as rules). When 1898/1065 rules are loaded they must use their own `rule_group`.
10. Rows 25 (1064) and 24 (1152) listed in the `*_failures.csv` stay `needs_review` until the owner fills `owner_decision`; reloading after that is the intended path (the loader reads the CSV on each build).
