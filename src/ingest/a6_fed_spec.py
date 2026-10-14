"""A6: printed text of the First Schedule rows of the Federal Excise Act 2005 (Table I, Table IA).

This is a READING of the printed pages (text layer in reading order, checked against the page images), kept as data.
It is NOT trusted by itself: a6_fed.py checks every field against the text layer of the same page (every printed word
must be on the cited page), parses the codes and rates with code (never typed numbers), and compares the serial list
with the serial anchors found by coordinates. Row text is copied as printed (footnote marks and square brackets that
only mark amendments are removed; the amended words are kept).

Fields per item: tbl (table), sno (serial as printed), sub (sub-clause label or ''), desc (description column, with the
sub-clause text in `sub_desc`), heading (heading/sub-heading column), rate (rate column), page (PDF page == printed page
number in both FED files), applies (import_only | local_only | import_and_local, read from the words of the description).
"""

YEARS = {
    "2026": dict(fy="FY2026-27", file="20267171373633512FEDAct2005updatedupto30-06-2026.pdf",
                 valid_from="2026-07-01", valid_to="9999-12-31"),
    "2025": dict(fy="FY2025-26", file="202588138517680FEDAct,2005withindexupdatedupto30-06-2025.pdf",
                 valid_from="2025-07-01", valid_to="2026-06-30"),
}

# Omitted serial numbers printed in Table I (footnotes and "omitted" cells). Used only to prove that live + omitted serials
# leave no gap between 1 and the last serial (serial continuity).
OMITTED_I = {
    "2026": ["1", "2", "11", "10a", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28",
             "29", "30", "38", "39", "40", "42", "43", "44", "45", "46", "47", "48", "49", "50", "51", "52", "53", "54",
             "57", "58"],
}
OMITTED_I["2025"] = list(OMITTED_I["2026"])

_V55 = ("Imported motor cars, SUVs and other motor vehicles, excluding auto rickshaws, principally designed for the "
        "transport of persons (other than those of headings 87.02), and till the 30th day of June, {Y} electric vehicles "
        "(4 wheelers) including station wagons and racing cars")
_V55B = ("Locally manufactured or assembled motor cars, SUVs and other motor vehicles, excluding auto rickshaws "
         "principally designed for the transport of persons (other than those of headings 87.02), and till the 30th day "
         "of June, {Y} electric vehicles (4 wheelers) including station wagons and racing cars")


def _r(tbl, sno, desc, heading, rate, page, applies="import_and_local", sub="", sub_desc=""):
    return dict(tbl=tbl, sno=sno, sub=sub, desc=desc, sub_desc=sub_desc, heading=heading, rate=rate, page=page, applies=applies)


def _vehicle_rows(tbl, sno, desc, heading, page, applies, bands):
    return [_r(tbl, sno, desc, heading, rate, page, applies, sub=sub, sub_desc=sd) for sub, sd, rate in bands]


