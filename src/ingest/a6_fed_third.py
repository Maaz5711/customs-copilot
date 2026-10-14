"""A6: Third Schedule, Table-I (Goods) of the Federal Excise Act 2005: conditional exemptions ("See sub-section (1) of section 16").

Printed text copied from the page text layer (reading order) and checked against the page images. Same text in both snapshots
except S.No 28 (inserted by Finance Act 2026, red on page 100 of the 2026 file). Table-II (Services) is not covered (services are
not imported goods). Checked by a6_fed.py exactly like the First Schedule rows (every word on the cited pages).

Tuple: (s_no, description as printed, heading column as printed, start page 2026 file, start page 2025 file, extra pages the text runs over)
"""

THIRD = [
    ("1", "Crude vegetable oil, if obtained from the locally grown seeds excluding cooking oil, without having undergone any "
     "process other than the process of washing.", "5.07, 15.08, 15.09, 15010, 15.11, 15.12, 15.13, 15.14 15.15, 15.16, 15.17 & 15.18", 88, 90, 1),
    ("3", "Un-manufactured tobacco or tobacco refuses if used for the purposes other than the manufacturer of cigarettes, smoking "
     "mixtures for pipes and cigarettes and cigars and cheroots.", "24.01", 88, 90, 1),
    ("4", "Cigars, cheroots, cigarillos and cigarettes, of tobacco or of tobacco substitutes,- (i) If supplied to Pakistan Navy for "
     "consumption by its personnel on board its vessels. (ii) If made by hand in tapered shape of biris without the use of any "
     "manual or power-operated machine in any process of their manufacture. (iii) If supplied for consumption by the President of "
     "Pakistan, the President of Azad Jammu & Kashmir and the Governors of the Provinces, members of their families and guests "
     "provided that the cigarettes are manufactured and supplied on the specific written orders of the competent official authority "
     "and the cigarettes and their packets are special-crested for the respective privileged House. (iv) If supplied against payment "
     "in foreign exchange, to M/s Duty Free Shops Ltd for sale in its Duty Free Shops and on board international flight by the "
     "Pakistan International Airlines subject to the same conditions and procedures as are applicable for the purposes of "
     "exemption of customs duty.", "24.02", 88, 90, 2),
    ("6", "Motor spirit,- (i) If supplied to Pakistan Navy for consumption in its vessels (ii) If supplied for consumption by the "
     "International Bank for Reconstruction and Development in its official cars", "2710.1110", 89, 91, 1),
    ("9", "Sludge and sediment recovered from storage tanks of the incoming vessels or ships meant for breaking", "2710.9900", 89, 91, 1),
    ("10", "Natural gas if produced and used in the same field for drilling, production, pressure maintenance or in any other joint "
     "operations including flaring in the same field.", "2711.2100", 89, 92, 1),
    ("11", "Carbon black oil (carbon black feed stock) if imported by a duly registered manufacturer of carbon black.",
     "2707.9910 2713.9010", 90, 92, 0),
    ("12", "Goods,- (i) If donated to the President's Funds for Afghan Refugees, Assistance to Palestine and Famine Relief for "
     "Africa, provided that before making such donation the manufacturer or importer shall inform in writing to the Collector of "
     "Federal Excise or as the case may be, Collector of Customs about quantity, value and the duty involved on such goods and shall "
     "in case of imports, fulfill the conditions and comply with the procedures specified for the purposes of exemption from customs "
     "duty. (ii) If purchased by the Cabinet Division, Government of Pakistan, for donation to a foreign country in the event of "
     "natural disasters as certified by the Emergency Relief Cell of that Division. (iii) If supplied against international tender "
     "issued by UNICEF, UNDP, WHO, WFP, UNHCR, International Red Cross or any other relief agency, for Afghan Refugees subject to the "
     "conditions given below. (iv) If supplied as ship stores to ships and aircrafts leaving for abroad subject to the satisfaction of "
     "the Collector of Customs in terms of section 24 of the Customs Act, 1969.", "Respective headings", 90, 92, 1),
    ("13", "Goods imported or supplied under grants-in-aid for which a specific consent has been obtained from the Board.",
     "Respective Heading", 91, 93, 0),
    ("14", "Goods if imported as bonafide baggage", "Respective Heading", 91, 94, 0),
    ("15", "Goods if imported by Duty Free Shops as baggage free of custom duty, regulatory duty and sales tax under the baggage rules "
     "made under the Customs Act, 1969 (IV of 1969).", "Respective Heading", 91, 94, 0),
    ("16", "Any goods, excluding un-manufactured tobacco, which are manufactured produced in-house by a registered person and used for "
     "the manufacture and production of goods on which duty of excise is paid by such person.", "Respective Headings.", 91, 94, 0),
    ("19", "Materials and equipment (plant, machinery, equipment, appliances and accessories) for construction and operation of Gwadar "
     "Port and development of Free Zone for Gwadar Port as imported by or supplied to China Overseas Ports Holding Company Limited "
     "(COPHCL) and its operating companies namely (i) China Overseas Ports Holding Company Pakistan (Private) Limited, (ii) Gwadar "
     "International Terminals Limited, (iii) Gwadar Marine Services Limited and (iv) Gwadar Free Zone Company Limited, their "
     "contractors and sub-contractors; and Ship Bunker Oils bought and sold to the ships calling on/visiting Gwadar Port, having "
     "Concession Agreement with the Gwadar Port Authority, for a period of forty years, subject to the conditions and procedure as "
     "specified under S. No. 100A of Table-1 of Sixth Schedule to the Sales Tax Act, 1990.", "Respective Headings", 92, 94, 0),
    ("20", "Supplies made by the businesses to be established in the Gwadar Free Zone for a period of twenty-three years within the "
     "Gwadar Free Zone, subject to the condition that the sales and supplies outside the Gwadar Free Zone and into the territory of "
     "Pakistan shall be subjected to Federal Excise Duty.", "Respective Headings", 92, 95, 0),
    ("21", "Vehicles imported by China Overseas Ports Holding Company Limited (COPHCL) and its operating companies, namely: (a) China "
     "Overseas Ports Holding Company Pakistan (Private) Limited; (b) Gwadar International Terminal Limited; (c) Gwadar Marine Services "
     "Limited; and (d) Gwadar Free Zone Company Limited; for a period of twenty-three years for construction, development and "
     "operations of Gwadar Port and Free Zone Area subject to limitations, conditions prescribed under PCT heading 9917 (3).",
     "Respective Headings", 92, 95, 1),
    ("22", "Equipment imported by M/s China Railway Corporation to be furnished and installed in Lahore Orange Line Metro Train Project "
     "subject to the following conditions: (a) that the equipment imported under this serial number shall only be used in the "
     "aforesaid Project; (b) that the importer shall furnish an indemnity bond, in the prescribed manner and format as set out in "
     "Annex-A to this serial number, at the time of import to the extent of federal excise duty exempted under this serial number on "
     "consignment to consignment basis; (c) that the Punjab Mass Transit Authority shall certify in the prescribed manner and format "
     "as set out in Annex-B to this serial number that the imported equipment is bona fide requirement of the Project under the "
     "Contract No. PMA-CR-NORINCO-OL, dated 20.04.2015.", "", 93, 95, 2),
    ("23", "Imports made by diplomats, diplomatic missions, privileged persons and privileged organizations which are covered under "
     "various Acts, Orders, Rules, Regulations and Agreements passed by the Parliament or issued or agreed by the Government of "
     "Pakistan.", "99.01, 99.02 and 99.05.", 95, 98, 1),
    ("24", "The following goods, when supplied within the limits of the Border Sustenance Markets, established in cooperation with Iran "
     "and Afghanistan: (i) Animal Fats and Oil and their fractions (ii) Vegetable Fats and their fractions (iii) Vegetable Oils and "
     "their fractions Provided that, such items in case of import, shall be allowed clearance by the Customs Authorities subject to "
     "furnishing of bank guarantee equal to the amount of duty involved and the same shall be released after presentation of "
     "consumption certificate issued by the Commissioner Inland Revenue having jurisdiction: Provided further that, the said "
     "exemption shall only be available to a person upon furnishing proof of having a functional business premises located within "
     "limits of the Border Sustenance Markets.", "1516.1000 1516.2010 1516.2020", 99, 101, 0),
    ("25", "Import and supply of raw materials, components, parts and plant and machinery by registered persons authorized under Export "
     "Facilitation Scheme, 2021 notified by the Board with such conditions, limitations and restrictions.", "Respective headings", 99, 101, 0),
    ("26", "Imports or supplies made by, for or to a qualified investment as specified at Serial No.1 of the First Schedule to the "
     "Foreign Investment (Promotion and Protection) Act, 2022 for the period as specified in the Second Schedule to the said Act.",
     "Respective heading.", 99, 101, 0),
    ("27", "Imported construction materials and goods imported by M/s China State Construction Engineering Corporation Limited "
     "(M/s CSCECL), whether or not locally manufactured, for construction of Karachi-Peshawar Motorway (Sukkur-Multan Section) subject "
     "to fulfilment of same conditions, limitations and restrictions as are specified under S. No. 145 of Table-1 of Sixth Schedule to "
     "the Sales Tax Act, 1990, provided that total incidence of exemptions of all duties and taxes in respect of construction "
     "materials and goods imported for the project shall not exceed ten thousand eight hundred ninety-eight million rupees including "
     "the benefit of exemption from duties and taxes availed before 30th June, 2018 under the provisions of Sales Tax Act, 1990, the "
     "Customs Act, 1969, The Federal Excise Act 2005 and the Income Tax Ordinance, 2001 and the notifications issued thereunder.",
     "Respective headings", 99, 102, 1),
]
THIRD_2026_ONLY = [
    ("28", "Import of bulletproof vehicles by the: i. Federal Government for logistic arrangements for Shanghai Cooperation "
     "Organization (SCO) summit subject to the prior approval from the Ministry of Foreign Affairs and the Ministry of Interior and "
     "Narcotics Control ii. By the Federal Government or Provincial Government for threat of terrorism against a public functionary "
     "as determined by the Ministry of Interior and Narcotics Control, subject to approval by the Federal Government.",
     "Respective heading.", 100, None, 0),
]


def third_rows(year: str):
    out = []
    for s_no, desc, head, p26, p25, span in THIRD + (THIRD_2026_ONLY if year == "2026" else []):
        page = p26 if year == "2026" else p25
        if page is None:
            continue
        out.append(dict(tbl="3T1", sno=s_no, sub="", desc=desc, sub_desc="", heading=head, rate="exempt (conditional)", page=page,
                        applies="import_and_local", span=span))
    return out
