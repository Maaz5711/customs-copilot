# AI second read: summary

**These are AI readings of the page images, NOT owner verification.** The AI (Claude) read each cited page image first and compared afterwards. A "match" means the AI saw the same value on the page. It is not proof. Dot-less rate cells (OCR risk) were checked on enlarged crops. Please still do your own spot check.

Crucial RD rows (12 ids) and SRO 1064 pages 1-8 were skipped on purpose. The *_failures sheets were not read (mapping decisions).

Some `a3_it` rows are legal clauses, not values. For those a match means: the clause is on the cited page and says what the parsed text says.

## Counts per sheet

| Sheet | Rows | match | mismatch | unsure |
|---|---|---|---|---|
| spotcheck_a3_it | 163 | 162 | 0 | 1 |
| spotcheck_a3_sro | 106 | 99 | 0 | 7 |
| spotcheck_a3_st_other_schedules | 71 | 68 | 0 | 3 |
| spotcheck_a3_st_sixth_schedule | 69 | 60 | 0 | 9 |
| spotcheck_a3_st_sixth_table3 | 15 | 15 | 0 | 0 |
| spotcheck_legal_notes | 80 | 80 | 0 | 0 |
| spotcheck_sro_1064_rd | 41 | 41 | 0 | 0 |
| spotcheck_tariff_2026_27_specific | 54 | 54 | 0 | 0 |

## Rows to review (every mismatch and unsure row)

No mismatches found. Unsure rows below.

### spotcheck_a3_it

- **unsure** `r123:p126:s.53A(1):Income Tax Ordinance 2001, s` (page 126): parsed `s.53A(1) | Income Tax Ordinance 2001, section 53A (inserted b | reduction of up `. Section 53A starts at the bottom of the cited page and ends "by one"; the next page (not cited) continues "percent on the basis of economic viability". Literal text is "reduce the rate ... by one percent", not "up to 1 percentage point"; the parsed wording adds up to and percentage point, which is an interpretation. Also only the first page is cited
### spotcheck_a3_sro

- **unsure** `r91:p1:S1:87.03` (page 1): parsed `87.03 | twenty five percent | valid 2026-09-13 to 9999-12-31`. the parsed row (S.No 1, code 87.03, from 2026-09-13) is not printed on the cited page; it is the carried-over Table-II with SRO 1525 as the new source. The legal reading is plausible but the hybrid carve-out (upto 2000cc) is not represented in the parsed row, so a hybrid vehicle would be wrongly taxed at 25 percent. Owner decision
- **unsure** `r93:p1:S2:87.03` (page 1): parsed `87.03 | twenty five percent | valid 2026-09-13 to 9999-12-31`. the parsed row (S.No 2, code 87.03, from 2026-09-13) is not printed on the cited page; it is the carried-over Table-II with SRO 1525 as the new source. The legal reading is plausible but the hybrid carve-out (upto 2000cc) is not represented in the parsed row, so a hybrid vehicle would be wrongly taxed at 25 percent. Owner decision
- **unsure** `r95:p1:S3:87.04` (page 1): parsed `87.04 | twenty five percent | valid 2026-09-13 to 9999-12-31`. the parsed row (S.No 3, code 87.04, from 2026-09-13) is not printed on the cited page; it is the carried-over Table-II with SRO 1525 as the new source. The legal reading is plausible but the hybrid carve-out (upto 2000cc) is not represented in the parsed row, so a hybrid vehicle would be wrongly taxed at 25 percent. Owner decision
- **unsure** `r97:p1:S:white crystalline sugar (no PC` (page 1): parsed `white crystalline sugar (no PCT code printed) | 0.25% (reduced from eighteen per`. 28 Feb 2026 read OK; valid_from 2025-12-01 is derived, not printed. SRO 663(I)/2026 (22 Apr 2026, read) rescinds SRO 527 and SRO 455, so whether this window should be stored as valid is a legal decision for the owner. 0.25% is on SRO 1217, not this page
- **unsure** `r98:p1:S:white crystalline sugar (no PC` (page 1): parsed `white crystalline sugar (no PCT code printed) | 0.25% of the value of commercial`. 0.25% read OK, but the handwritten date on the page reads like 24th July 2025, not 8th. SRO 455, SRO 1833 and the Ordinance footnote all call SRO 1216 dated 08.07.2025, which is what valid_from 2025-07-08 uses. Nov 30 end date is supported by SRO 1833(I)/2025 (22 Sep 2025, read)
- **unsure** `r99:p1:S:white crystalline sugar (no PC` (page 1): parsed `white crystalline sugar (no PCT code printed) | 0.25% of the value of commercial`. 28 Feb 2026 read OK; valid_from 2025-12-01 is derived, not printed. SRO 663(I)/2026 (22 Apr 2026, read) rescinds SRO 455 and 527, so the extended window is doubtful. 0.25% is on SRO 1216, not this page
- **unsure** `r100:p1:S:white crystalline sugar (no PC` (page 1): parsed `white crystalline sugar (no PCT code printed) | exempt from the whole of customs`. exemption, 0.500 MMT and 8 July read OK. Parsed valid_to 2025-11-30 is not supported by this page (it prints 30 Sep 2025); SRO 1832/1833 extend only the sales tax and income tax twins (1217, 1216) and no extension of SRO 1215 is in data/raw
### spotcheck_a3_st_other_schedules

