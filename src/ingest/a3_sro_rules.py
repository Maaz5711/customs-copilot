"""A3 (lead part): instruments chain + rules that come from small SROs (sales tax, income tax, customs concessions).

How it works (same method as A2): every SRO page is rendered to an image and read by Claude; the values below were typed
from those images (dates, clause numbers, rates, conditions). SRO 297(I)/2023 has embedded OCR text, which we parse for the
code lists and then compare with the page image (log in `vision_notes`). Validators then check every row (codes in tariff,
date logic, rate range). Nothing is fixed silently: problems are written to the failures CSV and the row is marked needs_review.

Outputs (data/processed):
  a3_instruments.csv/json          supersession chain with dates
  a3_sro_rules.csv/json            rule rows (store-compatible columns)
  a3_sro_failures.csv              rows with issues
  spotcheck_a3_sro.csv             sample for the owner
Usage: python -m src.ingest.a3_sro_rules
"""
import csv
import json
import re
from pathlib import Path

import pymupdf

from src.ingest.a3_sro297 import CORRECTIONS, SRC297, SRC370, SRC1525, ocr_blocks

RAW = Path("data/raw")
OUT = Path("data/processed")
IMG = OUT / "page_images"
OPEN = "9999-12-31"

F = {  # source files
    "1217": "2025791374443892SRO1217-2025.pdf",
    "1832": "2025923149194307SRO1832SalesTax.pdf",
    "527": "20263191331255840SRO527(I)2026.pdf",
    "663": "2026423042643455SRO663.pdf",
    "663b": "2026423043053420SRO663.pdf",
    "455": "202635143564166SRO455.pdf",
    "1216": "2025791374222561SRO1216-2025.pdf",
    "1833": "2025923149161117Sro1833IncomeTax.pdf",
    "1215": "2025791575242748SRO1215-2025.pdf",
    "1834": "20259221693431493SRO-1834-2025.pdf",
    "1386": "2025731227123130SRO1386.pdf",
    "297": SRC297, "370": SRC370, "1525": SRC1525,
    "1151": "202572975414701SRO1151OF2025.pdf", "1152": "202572975650649SRO.1152of2025.pdf",
    "1063": "20266301763307131063-2026.pdf", "1064": "202663017637155381064-2026.pdf",
    "1065": "202663020651815SRO1065 (1).pdf", "1898": "202510117101711806SRO-1898(2025).pdf",
}

