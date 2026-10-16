# Concessions findings: Fifth Schedule and China-Pakistan FTA Phase II (read 2026-10-16)

Plan: `docs/concessions_plan.md`. This note says what the two documents look like, what every column means, and which edge cases the code handles. Page numbers are PDF pages.
Plain-language summary: the First Schedule tariff gives one customs duty (CD) per code. These two documents lower that CD for certain goods. The tools must show the normal bill, the bill with the concession, and the conditions the importer must prove. They must never apply a concession on their own.

## 1. Fifth Schedule to the Customs Act 1969

File: `data/raw/2026825118858478FifthSchedule2026-27.pdf`, 59 pages, text layer present, "Updated 30th June, 2026".

### Which year does it belong to?
* Page 2 says "The Second Schedule [See section 3(14)] ... FOR THE Fifth Schedule, the following shall be substituted". Finance Act 2026 section 3(14) (Finance Act 2026 PDF, page 8) says exactly this: "The Fifth Schedule ... shall be substituted in the manner provided for in the Second Schedule to this Act". So this file is the whole Fifth Schedule as substituted for **1 July 2026 onwards** (FY2026-27). Rows are loaded with `valid_from = 2026-07-01`, `valid_to = 9999-12-31`.
* The FY2025-26 version is **not available**. The two Customs Act consolidations (`...CustomsAct1969(June2025)...pdf` p.278 and `...Customs-Act-1969.pdf` p.281) print only the title "THE FIFTH SCHEDULE (See Finance Act, 2025 / 2026)" and nothing else. The Finance Act 2025 and the Finance Act 2026 PDFs are scans (no text) and the substituting Second Schedule is inside them. Nothing was guessed: the tools say "Fifth Schedule for FY2025-26 not in the store" for dates before 1 July 2026. Owner question OQ-A7-1 in `docs/owner_questions.md`.

### Structure (Parts and tables)
| Part | Pages | Content | Columns |
|---|---|---|---|
| I | 2-22 | Plant, machinery, equipment and capital goods for industries/sectors (agriculture, mining, power, solar, tourism ...). Table with S.No 1-39 (+8(a), 15A). | S.No, Description, PCT Code, Customs Duty (%), Conditions |
| II | 23-41 | Pharmaceutical inputs. Table A active ingredients (S.No 1-476), B excipients, C drugs/medicines, D packing material, E omitted. | Sr.No, Description, PCT code, Customs duty (%) (conditions are in the Part preamble, p.23) |
| III | 41-49 | Raw materials/inputs for poultry, textile and other sectors, S.No 1-154. | five columns incl. Condition |
| IV | 49-50 | Machinery for the textile sector. 47 rows, 41 omitted, 6 live (S.No 15, 16, 44-47). | S.No, PCT Code, Rate of Duty, Condition |
| V(A) | 50-54 | Electric vehicles (CBU, CKD parts, plant inputs), policy 2020. | Table I five columns; Table II has two description columns (vehicle, imported goods); Table III |
| V(B) | 54-55 | Hybrid vehicles (AIDEP 2021-26). | five columns |
| V(C) | 55 | Agricultural tractors (S.No 1, 2). | four columns |
| VI | 56 | Aviation (aircraft, spare parts, MRO). | five columns (Special Condition) |
| VII | 56 | "[Omitted]" | - |
| VIII | 56-59 | Joint Border Sustenance Markets, 3 categories (5%, 10%, 20%), US$50 per visitor per day. | four columns |
Pages 21-22 also hold the printed forms Annex-A / Annex-B (chief-executive certificate and related forms). They are not concessions and are skipped by the parser.

