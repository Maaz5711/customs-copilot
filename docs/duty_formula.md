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
FED  = (out of scope, see OPEN-1)
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
| 2 | CD: rate in the Tariff for the code and date (percent, or Rs per unit for the 53 specific/compound lines). | `data/processed/tariff_2026_27.csv`, `tariff_2025_26.csv` (A1); Customs Act s.18(1) p.45 |
| 3 | RD: rate in the RD SRO in force on the date (1152(I)/2025 until 30 Jun 2026, 1064(I)/2026 from 1 Jul 2026); used vehicles also 40% (1898(I)/2025, from 1 Oct 2025) then 30% (1065(I)/2026), in addition. | A2 data; Customs Act s.18(3), s.18(4) p.45; `a3_instruments.csv` |
| 4 | ACD: rate in the ACD SRO (1151(I)/2025, then 1063(I)/2026). | A2 data; Customs Act s.18(5)-(6) p.45-46. Proviso to s.18(5): cumulative CD and ACD must not exceed rates agreed under multilateral trade agreements (not checked by the tools). |
| 5 | Sales tax base V_ST = V + CD + RD + ACD + FED. For goods in the Third Schedule the base is the retail price printed on the pack (s.3(2)(a)). | Sales Tax Act (30.06.2026 file) s.2(46)(d) p.25, s.3(2)(a) p.29; FY2025-26 file same text (s.2(46) p.24-25, s.3 p.27-29) |
| 6 | Sales tax rate, first match wins in this order: (a) exemption in the Sixth Schedule Table-1 (a3_st_sixth_schedule); (b) Ninth Schedule specific amounts (mobile phones); (c) Eighth Schedule reduced rate (s.3(2)(aa)); (d) SRO 297(I)/2023 Table-I 25% (goods listed; **not** for Eighth Schedule goods, SRO 297 para 2 Explanation); (e) Third Schedule retail-price rule (18% of retail price); (f) standard rate 18% (s.3(1)(b)). **The order among (a)-(f) is my reading of the Act; the Act does not state a precedence list: OPEN-3.** | Sales Tax Act s.3(1)(b) p.28, s.3(2)(a) p.29, s.3(2)(aa)-(b) p.30, s.3(3B) p.31; SRO 297(I)/2023 pp.1-5 and Explanation p.5; schedules: `a3_st_*` files |
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

- **OPEN-1 Federal excise duty.** s.2(46)(d) (sales tax) and Part II column (3) (income tax) both add "federal excise duty" to the base, and the budget
  salient features 2026-27 mention new FED on luxury vehicles. The Federal Excise Act and its First Schedule are not in `data/raw/`, and FED is outside the
  stated v1 scope. Until supplied, V_ST and V_IT omit FED and the tool must warn for vehicles and other FED goods.
- **OPEN-2 Are RD and ACD part of "customs-duties" in s.2(46)(d)?** The Sales Tax Act text says "including the amount of customs-duties and federal excise duty"
  and does not define "customs-duties". Customs Act s.18A (special customs duty) says SCD is not part of the value of supply, which implies that the other
  s.18 duties (CD, RD, ACD) are. This is the reading used above but it is an inference: confirm against a real sample Goods Declaration.
- **OPEN-3 Precedence between the sales tax rate sources** (exemption, Ninth, Eighth, SRO 297, Third, standard). Only SRO 297 para 2 states one rule (Eighth beats 297).
- **OPEN-4 Further tax on imports by unregistered persons.** Searched the Sales Tax Act (both snapshots), schedules and the SROs in `data/raw/` for
  "further tax", "unregistered": the only rule is s.3(1A) on supplies. If Customs does collect further tax at import, its source is not in the documents.
- **OPEN-5 Rounding** of each tax line is not stated anywhere in the provided documents.
- **OPEN-6 Sugar window** (SRO 1217/1216/527/455/663): see `docs/a3_findings.md`; legal effect of the rescinded SROs 527 and 455 is ambiguous.
- **OPEN-7 Income tax and filer status.** The Part II table in the ITO has no filer / non-filer column; the only status split is "commercial importer" (and, in the
  provisos, manufacturers under rescinded SRO 1125(I)/2011, finished pharmaceuticals, CKD kits of electric vehicles). Confirm there is no import-stage surcharge for
  persons outside the active taxpayer list in a provision this task did not read (the agent that read the ITO reports on this in `docs/a3_findings.md`).
