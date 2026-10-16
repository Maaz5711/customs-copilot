# Exact tools (B3): `lookup_code`, `get_applicable_sros`, `compute_duty`

Code: `src/tools/` (`lookup.py`, `sros.py`, `compute.py`, `rules.py`, `_util.py`, `mcp_server.py`). Tests: `tests/test_tools.py` (20 tests, 10 hand-computed bills).
No LLM is called anywhere in these tools. Every rate is read from the dated store (`data/processed/legal_store.sqlite`; the tools rebuild it with
`python -m src.store.build` if it is missing). Money and rates are strings (Decimal), never floats. Order and bases follow `docs/duty_formula.md`.

## Use

```python
from src.tools import lookup_code, get_applicable_sros, compute_duty
lookup_code("8471.3010", "2026-07-15")
get_applicable_sros("6109.1000", "2026-06-30")
compute_duty("9506.9911", 500000, "2026-07-15",
             importer={"registration_status": "registered", "commercial_importer": True, "active_taxpayer": True, "manufacturer_in_house_use": False})
```
MCP (stdio): `.venv/Scripts/python -m src.tools.mcp_server` (tool names `lookup_code`, `get_applicable_sros`, `compute_duty`; same arguments, JSON in and out).

## `lookup_code(code, as_of_date)`
`code` dotted or not. `status`: `found`, `not_found` (with `nearest_codes`, and `exists_in_other_fy`), `not_a_full_code` (4 or 6 digits: lists the 8-digit `children`),
`invalid_input`, `date_outside_store` (store covers 2025-07-01 to 2027-06-30). A found line has: `code`, `fy`, `description`, `description_levels` (heuristic split, display only),
`chapter`, `heading {code,text,page}`, `cd` (`plain` -> `rate_pct`; `specific` -> `amount_pkr` + `unit`; `compound` -> `raw` only), `row_status`, `flags`, `source_file`, `page`.
The tariff prints only CD; RD, ACD, sales tax and income tax come from the other two tools.
Example (abridged): `{"status":"found","code":"1507.1000","fy":"FY2026-27","cd":{"kind":"specific","amount_pkr":"10550","unit":"MT"},"row_status":"needs_review","page":30,...}`

## `get_applicable_sros(code, as_of_date)`
Blocks `rd`, `acd`, `sales_tax`, `income_tax`, `concessions`, each with:
* `applicable`: rows valid on the date that match the code (exact, 6-digit, heading, chapter or general rule), not removed by an `except` clause, and the most specific row of their rule group
  (store rule, `docs/store_schema.md`). Each row: `rule_id`, `instrument` (SRO number or Act/Schedule), `clause`, `rate`, `condition`, `matched_on`, `valid_from/valid_to`, `source_file`, `page`, `status`, `flags`.
  `status: needs_review` and flags such as `condition_must_be_checked`, `matched_by_prefix_not_exact_code` are shown, never hidden.
* `excluded`: every row that matched the code by prefix but does not apply, with `excluded_because`: `not_in_force_on_date (valid a to b)`, `excluded_by_except_clause [...]`,
  `shadowed_by_more_specific_row_in_same_rule_group`, `slab_mismatch: ...` (ACD, tariff-CD slab test), SRO 297 Table-II (supply of locally made vehicles, not an import rule),
  `local_supply_wording_probably_not_an_import_rule` (rows the A3 reader marked). Reasons about the code come first, date-only exclusions last (list capped at 60; `excluded_total` has the real count).
* `notifications`: the RD/ACD/ST/IT notifications in force on the date and those not in force (with `sro_status` and `superseded_by`).
* extras: `acd.tariff_cd_slab`, `income_tax.twelfth_schedule_class` (Part I/II/III), `sales_tax.general_rules_by_group` (the 3% value addition tax row), `concessions` (Fifth Schedule and China FTA options for the code on the date, see section "Customs-duty concessions" below; sugar and Early Harvest SROs name no PCT code).

## `compute_duty(code, assessable_value_pkr, as_of_date, importer, quantity, quantity_unit, goods, claimed_rules, rounding)`

