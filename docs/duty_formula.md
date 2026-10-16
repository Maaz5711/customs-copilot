# Duty formula (DRAFT, A3): what each tax is charged on, and in what order

Status: DRAFT for owner review before `compute_duty` is coded. Every statement below cites the document and clause it comes from
(PDF page numbers are the page index of the file in `data/raw/`). Where the documents do not say something, this file says so
and marks it **OPEN**. No rate is written here from memory: rates live in the A3 CSV files and are quoted from them.
Scope: customs duty (CD), regulatory duty (RD), additional customs duty (ACD), sales tax (ST) and income tax collected at import (IT)
for FY2025-26 and FY2026-27. Federal excise duty (FED) and special customs duty (SCD) are named only where the law that governs the
other taxes mentions them.

## 1. The order, in one picture

```
V    = assessable value                              Customs Act s.25 (value of imported goods)
CD   = rate_CD  x V   (or specific Rs/unit)          Customs Act s.18(1) + First Schedule (Tariff, column CD)
RD   = rate_RD  x V                                  Customs Act s.18(3): "% of the value of such goods as determined under section 25"
ACD  = rate_ACD x V                                  Customs Act s.18(5): "% of value of such goods as determined under section 25"
FED  = Table I rate x base (see section 7 below); SED (Table IA) in addition
SCD  = (out of scope; Customs Act s.18A, never part of the sales tax base)

V_ST = V + CD + RD + ACD + FED                       Sales Tax Act s.2(46)(d)  (see OPEN-2 for RD and ACD)
ST   = rate_ST x V_ST                                Sales Tax Act s.3(1)(b), or the Schedule / SRO rate for the goods
                                                      (Third Schedule goods: rate x retail price, s.3(2)(a))

V_IT = V + CD + RD + ACD + FED + ST                  Income Tax Ordinance First Schedule Part II, column (3):
                                                      "of the import value as increased by customs-duty, sales tax and federal excise duty"
IT   = rate_IT x V_IT                                ITO s.148(1) and First Schedule Part II (rate by class of goods: Twelfth Schedule Part I/II/III;
                                                      higher rate for a commercial importer)
Total payable at import = CD + RD + ACD (+FED) + ST + IT
```

RD and ACD are each computed on V (the s.25 value) and are NOT computed on top of CD (not cascading): Customs Act s.18(3) and s.18(5) both say
"of the value of such goods as determined under section 25", and s.18(4)(a) / s.18(6)(a) say they are "in addition to" the duty under s.18(1).

## 2. Step by step with citations