# ---------------------------------------------------------------- instruments (the chain)
# issue_date = date line printed on the SRO. effective_from = the SRO's own effective date clause if there is one, else issue date.
INSTR = [
    # sales tax: sugar chain
    dict(id="ST-1217-2025", sro="1217(I)/2025", tax="ST", authority="Sales Tax Act s.13(2)(a)", issue="2025-07-08", eff="2025-07-08",
         eff_basis="date_line (no effective-date clause printed)", effect="base",
         target="", status="amended", summary="Sales tax on import and supply of white crystalline sugar (up to 500,000 MT, TCP or private sector) reduced from 18% to 0.25%; minimum VAT 3% (Twelfth Schedule) exempted; cut-off date for import 30 Sep 2025.",
         file=F["1217"], page=1, clause="preamble; conditions (i)-(iii)", scope="in scope (concession on one good; kept for the chain)"),
    dict(id="ST-1832-2025", sro="1832(I)/2025", tax="ST", authority="Sales Tax Act s.13(2)(a)", issue="2025-09-22", eff="2025-09-22",
         eff_basis="date_line", effect="amends 1217(I)/2025", target="1217(I)/2025", status="in_force",
         summary="In condition (iii) of SRO 1217(I)/2025 'September' replaced by 'November' (cut-off becomes 30 Nov 2025).",
         file=F["1832"], page=1, clause="para 1", scope="in scope (chain)"),
    dict(id="ST-527-2026", sro="527(I)/2026", tax="ST", authority="Sales Tax Act s.13(2)(a)", issue="2026-03-19", eff="2026-03-19",
         eff_basis="date_line", effect="amends 1217(I)/2025", target="1217(I)/2025", status="rescinded",
         summary="In condition (iii) of SRO 1217(I)/2025 '30th day of November, 2025' replaced by '28th day of February, 2026'. Issued after both dates.",
         file=F["527"], page=1, clause="para 1", scope="in scope (chain)"),
    dict(id="ST-663-2026", sro="663(I)/2026", tax="ST+IT", authority="Sales Tax Act s.3, Customs Act s.19, ITO s.148(2A)", issue="2026-04-22", eff="2026-04-22",
         eff_basis="clause: 'with immediate effect'", effect="rescinds 455(I)/2026 and 527(I)/2026", target="455(I)/2026; 527(I)/2026", status="in_force",
         summary="Rescinds SRO 455(I)/2026 (5 Mar 2026) and SRO 527(I)/2026 (19 Mar 2026) with immediate effect.",
         file=F["663"], page=1, clause="paras (i) and (ii)", scope="in scope (chain)"),
    # sales tax: SRO 297 chain
    dict(id="ST-297-2023", sro="297(I)/2023", tax="ST", authority="Sales Tax Act s.3(2)(b) read with first proviso to s.3(2)(a)", issue="2023-03-08", eff="2023-03-08",
         eff_basis="date_line (no effective-date clause printed)", effect="base", target="", status="amended",
         summary="Sales tax at 25% of value of imported goods (and their subsequent supply or retail price) listed in Table-I (36 serials) and 25% on supply of locally manufactured vehicles in Table-II. Not applicable to Eighth Schedule goods (para 2 Explanation).",
         file=F["297"], page=1, clause="preamble; Table-I; Table-II; Explanation", scope="in scope"),
    dict(id="ST-370-2024", sro="370(I)/2024", tax="ST", authority="Sales Tax Act s.3(2)(b) read with first proviso to s.3(2)(a)", issue="2024-03-08", eff="2024-03-08",
         eff_basis="date_line", effect="amends 297(I)/2023 (substitutes Table-II)", target="297(I)/2023", status="in_force",
         summary="Table-II (supply of locally manufactured goods) substituted: (1) vehicles with engine 1400cc and above, 87.03; (2) vehicles with invoice price (excl. sales tax) above Rs 4 million, 87.03; (3) double cabin (4x4) pick-up vehicles, 87.04. NOTE: the file name says 'dated 08.03.2023' but the page shows SRO 370(I)/2024 dated 8 March 2024.",
         file=F["370"], page=1, clause="Table-II substituted", scope="in scope (local supply only)"),
    dict(id="ST-1525-2026", sro="1525(I)/2026", tax="ST", authority="Sales Tax Act s.3(2)(b) read with first proviso to s.3(2)(a)", issue="2026-09-13", eff="2026-09-13",
         eff_basis="clause: 'immediate effect' (para 2)", effect="amends 297(I)/2023 as amended by 370(I)/2024", target="297(I)/2023", status="in_force",
         summary="Proviso added after Table-II: provisions of Table-II do not apply to locally manufactured hybrid electric vehicles with engine capacity up to 2000cc.",
         file=F["1525"], page=1, clause="para 1 (new proviso), para 2", scope="in scope (local supply only)"),
    # income tax sugar chain
    dict(id="IT-1216-2025", sro="1216(I)/2025", tax="IT", authority="ITO s.53(2)", issue="2025-07-08", eff="2025-07-08",
         eff_basis="date_line (handwritten date on the scan: 8th July 2025; confirmed by SRO 455 which cites it as dated 8 Jul 2025)", effect="base (adds clause (9AD) to Second Schedule Part II)", target="", status="amended",
         summary="Tax under s.148 on commercial import of white crystalline sugar (up to 500,000 MT in aggregate) collected at 0.25% of value; cut-off 30 Sep 2025.",
         file=F["1216"], page=1, clause="new clause (9AD)", scope="in scope (concession on one good; kept for the chain)"),
    dict(id="IT-1833-2025", sro="1833(I)/2025", tax="IT", authority="ITO s.53(2)", issue="2025-09-22", eff="2025-09-22",
         eff_basis="date_line", effect="amends 1216(I)/2025", target="1216(I)/2025", status="in_force",
         summary="Condition (iii) of SRO 1216(I)/2025: 'September' replaced by 'November' (cut-off 30 Nov 2025).",
         file=F["1833"], page=1, clause="para 1", scope="in scope (chain)"),
    dict(id="IT-455-2026", sro="455(I)/2026", tax="IT", authority="ITO s.53(2)", issue="2026-03-05", eff="2026-03-05",
         eff_basis="date_line", effect="amends 1216(I)/2025", target="1216(I)/2025", status="rescinded",
         summary="Condition (iii) of SRO 1216(I)/2025: '30th day of November, 2025' replaced by '28th day of February, 2026'.",
         file=F["455"], page=1, clause="para 1", scope="in scope (chain)"),
    # customs concessions (out of v1 scope, in chain because A3 source list names them)
    dict(id="CU-1215-2025", sro="1215(I)/2025", tax="CUSTOMS", authority="Customs Act s.19(1)", issue="2025-07-08", eff="2025-07-08",
         eff_basis="date_line", effect="base", target="", status="amended",
         summary="Exempts up to 0.500 MMT of white crystalline sugar (respective PCT codes) from the whole of customs duties; cut-off date 30 Sep 2025.",
         file=F["1215"], page=1, clause="preamble; conditions (i)-(iii)", scope="concession (out of v1 scope)"),
    dict(id="CU-1834-2025", sro="1834(I)/2025", tax="CUSTOMS", authority="Customs Act s.19(1)", issue="2025-09-22", eff="2025-09-22",
         eff_basis="date_line (handwritten '22nd')", effect="amends 1215(I)/2025", target="1215(I)/2025", status="in_force",
         summary="Clause (iii) of SRO 1215(I)/2025: 'September' replaced by 'November'. No later amendment is in data/raw (SRO 663 rescinds only the sales tax and income tax notifications).",
         file=F["1834"], page=1, clause="para 1", scope="concession (out of v1 scope)"),
    dict(id="CU-1386-2025", sro="1386(I)/2025", tax="CUSTOMS", authority="Customs Act ss.18C and 19", issue="2025-07-31", eff="2025-08-01",
         eff_basis="clause: 1 Aug 2025 to 31 Jul 2026", effect="base", target="", status="expired",
         summary="Early Harvest Programme with Afghanistan: CD/ACD/RD capped at the rates in the Table for 4 products within tonnage quota (TRQ), 1 Aug 2025 to 31 Jul 2026.",
         file=F["1386"], page=1, clause="preamble; Table S.No 1-4", scope="concession (out of v1 scope)"),
    # customs chain from A2 (read-only reference, A2 owns the data)
    dict(id="CU-1151-2025", sro="1151(I)/2025", tax="ACD", authority="Customs Act s.18(5)", issue="2025-06-30", eff="2025-07-01",
         eff_basis="A2 findings (see a2_sro_findings.md)", effect="supersedes 929(I)/2024", target="929(I)/2024", status="superseded", superseded_by="1063(I)/2026",
         summary="Additional customs duty slabs FY2025-26.", file=F["1151"], page=1, clause="preamble", scope="A2 data (reference)"),
    dict(id="CU-1063-2026", sro="1063(I)/2026", tax="ACD", authority="Customs Act s.18(5)", issue="2026-06-30", eff="2026-07-01",
         eff_basis="A2 findings", effect="supersedes 1151(I)/2025", target="1151(I)/2025", status="in_force",
         summary="Additional customs duty slabs FY2026-27.", file=F["1063"], page=1, clause="preamble", scope="A2 data (reference)"),
    dict(id="CU-1152-2025", sro="1152(I)/2025", tax="RD", authority="Customs Act s.18(3)", issue="2025-06-30", eff="2025-07-01",
         eff_basis="clause 6: takes effect 1 Jul 2025, in force till 30 Jun 2026", effect="supersedes 928(I)/2024", target="928(I)/2024", status="superseded", superseded_by="1064(I)/2026",
         summary="Regulatory duty table FY2025-26.", file=F["1152"], page=39, clause="para 6", scope="A2 data (reference)"),
    dict(id="CU-1064-2026", sro="1064(I)/2026", tax="RD", authority="Customs Act s.18(3)", issue="2026-06-30", eff="2026-07-01",
         eff_basis="clause 6: takes effect 1 Jul 2026", effect="supersedes 1152(I)/2025", target="1152(I)/2025", status="in_force",
         summary="Regulatory duty table FY2026-27.", file=F["1064"], page=30, clause="para 6", scope="A2 data (reference)"),
    dict(id="CU-1898-2025", sro="1898(I)/2025", tax="RD", authority="Customs Act s.18(3)", issue="2025-10-01", eff="2025-10-01",
         eff_basis="date_line", effect="in addition to 1152(I)/2025", target="", status="superseded", superseded_by="1065(I)/2026",
         summary="40% RD on commercial import of used vehicles (8702, 8703, 8704, 8711).", file=F["1898"], page=1, clause="para 1-2", scope="A2 data (reference)"),
    dict(id="CU-1065-2026", sro="1065(I)/2026", tax="RD", authority="Customs Act s.18(3)", issue="2026-06-30", eff="2026-06-30",
         eff_basis="date_line (no effective-date clause printed; says 'in addition to' 1064(I)/2026, which starts 1 Jul 2026: see open question)", effect="supersedes 1898(I)/2025", target="1898(I)/2025", status="in_force",
         summary="30% RD on commercial import of used vehicles (8702, 8703, 8704, 8711).", file=F["1065"], page=1, clause="para 1-2", scope="A2 data (reference)"),
    # laws
    dict(id="LAW-FA2025", sro="Finance Act 2025", tax="LAW", authority="Parliament", issue="", eff="2025-07-01",
         eff_basis="Finance Act 2026 s.1(2) style: 'unless otherwise provided, come into force on the first day of July'; the Finance Act 2025 file is a scan not read in A3 (date to confirm)", effect="amends Sales Tax Act 1990 and ITO 2001", target="", status="in_force",
         summary="Source of the FY2025-26 snapshot of the Sales Tax Act (updated up to 2025-26) and the ITO (up to 31.07.2025).", file="2025629106147620FInanceAct2025.pdf", page=1, clause="", scope="law"),
    dict(id="LAW-FA2026", sro="Finance Act 2026 (Act XLIII of 2026)", tax="LAW", authority="Parliament", issue="2026-06-26", eff="2026-07-01",
         eff_basis="clause: s.1(2) 'It shall, unless otherwise provided, come into force on the first day of July, 2026'", effect="amends Sales Tax Act 1990 and ITO 2001", target="", status="in_force",
         summary="Source of the FY2026-27 snapshot (Sales Tax Act up to 30.06.2026, ITO up to 30.06.2026). Gazette Extraordinary 26 Jun 2026; assent 26 Jun 2026.", file="20266291261044366FinanceAct2026.pdf", page=2, clause="s.1", scope="law"),
]


