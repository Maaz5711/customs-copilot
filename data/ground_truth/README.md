# Ground truth for the classification agent (C2 preparation)

Status: written 2026-10-14. **This set is small, partly synthetic, and has not been checked by a customs expert.** Every number you report from it must come with its sample size (see "How to report results" below). It is not the "about 85 rulings from one Karachi office" that SPEC.md section 6 planned: the owner had no office cases ready, so the real part was collected from public Pakistani sources and the rest was written by Claude. When office cases arrive they should be added as a separate file and reported separately.

Counts (checked by tests): real=79; real_out_of_scope=5; synthetic=60; owner_review_sample=20

## Files

| File | What it is |
|---|---|
| `cases_real.csv` | 79 real cases: a product and the PCT code a public Pakistani source gives for it. Every code was checked to exist in the tariff of the right fiscal year. |
| `cases_real_outofscope.csv` | 5 real cases that were read but must not be used as ground truth (code not in our tariffs, or its meaning changed). Each has a `reason`. |
| `cases_synthetic.csv` | 60 cases written by Claude in the way importers and clearing agents type: 48 with an expected code, 9 where the agent should ask or say "not sure", 3 where it should refuse. **Synthetic, unverified, written by Claude, must be confirmed by a qualified person.** |
| `owner_review_sample.csv` | 20 cases (10 real, 10 synthetic) for the owner to eyeball, with Y/N and correction columns. |

Validate with `python -m src.eval.validate_cases` (add `--store` to also cross-check with the `lookup_code` tool). Tests: `tests/test_ground_truth.py`.

## Columns

### cases_real.csv
`id`, `description` (my own short paraphrase, not a copy), `expected_code` (as printed in the source, with a dot after the 4th digit), `expected_level_note` (says whether the source gives 8, 6 or 4 digits), `as_of_date`, `fiscal_year` (FY2025-26 or FY2026-27, from the date), `source` (ruling, tribunal, court or other), `source_url` (the page I read), `source_ref` (notice, ruling or case number), `page_or_section`, `notes`, and four extra columns:
- `ruling_kind`: classification_committee_public_notice, valuation_ruling, supreme_court, high_court, tribunal_order_in_high_court_file.
- `disputed_codes`: the code the importer declared or the department argued, when the source says so. Useful for finding wrong-but-plausible answers.
- `date_basis`: where `as_of_date` comes from (the date printed on the document, or the FBR upload date when the printed date was unreadable or inconsistent).
- `code_also_in_other_fy`: true if the same 8-digit (or prefix) code also exists in the other fiscal year's tariff. It is true for all 79 rows, so each case can be run at an FY2025-26 date and at an FY2026-27 date.

For 6-digit and 4-digit expected codes (8 rows) the source names only a sub-heading or heading. Score those at 6 or 4 digits only.

### cases_synthetic.csv
`id`, `description` (as typed by a user, messy on purpose), `as_of_date`, `fiscal_year`, `expected_behavior` (answer, not_sure_or_clarify or refuse), `expected_code` (empty unless answer), `expected_level_note`, `alt_acceptable_codes` (rarely used), `candidate_headings` (for not_sure_or_clarify rows: the headings the agent might show as its top candidates), `hardness_tags`, `basis` (the tariff text or legal note I used), `tariff_page` (page of the tariff PDF for that fiscal year), `verified` (always `false`), `label` (always the sentence in bold above), `notes`.

### owner_review_sample.csv
`sample_no`, `kind`, `case_id`, `description`, `as_of_date`, `fiscal_year`, `expected_behavior`, `expected_code`, `evidence_or_basis`, `where_to_check`, `what_to_check`, then three columns for the owner: `owner_agrees_Y_or_N`, `owner_correction`, `owner_comment`.

## Where the real cases come from

All pages were read on 2026-10-14. Nothing was downloaded or saved as a file: PDFs were read as remote text. The text of each PDF was pulled with an extraction tool in direct-quote mode, not opened in a viewer, so a misread digit is possible (this is why the owner sample contains real cases).

| Source | Documents read | Rows | Notes |
|---|---|---|---|
| FBR "Public Notice (Classification)" page, https://www.fbr.gov.pk/public-notice-classification/51149/152293. Decisions of the Classification Committee, Collectorate of Customs (Appraisement-East), Karachi, Aug 2025 to Sep 2026 | 59 | 63 | Best source: a real dispute, a decision, usually an 8-digit code. Several notices decide old imports (GD dates 2017 to 2024). |
| FBR "Customs Valuation Rulings" page, https://www.fbr.gov.pk/showvaluations (932 entries, about 125 of them from Jul 2025 on, including some addenda and publications) | 12 | 12 | Weaker: the ruling's own text says HS codes are printed for illustrative purposes and one ruling prints an outdated code. Only simple single-product rows with one printed 8-digit code were used. |
| Supreme Court of Pakistan (limousine, reported by Dawn, 24 Sep 2026) | 1 | 1 | Only the news report was read, not the judgment. |
| High Court of Sindh case-law site (caselaw.shc.gov.pk) | 3 | 3 | Two High Court orders (potato fryer 13.05.2026, BOPP film 09.04.2026) and one Tribunal order quoted in a High Court order sheet dated 17.11.2025. |
| Customs Appellate Tribunal | 0 directly | 0 | The searches I ran did not turn up tribunal orders on a public site, only tribunal findings quoted inside High Court files. |