| Step | What | Source (file, page, clause) |
|---|---|---|
| 1 | Assessable value V = value determined under section 25 of the Customs Act. The user supplies it. | `20268241784853463Customs-Act-1969.pdf` p.72-73 (s.25); s.18(3) and s.18(5) p.45 |
| 2 | CD: rate in the Tariff for the code and date (percent, or Rs per unit for the 54 specific lines). | `data/processed/tariff_2026_27.csv`, `tariff_2025_26.csv` (A1); Customs Act s.18(1) p.45 |
| 3 | RD: rate in the RD SRO in force on the date (1152(I)/2025 until 30 Jun 2026, 1064(I)/2026 from 1 Jul 2026); used vehicles also 40% (1898(I)/2025, from 1 Oct 2025) then 30% (1065(I)/2026), in addition. | A2 data; Customs Act s.18(3), s.18(4) p.45; `a3_instruments.csv` |
| 4 | ACD: the ACD notification in force on the date (1151(I)/2025 for 1 Jul 2025 to 30 Jun 2026, 1063(I)/2026 from 1 Jul 2026: 1063 para 1 "in supersession of ... S.R.O. 1151(I)/2025", para 4 effect 1 Jul 2026, page 1-2). The rate depends on the code's **tariff CD slab** (first column of the Tariff): 1063 gives 2% for the 20% slab (4% for 36 listed codes), 2% for 97 listed codes, 4% for slabs of 25% and above and specific-rate slabs (6% for 17 listed codes, 2% for 14 listed codes); 1151 gives 2% for the 15% slab, 4% for 20%, 6% for 30% and above and specific-rate slabs (2% for 14 listed codes), 2% for 95 listed codes. The value is "the value as determined under section 25 or section 25A" (para 2, page 2 of both SROs). Para 3 lists imports on which ACD is **not levied** (Chapter 84/85 plant and machinery, Chapter 99, Fifth Schedule except listed serials, Baggage Rules, SROs 577/565/693/492/678, CKD cars up to 1,000cc and CBU vehicles up to 850cc, PCT codes 8703.8030, 8711.6040, 8711.6060). | `data/processed/a3_acd_rules.csv` (extractor `src/ingest/a3_acd.py`); `20266301763307131063-2026.pdf` p.1-2, `202572975414701SRO1151OF2025.pdf` p.1-2; Customs Act s.18(5)-(6) p.45-46. Proviso to s.18(5): cumulative CD and ACD must not exceed rates agreed under multilateral trade agreements (not checked by the tools). |
| 5 | Sales tax base V_ST = V + CD + RD + ACD + FED. For goods in the Third Schedule the base is the retail price printed on the pack (s.3(2)(a)). | Sales Tax Act (30.06.2026 file) s.2(46)(d) p.25, s.3(2)(a) p.29; FY2025-26 file same text (s.2(46) p.24-25, s.3 p.27-29) |
| 6 | Sales tax rate, first match wins in this order: (a) exemption in the Sixth Schedule Table-1 (a3_st_sixth_schedule); (b) Ninth Schedule Table-II (cellular mobile phones: 18% ad valorem, or 25% for CBU above US$ 500 at import/registration; Sales Tax Act p.216); (c) Eighth Schedule reduced rate (s.3(2)(aa)); (d) SRO 297(I)/2023 Table-I 25% (goods listed; **not** for Eighth Schedule goods, SRO 297 para 2 Explanation); (e) Third Schedule retail-price rule (18% of retail price); (f) standard rate 18% (s.3(1)(b)). **The order among (a)-(f) is my reading of the Act; the Act does not state a precedence list: OPEN-3.** | Sales Tax Act s.3(1)(b) p.28, s.3(2)(a) p.29, s.3(2)(aa)-(b) p.30, s.3(3B) p.31; SRO 297(I)/2023 pp.1-5 and Explanation p.5; schedules: `a3_st_*` files |
| 7 | Further tax (s.3(1A), 4%): charged on taxable SUPPLIES to unregistered persons. The Act does not say it is collected at import. Not part of the import calculation unless a source is found (OPEN-4). | Sales Tax Act s.3(1A) p.28 |
| 8 | Income tax: collected by the Collector of Customs on the import value increased by customs-duty, sales tax and federal excise duty, at the Part II rate for the class of goods (Twelfth Schedule Part I = 1%, Part II = 2% or 3.5% for a commercial importer, Part III = 5.5% or 6% for a commercial importer). Collected at the same time as customs duty (s.148(5)). It is a minimum tax (s.148(7)) except for an industrial undertaking importing for its own use. | ITO (30.06.2026 file) s.148(1) p.329, s.148(5) p.330, s.148(7) p.331; First Schedule Part II pp.550-553; Twelfth Schedule pp.811-832. FY2025-26 file: s.148 p.323-327, Part II p.533-537. |
| 9 | Third Schedule goods: for income tax the "value of goods" is the retail price increased by the sales tax payable in respect of the import and taxable supply. | ITO s.148(9) "Value of goods" (a) p.332 |

The rate tables behind steps 6 and 8 are in the A3 CSV files named in `docs/a3_findings.md`. For each date the tools must pick the row whose
`valid_from <= date <= valid_to` (never open-ended guesses): see the dating convention in `docs/a3_findings.md`.

## 3. Worked arithmetic shape (no rates, no numbers from memory)

Let V be the assessable value in rupees. With rates `c, r, a` (percent) from the Tariff, the RD SRO and the ACD SRO for the code and date, and
`s`, `i` from the sales tax and income tax tables:

```
CD = c/100 * V            RD = r/100 * V            ACD = a/100 * V
V_ST = V + CD + RD + ACD  (+ FED)
ST = s/100 * V_ST
V_IT = V + CD + RD + ACD (+ FED) + ST
IT = i/100 * V_IT
Total = CD + RD + ACD + ST + IT
```
For a specific duty (Rs per unit) replace `c/100 * V` by `amount * quantity`; RD/ACD/CD specific rules are in the Tariff and SRO tables (A1, A2).
For a Third Schedule good replace V_ST by the retail price R: ST = s/100 * R, and V_IT = R + ST (ITO s.148(9)).
Rounding rules (to the rupee or paisa) are not in any provided document: **OPEN-5**.