def instruments():
    rows = []
    for i in INSTR:
        rows.append(dict(
            instrument_id=i["id"], sro_number=i["sro"], tax=i["tax"], authority_clause=i["authority"],
            issue_date=i["issue"], effective_from=i["eff"], effective_basis=i["eff_basis"], effect=i["effect"],
            amends_or_supersedes=i["target"], superseded_by=i.get("superseded_by", ""), status=i["status"],
            summary=i["summary"], source_file=i["file"], page=i["page"], clause=i["clause"], scope=i["scope"]))
    # derive superseded_by / amended_by from the targets (cross-check, no manual duplication)
    by_sro = {r["sro_number"]: r for r in rows}
    amended_by = {}
    for r in rows:
        for t in [x.strip() for x in r["amends_or_supersedes"].split(";") if x.strip()]:
            amended_by.setdefault(t, []).append(r["sro_number"])
    for r in rows:
        r["amended_or_superseded_by"] = "; ".join(amended_by.get(r["sro_number"], []))
    return rows, by_sro


# ---------------------------------------------------------------- tariff helpers
def load_tariffs():
    t = {}
    for fy in ("2025_26", "2026_27"):
        j = json.loads((OUT / f"tariff_{fy}.json").read_text(encoding="utf-8"))
        t[fy] = ({r["code"] for r in j["rows"]}, {h["heading"] for h in j["headings"]})
    return t


def code_entry(tok):
    """Turn one printed token into (code_raw, code_norm, match_level, issues)."""
    iss = []
    raw = tok
    if re.fullmatch(r"\d{4}\.\d{4}", tok):
        return raw, tok.replace(".", ""), "code8", iss
    if re.fullmatch(r"\d{4},\d{4}", tok):
        iss.append("code_format: printed with a comma instead of a dot")
        return raw, tok.replace(",", ""), "code8", iss
    if re.fullmatch(r"\d{8}", tok):
        iss.append("code_format: printed without the dot")
        return raw, tok, "code8", iss
    if re.fullmatch(r"\d{2}\.\d{2}", tok):
        return raw, tok.replace(".", ""), "heading4", iss
    return raw, "", "unmapped", ["code_format: cannot parse " + tok]


def tariff_flags(norm, level, tariffs):
    iss = []
    for fy, (codes, heads) in tariffs.items():
        label = "FY" + fy.replace("_", "-")
        if level == "code8":
            c = norm[:4] + "." + norm[4:]
            if c not in codes:
                iss.append(f"code_not_in_tariff {label}")
        elif level == "heading4":
            h = norm[:2] + "." + norm[2:]
            if h not in heads:
                iss.append(f"heading_not_in_tariff {label}")
    return iss


BASE = dict(tax="", schedule_or_section="", s_no="", description="", code_raw="", code_norm="", match_level="all", except_codes="[]",
            unparsed_except_text=0, rule_group="", rate_kind="percent", rate_pct="", rate_specific_amount="", rate_specific_unit="",
            rate_raw="", condition_text="", charged_on="", valid_from="", valid_to=OPEN, date_basis="", snapshot="", footnote="",
            source_file="", page=1, clause="", status="accepted", issues="", extraction_method="", tax_kind="sales_tax",
            importer_status="any", instrument="")


def mk(**kw):
    r = dict(BASE)
    r.update(kw)
    if isinstance(r["except_codes"], list):
        r["except_codes"] = json.dumps(r["except_codes"])
    return r


