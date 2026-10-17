# A8: China-Pakistan FTA Phase II, SRO 1640(I)/2019: how it was read and how far to trust it

Plain summary: the SRO is a 177-page scan (no text). Nothing here was typed in by hand. A program on this PC (RapidOCR) read the pictures; a second program checked every line against the straight-line pattern the SRO prints, the order of the codes and the Sr.No count; the lines that fail a check are flagged `needs_review` and listed. **Every number is an AI reading of a scan until the owner checks the spot-check sheet.**

Code: `src/ingest/a8_cpfta_ocr.py` (read pages), `a8_cpfta.py` (rows, validators, outputs), `a8_cpfta_codes.py` (second reading of unclear codes), `a8_cpfta_spotcheck.py`, `a8_cpfta_vision_check.py` (test of a paid vision model). Tests: `tests/test_a8_cpfta.py`, `tests/test_concessions.py`.
Outputs in `data/processed/`: `a8_cpfta_rows.csv/json` (one line per SRO table line, Year 1 to Year 15), `a8_cpfta_rules.csv` (long form for the store: Years 6, 7, 8 = 2025, 2026, 2027), `a8_cpfta_failures.csv`, `a8_cpfta_code_reread.csv`, `a8_cpfta_validation.json`, `spotcheck_a8_cpfta.csv` (1,003 lines, 15%) with page images in `data/processed/page_images/cpfta/` (gitignored). Raw OCR boxes: `data/processed/cpfta_ocr/` (gitignored, rebuild with `python -m src.ingest.a8_cpfta_ocr`, about 1 hour).

## Method
1. Each page is rendered at 200 dpi, straightened (the scans tilt up to 1.2 degrees) and read by RapidOCR (PP-OCR models, onnxruntime, free, local). 22 to 110 seconds a page on this PC; 177 pages. **Cost: nothing paid.**
2. Rows are rebuilt from the text boxes: Sr.No and code on the left, 15 yearly numbers placed in their columns (a few pages are not straight and needed a merge of two half-rows).
3. Numbers: OCR often drops the point ("0.00" read as `00'0`); the rules in `parse_number` restore it only when exactly three or four digits remain.
4. **Pattern fit.** Every line of the SRO is flat at a starting rate and then falls in equal steps to 0, or is flat all the way: FBR's categories A0 (zero), A07 (steps from year 2 to year 7), A15 (steps from year 4 to year 15), and constant rates (C1/C2/MOP). The OCR cells of a line are compared with these four shapes. If at least 9 cells (75% or more, at most 4 off) agree, the line gets the shape's values and the cells that disagree are written to the failures report (`ocr_cell_disagrees_with_pattern`, 2,208 cells of about 100,000). Otherwise the OCR cells are kept and the line is `needs_review` (33 lines fit nothing, 57 weak).
5. **Codes.** The code must be eight digits and the codes must run in tariff order. Out-of-order or unreadable codes (about 700) were read a second time from a 300 dpi strip; 261 were repaired, 82 of them by filling one unreadable digit from the neighbours and the tariff (flagged). The rest stay unmatched or `needs_review`.

## Result (`a8_cpfta_validation.json`)
| Check | Result |
|---|---|
| Lines read | 6,778 of the 6,786 Sr.No; 8 Sr.No not read (listed in the failures report) |
| Sr.No continuity | numbering by sequence with checks against the read numbers; 22 double readings of one Sr.No dropped (logged) |
| Status | 6,062 accepted, 716 needs_review (158 without a code, others with a code out of order or a weak pattern) |
| Pattern counts | zero in all years 3,284 (FBR says 3,251 lines are A0); A07 1,033; A15 1,036; constant rate 1,392; unfitted 33 |
| Codes found in a tariff | 6,105 in both tariffs, 4 in FY2025-26 only, 511 in neither (HS 2017 codes of 2019 that were renumbered, or misreads) |
| AI second reader (Claude looked at the page images, not the owner) | pages 17 and 100 compared line by line (about 100 lines) plus 12 lines of pages 1 and 3: every rate agrees; 5 codes were misread before the order check (page 17 Sr.No 606, page 100 Sr.No 3814 to 3817) and all 5 are flagged |
| Paid vision model test | DeepSeek flash vision on page 100: 1,193 input and 2,242 output tokens (about 0.002 USD), but 18 of 52 rows differ (shifted columns, invented codes). **Not used.** |

## Check against real customs data (aggregates only, `docs/gd_concession_check.md`)
The importer's Goods Declaration extract (Chapter 85, Feb 2026, private) has 5,491 lines that name SRO 1640(I)/2019. For the 4,329 lines whose code has a row in our reading, the customs duty Customs charged equals IV x min(tariff CD, our 1-Jan-2026 rate) (tolerance 2 PKR) on **4,261 (98.4%)**; 68 lines differ (10 codes, in every case Customs charged less than our rate, probably another concession on the line). **1,162 lines (21% of all lines, 44 codes such as 8504.4020, 8504.4090, 8542.3100, 8501.3200, 8517.7900) have no row at all**: these are HS 2022 codes that did not exist in the 2019 SRO. The amendments of SRO 1640(I)/2019 that carry the renumbering are not in `data/raw` (OQ-A8-1). This is the largest gap.

## Not done / limits
* The reading is "as issued 31 Dec 2019": no amendment applied.
* About 2% of the lines (158) have no readable code. Wrong digits that still look in order may remain (the order check and second reading catch most; on the two pages compared line by line all 5 wrong codes were caught). The owner's spot check should look at the code column first.
* Descriptions are OCR text, for context only.
* Years 1 to 5 and 9 to 15 are in `a8_cpfta_rows.csv` only; the store holds the three calendar years of FY2025-26 and FY2026-27.
