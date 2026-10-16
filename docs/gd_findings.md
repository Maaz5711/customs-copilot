# What the importer's Goods Declaration extract showed (Chapter 85, February 2026)

Source: an Excel file shared by an importer (a friend of the owner): `data/raw/importer_data/IMP_Ch85_Feb2026.xlsx`, **private and gitignored**. 19,525 lines of cleared Goods Declarations at Karachi and Port Qasim collectorates (KAPW, KAPS, KAPE, KPPI) for 1 to 28 February 2026 (FY2025-26 rules). 14,950 are home-consumption (HC) lines. Columns: GD type, date, PCT code (stored as a spreadsheet NUMBER, so `8536.909` means 8536.9090), description, origin, importer identity, quantity, unit, assessable value (IV, PKR), the duties actually assessed (CD, ST, IT, ADD. ST, RD, ADD. CD, FED, others) and up to four SRO / schedule references.
Rules: never commit the raw file or any identity column (NTN, importer, consignee, IGM, BL, GD number). Only aggregates and anonymised ids are kept in git. Loader: `src/eval/gd_data.py`.

## 1. A real classification test set
* All 14,950 HC lines carry a code that is a real 8-digit tariff line on its date (358 distinct codes).
* After cleaning the description (dropping the typed quantity tail) and removing exact duplicates there are 13,375 unique (description, code) pairs; 960 cases (at most 3 per code) are written to `data/raw/importer_data/cases_importer.csv` (private).
* The label is the **declared code on a cleared GD**: strong evidence of everyday practice, not expert verification (some declared codes may be wrong). Chapter 85 only.
* Run: `python -m src.eval.run --llm deepseek --tag importer --kinds importer --sample 150 --seed 3 --classify-thinking enabled`. Off-peak only (see docs/eval.md). A first run stopped at 131 of 150 plain-LLM cases (peak hours); resume it, results are kept.

## 2. A check of the duty rules against what Customs charged (`python -m src.eval.gd_duty_compare 1500`, `docs/gd_duty_comparison.md`)
1,500 random HC lines. Importer facts are inferred per line (commercial importer from the income-tax rate; manufacturer in-house use if the 3% tax was not charged; filer).
* **Plain-rate lines (no concession SRO on the line): 652 of 770 (84%) match Customs on every tax** (CD, RD, ACD, ST, the 3% tax, IT within 2 rupees).
* China FTA lines (SRO 1640(I)/2019), Fifth Schedule lines, SRO 655/656 and exemption lines mostly do not match, as expected: the tool still applies the tariff CD. These lines are the test set for the concessions work (docs/concessions_plan.md): 2,374 HC lines carry SRO 1640(I)/2019 and about 100 carry the Fifth Schedule.

## 3. Questions the data answered
| Question | Answer from the data |
|---|---|
| Is the 3% value-addition tax charged at import, and on what base? (OQ-B3-1, OQ-W3) | Yes. Column "ADD. ST" is exactly 3.0% of (IV + CD + RD + ACD [+ FED]) on 7,704 of 7,723 lines where it appears (7,226 HC lines have none: manufacturers in-house use and exclusions). Same base as the 18% sales tax, before sales tax. |
| Is income tax at import 6% or 12%? | Filer: 6%, 5.5%, 3.5%, 2% or 1% by Twelfth Schedule class and importer type. Only 45 of 14,950 lines show the doubled non-filer rate (12%). Non-filers exist but are rare. The tool now asks (Tenth Schedule rule 1). |
| Does our Twelfth Schedule class by code match Customs? | Yes for 342 of 345 codes (14,142 lines). Three codes differ; 8532.2900 (193 lines) is split between Part II and Part III treatment, which suggests an importer-specific rule (Part III goods imported as raw material for own use are treated as Part II under the second proviso to s.148(1)). |
| Sales tax rates seen | 18% on 12,836 lines, 25% on 1,075, 10% on 254. |
| ACD rates seen | 2% (2,067 lines), 4% (4,567), 6% (897), 11% (205), a few other. |

## 4. Open items found
* **ACD 11%.** About ten automotive electrical codes (8507.1010, 8511.xxxx, 8512.xxxx, 8536.5021, 8544.3011 and similar) were charged 11% additional customs duty in February 2026, and WeBOC shows 11% for 4008.1110, 4011.2011, 8421.3110 in FY2026-27. SRO 1151(I)/2025 and SRO 1063(I)/2026 (read from the page images) contain no 11% rate, and the lines name no ACD notification. Question for a clearing agent or FBR (OQ-W1). SRO 1151 also skips clause (iii) (the 25% slab; OQ-A3-2): no 25% slab line occurs in this Chapter 85 extract, so the data cannot say what (iii) holds.
* **Income-tax importer category.** Some lines of Part III goods are charged 2% (Part II treatment) for what looks like a manufacturer importing raw material for its own use. The tool cannot know this from the code; it should ask a manufacturer which goods are covered by the Board's notification.
* **Income-tax base.** Some lines show 6.35%, 6.48% or 5.82% of our base, so Customs used a slightly larger base (possibly a notified minimum value, s.148(6A)). Not yet explained.
* **Regulatory duty differences** on a few lines (24 of 1,500): not yet analysed.

## 4b. How noisy are the declared codes? (measured from the file itself, no human review)
For descriptions typed identically (after removing numbering, weights and quantities) by at least two different importers: 353 descriptions, 1,646 lines (11% of lines; the rest of the 10,096 distinct descriptions are used once).
* All importers used the **same 8-digit code for 72%** of these descriptions, the same 6-digit code for 76%, the same 4-digit heading for 95%.
* So at the exact Pakistan line, importers disagree with each other for about 28% of the *same* product words (mostly choosing between neighbouring national lines, for example "other" against a specific line). At most one of two disagreeing declarations can be right.
* If a system always picked the majority code for such a description it would match the declared code on only about 91% of those lines. Matching declared labels exactly therefore has a ceiling well below 100% on the exact line, and a measured 42% for the full agent is not as low as it first looks. It is still a lower bound against the truth, because declared codes include genuine mistakes.
* No importer, NTN or GD number is stored in this analysis; it ran in memory over the private file.

## 5. Limits
Chapter 85 only (electronics and electrical goods), one month, one importer's shipments (many importers and 5,484 GDs, but the file is one source). Declared codes are not verified. The importer facts used for the duty check are inferred, not known.