# ---------------------------------------------------------------- SRO 297 Table-I
CHAPTER_RULES = {
    # serial -> list of (kind, payload). Chapter-wide entries read from the page image (page 3/4 of the scan)
    16: [("chapter", "03", [], "All tariff lines of Chapter 03 (and the listed 1604/1605 lines)")],
    18: [("chapter", "08", ["0801.1910", "0801.1200"], "All tariff lines of Chapter 08 except 0801.1910, 0801.1200")],
    25: [("chapter", "02", [], "All tariff lines of Chapter 02 (and the listed 1602/1603 lines)")],
    28: [("chapter", "93", [], "Respective Heading of Chapter 93 of PCT")],
}
UNMAPPED = {33: "Respective headings (ships designed or adapted for recreation, pleasure or private use): no code printed",
            34: "Respective headings (aircraft designed or adapted for recreation, pleasure or private use): no code printed"}
TITLES = {}


# informational only (not corrections): nearest tariff lines found in tariff_2025_26/2026_27.json for codes printed in the SRO that do not exist
HINTS = {"7234.2900": "info: printed as in the SRO (page image checked); tariff has 7324.2100 and 7324.2900 but no 7234 line; likely typo, human to confirm",
         "9403.5030": "info: tariff has 9403.5010, 9403.5020, 9403.5090 but no 9403.5030; printed as in the SRO (page image checked)",
         "9004.9000": "info: tariff has 9004.9010 and 9004.9090 but no 9004.9000; printed as in the SRO (page image checked)"}


def sro297_rows(tariffs):
    txt, body, blocks = ocr_blocks()
    # explicit page map read from the scan (page 1: S.No 1-3, 2: 3(cont)-14, 3: 15-21, 4: 22-33, 5: 34-36)
    page_of = {**{n: 1 for n in (1, 2, 3)}, **{n: 2 for n in range(4, 15)}, **{n: 3 for n in range(15, 22)},
               **{n: 4 for n in range(22, 34)}, **{n: 5 for n in (34, 35, 36)}}
    desc = {}
    for n, seg in blocks.items():
        if n == 99:
            continue
        first = seg.strip().split("\n")[0].strip()
        desc[n] = first
    # human-read descriptions (printed, column 2)
    names = {1: "Aerated water and juices", 2: "Confectionary", 3: "Vehicles in CBU condition", 4: "Sanitary and bathroom wares",
             5: "Carpets (excluding those from Afghanistan)", 6: "Chandeliers and lighting devices or equipment", 7: "Chocolates",
             8: "Cigarettes, cigars and e-cigarettes", 9: "Corn flakes and other ready-to-use cereals", 10: "Cosmetics and shaving items",
             11: "Tissue papers", 12: "Crockery, kitchenware and tableware and household articles", 13: "Decorations or ornamental articles",
             14: "Dog and cat food only", 15: "Doors and window frames", 16: "Fish", 17: "Footwear",
             18: "Fruits and dry fruits (excluding those imported through land route or barter mechanism)", 19: "Furniture",
             20: "Home appliances CBU", 21: "Ice cream", 22: "Jams, jellies, preserved fruits and fruit and vegetable juices",
             23: "Leather jackets and apparels", 24: "Mattress and sleeping bags", 25: "Fresh, chilled, frozen, preserved or processed meat",
             26: "Musical instruments", 27: "Pasta", 28: "Arms and ammunition excluding defense stores", 29: "Shampoos", 30: "Sunglasses",
             31: "Tomato ketchup and sauces", 32: "Travelling bags and suitcases",
             33: "A ship designed or adapted for use for recreation or pleasure or private use",
             34: "An aircraft designed or adapted for use for recreation or pleasure or private use",
             35: "Articles of jewelry (both precious metals and imitation)", 36: "Wristwatches"}
    rows, vision = [], []
    common = dict(tax="ST", schedule_or_section="SRO 297(I)/2023 Table-I (import and supply thereof)", rule_group="ST-SRO297-T1",
                  rate_kind="percent", rate_pct=25.0, rate_raw="twenty five percent",
                  charged_on="value of the goods imported and their subsequent supply, or the retail price, as the case may be (SRO preamble)",
                  condition_text="Not applicable to goods specified in the Eighth Schedule to the Sales Tax Act (SRO 297 para 2 Explanation).",
                  valid_from="2023-03-08", valid_to=OPEN, date_basis="SRO date line 8 Mar 2023; no effective-date clause; predates scope",
                  snapshot="both", source_file=SRC297, extraction_method="embedded OCR text + page image comparison", tax_kind="sales_tax",
                  instrument="SRO 297(I)/2023")
    for n in range(1, 37):
        seg = blocks[n]
        toks = re.findall(r"\d{4}[.,]\d{4}|\d{4}\.[\dA-Za-z]{4}|\d{8}|\d{2}\.\d{2}", seg)
        # OCR repair recorded from the image (zoomed): see CORRECTIONS
        fixed = []
        for t in toks:
            if (n, t) in CORRECTIONS:
                vision.append((n, t, CORRECTIONS[(n, t)]))
                fixed.append((CORRECTIONS[(n, t)], f"ocr_text_read '{t}'; page image prints '{CORRECTIONS[(n, t)]}'"))
            else:
                fixed.append((t, ""))
        if n == 2:  # the broken token '1704.90W' was matched as '04.90'
            pass
        entries = [] if n == 18 else list(fixed)  # S.No 18 tokens are the 'except' codes, kept in except_codes
        for kind, ch, exc, text in CHAPTER_RULES.get(n, []):
            r = mk(**common, s_no=str(n), description=names[n], code_raw=text, code_norm=ch, match_level="chapter2",
                   except_codes=[e.replace(".", "") for e in exc], unparsed_except_text=0,
                   page=page_of[n], clause=f"SRO 297(I)/2023 Table-I S.No {n} col (3)")
            rows.append(r)
        if n in UNMAPPED:
            rows.append(mk(**common, s_no=str(n), description=names[n], code_raw=UNMAPPED[n].split(":")[0], code_norm="", match_level="unmapped",
                           page=page_of[n], clause=f"SRO 297(I)/2023 Table-I S.No {n} col (3)", status="needs_review",
                           issues="no code printed ('Respective headings'); mapping to PCT headings must be done by a human with the tariff; no guess made"))
            continue
        if n == 28:
            continue  # chapter rule above
        for idx, (t, note) in enumerate(entries):
            raw, norm, lvl, iss = code_entry(t)
            if note:
                iss = iss + [note]
            tf = tariff_flags(norm, lvl, tariffs)
            iss += tf
            if tf and raw in HINTS:
                iss.append(HINTS[raw])
            rows.append(mk(**common, s_no=str(n), description=names[n], code_raw=raw, code_norm=norm, match_level=lvl,
                           page=(2 if (n == 3 and idx >= 44) else page_of[n]), clause=f"SRO 297(I)/2023 Table-I S.No {n} col (3)",
                           status="needs_review" if any(not x.startswith("ocr_text_read") for x in iss) else "accepted",
                           issues="; ".join(iss)))
    return rows, vision