- **unsure** `r27:p211:eighth:both:84(i):3213.1000` (page 211): parsed `3213.1000 | 10%`. on p.211 the rate cell next to (i) Colors in sets (3213.1000) is empty and has its own border; 10% is printed only beside (ii)-(vii). Parsed gives 10% for (i): probably the intended reading of the serial but it is not literally printed beside (i). Owner decision
- **unsure** `r69:p226:twelfth:both:(2)(xi):` (page 226): parsed ` | value addition tax under the Table is not charged on these goods/importers`. clause is printed with an end date of 30 June 2026, so it should not run into FY2026-27; the sheet row is snapshot both and shows no end date, so I could not confirm valid_to. Check the stored valid_to is 2026-06-30
- **unsure** `r70:p226:twelfth:both:(2)(xii):` (page 226): parsed ` | value addition tax under the Table is not charged on these goods/importers`. clause is printed with an end date of 30 June 2026, so it should not run into FY2026-27; the sheet row is snapshot both and shows no end date, so I could not confirm valid_to. Check the stored valid_to is 2026-06-30
### spotcheck_a3_st_sixth_schedule

- **unsure** `r35:p169:S133:Respective headings` (page 169): parsed `S.No 133 | Respective headings | Exempt`. I count 11 printed Respective headings entries in the S.No 133 list but the sheet has 9 such rows (rows 35-43 are identical). Either two are missing or some are merged. Owner to check the count once for all nine rows
- **unsure** `r36:p169:S133:Respective headings` (page 169): parsed `S.No 133 | Respective headings | Exempt`. I count 11 printed Respective headings entries in the S.No 133 list but the sheet has 9 such rows (rows 35-43 are identical). Either two are missing or some are merged. Owner to check the count once for all nine rows
- **unsure** `r37:p169:S133:Respective headings` (page 169): parsed `S.No 133 | Respective headings | Exempt`. I count 11 printed Respective headings entries in the S.No 133 list but the sheet has 9 such rows (rows 35-43 are identical). Either two are missing or some are merged. Owner to check the count once for all nine rows
- **unsure** `r38:p169:S133:Respective headings` (page 169): parsed `S.No 133 | Respective headings | Exempt`. I count 11 printed Respective headings entries in the S.No 133 list but the sheet has 9 such rows (rows 35-43 are identical). Either two are missing or some are merged. Owner to check the count once for all nine rows
- **unsure** `r39:p169:S133:Respective headings` (page 169): parsed `S.No 133 | Respective headings | Exempt`. I count 11 printed Respective headings entries in the S.No 133 list but the sheet has 9 such rows (rows 35-43 are identical). Either two are missing or some are merged. Owner to check the count once for all nine rows
- **unsure** `r40:p169:S133:Respective headings` (page 169): parsed `S.No 133 | Respective headings | Exempt`. I count 11 printed Respective headings entries in the S.No 133 list but the sheet has 9 such rows (rows 35-43 are identical). Either two are missing or some are merged. Owner to check the count once for all nine rows
- **unsure** `r41:p169:S133:Respective headings` (page 169): parsed `S.No 133 | Respective headings | Exempt`. I count 11 printed Respective headings entries in the S.No 133 list but the sheet has 9 such rows (rows 35-43 are identical). Either two are missing or some are merged. Owner to check the count once for all nine rows
- **unsure** `r42:p169:S133:Respective headings` (page 169): parsed `S.No 133 | Respective headings | Exempt`. I count 11 printed Respective headings entries in the S.No 133 list but the sheet has 9 such rows (rows 35-43 are identical). Either two are missing or some are merged. Owner to check the count once for all nine rows
- **unsure** `r43:p169:S133:Respective headings` (page 169): parsed `S.No 133 | Respective headings | Exempt`. I count 11 printed Respective headings entries in the S.No 133 list but the sheet has 9 such rows (rows 35-43 are identical). Either two are missing or some are merged. Owner to check the count once for all nine rows

