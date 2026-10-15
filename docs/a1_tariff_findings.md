# A1 findings: Tariff FY2026-27 parse

Source: `20268251181330180Tariff-2026-27.pdf` (345 pages, clean text layer).
Parser: `src/ingest/tariff.py`, run with `python -m src.ingest.run_tariff`. Tests: `tests/test_tariff_2026_27.py`.

## Results (reproduced by the tests)
| Item | Count |
|---|---|
| Four-digit headings | 1,017 |
| Eight-digit code rows (unique, no duplicates) | 7,605 |
| Plain CD (%) rows | 7,551 |
| Specific-duty rows (Rs. per unit) | 54 |
| Chapter 99 four-digit codes (kept separately) | 56 |

## Differences from the trial numbers in CLAUDE.md (explained)
- **"6 duplicate codes" are not duplicates.** 8703.2115, 8703.2193, 8703.3225, 8704.3130, 8704.3150 and 8704.3190
  each appear once as a table row (code at the left margin). The other hits are references to the code inside
  Chapter 87 notes and footnotes (pages ~107-320). The trial counted those text mentions as code lines.
- Trial: 7,553 plain / 53 specific. This parse: 7,551 plain / 54 specific. Two split values ("2 5", "1 0" for
  4009.2110 and 8421.3920) are now read as 25 and 10; the specific count differs by one. Both are in the
  spot-check sheet.

## Specific duties: how they are read
The specific-duty cells (for example soya bean oil) are rotated 90 degrees and wrapped mid-number
("Rs." / "105" / "50/" / "MT"). Joining the characters gives **Rs.10550/MT** (Rs. 10,550 per MT), not 105.50.
Evidence: the PDF text has no decimal character in these cells, and Rs.105/MT would be a negligible duty on a
product worth hundreds of thousands of rupees per MT. CLAUDE.md's example "Rs. 117.00/MT" is therefore most
likely Rs. 11,700/MT. **This is an inference. Maaz must confirm on the spot-check sheet.**

## Spot check
`data/processed/spotcheck_tariff_2026_27.csv`: all 54 specific rows plus a seeded 10% sample (755 plain rows).
Fill the `correct?` column by looking at the PDF page.

## Description fix: sub-group headers (both tariffs)
Bug (found by the owner's review, confirmed on pages 267, 214, 110): bordered sub-group header lines that have no code
and no duty cell (for example "- - - Of a cylinder capacity exceeding 850cc but not exceeding 1000cc:") are printed
BEFORE the rows they describe. The old parser glued them to the end of the row above, so 8703.4019 showed the
850-1000cc header, and 8703.4039 showed 1,500-1,800cc.

Rule now in `src/ingest/tariff.py`:
- A no-code, no-duty line that starts with a dash opens a header. It applies to the coded rows printed after it,
  until a header of the same or shallower dash depth.
- A no-code line without a leading dash is wrapped text of the item it follows (header, row or heading), also across
  a page break (this also recovers long Chapter 87 parts lists that used to be cut at the page top, 37 rows).
- Exception: a row whose code line has no description text (8479.8960, 8704.6030) owns the lines below it.
- A header printed at the same depth as its first row (8479.7100) still applies to that row.

New row fields: `own_description` (own text, dashes removed), `own_text` (as printed, with dashes), `dash_depth`,
`parent_chain` (enclosing headers), `full_description` ("header > header > own"). `description` stays and now holds the
corrected text in print order (headers, then own text). Headings no longer carry glued sub-headers (84.15 etc.).

Safety (tests/test_tariff_descriptions.py): codes, CD values, specific duties, pages, heading list and Chapter 99 rows are
identical to the JSON committed before the fix (7,605 / 7,590 unique codes, 1,228 headings, 54 specific rows each).
Only descriptions changed. List of changes: `data/processed/tariff_description_changes.csv`
(11,567 rows: 5,767 had the next group's header glued on, 8,663 gained their enclosing headers (counts overlap by type, see
`change_type`), 37 recovered wrapped text). Pages 20, 124, 269, 315, 323 of FY2026-27 and the three pages above were
checked against page images with no errors found. Known limit: footnote or note text printed under the last row of a page
(for example pages 98, 113) is still appended to that row, as before.