def sro297_t2_rows():
    common = dict(tax="ST", rule_group="ST-SRO297-T2", rate_kind="percent", rate_pct=25.0, rate_raw="twenty five percent",
                  charged_on="value of the supply of goods (SRO 297 preamble)", match_level="heading4", snapshot="both",
                  tax_kind="sales_tax", importer_status="any", schedule_or_section="SRO 297(I)/2023 Table-II as substituted by SRO 370(I)/2024 (supply of locally manufactured goods)",
                  extraction_method="page image read by Claude", source_file=SRC370, page=1)
    base = [("1", "Locally manufactured or assembled vehicles having engine capacity of 1400cc and above", "87.03", "8703", ""),
            ("2", "Locally manufactured or assembled vehicles if invoice price (excluding sales tax) exceeds Rs. 4 million", "87.03", "8703", ""),
            ("3", "Locally manufactured or assembled double cabin (4x4) pick-up vehicles", "87.04", "8704", "")]
    rows = []
    for s, desc, raw, norm, cond in base:
        rows.append(mk(**common, s_no=s, description=desc, code_raw=raw, code_norm=norm, condition_text="LOCAL SUPPLY ONLY (not an import rule). " + cond,
                       valid_from="2024-03-08", valid_to="2026-09-12", date_basis="SRO 370(I)/2024 date line 8 Mar 2024",
                       clause=f"SRO 297(I)/2023 Table-II S.No {s} as substituted by SRO 370(I)/2024", instrument="SRO 370(I)/2024"))
        # From 13 Sep 2026 the same Table-II row carries the carve-out added by SRO 1525(I)/2026. The rate is still
        # printed on SRO 370 (page 1), so that is the source of the row; SRO 1525 is cited in clause and condition.
        rows.append(mk(**{**common, "snapshot": "FY2026-27"}, s_no=s, description=desc, code_raw=raw, code_norm=norm,
                       condition_text="LOCAL SUPPLY ONLY (not an import rule). CARVE-OUT added by SRO 1525(I)/2026 para 1: 'the provisions of Table-II shall not apply to locally manufactured hybrid electric vehicles with engine capacity upto 2000cc'; so this 25% row does NOT apply to such hybrids (see the exempt row of group ST-SRO297-T2-1525-HYBRID).",
                       valid_from="2026-09-13", valid_to=OPEN, date_basis="Rate and Table-II: SRO 370(I)/2024 (8 Mar 2024). Carve-out: SRO 1525(I)/2026 date line 13 Sep 2026, 'immediate effect' (para 2)",
                       clause=f"SRO 297(I)/2023 Table-II S.No {s} (substituted by SRO 370(I)/2024), subject to the proviso added by SRO 1525(I)/2026 para 1",
                       instrument="SRO 297(I)/2023 Table-II as substituted by SRO 370(I)/2024 and amended by SRO 1525(I)/2026"))
    for raw, norm in (("87.03", "8703"), ("87.04", "8704")):
        rows.append(mk(**{**common, "rule_group": "ST-SRO297-T2-1525-HYBRID", "rate_kind": "exempt", "rate_pct": "", "rate_raw": "Table-II does not apply",
                          "source_file": SRC1525, "snapshot": "FY2026-27"}, s_no="proviso", description="Locally manufactured hybrid electric vehicles with engine capacity upto 2000cc: provisions of Table-II shall not apply",
                       code_raw=raw, code_norm=norm,
                       condition_text="LOCAL SUPPLY ONLY (not an import rule). Applies only to locally manufactured hybrid electric vehicles with engine capacity upto 2000cc. The SRO names no PCT code; the heading is taken from the Table-II rows it qualifies (87.03 / 87.04).",
                       valid_from="2026-09-13", valid_to=OPEN, date_basis="SRO 1525(I)/2026 date line 13 Sep 2026, 'immediate effect' (para 2)",
                       clause="SRO 1525(I)/2026 para 1: proviso added after Table-II of SRO 297(I)/2023", instrument="SRO 1525(I)/2026 (proviso to SRO 297(I)/2023 Table-II)"))
    return rows


