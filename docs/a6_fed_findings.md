# A6 findings: federal excise duty (FED) on imported goods

Sources (data/raw, typeset PDFs with a text layer; PDF page index = printed page number in both files):
`FED26` = `20267171373633512FEDAct2005updatedupto30-06-2026.pdf` (103 pp, "as amended up to 30th June, 2026", Finance Act 2026 in red),
`FED25` = `202588138517680FEDAct,2005withindexupdatedupto30-06-2025.pdf` (105 pp, "up to 30th June, 2025", Finance Act 2025 in red),
`FA26` = `20266291261044366FinanceAct2026.pdf` (text layer), `FA25` = `2025629106147620FInanceAct2025.pdf` (scan, read as images), `SF` = `Salient-Feature.pdf`.
Every rate below was parsed from these documents; nothing from memory. AI readings of page images are **not owner verification**.

## 1. Verdict (plain)

**Partly.** Include FED in `compute_duty` for the goods whose rows are mapped to a code and whose inputs the tool can ask for; leave the rest as a visible warning.

| Goods | In compute_duty? | Why |
|---|---|---|
| Cement (2523), un-manufactured tobacco (2401), LNG / LPG / natural gas (2711.xxxx), flavours and concentrates (2106.9010, 3302.1010), incandescent bulbs (8539.2200, 8539.2990), lubricating oil (2710.1951-53, 1993), naphtha / white spirit / solvent oil (2710.1942, .1240, .1250) | **Yes** | Code-mapped, simple rate (percent, or Rs per kg / MMBTu / 100 m3 / liter), page-checked by two readers, FA2026 second source for the 2026 changes. Needs `quantity` in the printed unit, or the value. |
| Cars, SUVs, double-cabin pickups (8703, 8704.2190, 8704.3190), Table I S.No 55 / 55C and Table IA | **Partly** | Rates and engine-capacity bands are read correctly (page images, FA2026 text, red-text cross-check). But four legal points are not settled by the Act (section 4 below): electric vehicles appear in two serials, 3001 cc is in no band, the base of the Special Excise Duty, and no Board notification on collection of Table IA. Compute only when the caller gives CBU / cc (and, for electric, USD value) and show the answer as `needs_review` with those caveats. |
| Cigarettes (24.02) imported | **Partly** | S.No 8 = 65% of retail price or the S.No 9 rate (Rs 16,500 per thousand) whichever is higher; the Rs 16,500 is a printed reference, not in the row. Needs the printed retail price per pack and the number of sticks. |
| Aerated waters 2201.1020 / 2202.1010 (20% of retail price) | **Partly** | Needs retail price (s.12(4)); S.No 6 and S.No 59 (juices) have no code ("Respective headings"). |
| E-liquids, acetate tow, cigars, heated-tobacco mixture, nicotine pouches, filter rod, fans, fertilizers, day-old chicks, EV (S.No 55A) | **No (warn)** | Heading column prints "Respective heading(s)": stored `unmapped`, never matches a code. A customs expert must map them to codes (open question OQ-A6-3). The tool should ask "is this one of these goods?" using `description` text. |
| Third Schedule exemptions | **Never applied** | Conditional (importer, project, quota); listed as `possible_exemptions` only. |
| Services (Table II), supply-only rows (S.No 9, 10, 12, 55B, 55D, Table III sugar) | not imports | stored for completeness, `applies_to = local_only`. |

## 2. How FED applies to imported goods (Act text, `FED26` unless stated; same text in `FED25`, pages in brackets)

