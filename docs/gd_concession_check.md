# Concession rates against the importer's Goods Declaration lines (aggregates only)

Source: the private GD extract (Chapter 85, February 2026, FY2025-26 rules). No line-level data is stored here. Script: `python -m src.eval.gd_concession_check`.

## China FTA (SRO 1640(I)/2019 named on the line)
Lines checked: 5491. Expected CD = IV x min(normal CD, SRO rate of the 1-Jan-2026 column) (tolerance 2 PKR).
* match: 4261 (77.6%)
* mismatch: 68 (1.2%)
* no_row_for_code_on_date: 1162 (21.2%)
* by category and row status: match:A0 (zero in all years):accepted=619, match:A0 (zero in all years):needs_review=62, match:A07:accepted=272, match:A07:needs_review=4, match:A15:accepted=1383, match:A15:needs_review=207, match:constant rate (C1/C2 or MOP):accepted=1714, mismatch:A15:accepted=52, mismatch:constant rate (C1/C2 or MOP):accepted=16
* mismatches by direction: our_rate_ge_charged=68

## Fifth Schedule (named on the line)
Lines checked: 587.
* some_option_matches: 446
* no_code_option(respective headings or code absent): 110
* no_option_matches: 31
* no_option_matches_but_charged_cd_is_normal_tariff_cd: 1