## Other things worth a look (rows marked match but with a caveat in the note)

- Tariff specific duties: 1404.9020, 7106.9110, 7106.9210, 7108.xxxx are printed as rotated, wrapped text (e.g. Rs. / 60 / 0/K / g), so the unit and digit grouping come from my reading; no decimal point appears. Parsed values with an inner space (Rs.80 00/MT etc.) must have the space removed.
- a3_it row 58: the schedule prints 5403.2010 in the table but a footnote says 5503.2010.
- a3_it clauses (12B), (12C), (12H), (12K), (12M), (123), (124) are time-limited and expired before FY2025-26; check their valid_to.
- a3_st_sixth S.No 152 (electricity, tribal areas) ends 30 June 2026; check valid_to.
- a3_sro rows 90-95: SRO 1525 prints no S.No/code rows; the hybrid vehicle carve-out is not in the parsed rows.
- SRO 663(I)/2026 rescinds SRO 455 and 527, which affects the Dec 2025 to Feb 2026 sugar rows.

## ACD sheet (spotcheck_a3_acd.csv): SRO 1063(I)/2026 and 1151(I)/2025

These are AI readings of the page images (re-rendered at 200 dpi from the scans), NOT owner verification. 67 of 82 rows were read; the 15 rows on the owner's hand-check cards (`acd_15_cards.html`) were skipped on purpose.

| Sheet | Rows read | match | mismatch | unsure |
|---|---|---|---|---|
| spotcheck_a3_acd | 67 | 67 | 0 | 0 |

No mismatch and no unsure rows. Points worth knowing (all marked match):

- Every listed code was found in the printed list under the cited clause with the stated percent. The 36 exception codes in 1063 (i)(a) and the 31 codes in 1063 (ii)(a)/(b)(i) were counted and agree with the store.
- Page 2 row for 1063 clause (ii) (4% on slab 25% and higher): the rate sentence is printed at the bottom of page 1; only the exceptions start on page 2.
- Heading codes 8703/8704 on the vehicle rows (clauses (ii)(b)(ii), (iv)(b), 3(x)) are a mapping of the printed words (cars, jeeps, LCV, heavy commercial vehicles); the headings themselves are not printed.
- 1151 3(iii) lists Part III S.No 110 as excluded; 1063 3(iii) does not. The store matches both.
- The CSV cells are cut at 80 characters, so the full parsed text of long rows was checked in `a3_acd_rules.json`.
