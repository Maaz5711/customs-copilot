"""A3: ACD (additional customs duty) rules from SRO 1063(I)/2026 and SRO 1151(I)/2025.

Source: the vision-read page JSON in data/processed/sro_claude/ (the SRO scans have no
text layer). The printed text of the pages is checked against the code lists, and every
listed code is checked against the tariff of the same fiscal year, including the tariff
slab the rule says the code sits in. Nothing is guessed: rows that need a mapping the SRO
does not print (vehicle classes in CKD condition) are `needs_review`.

Output: data/processed/a3_acd_rules.{csv,json} (loadable with load_table_file into
acd_rules) and a3_acd_issues.csv (every check that did not pass, plus open questions).

Slab convention (machine readable, first token of condition_text):
  SLAB_EQ <n>  the row applies to goods whose tariff CD is exactly <n> percent
  SLAB_GE <n>  tariff CD of <n> percent or higher, plus specific-rate (non-percent) slabs
slab_pct holds <n>. Rows without a slab apply by code (or by import regime, see condition_text).
The caller of get_rule_on_date must look up the tariff CD of the code and drop rows whose slab
does not match. Rows in different rule_groups are cumulative (all returned); inside a group the
most specific code prefix wins.
"""
import csv
import json
import re
from pathlib import Path

PROC = Path("data/processed")
OPEN_END = "9999-12-31"

COLS = ["sro_number", "clause", "code_norm", "match_level", "rule_group", "rate_kind", "slab_pct",
        "condition_text", "except_codes", "unparsed_except_text", "rate_pct", "rate_specific_amount",
        "rate_specific_unit", "rate_raw", "status", "valid_from", "valid_to", "source_file", "page"]

CODE_RE = re.compile(r"\b\d{4}\.\d{4}\b")

# Para 3 "not levied" clauses (same wording in 1063 and 1151 except where overridden below).
P3 = [
    ("3(i)", "chapter2", "84", "import of plant and machinery used in manufacturing or production of goods "
     "as is classifiable under Chapter 84 and 85 of the First Schedule (only if the goods are such plant and machinery)"),
    ("3(i)", "chapter2", "85", "import of plant and machinery used in manufacturing or production of goods "
     "as is classifiable under Chapter 84 and 85 of the First Schedule (only if the goods are such plant and machinery)"),
    ("3(ii)", "chapter2", "99", "import under Chapter 99 of the First Schedule"),
    ("3(iii)", "all", "", "ONLY import under the Fifth Schedule to the Customs Act, excluding serial numbers 30, 33 "
     "and 35 of the Table of Part-I and serial numbers 102, 111, 116 (except xvi), 117 and 118 of the Table of Part III"),
    ("3(iv)", "all", "", "ONLY import under the Baggage Rules, 2006"),
    ("3(v)", "all", "", "ONLY import under Notification SRO 577(I)/2005 dated 6 June 2005"),
    ("3(vi)", "all", "", "ONLY import under Notification SRO 565(I)/2006 dated 5 June 2006"),
    ("3(vii)", "all", "", "ONLY import under Notification SRO 693(I)/2006 dated 1 July 2006"),
    ("3(viii)", "all", "", "ONLY import under the temporary importation scheme, SRO 492(I)/2009 dated 13 June 2009"),
    ("3(ix)", "all", "", "ONLY imports under condition (vii) of SRO 678(I)/2004 dated 7 August 2004 by Exploration "
     "and Production Companies, their contractors and service companies, for offshore projects only, made with "
     "effect from 18 August 2018"),
]
FIFTH_1151 = ("ONLY import under the Fifth Schedule to the Customs Act, excluding serial numbers 30, 33 and 35 "
              "of the Table of Part-I and serial numbers 102, 110, 111, 116 (except xvi), 117 and 118 of the Table of Part III")