### Inputs
| Input | Needed when | Source of the requirement |
|---|---|---|
| `importer.registration_status` `registered`/`unregistered` | always | Sales Tax Act s.3(1A) (further tax) |
| `importer.commercial_importer` (bool) | income-tax class Part II or III | First Schedule Part II: 2% / 3.5%, 5.5% / 6% |
| `importer.active_taxpayer` (bool) | income tax at import | ITO Tenth Schedule rule 1: not on the Active Taxpayers' List = rate doubled (6% becomes 12%). Always asked, never assumed |
| `importer.manufacturer_in_house_use` (bool) | Chapter 84/85 goods (and always optional: true = raw material in-house) | Sales Tax Act Twelfth Schedule cond. (2)(x), (2)(i) |
| `importer.licensed_oil_marketing_company` (bool) | Chapter 27 | Twelfth Schedule cond. (2)(ii) |
| `importer.registered_service_provider_in_house_use`, `importer.income_tax_category` | optional | cond. (2)(iii); First Schedule Part II provisos (`sro_1125_manufacturer`, `pharma_drap_certified`, `ckd_ev_kit`) |
| `quantity` + `quantity_unit` equal to the tariff unit | a specific CD or RD in Rs per Kg / MT / set / meter | tariff column CD; RD SRO rate cell. No unit conversion is done |
| `goods.running_time_minutes` | RD per minute (cinematographic film, SRO 1064 S.No 687) | SRO 1064 |
| `goods.c_and_f_value_usd_per_unit` | RD by C&F tier (mobile phones, SRO 1064 S.No 550-555) | SRO 1064 |
| `goods.age_years` | RD by age (combine harvester, SRO 1152 S.No 511) | SRO 1152 |
| `goods.used_vehicle_commercial_import_ipo` (bool) | headings 8702/8703/8704/8711 while SRO 1898 or 1065 is in force | SRO 1898(I)/2025, 1065(I)/2026 para 1 |
| `goods.vehicle_form` `CKD`/`CBU`, `goods.engine_cc` | headings 8703/8704 | SRO 1063/1151 para 1 and 3(x) |
| `goods.plant_machinery_for_manufacturing` (bool) | Chapter 84/85 when ACD would be charged | SRO 1063/1151 para 3(i) |
| `goods.retail_price_total_pkr` | Third Schedule goods | Sales Tax Act s.3(2)(a); ITO s.148(9)(a) |
| `goods.import_regime` (list) | optional: claims an ACD "not levied" regime (`fifth_schedule`, `baggage_rules_2006`, `sro_577_2005`, `sro_565_2006`, `sro_693_2006`, `sro_492_2009_temporary_importation`, `sro_678_2004_offshore`, `sro_655_656_2006`) | SRO 1063/1151 para 3 and para 1 |
| `claimed_rules` (rule ids) | optional: the caller confirms the conditions of a conditional exemption / reduced rate (Sixth, Eighth, Fifth Schedule rows with a condition) | `possible_rules_not_applied` lists them with their conditions |

### Order of calculation (also returned in `order_of_calculation`)
```
V     = assessable value (given; Customs Act s.25)
CD    = tariff CD% x V            or  Rs x quantity (specific)
RD    = RD SRO rate x V           (SRO 1152 until 30 Jun 2026, SRO 1064 from 1 Jul 2026); used vehicles: separate line RD_USED_VEHICLE
                                   (SRO 1898 1 Oct 2025 to 29 Jun 2026; SRO 1065 from 30 Jun 2026), "in addition" to the main RD
ACD   = ACD rate x V              (SRO 1151 / SRO 1063; slab test on the code's tariff CD; para 3 not-levied clauses -> 0)
FED   = Table I rate x (V + CD + RD + ACD), or x retail price, or Rs x quantity (FED Act s.12(3)-(4), First Schedule)
SED   = Table IA rate x (V + CD + RD + ACD), in addition to FED (FED Act s.3(3B); base open, OQ-A6-2)
V_ST  = V + CD + RD + ACD + FED + SED  (Sales Tax Act s.2(46)(d)). Third Schedule goods: retail price
ST    = rate x V_ST               rate precedence: exemption (Sixth Schedule) > Eighth Schedule > SRO 297 Table-I > standard 18% (s.3(1))
VAT   = 3% x V_ST                 value addition tax at import (s.7A(2), Twelfth Schedule), unless an exclusion applies
V_IT  = V + CD + RD + ACD + ST + VAT   (Third Schedule goods: retail price + ST)
IT    = Part II rate for the Twelfth Schedule class (I 1%; II 2% or 3.5% commercial; III 5.5% or 6% commercial) x V_IT
Total = CD + RD + ACD + ST + VAT + IT
Further tax (unregistered, s.3(1A), 4% of V_ST) is reported in `optional_lines_not_in_total`; `totals.total_if_open_items_apply_pkr` shows the total with it.
```