def rows_2026():
    R = []
    R += [
        _r("I", "3", "Concentrates for aerated beverages in all forms including syrup form", "2106.9010", "Fifty per cent ad val.", 70),
        _r("I", "4", "Aerated waters", "2201.1020", "Twenty per cent of retail price", 70),
        _r("I", "5", "Aerated waters, containing added sugar or other sweetening matter or flavored", "2202.1010",
           "Twenty per cent of retail price", 70),
        _r("I", "6", "Aerated waters if manufactured wholly from juices or pulp of vegetables, food grains or fruits and which "
           "do not contain any other ingredient, indigenous or imported, other than sugar, coloring materials, preservatives or "
           "additives in quantities prescribed under the West Pakistan Pure Food Rules, 1965.", "Respective headings",
           "Twenty per cent of retail price", 70),
        _r("I", "7", "Un-manufactured tobacco", "24.01", "Three hundred and ninety rupees per kilogram", 71),
        _r("I", "7a", "Acetate tow", "Respective heading", "Rupees ten thousand per kg.", 71),
        _r("I", "8", "Cigarettes of tobacco or tobacco substitutes excluding locally produced cigarettes.", "24.02",
           "Sixty five percent of retail price or the rate of duty as prescribed against S. No. 9 whichever is higher.", 71,
           "import_only"),
        _r("I", "8a", "E-liquids by whatsoever name called, for electric cigarette kits.", "Respective heading",
           "Rupees sixteen thousand five hundred per kg", 71),
        _r("I", "8b", "Cigars, cheroots and cigarillos of tobacco and tobacco substitute.", "Respective heading",
           "Sixty five percent of retail price or rupees ten thousand per kg whichever is higher.", 71),
        _r("I", "8c", "Tobacco mixture in an electrically heated tobacco product by whatever name called, intended for "
           "consumption by using a tobacco heating system without combustion", "Respective headings",
           "Rupees sixteen thousand five hundred per kg", 71),
        _r("I", "8d", "Nicotine pouches", "Respective heading", "Rupees one thousand and two hundred per kg.", 72),
        _r("I", "9", "Locally produced cigarettes if their on-pack printed retail price exceeds twelve thousand five hundred "
           "rupees per thousand cigarettes.", "24.02", "Rupees sixteen thousand five hundred per thousand cigarettes", 72,
           "local_only"),
        _r("I", "10", "Locally produced cigarettes if their on-pack printed retail price does not exceed twelve thousand five "
           "hundred per thousand cigarettes.", "24.02", "Rupees five thousand and fifty per thousand cigarettes", 72, "local_only"),
        _r("I", "12", "Cigarettes manufactured by a manufacturer who remains engaged on and after the 10th June, 1994, either "
           "directly or through any other arrangement, if the manufacture of any brand of cigarette in non-tariff areas",
           "24.02", "Sixty five percent of retail price.", 72, "local_only"),
        _r("I", "13", "Portland cement, aluminous cement, slag cement, super sulphate cement and similar hydraulic cements, "
           "whether or not colored or in the form of clinkers", "25.23", "four rupees per kilogram", 72),
        _r("I", "31", "Liquefied Natural Gas", "2711.1100", "ten rupees per Million British Thermal Unit (MMBTu)", 73),
        _r("I", "32", "Liquefied propone", "2711.1200", "Seventeen rupees and eighteen paisa per hundred cubic meters.", 73),
        _r("I", "33", "Liquefied butanes", "2711.1300", "Seventeen rupees and eighteen paisa per hundred cubic meters.", 73),
        _r("I", "34", "Liquefied ethylene, propylene, butylenes and butadiene", "2711.1400",
           "Seventeen rupees and eighteen paisa per hundred cubic meters.", 73),
        _r("I", "35", "Other Liquefied petroleum Gases and gaseous hydrocarbons", "2711.1900",
           "Rupees sixty per hundred metric tonne.", 74),
        _r("I", "36", "Natural Gas in gaseous state", "2711.2100", "ten rupees per Million British Thermal Unit (MMBTu)", 74),
        _r("I", "37", "Other petroleum Gases in gaseous state", "2711.2900",
           "ten rupees per Million British Thermal Unit (MMBTu)", 74),
        _r("I", "41", "Flavors and concentrates for use in aerated beverages", "3302.1010", "Fifty per cent ad valorem.", 74),
    ]
    R += _vehicle_rows("I", "55", _V55.format(Y="2027"), "87.03", 75, "import_only", [
        ("(a)", "of cylinder capacity up to 1000cc", "2.5% ad val"),
        ("(b)", "of cylinder capacity from 1001cc to 1799cc", "10% ad val."),
        ("(c)", "of cylinder capacity 1800cc to 3000cc", "30% ad val."),
        ("(d)", "of cylinder capacity exceeding 3001cc", "40% ad val."),
    ])
    R += _vehicle_rows("I", "55A", "Electric cars and electric SUVs, imported in CBU condition having value as determined under "
                       "section 25 of the Customs Act, 1969:", "Respective Heading", 75, "import_only", [
        ("(a)", "Not exceeding USD seventy-five thousand;", "0%"),
        ("(b)", "exceeding USD seventy-five thousand and upto USD one hundred and ten thousand", "30% ad.val"),
        ("(c)", "exceeding USD one hundred and ten thousand:", "40% ad.val"),
    ])
    R += _vehicle_rows("I", "55B", _V55B.format(Y="2027") + ":", "87.03", 76, "local_only", [
        ("(a)", "of cylinder capacity up to 1300cc", "2.5 % ad val."),
        ("(b)", "of cylinder capacity from 1301cc to 2000cc", "5% ad val."),
        ("(c)", "of cylinder capacity 2001cc and above", "10% ad val."),
    ])
    R += [
        _r("I", "55C", "Imported double cabin (4x4) pick-up vehicles", "8704.2190 8704.3190", "30% ad val", 76, "import_only"),
        _r("I", "55D", "Locally manufactured double cabin (4x4) pick-up vehicles except the vehicles booked on or before the "
           "30th June, 2020 subject to the restriction or conditions specified by the Board.", "8704.2190 8704.3190",
           "10% ad val.", 76, "local_only"),
        _r("I", "56", "Filter rod for cigarettes", "Respective headings", "Rupees eighty thousand per kg", 76),
        _r("I", "59", "Sugary Fruit juices, syrups and squashes, waters whether or not containing added sugar or artificial "
           "sweeteners excluding mineral waters, aerated waters, hydration drinks or electrolyte beverages specifically "
           "formulated to support hydration, electrolytes replenishment containing artificial sweetener or sugar or both "
           "not exceeding 5g/100 ml", "Respective headings", "Twenty percent of retail price", 77),
        _r("I", "60", "Energy inefficient fans both locally manufactured and imported which do not comply with the MEPS, "
           "notified by PSQCA", "Respective heading", "Rupees two thousand per fan with effect from the 1st day of January, 2024", 77),
        _r("I", "61", "Incandescent bulbs both locally manufactured and imported", "8539.2200 and 8539.2990",
           "Twenty percent ad valorem with effect from the 1st day of January, 2024", 77),
        _r("I", "62", "Fertilizers", "Respective heading", "Five percent ad valorem.", 77),
        _r("I", "63", "Lubricating oil and base lubricating oils", "2710.1951 2710.1952 2710.1953 2710.1993",
           "Five percent ad valorem.", 78),
        _r("I", "64", "Day Old Chick (DOC)", "Respective Heading", "Rs.10 Per DOC", 78),
    ]
    R += [
        _r("I", "65", "Petroleum top Naphtha", "2710.1942", "Rs. 80 per liter", 78, sub="(i)"),
        _r("I", "65", "White Spirit/Mineral Turpentine Oil (MTT)", "2710.1240", "Rs. 80 per liter", 78, sub="(ii)"),
        _r("I", "65", "Solvent Oil", "2710.1250", "Rs. 80 per liter", 78, sub="(iii)"),
    ]
    R += _vehicle_rows("IA", "1", "Imported motor cars, SUVs and other motor vehicles, excluding auto rickshaws, principally "
                       "designed for the transport of persons (other than those of headings 87.02), electric vehicles "
                       "(4 wheelers) including station wagons, double cabin (4x4) pickup vehicles and racing cars:",
                       "87.03 8704.2190 8704.3190", 80, "import_only", [
        ("(a)", "of cylinder capacity 2000cc and above but not exceeding 3000cc", "86%ad val"),
        ("(b)", "of cylinder capacity exceeding 3000cc", "92% ad val."),
    ])
    R += [
        _r("III", "2", "Supply of white crystalline sugar by any person to a manufacturing, processing or packaging entity.",
           "Respective heading", "Rupees fifteen per kg.", 86, "local_only"),
    ]
    return R