# ---------------------------------------------------------------- sugar and concessions
def sugar_rows():
    rows = []
    unm = dict(code_raw="white crystalline sugar (no PCT code printed)", code_norm="", match_level="unmapped")
    # sales tax
    st = dict(tax="ST", tax_kind="sales_tax", rule_group="ST-SRO1217-SUGAR", rate_kind="percent", rate_pct=0.25, rate_raw="0.25% (reduced from eighteen percent)",
              charged_on="value of imported goods (Sales Tax Act s.2(46)); also on subsequent supply", **unm,
              description="White crystalline sugar, import and subsequent supply, up to 500,000 metric tons, by TCP or private sector; minimum VAT 3% (Twelfth Schedule) exempted",
              condition_text="(i) import by Commerce Division through TCP or private sector, subject to conditions, limitations and quota allotments; (ii) Commerce Division ensures quality assurance through an international inspection firm; (iii) cut-off date for import to avail exemption.",
              schedule_or_section="SRO 1217(I)/2025", snapshot="FY2025-26", importer_status="any")
    rows.append(mk(**st, valid_from="2025-07-08", valid_to="2025-11-30", date_basis="SRO 1217 date line 8 Jul 2025 to cut-off 30 Nov 2025 (30 Sep 2025 as issued, extended by SRO 1832 dated 22 Sep 2025)",
                   source_file=F["1217"], page=1, clause="SRO 1217(I)/2025 preamble and condition (iii), as amended by SRO 1832(I)/2025 (page 1)", instrument="SRO 1217(I)/2025 as amended by SRO 1832(I)/2025",
                   extraction_method="page image read by Claude", status="accepted"))
    rows.append(mk(**st, valid_from="2025-12-01", valid_to="2026-02-28", date_basis="SRO 527(I)/2026 (19 Mar 2026) cut-off 28 Feb 2026; rescinded by SRO 663(I)/2026 (22 Apr 2026)",
                   source_file=F["527"], page=1, clause="SRO 527(I)/2026 para 1; rescinded by SRO 663(I)/2026 paras (i)-(ii)", instrument="SRO 527(I)/2026 (rescinded)",
                   extraction_method="page image read by Claude", status="needs_review",
                   issues="DOUBTFUL WINDOW. SRO 527 (page image: dated 19 March 2026, 'in pursuance of the decision of the Federal Cabinet dated 4 Feb 2026') replaces the 30 Nov 2025 cut-off by 28 Feb 2026, but it was issued after BOTH dates and SRO 663(I)/2026 (22 Apr 2026) rescinded it 'with immediate effect'. Nothing in data/raw says whether imports between 1 Dec 2025 and 28 Feb 2026 got 0.25%, or what happens to them after the rescission. Stored as needs_review, never as an accepted rate. Owner question OQ-A3-3."))
    # income tax
    it = dict(tax="IT", tax_kind="withholding", rule_group="IT-9AD-SUGAR", rate_kind="percent", rate_pct=0.25, rate_raw="0.25% of the value of commercial import",
              charged_on="value of commercial import of white crystalline sugar (Second Schedule Part II clause (9AD))", **unm,
              description="Withholding tax under section 148 on commercial import of white crystalline sugar up to 500,000 metric ton in aggregate",
              condition_text="(i) import through Commerce Division/TCP or private sector subject to quota; (ii) quality assurance by international inspection firm; (iii) cut-off date for import.",
              schedule_or_section="Second Schedule Part II clause (9AD) added by SRO 1216(I)/2025", snapshot="FY2025-26", importer_status="any")
    rows.append(mk(**it, valid_from="2025-07-08", valid_to="2025-11-30", date_basis="SRO 1216 date line 8 Jul 2025 to cut-off 30 Nov 2025 (30 Sep 2025 as issued, changed by SRO 1833 dated 22 Sep 2025)",
                   source_file=F["1216"], page=1, clause="SRO 1216(I)/2025 new clause (9AD) conditions (iii), as amended by SRO 1833(I)/2025", instrument="SRO 1216(I)/2025 as amended by SRO 1833(I)/2025",
                   extraction_method="page image read by Claude", status="accepted"))
    rows.append(mk(**it, valid_from="2025-12-01", valid_to="2026-02-28", date_basis="SRO 455(I)/2026 (5 Mar 2026) cut-off 28 Feb 2026; rescinded by SRO 663(I)/2026 (22 Apr 2026)",
                   source_file=F["455"], page=1, clause="SRO 455(I)/2026 para 1; rescinded by SRO 663(I)/2026 para (i)", instrument="SRO 455(I)/2026 (rescinded)",
                   extraction_method="page image read by Claude", status="needs_review",
                   issues="DOUBTFUL WINDOW. SRO 455 (page image: dated 5 March 2026) replaces the 30 Nov 2025 cut-off by 28 Feb 2026, issued after the old cut-off and after the new one, and rescinded by SRO 663(I)/2026 (22 Apr 2026, 'with immediate effect'). The consolidated ITO (30.06.2026, p.649 footnotes 3-4) still prints '28th day of February 2026' next to a footnote that says 455 was rescinded: FBR's own consolidation is ambiguous. Stored as needs_review. Owner question OQ-A3-3."))
    # customs sugar
    cu = dict(tax="CUSTOMS", tax_kind="customs_concession", rule_group="CU-1215-SUGAR", rate_kind="exempt", rate_raw="exempt from the whole of customs duties (up to 0.500 MMT)",
              **unm, description="White crystalline sugar falling under respective PCT codes, up to 0.500 MMT, exempt from the whole of customs duties",
              condition_text="(i) import through Commerce Division/TCP or private sector subject to quota; (ii) quality assurance by international inspection firm; (iii) cut-off date for import.",
              schedule_or_section="SRO 1215(I)/2025", snapshot="FY2025-26", importer_status="any")
    rows.append(mk(**cu, valid_from="2025-07-08", valid_to="2025-11-30", date_basis="SRO 1215 date line 8 Jul 2025 to cut-off 30 Nov 2025 (30 Sep 2025 as issued, changed by SRO 1834 dated 22 Sep 2025)",
                   source_file=F["1215"], page=1, clause="SRO 1215(I)/2025 preamble, condition (iii), as amended by SRO 1834(I)/2025", instrument="SRO 1215(I)/2025 as amended by SRO 1834(I)/2025",
                   extraction_method="page image read by Claude", status="accepted",
                   issues="concession, out of v1 scope; not loaded into duty calculation. Cut-off 30 Nov 2025 = SRO 1215 clause (iii) '30th day of September 2025' with 'September' replaced by 'November' by SRO 1834(I)/2025 dated 22 Sep 2025 (file 20259221693431493SRO-1834-2025.pdf p1, page image read). No customs extension after 30 Nov 2025 is in data/raw (SRO 663 rescinds 455 and 527 only), so no window is stored after that date."))
    # 1386 Early Harvest Programme
    ahp = [("1", "07020000", "07020000", "Tomatoes", 3, 2, "", 0, 400000),
           ("2", "08061000", "08061000", "Grapes", 20, 6, "", 0, 230000),
           ("3", "08081000", "08031000", "Apples", 20, 6, "", 0, 100000),
           ("4", "08109010", "08109010", "Pomegranates", 20, 6, "", 0, 100000)]
    for s, pk, af, name, cd, acd, rd, pta, trq in ahp:
        norm = pk
        c = norm[:4] + "." + norm[4:]
        iss = tariff_flags(norm, "code8", load_tariffs())
        iss = [x for x in iss if "FY2026-27" not in x]  # concession expires 31 Jul 2026
        rows.append(mk(tax="CUSTOMS", tax_kind="customs_concession", schedule_or_section="SRO 1386(I)/2025 Table", s_no=s, description=name,
                       code_raw=pk, code_norm=norm, match_level="code8", rule_group="CU-1386-AHP", rate_kind="conditional",
                       rate_raw=f"CD {cd}% ; ACD {acd}% ; RD '-' (none printed) ; PTA CD {pta}% ; TRQ {trq:,} tons ; AF code {af}",
                       condition_text="Goods imported under the Early Harvest Programme with Afghanistan within the tonnage in column (9). Where the Table rate is higher than the First Schedule/notified rate, the lower rate applies (proviso).",
                       valid_from="2025-08-01", valid_to="2026-07-31", date_basis="SRO 1386(I)/2025: 1 Aug 2025 to 31 Jul 2026", snapshot="FY2025-26",
                       source_file=F["1386"], page=1, clause=f"SRO 1386(I)/2025 Table S.No {s}", instrument="SRO 1386(I)/2025",
                       status="needs_review" if iss else "accepted", issues="; ".join(iss + ["concession, out of v1 scope"]),
                       extraction_method="page image read by Claude"))
    return rows