## 4. Open questions that block "done" (need a human with the law or a real Goods Declaration)

- **OPEN-1 Federal excise duty (A6: data now in `fed_rules`, see section 7 and `docs/a6_fed_findings.md`; not yet in `compute_duty`).** s.2(46)(d) (sales tax) and Part II column (3) (income tax) both add "federal excise duty" to the base, and the budget
  salient features 2026-27 mention new FED on luxury vehicles. The Federal Excise Act and its First Schedule are not in `data/raw/`, and FED is outside the
  stated v1 scope. Until supplied, V_ST and V_IT omit FED and the tool must warn for vehicles and other FED goods.
- **OPEN-2 Are RD and ACD part of "customs-duties" in s.2(46)(d)?** The Sales Tax Act text says "including the amount of customs-duties and federal excise duty"
  and does not define "customs-duties". Customs Act s.18A (special customs duty) says SCD is not part of the value of supply, which implies that the other
  s.18 duties (CD, RD, ACD) are. This is the reading used above but it is an inference: confirm against a real sample Goods Declaration.
- **OPEN-3 Precedence between the sales tax rate sources** (exemption, Ninth, Eighth, SRO 297, Third, standard). Only SRO 297 para 2 states one rule (Eighth beats 297).
- **OPEN-4 Further tax on imports by unregistered persons.** Searched the Sales Tax Act (both snapshots), schedules and the SROs in `data/raw/` for
  "further tax", "unregistered": the only rule is s.3(1A) on supplies. If Customs does collect further tax at import, its source is not in the documents.