### What the columns mean (Part I)
* **Customs Duty (%)** is the concessionary customs duty that replaces the First Schedule CD **only if the conditions are met**. Examples: p.3 S.No 1 C(1) submersible pumps 8413.7011/8413.7019 = 0%; F(1) milk chillers 8418.6910/8418.6990 = 2%.
* **Several rates in one cell** ("0%,3%,5%", "0%, 3%, 10%", "0%,3%, 11%, 15%") are not alternatives the importer picks. Note (iv) and Explanations I-IV (pp.2-3) say: the low slab rates (0%, 3%, 11%) apply only to goods whose First Schedule CD is that same rate; goods in every higher slab pay the **last (maximum) rate** of the entry. Example: "0%,3%,5%": CD 0% -> 0%, CD 3% -> 3%, CD 11%/16%/20% -> 5%. Part II note (v) (p.23) does the same for "3%, 5%". This is a pure arithmetic rule; it is coded in `src/tools/fifth.py` (deliverable 5).
* **"Respective Headings"** in the PCT column means the entry covers the goods described in the Description column in whatever heading they fall under. The row cannot be matched to a code by machine. 169 of the 1,349 rules are of this kind (61 in Part I). They are stored with `match_level='unmapped'` and shown to the importer as "possible entry, check the description".
* **"50% of the prevailing rate"** (S.No 39 tourism, EV parts) is a fraction of the First Schedule CD, not a rate. Stored as `rate_kind='fraction_of_first_schedule'` with `rate_fraction_pct=50`.
* **Conditions column** and the Part preamble carry the real eligibility tests: not locally manufactured (Customs General Order list or Engineering Development Board certificate, p.2 note (i)), chief-executive certificate in Annex-A format (note (ii), except S.No 1(H), 14, 20, 21, 22), partial-shipment details (note (iii)), sector or ministry certificates, no sale within five years without FBR approval, and so on. The system cannot check these. They become questions to the importer (`claimed_rules`, `docs/tools.md`).
* **Capital goods** (p.3 Explanation): any plant, machinery, equipment, spares and accessories in Chapters 84, 85 or any other chapter, needed for manufacture/production, mining, agriculture, fisheries, dairy, poultry, IT, storage, communication or SEZ infrastructure.

### Edge cases found while reading
1. Table cells are merged heavily: one rate cell can cover many rows (S.No 20 solar, S.No 39 tourism across pages 19-21), and one conditions cell can span a whole serial across pages. The reader (`src/ingest/pdf_grid.py`) rebuilds cells from the ruling lines. Rates and conditions carried over a page break are flagged `rate_carried_over_page_break` (information, not an error).
2. Some items print no rate of their own and sit under a heading row that prints one (S.No 21 5(b), S.No 152). The rate is inherited and the row is `needs_review` (`rate_inherited_from_heading_row`; 53 rules). Four rows of S.No 122 (p.47) print an empty rate cell below a serial whose rate "0%" is printed once on p.46; they inherit it and are `needs_review` (`rate_inherited_from_earlier_row_of_same_serial`).
3. Part II Table A serial 325 (3505.2010, p.31) prints **no duty value**. It is kept with no rate and listed in the failures report; the tool will not apply a concession to it.
4. Rate "8.5%" (Part III S.No 51, p.43) is printed as such; it is outside the usual slab list and is reported as an `unusual_rate` finding, not changed.
5. Serial labels are not plain integers: "8(a)", "15A". The continuity check understands them.
6. Part V(A) Table II lists the imported EV parts by "PCT code 8504.4020" **inside the description text**. The codes are read from that text (`code_taken_from_description_text`), the rows carry the printed text rate ("1% (notwithstanding the rate of customs duty ...)"), which is not a plain percentage, so they are `needs_review` and not computed.
7. The 12 codes below are printed in the Fifth Schedule but are not lines of the FY2026-27 (or FY2025-26) tariff. They are logged in `a7_fifth_failures.csv` (`code_not_in_tariff_2026_27`) and never matched: 8481.3000, 3920.1000, 8507.2090, 7310.0000, 8507.0000, 9004.9000, 4419.0000 and 2934.4990 (these appear on pp. 3, 4, 11, 12, 15, 17, 20, 21, 35, 45, 47). Part III S.No 106 prints heading "9300" which matches no tariff line.
8. Part VIII (border markets) is a special regime with a US$50 per visitor per day cap. It is loaded for completeness (`scope='border_markets'`) and is not offered to normal importers.

### Validation that was run (details in `data/processed/a7_fifth_failures.csv`, `a7_fifth_validation.json`)
* Completeness: every 8-digit code printed in a table block of the PDF text layer is in a parsed row (0 missing).
* Two-tool diff against `pymupdf.find_tables()`: codes found only by the other tool are on pp. 51-53 and 56 and are codes quoted inside descriptions or conditions, not in code columns.
* Serial continuity per Part/Table: no gap or reversal (omitted rows count as present).
* Codes against the FY2026-27 tariff: 12 not found (see above).
* Rates: all in the usual set except 8.5%.
* Nothing was fixed silently. Spot-check sheet for the owner: `data/processed/spotcheck_a7_fifth.csv` (27% of the rules; every `needs_review` row, every row of Parts IV-VI, every 3rd row of Part I, every 8th of Part II ...) with page images in `data/processed/page_images/fifth/`.