| Point | Section and page |
|---|---|
| FED is levied and collected on goods imported into Pakistan | s.3(1)(b), p.11-12 ("goods imported into Pakistan, irrespective of their final destination") |
| Rate: 15% ad valorem for everything, "except the goods and services specified in the First Schedule, which shall be charged ... as, and at the rates, set-forth therein" | s.3(1), p.12 |
| But goods not specified in the First Schedule are exempt from the whole of FED, so the 15% default never applies to an unlisted import | s.16(1), p.24 ("All goods imported, produced or manufactured ... except such goods ... as are specified in the First Schedule shall be exempt") |
| Charged and collected by Customs, same manner and time as customs duty, Customs Act s.31A applies | s.3(2), p.12 |
| Person liable: the importer | s.3(5)(b), p.13 |
| **Value base at import:** "the value determined in accordance with section 25 of the Customs Act, 1969, including customs duties payable thereon" | s.12(3), p.20 |
| Goods taxed on retail price: duty on the manufacturer's retail price inclusive of duties, charges and taxes other than sales tax, printed on the pack; the proviso applies the rule to imports ("goods liable to duty on local production as percentage of retail price ... if such goods are imported") | s.12(4) and proviso, p.20-21 |
| Table-I rate applies also to imports; the description in column (2) prevails over tariff classification | Interpretation (1)-(2) printed under Table I: FED26 p.78-79, FED25 p.81 |
| Special Excise Duty (SED): "in addition to duty imposed under sub-section (1)" on goods in Table-IA, "at the rates specified therein"; the Board may prescribe time, mechanism, procedure, mode and manner of collection | s.3(3B) (inserted by Finance Act 2026 s.6(2), FA26 p.64), FED26 p.13; Table-IA FED26 p.80 |
| Sales tax mode (duty collected as if sales tax): goods in the Second Schedule; FY2026-27 adds S.No 5 naphtha 2710.1942, white spirit/MTT 2710.1240, solvent oil 2710.1250 "imported and locally produced" | s.2(21a) p.10, s.7 p.17, Second Schedule FED26 p.87 (FA26 s.6(15), p.75) |
| Rate in force: s.10 says the rate of the date on which goods are supplied for home consumption (a local-supply wording); for imports the Act relies on the Customs Act collection rules (s.3(2)). | s.10(a), p.19 (see OQ-A6-6) |
| Exemptions: Third Schedule Table-I (goods), conditional, "no adjustment under section 6 admissible" | s.16(1) proviso p.24; Third Schedule FED26 pp.88-100. Import-relevant serials: 11 (carbon black oil, 2707.9910 / 2713.9010), 12, 13 (grants-in-aid), 14-15 (baggage), 17, 19, 21, 22 (Orange Line), 23 (diplomats, 99.01, 99.02, 99.05), 24, 25 (Export Facilitation Scheme), 26, 27, and new 28 (bulletproof vehicles, SCO summit, Finance Act 2026, p.100). Federal Government may exempt more by notification, s.16(2), p.24-25. |
| FED is part of the sales-tax and income-tax bases | Sales Tax Act s.2(46)(d) ("including the amount of customs-duties and federal excise duty"), ITO First Schedule Part II column (3): already cited in `docs/duty_formula.md`; section 5 there |

## 3. What was extracted (data/processed/a6_fed_rules.csv, table `fed_rules`, 174 rows)

| | FY2025-26 (valid 2025-07-01 to 2026-06-30) | FY2026-27 (valid 2026-07-01 to 9999-12-31) |
|---|---|---|
| printed items (S.No + sub-clause) | 62 | 71 |
| rows (one per code, heading or unmapped item) | 80 | 94 |
| Table I | 44 | 51 |
| Table IA (SED) | 0 | 6 |
| Table III (First Schedule, sugar supply) | 1 | 1 |
| Third Schedule Table-I goods (exemptions) | 35 | 36 |
| `needs_review` | 7 | 16 |
| unmapped ("Respective heading") | 25 | 29 |

Dates: both Finance Acts say "unless otherwise provided, come into force on the first day of July" (FA25 file p.2, FA26 p.2). Each consolidated file is treated as the snapshot valid for its fiscal year; FY2025-26 ends 30 Jun 2026 because the FY2026-27 file replaces it. **Not covered:** any change made by notification or supplementary Act during the year (no FED SRO is in `data/raw`).
Table II (services: advertisements, air travel, insurance...) is not loaded: services are not imported goods. Chapter 98 codes are not in the goods tariff.

### Validators (code; every finding is in `a6_fed_failures.csv`, nothing silently fixed)
| Check | Result |
|---|---|
| Every printed word of every row is on the cited page(s) of its own PDF | 0 failures |
| Codes exist in the tariff of the same fiscal year (8-digit in `tariff_*.json`, headings incl. Chapter 99) | 2 errors: Third Schedule S.No 6 prints 2710.1110, in neither tariff (row `needs_review`); 1 warning per year: S.No 35 prints 2711.1900, tariff has 2711.1910 / 2711.1990, stored as 6-digit prefix 271119 (`needs_review`); Chapter 99 not checkable for FY2025-26 (A1 parse has none; info) |
| Rate range (0-100 percent; amounts > 0) and one-decimal / half-step check (all percents are multiples of 0.5); printed digits equal words-to-number result | 0 failures |
| Serial continuity Table I: live + printed "omitted" serials cover 1..64 (FY2025-26) and 1..65 (FY2026-27) | 0 gaps |
| Row count / serial anchors: live serials found by coordinates (61 anchors 2026, 57 anchors 2025) vs spec | 0 missing; Third Schedule S.No 17 not found by the coordinate reader (footnote glued to the serial; text checked on the page image) |
| Second source: FA2026 text pp.72-76 contains every new word of the 26 changed or added FY2026-27 rows | 26 of 26 |
| Red text (Finance Act changes) vs diff of the two years | Table I red serials 2026 = {7a, 8a, 55, 55A, 55B, 59, 63, 65} = the diff exactly; 2025 red = {64} = FA25 s.11(8)(a) (page 118 image: new S.No 64 "Day Old Chick (DOC) Rs.10 Per DOC"; Table III S.No 1 omitted) |
| Engine-capacity band continuity | warning: S.No 55 prints (c) "1800cc to 3000cc" and (d) "exceeding 3001cc": 3001 cc is in no band (both years). Table IA (2000-3000, above 3000) has no gap |