- **OPEN-5 Rounding** of each tax line is not stated anywhere in the provided documents.
- **OPEN-6 Sugar window** (SRO 1217/1216/527/455/663): windows A (8 Jul to 21 Sep 2025) and B (22 Sep to 30 Nov 2025) are read from the SRO pages; the 527/455 window (issued 19 Mar / 5 Mar 2026, rescinded by 663 on 22 Apr 2026 "with immediate effect", `2026423042643455SRO663.pdf` p.1) and the position after the rescission are stored `needs_review`: see `docs/a3_findings.md` section 3 and `docs/owner_questions.md` OQ-A3-3. Sugar rows name no PCT code, so a code lookup never returns them; they are reached by SRO number.
- **OPEN-7 Income tax and filer status (CORRECTED 2026-10-16: filer status IS needed).** Section 148 says "every importer" and the Part II table (ITO 30.06.2026 file, pdf pp.550-552) has no filer column, but the Tenth Schedule rule 1 ("Rules for persons not appearing in the active taxpayers' list", same file pdf p.798, in-file p.779; 20.02.2026 and 31.07.2025 files pdf p.780) says that where tax is collected from a person not on the Active Taxpayers' List "the rate ... shall be increased by hundred percent". Section 148 is not among its exceptions (those are s.231B, 236K, 236C, 236G, 236H). So income tax at import = Part II rate, doubled for a non-filer: for a commercial importer of Part III goods 6% (filer) or 12% (non-filer). FBR's Withholding Income Tax Rate Card TY2027 (https://download1.fbr.gov.pk/Docs/202681113864992WithholdingTaxRatesCard2027.pdf) prints the same ATL / Non-ATL rates, and the official WeBOC duty calculator shows 12% (it assumes a non-filer). Earlier versions of this document read the Part II table only and concluded filer status was not needed: that was wrong. The tool now asks `importer.active_taxpayer` and doubles the rate when false, citing the Tenth Schedule (hand case 11 in tests/test_tools.py: 761,760.00 for non-filer vs 667,380.00 for filer). The other split is "commercial importer" (3.5% Part II, 6% Part III) plus provisos (a)-(c) (manufacturers under rescinded SRO 1125(I)/2011 1%, finished pharmaceuticals 4%, CKD kits of EVs 1%) and mobile phones (cannot_compute). The SRO 1125(I)/2011 item list is not in data/raw (OPEN-8).
- **OPEN-8 Part II provisos without codes.** Provisos (a)-(c) name importer classes, not PCT codes, so they cannot be matched by code alone: the tool must ask the user.
- **OPEN-9 Twelfth Schedule order.** Part III is the residual class ("goods not specifically mentioned in Part I or II"): test Part I and Part II (with their "except" codes) first.

## 5. How the store answers each step (what `compute_duty` may rely on)

All lookups use `get_rule_on_date(conn, table, 8-digit code, date)` (exact code, no LLM). Rules of one `rule_group` compete (longest code prefix wins);
different groups are cumulative and all come back. Rows still need a caller decision where the flags say so.

- **ACD** (`acd_rules`): read the code's CD from `tariff_lines` for the same date. Keep rows whose `condition_text` starts `SLAB_EQ n` / `SLAB_GE n` only when the CD
  matches (a specific-rate line counts as "slab of specific rates"). Rows with `rate_kind='exempt'` are the para 3 not-levied clauses; a clause whose
  `condition_text` says ONLY applies only if that import regime is true (the store cannot tell). Rows `needs_review` are the CKD vehicle mapping (87.03/87.04 are an
  inference: the SROs print vehicle classes, not PCT codes). Convention is written at the top of `src/ingest/a3_acd.py`.
- **Sales tax and income tax**: rows that name goods only by description (Third, Sixth, Eighth Schedule, Twelfth Schedule exclusions) are stored `unmapped` so they can
  never match unrelated codes; the tool must reach them by text search and ask the user (Sales Tax Act Sixth Schedule Table-1 S.No 133, p.169-172, prints entries as "Respective
  headings" without a code). Rows with `match_level='all'` are true general rules (s.3 standard rate, s.148 text, Part II class rates).
- **SRO 297(I)/2023 Table-II** is a rule for the supply of locally made vehicles, not for imports. From 13 Sep 2026 SRO 1525(I)/2026 adds the proviso that Table-II
  "shall not apply to locally manufactured hybrid electric vehicles with engine capacity upto 2000cc" (`20269141794445366SRO1525.pdf` p.1): the Table-II rows
  carry this in `condition_text` and an exempt row of group `ST-SRO297-T2-1525-HYBRID` is cited to SRO 1525 itself. SRO 1525 prints no S.No or code rows.
- **Section 53A ITO** (inserted by Finance Act 2026, effective 1 Jul 2026): the Federal Government may reduce the rate of withholding taxes in the nature of minimum
  tax in the First Schedule, other than s.113, "by one percent on the basis of economic viability" (text starts at the bottom of p.126 and continues on p.127 of
  `2026724177725705IncomeTaxOrdinanace2001.pdf`). Whether this reaches s.148 is not stated, and "by one percent" is not interpreted (percentage point or percent of the rate).
  It is stored as a `conditional` row; no notification under it is in `data/raw/`. The tool must not apply a reduction.
- **Time-limited clauses.** The Second Schedule clauses 12B, 12C, 12H, 12K, 12M, 123 and 124 end between Sep 2020 and Feb 2023 (their own text, `a3_it_s148_special_rules.csv`),
  so none is loaded. Sixth Schedule Table-1 S.No 152 ends 30 Jun 2026 ("till [30th June, 2026]", p.176) and Twelfth Schedule conditions (2)(xi), (2)(xii) end 30 Jun 2026
  (p.226): all three are loaded with `valid_to = 2026-06-30`.
- **Legal notes** (`legal_notes`) are the HS 2022 texts printed in the FBR tariff PDF. Their validity 2025-07-01 to 9999-12-31 is an assumption, stored in the
  `hs_edition` field as "applicability to FY2025-26 and FY2026-27 assumed, not proven". Cite by reference only (WCO Explanatory Notes are not copied).

## 6. B3 additions (what `compute_duty` does, and what it found that this file had missed)
* **Value addition tax (new, OPEN-10).** Sales Tax Act s.7A(2) and the Twelfth Schedule (PDF p.39 and p.225-226 of the 30.06.2026 file): "3% ad valorem" levied at import "in addition to the tax chargeable under section 3", on all taxable goods,
  not charged on the exclusions of condition (2) (raw material and intermediate goods of a manufacturer for in-house use, Chapter 27 petroleum for a licensed OMC, registered service providers' in-house use, phones 8517.1419/8517.1430/8517.1390,
  LNG, second-hand clothing 6309, gold and silver, Third Schedule goods taxed on retail price, plant and machinery of Chapters 84/85 imported by a manufacturer, motor cars up to 850cc, EV items until 30 Jun 2026). The Schedule names no base.
  The tool takes it on V_ST and counts it as sales tax inside V_IT. This is a reading, not text of the law (OQ-B3-1).
* **Order of the sales-tax rate (OPEN-3).** Exemption (Sixth Schedule) > Eighth Schedule (s.3(2)(a) says the Eighth Schedule rate replaces 18% for Third Schedule goods) > SRO 297(I)/2023 Table-I (25%; para 2 Explanation: not for Eighth Schedule goods) > standard 18% (s.3(1)).
  Third Schedule goods change the BASE (retail price), not the rate. SRO 297 Table-II is a supply rule for locally made vehicles and is never applied to imports (section 5 above).
* **Rounding (OPEN-5).** Convention only: half-up to 0.01 per line, rounded amounts feed the next base.
* **Further tax (OPEN-4)** is reported but not added to the total.
* **Used vehicles.** SRO 1898 (40%, 1 Oct 2025 to 29 Jun 2026) and SRO 1065 (30%, from 30 Jun 2026) are separate "in addition" lines on V, applied only when the caller says the import is a used-vehicle commercial import under the Import Policy Order clause (xvi).
* **ACD slab.** SLAB_EQ n needs tariff CD = n; SLAB_GE n needs tariff CD >= n or a specific-rate line. Rows with an `except` list in the same SRO are carved out by the store before the slab test.
Full list of inputs, statuses and limits: `docs/tools.md`.

## 7. FED at import (A6, DRAFT; implemented in `compute_duty` via `src/tools/fed.py`, spec in `docs/a6_fed_findings.md` section 6)
Files: `FED26` = `20267171373633512FEDAct2005updatedupto30-06-2026.pdf`, `FED25` = `202588138517680FEDAct,2005withindexupdatedupto30-06-2025.pdf`. Rates are in table `fed_rules` (`a6_fed_rules.csv`).
```
FED_T1  = rate x base      base = V + CD + RD + ACD            FED Act s.12(3) p.20 "value ... section 25 of the Customs Act ... including customs duties payable thereon"
                           retail-price goods: base = retail price on the pack (s.12(4) and proviso p.20-21); specific rates: Rs x quantity
SED     = Table IA rate x base (additional to FED_T1)          s.3(3B) p.13, Table-IA p.80 (base not stated: open, OQ-A6-2)
V_ST    = V + CD + RD + ACD + FED_T1 + SED                     Sales Tax Act s.2(46)(d) p.25 (FED is named in the value of supply)
V_IT    = V + CD + RD + ACD + FED_T1 + SED + ST (+VAT)         ITO First Schedule Part II column (3) "customs-duty, sales tax and federal excise duty"
```
* Levy and collection: s.3(1)(b) p.11-12; collected by Customs like customs duty, s.3(2) p.12; importer liable, s.3(5)(b) p.13. Goods not in the First Schedule are exempt, s.16(1) p.24 (so the 15% default of s.3(1) never applies to an unlisted import).
* Order: FED comes after CD, RD, ACD and before sales tax and income tax. The statement "FED included in the sales tax and income tax bases" is in the two laws already cited above (sales tax s.2(46)(d), ITO Part II); nothing in the FED Act changes the sales-tax or income-tax base wording, so sections 1-3 above stay as written with FED no longer "out of scope".
* Whether "customs duties" in s.12(3) includes RD and ACD is the same inference as OPEN-2.
* Tables: First Schedule Table I (rates, `FED26` pp.70-78, `FED25` pp.72-81), Table IA (SED, new from 1 Jul 2026, `FED26` p.80), Third Schedule (conditional exemptions, `FED26` pp.88-100), Second Schedule (sales tax mode, p.87). Interpretation under Table I: description prevails over tariff classification, rate applies to imports (`FED26` pp.78-79).
* Rounding and date of rate: not stated for imports (OQ-A6-6).
* **As implemented.** FED = rate x (V + CD + RD + ACD) for ad valorem rows (s.12(3) p.20); x retail price for retail-price rows (s.12(4) p.20-21); Rs x quantity for specific rows; larger of the two parts for compound rows. SED (Table IA) uses the same base and is a separate line (OQ-A6-2 shown as the alternative amount in the line note). V_ST adds FED and SED (Sales Tax Act s.2(46)(d) p.25); V_IT adds FED, SED, ST and VAT (ITO First Schedule Part II col. 3). Each line is rounded half-up to 0.01 and the rounded amount feeds the next base. Third Schedule goods keep the retail-price base for sales tax; their FED line is still computed.
* **Mapping of 'Respective heading(s)' rows** (`data/processed/a6_fed_mapping.csv`): 16 of 54 rows (S.No 7a acetate tow, 8a e-liquid, 8b cigars, 8c heated tobacco, 8d nicotine pouches, 60 fans, 62 fertilizers, 64 day-old chicks, in both years) are mapped by description match to tariff codes or headings, status needs_review, owner has not verified. Left unmapped: 6, 56, 59, 55A (ambiguous or OQ-A6-1), Third Schedule rows (exemptions by importer or project, not goods) and Table III sugar (local supply). Cigars (2402.1000) now take S.No 8b instead of the cigarette row S.No 8, which matches the whole heading 2402.

## 8. Customs-duty concessions: Fifth Schedule and China-Pakistan FTA Phase II (A7/A8; `src/tools/concessions.py`, findings `docs/concessions_findings.md`)
A concession changes **only the customs duty line** (CD). It is an option shown next to the normal bill and is applied only if the caller lists its rule id in `claimed_rules` (China FTA: `goods.claim_china_fta=true`, plus `goods.origin_country` China and `goods.has_certificate_of_origin=true`).
```
CD_normal     = tariff CD% x V (or specific)                                   Customs Act s.18(1), First Schedule
CD_fifth      = rate of the Fifth Schedule entry x V                           Customs Act s.18(1A) p.45: "customs duties shall be levied at such rates ... as are prescribed in the Fifth Schedule, subject to such conditions"
CD_china_fta  = min(tariff CD%, rate in the SRO column of the year) x V        SRO 1640(I)/2019 p.1: exempt "from so much of the customs duty ... as is in excess of the rates specified in columns (4) to (18)"
```
* **Which rate (Fifth Schedule).** One printed rate: that rate. Several printed rates ("0%,3%,5%", Part I note (iv), Explanations I-IV pp.2-3; Part II note (v) p.23): the lower rates (0%, 3%, 11%) apply only to goods whose First Schedule CD is that same rate; goods in any higher slab pay the **last** (maximum) printed rate. Example "0%,3%,5%": CD 0 -> 0, CD 3 -> 3, CD 11/16/20 -> 5. A tariff CD below the maximum that is not a listed slab keeps the normal rate (assumption, OQ-A7-4). "50% of the prevailing rate" = 50% of the tariff CD (S.No 39 tourism, EV CBU).
* **Which rate (China FTA).** The column of the calendar year of the import date: 1-Jan-2025 column (Year 6) for Jul-Dec 2025, 1-Jan-2026 (Year 7) for 2026, 1-Jan-2027 (Year 8) for Jan-Jun 2027. The importer pays the lower of the normal CD and that rate.
* **Other taxes after a concession.** RD: unchanged (its own SRO). **ACD:** Fifth Schedule goods are "not levied" under ACD SRO para 3(iii) (SRO 1063(I)/2026 and 1151(I)/2025, p.2), except Part I serials 30, 33, 35 and Part III serials 102, 111, 116 (except xvi), 117, 118 (and 110 in 2025-26): the tool reads the exclusion list from the stored clause. China FTA goods: ACD stays (the SRO exempts customs duty only; the ACD slab test uses the First Schedule CD of the code). **Sales tax, value addition tax, income tax:** same formulas, with the CD actually paid in V_ST and V_IT (so the bases fall by the CD saved, then by the sales tax saved).
* **Not checked by the tool (shown as questions/conditions):** local-manufacture list, chief-executive certificate, sector certificates, no-resale conditions (Fifth Schedule); Chinese origin, Form E certificate, Rules of Origin (SRO 1640 proviso). A claimed concession is flagged `concession_applied_conditions_unchecked` and `review_required`.
* **Not in scope:** other FTAs/PTAs (Malaysia, Indonesia, Sri Lanka, SAFTA, Iran, Mauritius, Uzbekistan, Afghanistan), concession SROs naming no code, the FY2025-26 amendments of SRO 1640(I)/2019 (OQ-A8-1).
