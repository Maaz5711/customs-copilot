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