### Spot check and second read
`data/processed/spotcheck_a6_fed.csv`: 51 of 174 rows (29%): every vehicle band, every changed row, specific and compound rates, exemption samples. AI second read: `data/processed/ai_second_read/spotcheck_a6_fed.csv` (**AI second reader, not owner verification**): 45 match, 6 unsure (S.No 35 code mapping both years, and Third Schedule rows whose page image was not viewed: FY2025-26 pp.92, 94, 98, 101). No mismatch. The 15 owner cards (`data/processed/review/fed_15_cards.html`) were read too; the owner check is still needed.

## 4. FY2025-26 versus FY2026-27 (data/processed/a6_fed_diff_2025_2026.csv)
| S.No | Change | Finance Act clause |
|---|---|---|
| 7a acetate tow | Rs 44,000 to Rs 10,000 per kg | FA26 s.6(14)(1)(a), p.72 (SF p.13 item 1.ii) |
| 8a e-liquid | "Rs 10,000 per kg or 65% of retail price whichever is higher" to "Rs 16,500 per kg" | FA26 s.6(14)(1)(b), p.72 (SF p.13 item 2.i) |
| 55, 55B | electric-vehicle words "till 30 June 2026" to "2027" | FA26 s.6(14)(1)(c), p.72 |
| 55A (new) | electric cars and SUVs imported CBU by USD value: 0% up to USD 75,000; 30% above 75,000 up to 110,000; 40% above 110,000 | FA26 s.6(14)(1)(d), p.72 |
| 59 | exclusion wording widened (hydration / electrolyte drinks) | FA26 s.6(14)(1)(e), p.73 (SF p.13 item 1.iii) |
| 63 | "Lubricating oil" to "Lubricating oil and base lubricating oils", 2710.1993 added | FA26 s.6(14)(1)(f), p.73 (SF item 2.iv) |
| 65 (new) | naphtha, white spirit/MTT, solvent oil Rs 80 per liter | FA26 s.6(14)(1)(g), p.73 (SF item 2.ii) |
| Table IA (new) | SED 86% (2000-3000 cc) / 92% (above 3000 cc) on imported cars, SUVs, EVs, double cabin pickups: 87.03, 8704.2190, 8704.3190 | FA26 s.6(14)(2), p.74-75; s.6(2), p.64 (SF item 2.iii, 2.v) |
| Third Schedule 28 (new) | bulletproof vehicles: SCO summit and counter-terrorism | FA26 s.6(16), p.75-76 (SF p.13 item 1.iv) |
Also in FA26 (not rates): Restriction-2 on cigarette brand variants (s.6(14)(1)(h)), Table II air-ticket rates, Second Schedule S.No 5. FA25 (FY2025-26): new S.No 64 DOC Rs 10 per DOC; Table III S.No 1 omitted; Third Schedule S.No 23 renumbered 27; s.3(5)(e) added (FA25 pp.116-118).
SF item "CKD kits for electric vehicles ... extended to 30.06.2027" is listed under FED but the only matching FED text is the "till the 30th day of June, 2027" words inside S.No 55 / 55B; no separate Third Schedule entry for CKD kits exists in `FED26`.
Table I 55 rates (2.5 / 10 / 30 / 40%) did not change between the two files.

## 5. Open questions (not resolved by the documents)
| ID | Question |
|---|---|
| OQ-A6-1 | **Electric vehicles.** S.No 55 still names "till the 30th day of June, 2027 electric vehicles (4 wheelers)" (cc bands, an EV has no cc) and S.No 55A (new, USD bands, "Respective Heading") covers imported electric cars and SUVs; Table IA also names electric vehicles. Which applies to an imported EV, and are they charged together? |
| OQ-A6-2 | **Base of the Special Excise Duty (Table IA) and of the FED on the FED.** s.12(3) gives V + customs duties for FED at import. Table IA is "in addition to" s.3(1) duty; the Act does not say whether SED is charged on V + customs duties only or also on the Table I FED. And whether "customs duties" means CD + RD + ACD (the same question as OPEN-2). |
| OQ-A6-3 | **Unmapped rows.** 54 rows print "Respective heading(s)". A customs expert should map them to tariff codes (e.g. fertilizers, e-liquids, day-old chicks). |
| OQ-A6-4 | Engine capacity 3001 cc (S.No 55): no band. Which rate applies? |
| OQ-A6-5 | Table IA: has the Board prescribed a collection mode under s.3(3B)? No notification is in `data/raw` (see `docs/chrome_prompt_fed.md`). |
| OQ-A6-6 | Which date fixes the FED rate for an import (Customs Act clearance date)? FED s.10(a) speaks of supply for home consumption. |
| OQ-A6-7 | S.No 8 cigarette import: confirm the "rate against S.No 9" is the Rs 16,500 per thousand (stored `needs_review`). |
| OQ-A6-8 | S.No 35: printed 2711.1900; confirm the mapping to 2711.1910 and 2711.1990. Third Schedule S.No 6 prints 2710.1110 (not in either tariff). |
| OQ-A6-9 | Mid-year FED notifications (SROs) for FY2025-26 / FY2026-27 are not in `data/raw`. |