# ---------------------------------------------------------------- Act-body rules read by the lead (sales tax s.2(46), s.3)
ST26 = "20267171373418951SalesTaxAct1990updatedupto30.06.2026.pdf"
ST25 = "202586148252375SalesTaxActupdatedupto2025-26.pdf"


def act_rows():
    rows = []
    c = dict(tax="ST", snapshot="both", valid_from="2025-07-01", valid_to=OPEN, date_basis="snapshot (identical text in the FY2025-26 and FY2026-27 consolidated Acts; the rule may be older)",
             source_file=ST26, extraction_method="text layer, read and checked by Claude", importer_status="any", instrument="Sales Tax Act 1990",
             code_raw="", code_norm="", match_level="all", rule_group="ST-ACT-S3")

    def M(**kw):
        return mk(**{**c, **kw})

    rows.append(M(schedule_or_section="s.3(1)(b)", s_no="3(1)(b)", description="Standard rate of sales tax on goods imported into Pakistan",
                   tax_kind="sales_tax", rate_kind="percent", rate_pct=18.0, rate_raw="eighteen per cent",
                   charged_on="value of goods imported = value determined under section 25 of the Customs Act plus customs-duties and federal excise duty levied thereon (s.2(46)(d))",
                   condition_text="Applies unless a Schedule, notification or SRO gives another rate/exemption. 'Eighteen' substituted for 'seventeen' by Finance (Supplementary) Act 2023.",
                   page=28, clause="Sales Tax Act s.3(1)(b); value: s.2(46)(d) (PDF pp. 28 and 25); FY2025-26 file p.27", footnote="FY2025-26 snapshot file: " + ST25))
    rows.append(M(schedule_or_section="s.2(46)(d)", s_no="2(46)(d)", description="Value of imported goods for sales tax",
                   tax_kind="sales_tax", rate_kind="conditional", rate_raw="base, not a rate",
                   charged_on="in case of imported goods (excluding those specified in the Third Schedule): the value determined under section 25 of the Customs Act, including the amount of customs-duties and federal excise duty levied thereon",
                   condition_text="Third Schedule goods are valued at retail price (s.3(2)(a)). Proviso: the Board may fix the value of imported goods (including Third Schedule goods); if the declared value is higher than the fixed value, the declared value is used.",
                   page=25, clause="Sales Tax Act s.2(46)(d) and provisos (PDF pp. 25-27)", rule_group="ST-ACT-S2-46"))
    rows.append(M(schedule_or_section="s.3(2)(a)", s_no="3(2)(a)", description="Third Schedule goods (supplies and imports) taxed on retail price",
                   tax_kind="sales_tax", rate_kind="percent", rate_pct=18.0, rate_raw="eighteen per cent of the retail price",
                   charged_on="retail price (printed by manufacturer or importer on each article/packet); where the goods are also in the Eighth Schedule, the Eighth Schedule rate applies to the retail price",
                   condition_text="Federal Government may notify a higher rate on retail price (first proviso). Third Schedule list is extracted separately (a3_st_third_schedule.csv).",
                   page=29, clause="Sales Tax Act s.3(2)(a) (PDF p.29)", rule_group="ST-ACT-S3-2A"))
    rows.append(M(schedule_or_section="s.3(2)(aa)", s_no="3(2)(aa)", description="Eighth Schedule goods taxed at the Schedule's rates and conditions",
                   tax_kind="sales_tax", rate_kind="conditional", rate_raw="rate per Eighth Schedule row", charged_on="as stated in the Eighth Schedule row",
                   condition_text="List extracted separately (a3_st_eighth_schedule.csv).", page=30, clause="Sales Tax Act s.3(2)(aa) (PDF p.30)", rule_group="ST-ACT-S3-2AA"))
    rows.append(M(schedule_or_section="s.3(2)(b)", s_no="3(2)(b)", description="Federal Government may by notification set higher or lower rates for taxable goods (basis of SRO 297(I)/2023 and SRO 1217(I)/2025)",
                   tax_kind="sales_tax", rate_kind="conditional", rate_raw="rate per notification", condition_text="power clause; each notification is in a3_sro_rules.csv",
                   page=30, clause="Sales Tax Act s.3(2)(b) (PDF p.30)", rule_group="ST-ACT-S3-2B"))
    rows.append(M(schedule_or_section="s.3(1A)", s_no="3(1A)", description="Further tax on taxable supplies to a person who has no registration number or is not an active taxpayer",
                   tax_kind="further_tax", importer_status="unregistered", rate_kind="percent", rate_pct=4.0, rate_raw="four percent of the value, in addition to the rates in s.3(1), (1B), (2), (5), (6) and s.4",
                   charged_on="value of the taxable supply", condition_text="Applies to TAXABLE SUPPLIES made to unregistered persons. The Act text does not say it is collected at import. Federal Government may notify supplies exempt from further tax. 'four' substituted for 'three' by Finance Act 2023.",
                   page=28, clause="Sales Tax Act s.3(1A) (PDF p.28; FY2025-26 file p.27)", rule_group="ST-ACT-S3-1A", status="needs_review",
                   issues="open question: is further tax collected by Customs on imports by unregistered importers? Nothing in the provided Act, schedules or SROs says so (searched 'further tax', 'unregistered'); do not apply to imports without a source"))
    rows.append(M(schedule_or_section="s.3(5)", s_no="3(5)", description="Extra tax: Federal Government may levy tax at an extra rate or amount on goods or persons, by rules",
                   tax_kind="extra_tax", rate_kind="conditional", rate_raw="not exceeding eighteen per cent of the value, as prescribed by rules",
                   charged_on="value of such goods or class of goods", condition_text="Power clause. No rate is fixed in the Act; the rules are not in data/raw.",
                   page=31, clause="Sales Tax Act s.3(5) (PDF p.31)", rule_group="ST-ACT-S3-5", status="needs_review",
                   issues="power only; no rate in documents; the rules under s.3(5) are not in data/raw"))
    rows.append(M(schedule_or_section="s.3(3B)", s_no="3(3B)", description="Ninth Schedule goods (cellular mobile phones etc.): tax at the rates, manner and time specified in the Ninth Schedule, on import and supply",
                   tax_kind="sales_tax", rate_kind="conditional", rate_raw="rate per Ninth Schedule", condition_text="List extracted separately (a3_st_ninth_schedule.csv).",
                   page=31, clause="Sales Tax Act s.3(3B) (PDF p.31)", rule_group="ST-ACT-S3-3B"))
    rows.append(M(schedule_or_section="s.3(1B)", s_no="3(1B)", description="Tenth Schedule goods: tax in lieu of s.3(1), levied in the mode and manner specified in the Schedule (by capacity or fixed basis)",
                   tax_kind="sales_tax", rate_kind="conditional", rate_raw="per Tenth Schedule", condition_text="Tenth Schedule applicability to imports is checked by sub-agent (see a3_findings).",
                   page=28, clause="Sales Tax Act s.3(1B) (PDF p.28-29)", rule_group="ST-ACT-S3-1B"))
    rows.append(M(schedule_or_section="s.18A Customs Act (proviso)", s_no="", description="Special customs duty (Customs Act s.18A) is not part of the value of supply for sales tax",
                   tax="ST", tax_kind="sales_tax", rate_kind="conditional", rate_raw="base rule, not a rate",
                   charged_on="exclusion from value", source_file="20268241784853463Customs-Act-1969.pdf", page=46, clause="Customs Act 1969 s.18A, second proviso (PDF p.46)",
                   instrument="Customs Act 1969", rule_group="ST-VALUE-SCD", condition_text="'for the purposes of the Sales Tax Act 1990, the special customs duty shall not constitute a part of the value of supply'",
                   date_basis="Customs Act consolidated 2026; no date in text", snapshot="both"))
    return rows