def rows_2025():
    """FY2025-26 snapshot (Act 'as amended up to 30th June, 2025', Finance Act 2025 shown in red). Page numbers are
    those of the 2025 file; its table is laid out over 11 pages (72-82)."""
    R = []
    R += [
        _r("I", "3", "Concentrates for aerated beverages in all forms including syrup form", "2106.9010", "Fifty per cent ad val.", 72),
        _r("I", "4", "Aerated waters", "2201.1020", "Twenty per cent of retail price", 72),
        _r("I", "5", "Aerated waters, containing added sugar or other sweetening matter or flavored", "2202.1010",
           "Twenty per cent of retail price", 72),
        _r("I", "6", "Aerated waters if manufactured wholly from juices or pulp of vegetables, food grains or fruits and which "
           "do not contain any other ingredient, indigenous or imported, other than sugar, coloring materials, preservatives or "
           "additives in quantities prescribed under the West Pakistan Pure Food Rules, 1965.", "Respective headings",
           "Twenty per cent of retail price", 72),
        _r("I", "7", "Un-manufactured tobacco", "24.01", "Three hundred and ninety rupees per kilogram", 73),
        _r("I", "7a", "Acetate tow", "Respective heading", "Rupees forty four thousand per kg.", 73),
        _r("I", "8", "Cigarettes of tobacco or tobacco substitutes excluding locally produced cigarettes.", "24.02",
           "Sixty five percent of retail price or the rate of duty as prescribed against S. No. 9 whichever is higher.", 73,
           "import_only"),
        _r("I", "8a", "E-liquids by whatsoever name called, for electric cigarette kits.", "Respective heading",
           "Rupees ten thousand per kg or sixty five percent of retail price whichever is higher.", 73),
        _r("I", "8b", "Cigars, cheroots and cigarillos of tobacco and tobacco substitute.", "Respective heading",
           "Sixty five percent of retail price or rupees ten thousand per kg whichever is higher.", 73),
        _r("I", "8c", "Tobacco mixture in an electrically heated tobacco product by whatever name called, intended for "
           "consumption by using a tobacco heating system without combustion", "Respective headings",
           "Rupees sixteen thousand five hundred per kg", 73),
        _r("I", "8d", "Nicotine pouches", "Respective heading", "Rupees one thousand and two hundred per kg.", 75),
        _r("I", "9", "Locally produced cigarettes if their on-pack printed retail price exceeds twelve thousand five hundred "
           "rupees per thousand cigarettes.", "24.02", "Rupees sixteen thousand five hundred per thousand cigarettes", 75,
           "local_only"),
        _r("I", "10", "Locally produced cigarettes if their on-pack printed retail price does not exceed twelve thousand five "
           "hundred per thousand cigarettes.", "24.02", "Rupees five thousand and fifty per thousand cigarettes", 75, "local_only"),
        _r("I", "12", "Cigarettes manufactured by a manufacturer who remains engaged on and after the 10th June, 1994, either "
           "directly or through any other arrangement, if the manufacture of any brand of cigarette in non-tariff areas",
           "24.02", "Sixty five percent of retail price.", 75, "local_only"),
        _r("I", "13", "Portland cement, aluminous cement, slag cement, super sulphate cement and similar hydraulic cements, "
           "whether or not colored or in the form of clinkers", "25.23", "four rupees per kilogram", 76),
        _r("I", "31", "Liquefied Natural Gas", "2711.1100", "ten rupees per Million British Thermal Unit (MMBTu)", 76),
        _r("I", "32", "Liquefied propone", "2711.1200", "Seventeen rupees and eighteen paisa per hundred cubic meters.", 76),
        _r("I", "33", "Liquefied butanes", "2711.1300", "Seventeen rupees and eighteen paisa per hundred cubic meters.", 76),
        _r("I", "34", "Liquefied ethylene, propylene, butylenes and butadiene", "2711.1400",
           "Seventeen rupees and eighteen paisa per hundred cubic meters.", 77),
        _r("I", "35", "Other Liquefied petroleum Gases and gaseous hydrocarbons", "2711.1900",
           "Rupees sixty per hundred metric tonne.", 77),
        _r("I", "36", "Natural Gas in gaseous state", "2711.2100", "ten rupees per Million British Thermal Unit (MMBTu)", 77),
        _r("I", "37", "Other petroleum Gases in gaseous state", "2711.2900",
           "ten rupees per Million British Thermal Unit (MMBTu)", 77),
        _r("I", "41", "Flavors and concentrates for use in aerated beverages", "3302.1010", "Fifty per cent ad valorem.", 77),
    ]
    R += _vehicle_rows("I", "55", _V55.format(Y="2026"), "87.03", 79, "import_only", [
        ("(a)", "of cylinder capacity up to 1000cc", "2.5% ad val"),
        ("(b)", "of cylinder capacity from 1001cc to 1799cc", "10% ad val."),
        ("(c)", "of cylinder capacity 1800cc to 3000cc", "30% ad val."),
        ("(d)", "of cylinder capacity exceeding 3001cc", "40% ad val."),
    ])
    R += _vehicle_rows("I", "55B", _V55B.format(Y="2026") + ":", "87.03", 79, "local_only", [
        ("(a)", "of cylinder capacity up to 1300cc", "2.5 % ad val."),
        ("(b)", "of cylinder capacity from 1301cc to 2000cc", "5% ad val."),
        ("(c)", "of cylinder capacity 2001cc and above", "10% ad val."),
    ])
    R += [
        _r("I", "55C", "Imported double cabin (4x4) pick-up vehicles", "8704.2190 8704.3190", "30% ad val", 80, "import_only"),
        _r("I", "55D", "Locally manufactured double cabin (4x4) pick-up vehicles except the vehicles booked on or before the "
           "30th June, 2020 subject to the restriction or conditions specified by the Board.", "8704.2190 8704.3190",
           "10% ad val.", 80, "local_only"),
        _r("I", "56", "Filter rod for cigarettes", "Respective headings", "Rupees eighty thousand per kg", 80),
        _r("I", "59", "Sugary Fruit juices, syrups and squashes, waters whether or not containing added sugar or artificial "
           "sweeteners excluding mineral and aerated waters", "Respective headings", "Twenty percent of retail price", 80),
        _r("I", "60", "Energy inefficient fans both locally manufactured and imported which do not comply with the MEPS, "
           "notified by PSQCA", "Respective heading", "Rupees two thousand per fan with effect from the 1st day of January, 2024", 81),
        _r("I", "61", "Incandescent bulbs both locally manufactured and imported", "8539.2200 and 8539.2990",
           "Twenty percent ad valorem with effect from the 1st day of January, 2024", 81),
        _r("I", "62", "Fertilizers", "Respective heading", "Five percent ad valorem.", 81),
        _r("I", "63", "Lubricating oil", "2710.1951, 2710.1952 and 2710.1953", "Five percent ad valorem.", 81),
        _r("I", "64", "Day Old Chick (DOC)", "Respective Heading", "Rs.10 Per DOC", 81),
        _r("III", "2", "Supply of white crystalline sugar by any person to a manufacturing, processing or packaging entity.",
           "Respective heading", "Rupees fifteen per kg.", 88, "local_only"),
    ]
    return R