def _pages(stem):
    out = {}
    for p in sorted((PROC / "sro_claude" / stem).glob("p*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out[d["page"]] = d
    return out


def _lists(pages):
    return {(pg, l["clause"]): l["codes"] for pg, d in pages.items() for l in d["pct_code_lists"]}


def _tariff(fy):
    rows = json.loads((PROC / f"tariff_{fy}.json").read_text(encoding="utf-8"))["rows"]
    return {r["code"]: r for r in rows}


def _slab(t, code):
    r = t.get(code)
    if r is None:
        return "MISSING"
    return r["cd_plain"] if r["cd_kind"] == "plain" else "specific"


def _below(slab, n):
    return slab == "MISSING" or (slab != "specific" and slab < n)


def build():
    rows, issues = [], []

    def issue(sro, clause, msg):
        issues.append({"sro_number": sro, "clause": clause, "issue": msg})

    def add(sro, src, page, valid, group, clause, level, code, rate, rate_raw, slab=None, cond=None,
            exc=None, status="accepted"):
        rows.append(dict(
            sro_number=sro, clause=clause, code_norm=code or "", match_level=level, rule_group=group,
            rate_kind="exempt" if rate is None else "percent", slab_pct=slab, condition_text=cond,
            except_codes=json.dumps(exc or []), unparsed_except_text=0, rate_pct=rate,
            rate_specific_amount=None, rate_specific_unit=None, rate_raw=rate_raw, status=status,
            valid_from=valid[0], valid_to=valid[1], source_file=src, page=page))

    norm = lambda c: c.replace(".", "")

    # ------------------------------------------------------------------ SRO 1063(I)/2026
    S = "1063(I)/2026"
    stem = "20266301763307131063-2026"
    src = stem + ".pdf"
    pages = _pages(stem)
    L = _lists(pages)
    t = _tariff("2026_27")
    V = ("2026-07-01", OPEN_END)  # para 4, page 2: "shall take effect from the 1st day of July, 2026"
    p1, p2 = pages[1]["text"], pages[2]["text"]
    a_txt = p1.split("(a) goods falling under tariff slab")[1].split("(b) goods falling")[0]
    b_txt = p1.split("(b) goods falling under the following PCT codes")[1].split("(c) goods imported")[0]
    a2_txt = p2.split("(a) the following goods")[1].split("(b) the following goods")[0]
    b2_txt = p2.split("(b) the following goods")[1].split("(ii) cars")[0]
    for nm, txt, key in (("(i)(a)", a_txt, (1, "(i)(a)")), ("(i)(b)", b_txt, (1, "(i)(b)")),
                         ("(ii)(a)", a2_txt, (2, "(ii)(a)")), ("(ii)(b)(i)", b2_txt, (2, "(ii)(b)(i)"))):
        printed = CODE_RE.findall(txt)
        if printed != L[key]:
            issue(S, nm, f"code list differs between page text ({len(printed)}) and list ({len(L[key])})")
    ia, ib, iia, iib = L[(1, "(i)(a)")], L[(1, "(i)(b)")], L[(2, "(ii)(a)")], L[(2, "(ii)(b)(i)")]
    g = S
    add(S, src, 1, V, g, "(i)(a)", "all", "", 2, "two per cent", 20,
        "SLAB_EQ 20 (tariff CD slab of 20%); the 36 listed codes carry their own 4% rows", [norm(c) for c in ia])
    for c in ia:
        add(S, src, 1, V, g, "(i)(a) except-list", "code8", norm(c), 4, "four percent", 20,
            "SLAB_EQ 20 (exception to the 20% slab rate)")
        if _slab(t, c) != 20.0:
            issue(S, "(i)(a) except-list", f"{c}: tariff CD is {_slab(t, c)}, rule says it sits in slab 20")
    for c in ib:
        add(S, src, 1, V, g, "(i)(b)", "code8", norm(c), 2, "two per cent")
        if _slab(t, c) == "MISSING":
            issue(S, "(i)(b)", f"{c} not in tariff FY2026-27")
    add(S, src, 2, V, g, "(ii)", "all", "", 4, "four percent", 25,
        "SLAB_GE 25 (tariff CD slab of 25% and higher, as well as slabs of specific rates); the 31 listed codes "
        "carry their own rows", [norm(c) for c in iia + iib])
    for c in iia:
        add(S, src, 2, V, g, "(ii)(a)", "code8", norm(c), 6, "six percent", 25, "SLAB_GE 25 (exception to clause (ii))")
        if _below(_slab(t, c), 25):
            issue(S, "(ii)(a)", f"{c}: tariff CD {_slab(t, c)} is not in a slab of 25% or higher")
    for c in iib:
        add(S, src, 2, V, g, "(ii)(b)(i)", "code8", norm(c), 2, "two percent", 25,
            "SLAB_GE 25 (exception to clause (ii)); in the tariff these are specific-rate lines")
        if _slab(t, c) != "specific":
            issue(S, "(ii)(b)(i)", f"{c}: tariff CD {_slab(t, c)} is not a specific rate")
    add(S, src, 1, V, S + "#(i)(c)", "(i)(c)", "all", "", 2, "two per cent", None,
        "ONLY goods imported under Notifications SRO 655(I)/2006 and 656(I)/2006, both dated 5 June 2006 "
        "(regime condition, not a tariff code or slab)")
    for c in ("8703", "8704"):
        add(S, src, 2, V, S + "#(ii)(b)(ii)", "(ii)(b)(ii)", "heading4", c, 2, "two percent", 25,
            "ONLY cars, jeeps, light commercial vehicles in CKD condition exceeding 1,000 cc and heavy "
            "commercial vehicles in CKD condition (exception to clause (ii))", status="needs_review")
    issue(S, "(ii)(b)(ii)", "The SRO names vehicle classes in CKD condition and prints no PCT codes. Mapped to "
          "headings 87.03 and 87.04 as an inference; which tariff lines are CKD must be decided by a person. "
          "Row status needs_review.")
    for cl, lvl, code, cond in P3:
        add(S, src, 2, V, f"{S}#{cl}", cl, lvl, code, None, "not levied", None, cond)
    for c in ("8703", "8704"):
        add(S, src, 2, V, f"{S}#3(x)", "3(x)", "heading4", c, None, "not levied", None,
            "ONLY import of cars, jeeps and light commercial vehicles in CKD condition up to 1,000cc, and import of "
            "vehicles in CBU condition up to 850cc", status="needs_review")
    issue(S, "3(x)", "Vehicle classes without PCT codes; mapped to headings 87.03/87.04 as an inference "
          "(the 'vehicles in CBU condition' could also mean other headings such as 87.11). needs_review.")
    for c in ("8703.8030", "8711.6040", "8711.6060"):
        add(S, src, 2, V, f"{S}#3(xi)", "3(xi)", "code8", norm(c), None, "not levied", None, "import under this PCT code")
        if c not in t:
            issue(S, "3(xi)", f"{c} not in tariff FY2026-27")

    # ------------------------------------------------------------------ SRO 1151(I)/2025
    S = "1151(I)/2025"
    stem = "202572975414701SRO1151OF2025"
    src = stem + ".pdf"
    pages = _pages(stem)
    L = _lists(pages)
    t = _tariff("2025_26")
    V = ("2025-07-01", "2026-06-30")  # para 4 page 2: effect 1 Jul 2025; SRO 1063(I)/2026 supersedes it from 1 Jul 2026
    p1 = pages[1]["text"]
    c_txt = p1.split("(c) goods imported under following PCT codes")[1].split("(ii) four percent")[0]
    d_txt = p1.split("(a) goods falling under PCT codes")[1]
    for nm, txt, key in (("(i)(c)", c_txt, (1, "(i)(c)")), ("(iv)(a)", d_txt, (1, "(iv)(a)"))):
        printed = CODE_RE.findall(txt)
        if printed != L[key]:
            issue(S, nm, f"code list differs between page text ({len(printed)}) and list ({len(L[key])})")
    ic, iva = L[(1, "(i)(c)")], L[(1, "(iv)(a)")]
    g = S
    add(S, src, 1, V, g, "(i)(a)", "all", "", 2, "two percent", 15, "SLAB_EQ 15 (tariff CD slab of 15%)")
    add(S, src, 1, V, S + "#(i)(b)", "(i)(b)", "all", "", 2, "two percent", None,
        "ONLY goods imported under Notifications SRO 655(I)/2006 and 656(I)/2006, both dated 5 June 2006")
    for c in ic:
        add(S, src, 1, V, g, "(i)(c)", "code8", norm(c), 2, "two percent")
        if _slab(t, c) == "MISSING":
            issue(S, "(i)(c)", f"{c} not in tariff FY2025-26")
    add(S, src, 1, V, g, "(ii)", "all", "", 4, "four percent", 20, "SLAB_EQ 20 (tariff CD slab of 20%)")
    add(S, src, 1, V, g, "(iv)", "all", "", 6, "six percent", 30,
        "SLAB_GE 30 (tariff CD slab of 30% and higher, as well as slabs of specific rates); the 14 listed codes "
        "carry their own 2% rows", [norm(c) for c in iva])
    for c in iva:
        add(S, src, 1, V, g, "(iv)(a)", "code8", norm(c), 2, "two percent", 30,
            "SLAB_GE 30 (exception to clause (iv)); in the tariff these are specific-rate lines")
        if _slab(t, c) != "specific":
            issue(S, "(iv)(a)", f"{c}: tariff CD {_slab(t, c)} is not a specific rate")
    for c in ("8703", "8704"):
        add(S, src, 2, V, S + "#(iv)(b)", "(iv)(b)", "heading4", c, 2, "two percent", 30,
            "ONLY cars, jeeps, light commercial vehicles in CKD condition exceeding 1,000 cc and heavy commercial "
            "vehicles in CKD condition (exception to clause (iv))", status="needs_review")
    issue(S, "(iv)(b)", "Same CKD vehicle mapping inference as 1063 (ii)(b)(ii): headings 87.03/87.04, needs_review.")
    issue(S, "numbering", "The printed clauses run (i), (ii), (iv): clause (iii) is absent in the SRO as printed. Stored as "
          "printed. The FY2025-26 tariff has CD slabs 0,5,10,15,20,30,35 and above (no 25%), so no slab is left uncovered "
          "between 15 and 30, but a missing clause cannot be ruled out. Owner may confirm with FBR.")
    for cl, lvl, code, cond in P3:
        if cl == "3(iii)":
            cond = FIFTH_1151
        add(S, src, 2, V, f"{S}#{cl}", cl, lvl, code, None, "not levied", None, cond)
    for c in ("8703", "8704"):
        add(S, src, 2, V, f"{S}#3(x)", "3(x)", "heading4", c, None, "not levied", None,
            "ONLY import of cars, jeeps and light commercial vehicles in CKD condition up to 1,000cc, and import of "
            "vehicles in CBU condition up to 850cc", status="needs_review")
    for c in ("8703.8030", "8711.6040", "8711.6060"):
        add(S, src, 2, V, f"{S}#3(xi)", "3(xi)", "code8", norm(c), None, "not levied", None, "import under this PCT code")
        if c not in t:
            issue(S, "3(xi)", f"{c} not in tariff FY2025-26")
    issue("both", "para 3(iii)", "1151 para 3(iii) excludes Part III serial 110 as well; 1063 does not. Stored as printed.")
    issue("both", "para 3 scope", "Para 3 'not levied' rows are stored with rate_kind exempt in their own rule_group each, "
          "so they come back next to the levy rows. Rows whose condition says ONLY apply only if the import regime "
          "named in condition_text is true; the store cannot evaluate that.")
    return rows, issues


def write():
    rows, issues = build()
    with open(PROC / "a3_acd_rules.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    (PROC / "a3_acd_rules.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    with open(PROC / "a3_acd_issues.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["sro_number", "clause", "issue"])
        w.writeheader()
        w.writerows(issues)
    return rows, issues


def spotcheck(rows):
    """Sheet for the owner: every non-code row (slab, regime, para 3, CKD) and about 15% of the code rows (seeded)."""
    import random
    rnd = random.Random(2026)
    code_rows = [r for r in rows if r["match_level"] == "code8" and r["rate_kind"] == "percent"]
    pick = {id(r) for r in rows if r not in code_rows}
    pick |= {id(r) for r in rnd.sample(code_rows, k=max(1, round(len(code_rows) * 0.15)))}
    out = [["page", "page_image", "clause", "pct_code", "rate", "correct? (Y/N)", "true_value_if_N"]]
    for r in sorted((r for r in rows if id(r) in pick), key=lambda r: (r["sro_number"], r["page"], r["clause"], r["code_norm"])):
        stem = Path(r["source_file"]).stem
        what = r["code_norm"] or "(all codes)"
        if r["rate_kind"] == "exempt":
            rate = "not levied | " + (r["condition_text"] or "")[:90]
        else:
            rate = f"{r['rate_raw']} ({r['rate_pct']}%)" + (f" | {r['condition_text'][:70]}" if r["slab_pct"] else "")
        out.append([r["page"], f"data/processed/page_images/{stem}/p{int(r['page']):03d}.png", f"{r['sro_number']} {r['clause']}", what, rate, "", ""])
    with open(PROC / "spotcheck_a3_acd.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(out)
    return len(out) - 1


if __name__ == "__main__":
    import collections
    r, i = write()
    print(len(r), "rows;", len(i), "issues;", spotcheck(r), "spot-check rows")
    print(collections.Counter((x["sro_number"], x["rate_kind"], x["status"]) for x in r))
    for x in i:
        print(" -", x["sro_number"], x["clause"], x["issue"][:110])