# ---------------------------------------------------------------- run
def write(name, rows):
    cols = list(rows[0].keys())
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    (OUT / f"{name}.json").write_text(json.dumps({"meta": {"rows": len(rows)}, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")


def render_pages():
    for key in ("1217", "1832", "527", "663", "455", "1216", "1833", "1215", "1834", "1386", "297", "370", "1525"):
        pdf = RAW / F[key]
        stem = pdf.stem
        d = pymupdf.open(pdf)
        (IMG / stem).mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(d, 1):
            f = IMG / stem / f"p{i:03d}.png"
            if not f.exists():
                p.get_pixmap(dpi=120).save(f)


def main():
    tariffs = load_tariffs()
    render_pages()
    instr, by_sro = instruments()
    # chain checks (validators)
    chain_issues = []
    for r in instr:
        for t in [x.strip() for x in r["amends_or_supersedes"].split(";") if x.strip()]:
            if t not in by_sro and not t.startswith(("929", "928", "1121")):
                chain_issues.append(f"{r['sro_number']} targets {t} which is not in the instrument list")
        if r["issue_date"] and r["effective_from"] and r["effective_from"] < r["issue_date"] and r["tax"] != "CUSTOMS":
            chain_issues.append(f"{r['sro_number']} effective before issue date")
    write("a3_instruments", instr)
    r297, vision = sro297_rows(tariffs)
    rows = r297 + sro297_t2_rows() + sugar_rows() + act_rows()
    for i, r in enumerate(rows, 1):
        r["rule_id"] = f"A3SRO-{i:04d}"
        if r["valid_to"] < r["valid_from"]:
            r["issues"] = (r["issues"] + "; " if r["issues"] else "") + "date_order: valid_to < valid_from"
            r["status"] = "needs_review"
    cols = ["rule_id"] + [c for c in rows[0].keys() if c != "rule_id"]
    rows = [{c: r.get(c, "") for c in cols} for r in rows]
    write("a3_sro_rules", rows)
    fails = [r for r in rows if r["issues"]]
    with open(OUT / "a3_sro_failures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "page_image", "s_no", "code_raw", "rate_raw", "issues", "rule_id", "source_file"])
        for r in fails:
            stem = Path(r["source_file"]).stem
            w.writerow([r["page"], f"data/processed/page_images/{stem}/p{int(r['page']):03d}.png", r["s_no"], r["code_raw"], r["rate_raw"], r["issues"], r["rule_id"], r["source_file"]])
    # spot check: every non-297 row from images + >=10% of the 297 code rows (every 7th) + all flagged
    sp = []
    for k, r in enumerate(rows):
        pick = (r["rule_group"] != "ST-SRO297-T1" and r["source_file"] != ST26 and r["source_file"] != "20268241784853463Customs-Act-1969.pdf") \
            or r["issues"] or (r["rule_group"] == "ST-SRO297-T1" and k % 6 == 0)
        if pick:
            stem = Path(r["source_file"]).stem
            rate = r["rate_raw"] if r["rate_raw"] else r["rate_pct"]
            sp.append([r["page"], f"data/processed/page_images/{stem}/p{int(r['page']):03d}.png", r["s_no"], r["code_raw"] or r["description"][:60],
                       f"{rate} | valid {r['valid_from']} to {r['valid_to']}", "", ""])
    with open(OUT / "spotcheck_a3_sro.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "page_image", "s_no", "pct_code", "rate", "correct? (Y/N)", "true_value_if_N"])
        w.writerows(sp)
    n297 = sum(1 for r in rows if r["rule_group"] == "ST-SRO297-T1")
    print("instruments", len(instr), "chain issues", chain_issues)
    print("rules", len(rows), "SRO297 T1 rows", n297, "flagged rows", len(fails), "spotcheck rows", len(sp))
    print("vision corrections", vision)


if __name__ == "__main__":
    main()