# Finance Act text that explains each change between the two snapshots (page = PDF page of the Finance Act file).
FA2026 = "20266291261044366FinanceAct2026.pdf"
FA2025 = "2025629106147620FInanceAct2025.pdf"
CHANGES_2026 = {
    ("I", "7a"): ("Finance Act 2026 s.6(14)(1)(a): in S.No 7a 'forty-four' replaced by 'ten'", 72),
    ("I", "8a"): ("Finance Act 2026 s.6(14)(1)(b): S.No 8a entries replaced by 'Rupees sixteen thousand five hundred per kg'", 72),
    ("I", "55"): ("Finance Act 2026 s.6(14)(1)(c): in S.No 55 and 55B column (2) '2026' replaced by '2027'", 72),
    ("I", "55A"): ("Finance Act 2026 s.6(14)(1)(d): new S.No 55A inserted after S.No 55", 72),
    ("I", "55B"): ("Finance Act 2026 s.6(14)(1)(c): in S.No 55 and 55B column (2) '2026' replaced by '2027'", 72),
    ("I", "59"): ("Finance Act 2026 s.6(14)(1)(e): S.No 59 column (2) exclusion words replaced", 73),
    ("I", "63"): ("Finance Act 2026 s.6(14)(1)(f): S.No 63 substituted (adds base lubricating oils and 2710.1993)", 73),
    ("I", "65"): ("Finance Act 2026 s.6(14)(1)(g): new S.No 65 added after S.No 64 (naphtha, white spirit/MTT, solvent oil, Rs. 80 per liter)", 73),
    ("Third-I", "28"): ("Finance Act 2026 s.6(16): new S.No 28 inserted in Table-I of the Third Schedule after S.No 27 (bulletproof vehicles, SCO summit)", 76),
    ("IA", "1"): ("Finance Act 2026 s.6(14)(2): new Table-IA inserted after Table-I; s.6(2) inserts section 3(3B) (Special Excise Duty)", 74),
}
