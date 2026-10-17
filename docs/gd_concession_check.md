# Concession rates against the importer's Goods Declaration lines (aggregates only)

Source: the private GD extract (Chapter 85, February 2026, FY2025-26 rules). No line-level data is stored here. Script: `python -m src.eval.gd_concession_check`.

## China FTA (SRO 1640(I)/2019 named on the line)
Lines checked: 5491. Expected CD = IV x min(normal CD, SRO rate of the 1-Jan-2026 column) (tolerance 2 PKR).
* match: 5204 (94.8%)
* mismatch: 136 (2.5%)
* no_row_for_code_on_date: 151 (2.7%)
* by category and row status: match:A0 (zero in all years):accepted=1003, match:A0 (zero in all years):needs_review=2, match:A07:accepted=285, match:A15:accepted=1788, match:constant rate (C1/C2 or MOP):accepted=2126, mismatch:A0 (zero in all years):accepted=102, mismatch:A15:accepted=5, mismatch:constant rate (C1/C2 or MOP):accepted=29
* mismatches by direction: our_rate_lt_charged=102, our_rate_ge_charged=34

## Fifth Schedule (named on the line)
Lines checked: 597.
* some_option_matches: 456
* no_code_option(respective headings or code absent): 110
* no_option_matches: 31
* no_option_matches_but_charged_cd_is_normal_tariff_cd: 1