### Output
`status`: `computed`, `needs_input` (a `missing_inputs` list, each with `field`, `question`, `why`, `allowed`, `affects`; `totals` is null), `cannot_compute` (a `cannot_compute` list with the reason and an owner question; `totals` null),
`not_found`, `invalid_input`. A bill has `lines` (each: `tax`, `label`, `rate`, `base_label`, `base_pkr`, `amount_pkr`, `rule_id`, `instrument`, `clause`, `source_file`, `page`, `valid_from/valid_to`,
`status`, `flags`, `assumptions`, `included_in_total`), `totals {customs_duties, sales_tax, income_tax, total_payable_pkr}`, `assumptions`, `flags` (every `needs_review` row used), `review_required`,
`possible_rules_not_applied`, `notes`, `not_applied`. Partial results still list the lines that could be computed, plus `partial_total_of_computed_lines_pkr`.
Example line (hand case 2, 9506.9911, 500,000 PKR, 2026-07-15):
`{"tax":"RD","label":"Regulatory duty (1064(I)/2026 S.No 673)","rate":{"kind":"percent","pct":"20"},"base_pkr":"500000.00","amount_pkr":"100000.00","instrument":"1064(I)/2026","clause":"Table S.No 673","source_file":"202663017637155381064-2026.pdf","page":28,...}`
Totals for that bill: `{"customs_duties":"150000.00","sales_tax":"136500.00","income_tax":"47190.00","total_payable_pkr":"333690.00"}`.
Example of `missing_inputs` (1507.1000 without quantity): `[{"field":"quantity","question":"Quantity in MT (with quantity_unit='MT'). ...","affects":["CD","RD"]}]`.

### Rounding
No source document gives a rounding rule (OPEN-5). Convention (flagged assumption `ROUNDING` on every bill): each line is computed exactly with `Decimal`, rounded half-up to 0.01 PKR
(`rounding="rupee"`: to 1 PKR), and the rounded amounts feed the next base so the printed bill adds up. Test: IT 44,090.585 -> 44,090.59 (paisa) or 44,091 (rupee).

## What is flagged `needs_review` (carried from the store, never hidden)
Tariff specific duties from rotated cells (48 rows per year, e.g. 1507.1000 Rs 10,550/MT); RD rows that failed an A2 validator; SRO 1898/1065 (no effective-date clause printed, OQ-A3-4);
CKD vehicle rows of the ACD SROs (OQ-A3-1); Sixth Schedule rows with unconfirmed codes (155 of 199 rows); SRO 297 Table-I notification status; First Schedule Part II provisos; sugar chain
(not applied); s.3(1A) further tax (OPEN-4); every assumption id in `assumptions` (`ROUNDING`, `FED`, `OPEN2`, `OPEN3`, `OPEN10`, `OPEN4`, `REGIME`, `VATFACTS`, `TWELFTH_P3`, `PROVISOS`).

## Known limits (the tools say so; they do not guess)
* Federal excise duty (A6): lines `FED` and `SED` are added after ACD (`src/tools/fed.py`, rows of the store table `fed_rules`) and are part of the sales-tax, VAT and income-tax bases. Totals have a new key `federal_excise_duty`. The old flag `FED_not_included` is gone.
  * Inputs: `goods.engine_cc` and `goods.vehicle_form` (cars, pickups, Table IA); `goods.retail_price_total_pkr` (retail-price rates: cigarettes, cigars, aerated waters, e-liquid); `goods.fed_quantity` or `quantity`+`quantity_unit` in the unit of the FED rate (kg, liter, MMBTu, 100 m3, 100 MT, 1000 cigarettes, fan, DOC); `goods.fan_not_meps_compliant` (S.No 60).
  * Compound rates (`higher_of`) take the larger of the percentage part and the specific part and say which in the line note.
  * Refusals (status `cannot_compute`, no total): electric vehicles 8703.80xx (OQ-A6-1), engine capacity 3001 cc (OQ-A6-4), CKD vehicles, several Table I serials on one code. Table IA below 2000 cc gives no SED and a note.
  * Rows mapped by description from 'Respective heading(s)' carry `fed_row_mapped_by_description_not_owner_verified` and assumption `FED_MAPPED`; serials left unmapped are never matched but raise flag `fed_unmapped_serial_possible`. Third Schedule exemptions are listed in `possible_rules_not_applied`, never applied.
  * Assumptions: `FED` (scope), `FED_DATE` (OQ-A6-6), `FED_MAPPED`, `FED_RETAIL`, `SED_BASE` (the line note shows the amount if the base also held the Table I FED).
  * `get_applicable_sros` has a `fed` block: `applicable`, `possible_exemptions`, `excluded` (local-only rows, other fiscal year, shadowed rows, each with `why_not_applied`) and `notes`.