Mix of the 79 rows by fiscal year: FY2025-26 = 65, FY2026-27 = 14 (most notices are from Jan to Jun 2026). By code length: 71 at 8 digits, 4 at 6 digits, 4 at 4 digits. They cover 33 chapters but lean to machinery and electronics (chapters 84 and 85 are 27 of the 79) and chemicals. There are few everyday food and textile items, which is why the synthetic set covers them.

## Problems found while collecting

- Five cases were read but not used (file `cases_real_outofscope.csv`):
  1. Public Notice 20/2026: printed code 9405.4090 is not in our tariffs (HS 2022 restructured 9405.4x; the goods were imported in 2018).
  2. Public Notice 10/2026 ("Predust and Batter"): printed code 1901.1920 is not a line of either tariff (probably a typo or an old national line).
  3. Public Notice 13/2025 (multi-split air conditioner): printed 8415.1030 is a 7-digit national sub-heading, not an 8-digit line (the lines are 8415.1031 and 8415.1039).
  4. Public Notice 23/2026 (spraying drone): the code string 8802.2000 exists, but the ruling decides an old import under older nomenclature. Under HS 2022 unmanned aircraft have their own heading 88.06, so this is probably not the right answer for today.
  5. Valuation Ruling 2093/2026 (CCTV cameras): printed 8525.8010 is not a tariff line today (the line is 8525.8910).
- Conflicts between sources: Valuation Ruling 2105/2026 lists plastic mobile covers under 8529.9090, but Public Notice 59/2026 decides 4202.3200. Valuation Ruling 2040/2026 prints 8517.6970 for wireless access points, but Public Notice 33/2026 decides 8517.6290. In both cases the notice is used and the ruling is only mentioned in `notes`.
- Dates: about 13 rows use the FBR upload date because the printed date was handwritten, garbled by the text layer, or later than the upload (see `date_basis`). The fiscal year is not affected. One notice (Public Notice 60/2026) has a handwritten day I could not read on the scan.
- The FBR list labels the link for "Public Notice 05/2025" and "06/2025" the other way round from the numbers printed inside the files. The rows use the printed number and say so.
- Notices read but not used as cases: Public Notice 47/2026 (two outcomes depending on documents), 11/2026 (several different items), 50/2026 (repeat of 14/2025).
- Reserve (valid, read, not included to stay near 80 rows; add if you need more): Public Notice 36/2026 (flavour mixtures for aerated drinks, 3302.1010, 15.04.2026), 27/2026 (boiler superheaters and economizers, 8404.1000, upload 06.05.2026), 13/2026 (control valve assembly, 8481.8090, upload 29.04.2026); Valuation Rulings 2079/2026 (cashew nuts, 0801.3200), 2062/2026 (lithium-ion batteries, 8507.6000), 2055/2026 (LED bulbs, 8539.5210), 2095/2026 (sunglasses, 9004.1000), 2096/2026 (stainless submersible motors, 8501.5210). URLs are on the FBR listing pages above.

## How the synthetic cases were made

Written by Claude on 2026-10-14. Each expected code was found by reading the tariff PDF text (the page is in `tariff_page`) and the legal notes in `data/processed/legal_notes.json` (note ids such as `section_note:SXI:2` appear in `basis`), then checked to exist in the tariff of the case's fiscal year. No search index or LLM was used to pick the code, so the set is not tuned to the agent. Descriptions are real-world phrasing, not tariff wording (a test checks that the answer code and the tariff line text are not in the description). Coverage: vehicles by engine size and CKD/CBU/used, mobile phones and electronics (some with specific duty), appliances, chemicals and plastics, textiles and footwear, food with specific duty (palm, soya, betel leaves), metals, sets and 'other' residual lines, parts versus complete goods, chapter 99 special-regime entries (diplomats, gift parcels, relief goods), a date-sensitive pair (used clothing is one line in FY2025-26 and three in FY2026-27), 9 cases where the right behaviour is to ask or say "not sure", and 3 to refuse (misdeclaration, a year outside the store, a non-customs question).

Weak spots to check first: S044 (hangers, 3926.9099 or 3924.9000), S037 (barber kit: essential character under GRI 3(b)), S046 to S048 (answers are 4-digit chapter 99 entries), and any case where "expected_code" rests on my reading of a national line.

## How to report results

- Report n with every number: real n=79 (71 at 8 digits, 4 at 6 digits, 4 at 4 digits) and synthetic n=48 answer cases, 9 clarify cases, 3 refuse cases. Give confidence intervals (for example Wilson); with n around 80 they are wide.
- Report real and synthetic results separately. Do not average them. Treat valuation-ruling rows (12) as weaker evidence than classification-committee rows.
- The real set comes from one office's committee (Karachi Appraisement-East) and public sources only, and leans to machinery, electronics and chemicals. State this limit.
- Do not call a synthetic row "wrong" until the owner or a qualified person has confirmed it. A mismatch may be my mistake.
- For refusal quality use the 9 clarify and 3 refuse rows; for the three-way ablation run every row at its own `as_of_date`, and the real rows also at an FY2026-27 date (`code_also_in_other_fy` is true).