## 2. China-Pakistan FTA Phase II: SRO 1640(I)/2019

File: `data/raw/cpfta/2020111213219376SRO1640(I)2019dated31.12.2019.pdf`, 177 pages, image-only scan (no text layer), landscape. "Islamabad, the 31st December, 2019", effective **1 January 2020**, supersedes S.R.O. 659(I)/2007.

### What it says (p.1)
* The Federal Government exempts the goods **imported from the People's Republic of China** in column (3), under the First Schedule heading/sub-heading in column (2), "from so much of the customs duty specified in the First Schedule as on 1 January 2020 as is **in excess of** the rates specified in columns (4) to (18)", each rate "with effect from the corresponding date".
* Proviso: the goods must be **manufactured or produced and imported in conformity with the Rules of Determination of Origin** and the operational certification procedures notified by S.R.O. 1286(I)/2005 (24 Dec 2005) read with the Import Policy Order 2016. So the preferential rate needs proof of Chinese origin (certificate of origin, Form E). The agent must ask; it must not assume.
* "In excess of" means the importer pays the **lower** of the normal CD and the SRO rate. The tools use `min(normal CD, SRO rate)` and show both.
* Only the customs duty is reduced. Nothing in the SRO touches regulatory duty, additional customs duty, sales tax or income tax. Those are computed as usual (on a value that includes the CD actually paid, see `docs/duty_formula.md`).

### Layout
* Columns: (1) Sr.No, (2) PCT code (8 digits), (3) Description, (4) to (18) = Year 1 to Year 15 with the dates 1-Jan-20, 1-Jan-21 ... 1-Jan-34. Each cell is a percentage with two decimals ("20.83").
* 6,786 rows (Sr.No 1 to 6786, last row 9706.0000 antiques, page 177). About 38-50 rows a page; descriptions wrap over several lines and the Sr.No, code and numbers sit on the bottom line of the row.
* Pattern of the numbers (this is what makes the scan checkable): each row is a straight-line taper. The value is flat at the starting rate up to a "start year", then falls by equal steps to 0 at an "end year", e.g. Sr.No 63: 20.00, 16.67, 13.33, 10.00, 6.67, 3.33, 0.00 (7-year taper); Sr.No 74: 25.00, 25.00, 25.00, 22.92, 20.83 ... 2.08, 0.00 (taper from year 3 to year 15); Sr.No 73: 20.00 in all 15 years (no concession); many rows are 0.00 throughout. The FBR summary (Phase II explanation page) names the groups A0, A07, A15, MOP1, MOP2, C1, C2; the reading is compared with its counts (`docs/a8_cpfta_findings.md`).
* Rates are by **calendar year**: the 1-Jan-2025 column applies to Jan-Dec 2025, the 1-Jan-2026 column to 2026, the 1-Jan-2027 column to 2027. FY2025-26 (1 Jul 2025 - 30 Jun 2026) therefore uses **Year 6 (Jul-Dec 2025) and Year 7 (Jan-Jun 2026)**; FY2026-27 uses **Year 7 (Jul-Dec 2026) and Year 8 (Jan-Jun 2027)**.

### Edge cases
1. HS edition: the SRO is from 2019 (HS 2017 codes). The tariffs of FY2025-26/2026-27 use HS 2022. Codes that no longer exist in the tariff are listed in the failures report. The amendments to SRO 1640(I)/2019 (FBR "Active SROs Import" row 26: "Amending SROs of 1640(I)/2019") are **not in `data/raw`**. They may carry the code changes and later edits. This is the open blocker for full coverage: owner question OQ-A8-1. The parse is labelled "as issued 31 Dec 2019; amendments not applied".
2. Page 2 is one image in a different size (1368 x 320 px strip) of the same table; the page contents continue from page 1 (rows 1-19 on p.1, 20-60 on p.2).
3. The scan is tilted by up to about one degree; the reader straightens it first.
4. Descriptions are not needed for the lookup (the code is the key); they are kept as AI reading for context only.