* Customs-duty concessions in the store: Fifth Schedule (FY2025-26 file and FY2026-27 file) and China FTA Phase II (SRO 1640(I)/2019, calendar years 2025-2027). They are options, never applied unless claimed (below). Other FTAs/PTAs and other concession SROs are not in the store; the tariff CD is applied.
* Rows that name goods only in words (no PCT code) cannot be matched by code: Third/Sixth/Eighth/Fifth Schedule descriptive entries, Twelfth Schedule descriptive entries (class falls to Part III by residual), Ninth Schedule mobile table.
* Mobile phones (8517.13xx/8517.14xx): CD and RD tiers are computed; sales tax and income tax return `cannot_compute` (Ninth Schedule Table-II and the First Schedule mobile table are not matchable to tariff lines; the IT table names 8517.1219/8517.1211 which are not tariff lines).
* Eighth Schedule rates printed as a formula (for example "Rs. 700 per metric tonne or 18%, whichever is higher") return `cannot_compute`.
* Sugar (heading 1701): the reduced sugar notifications name no code and are not applied; a flag says so.
* Conditional exemptions and reduced rates are not applied unless the caller lists the rule id in `claimed_rules`.
* ACD regime clauses with no code link (Fifth Schedule, Baggage Rules, SROs 577/565/693/492/678, 655/656) assume an ordinary import unless `goods.import_regime` claims them (assumption `REGIME`).
* Vehicle class (light vs heavy commercial) is not distinguished: `engine_cc` decides the CKD clause.
* Section 53A ITO, minimum values under s.148(6A), valuation rulings: not applied. Tools never convert units (Kg to MT).
* Dates outside 2025-07-01 .. 2027-06-30 are refused (the tariff stops there).
* The VAT base (OPEN-10), the RD/ACD-in-base reading (OPEN-2) and the precedence between sales-tax sources (OPEN-3) are readings, not text of the law; see `docs/owner_questions.md` OQ-B3-1 to OQ-B3-7.

## Customs-duty concessions (A7 Fifth Schedule, A8 China FTA Phase II): `src/tools/concessions.py`
Plain idea: the normal bill is always shown. Where the code has a concession row, the tool also shows what the bill would be **with** it and which conditions the importer must meet. It applies the concession only when asked.
* **New inputs.** `goods.origin_country` (`CN`/`China` or another country), `goods.has_certificate_of_origin` (true/false: Form E, issued in China), `goods.claim_china_fta` (true = use the China FTA rate; applied only if origin is China and the certificate is true), and `claimed_rules` with a rule id from `concessions.fifth_schedule.options[].rule_id` (for example `fifth_schedule_rules:9`). One customs-duty concession only; two claimed = `needs_input`.
* **New output `concessions`**: `fifth_schedule {status: checked | not_in_store_for_date, options[], not_offered[], possible_by_description[], notes}`, `china_fta {options[], origin, certificate}`, `questions[]` (what the agent should ask: origin, Form E, Fifth Schedule entitlement), `applied[]`, `bill_without_concession` (when one is applied), `notes`. Each option: `rule_id`, `clause` (Part, Table, S.No, item), `description`, `listed_rate` (as printed), `effective_cd_pct`, `tariff_cd_pct`, `how` (the slab or "lower of" rule used), `conditions_the_system_cannot_check`, `acd_not_levied` + `acd_note`, `status`, `flags`, page and source file, `bill_if_applied {totals, lines, difference_vs_normal_bill}` (the first 8 options).
* **Rates.** Fifth Schedule: `docs/duty_formula.md` section 8 (single rate; slab rule for lists such as "0%,3%,5%"; "50% of the prevailing rate"). China FTA: lower of the normal CD and the SRO rate of the calendar year of the import date.
* **What changes in the bill.** Only the CD line (label "Customs duty under concession: ...", note with the normal duty). ACD becomes "not levied" for Fifth Schedule goods except the serials excluded by SRO 1063/1151 para 3(iii). RD is unchanged. Sales tax, value addition tax and income tax bases use the CD actually paid.
* **Flags and assumptions.** `concession_applied_conditions_unchecked`, assumptions `CONCESSION_CONDITIONS`, `FIFTH_ACD`, `FTA_BASE`. Rows read by OCR carry `reading` (`ocr_fitted_to_taper_pattern` = AI reading of the scan fitted to the printed straight-line pattern) and `needs_review` when a check failed.
* **Limits.** Fifth Schedule entries printed "Respective Headings" name goods only in words: they are listed under `possible_by_description` for chapters 84, 85 and 90, never matched by code. EV/hybrid parts rows with text rates ("1% (notwithstanding ...)") are shown with `rate_not_computable`. Part VIII (border markets) is never offered. The FY2025-26 amendments of SRO 1640(I)/2019 are not in `data/raw` (OQ-A8-1); codes of the 2019 SRO that are not lines of the 2025-26/2026-27 tariffs are never matched.