## 6. Ready-to-apply spec for `compute_duty` (do NOT apply yet; `src/tools` untouched)

Store: `fed_rules` (docs/store_schema.md "A6 additions"), helper `src.store.resolve.get_fed_on_date(conn, code8, date)` returning `applicable_first_schedule`, `local_only_not_applied`, `possible_exemptions`.

1. After ACD, call `get_fed_on_date`. If `applicable_first_schedule` is empty: no FED line; add note `FED_unmapped_goods_check` when the code is in headings 2402, 8703, 8704 or the description may match an unmapped serial (see 5), because unmapped rows cannot match.
2. Choose the row(s) of each serial:
   * `cc_*` columns: ask `goods.engine_cc` (needs_input) when the rows carry bands; pick the row with `cc_ge <= cc` (or `cc_gt < cc`) and `cc <= cc_le`; if no band fits (3001) return `cannot_compute` citing OQ-A6-4.
   * `usd_*` (S.No 55A, only if mapped later): ask `goods.value_usd`.
   * Ask `goods.vehicle_form` CBU/CKD: S.No 55, 55C, Table IA say "imported" (CBU rows); for CKD say "FED for CKD not covered".
   * Several rows at the same specificity in one group: the caller picks by `applies_to` (drop `local_only`) and by band.
3. Line amount, by `rate_kind`:
   * `percent`, `rate_basis = ad_valorem`: `FED = pct/100 x (V + CD + RD + ACD)` (s.12(3), p.20).
   * `percent`, `rate_basis = retail_price`: `pct/100 x retail price` (needs `goods.retail_price_total_pkr`, s.12(4)); if missing: `needs_input`.
   * `specific`: `amount x quantity` in `rate_specific_unit` (no unit conversion; `needs_input` for quantity: kg, MMBTu, 100 m3, 100 MT, liter, 1000 cigarettes, fan, DOC).
   * `compound` (`higher_of`): compute the percent part and the specific part, take the larger (S.No 8, 8b, 8a of FY2025-26).
   * Table IA rows (`rule_group = FED-T1A`) are an additional line `SED`, base as ad valorem above until OQ-A6-2 is answered; flag `SED_base_open`.
4. `V_ST = V + CD + RD + ACD + FED (+ SED)`; `V_IT = V + CD + RD + ACD + FED + SED + ST + VAT` (replace the "FED not included" wording and the `FED_not_included` flag). Rows `needs_review` raise `review_required`.
5. Exemptions: list `possible_exemptions` in `possible_rules_not_applied` with their `condition_text`; apply only if `claimed_rules` names the row id.
6. Second Schedule goods (naphtha etc. S.No 65): FED in sales tax mode; mark `fed_sales_tax_mode` and do not claim adjustment; keep the Table I line.
7. Tests to add with the change: three hand bills (cement 25231000 per kg; 3302.1010 ad valorem on V + CD; 8703.2115 CBU 1500 cc 2026-07-15 incl. Table IA absent below 2000 cc and present at 2500 cc); date boundary 30 Jun vs 1 Jul 2026 (Table IA).

## 7. What the owner must do (plain steps)
1. Open `data/processed/review/fed_15_cards.html` in a browser. For each of the 15 cards compare the text with the page image (FED page numbers: cars FY2026-27 p.75; Table IA p.80; FY2025-26 cars p.79). Click Matches / Wrong / Not sure, then Save results and put the CSV in `data/processed/review_results/`.
2. Answer OQ-A6-1 (electric cars: p.74-75 and p.80 of `FED26`) and OQ-A6-2 (base of the Special Excise Duty) with a customs consultant or a real Goods Declaration of a car imported after 1 July 2026.
3. Run the Chrome prompt `docs/chrome_prompt_fed.md` to look for FED notifications (SROs) of FY2025-26 / FY2026-27, especially for vehicles and under s.3(3B).
4. Decide whether the 54 "Respective heading" rows should be mapped to codes (needs someone who knows the tariff).
