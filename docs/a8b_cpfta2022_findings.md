# SRO 1181(I)/2022: the current China FTA table (2026-10-17)

FBR's Amending/Archived SROs list (1,965 customs entries) names exactly three amendments of SRO 1640(I)/2019: 574(I)/2020 (29 Jun 2020), 905(I)/2021 (8 Jul 2021, one line: serial 1046, Himalayan rock salt) and 1181(I)/2022 (27-28 Jul 2022). No later amendment is listed. SRO 1181(I)/2022 substitutes the whole Table, so it is the current text; 574 and 905 are superseded by it.

## How it was read (`python -m src.ingest.a8b_cpfta_2022`, tests in tests/test_a8b_cpfta_2022.py)
The file (219 pages) has a text layer; each row is serial, 8-digit code and description, then 15 yearly rates (1 Jan 2020 to 1 Jan 2034). Rows are accepted only if: the 15 values form one of FBR's three patterns (constant, A07, A15) exactly; the code is in the tariff; and the code is in the proper place in the ascending order (longest in-order run; a misplaced row whose code is printed again in order is rejected as a misprint, for example sr 5888 prints 8507.8000 where 8507.4000 belongs). 'no exemption' years are counted, not guessed. Specific duties in rupees (for example 'Rs. 7240.0/MT', 45 rows) are listed as unsupported and never turned into percentages.

## Numbers
6,849 rows read (last serial 6,917); 6,687 accepted, 33 needs_review, 84 rejected, 45 specific-duty rows unsupported. 6,710 of the 7,605 FY2026-27 tariff codes have a usable row.
Cross-check against the old 2019 reading (OCR of a scan): of 5,700 codes in both, the 2025, 2026 and 2027 columns agree on 5,698. The two differences are errors of the old scan reading.
Against the importer's real assessed customs duty (docs/gd_concession_check.md): match 95.8% (was 77.6%), no row 2.7% (was 21.2%).

## What is still open
* 84 rejected rows (mostly scan-noise pages: 1, 24-25, 161, 183, 188, 195, 200 and similar): the store falls back to the old 2019 reading, flagged needs_review, only where the 2022 row is unusable. These pages can be read from page images if wanted.
* 45 rows with specific duties in rupees (edible oils and similar): the agent says the FTA row exists but cannot be modelled.
* The SRO's own date: FBR's list shows 27 Jul 2022, the file name says 28.7.22. It does not matter for the 2025-2027 columns.
