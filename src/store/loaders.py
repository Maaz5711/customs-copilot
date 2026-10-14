"""Loaders: parsed JSON/CSV from data/processed/ -> SQLite legal store.

Nothing is silently fixed. Rows that failed validation upstream are loaded with
status='needs_review'; a database constraint violation aborts the whole load.
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path

from .resolve import canon_sro, norm_code
from .schema import OPEN_END

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"

FY_META = {
    "tariff_2026_27": "FY2026-27",
    "tariff_2025_26": "FY2025-26",
}

# Facts about the SROs loaded now. Dates are read from the printed clauses
# (see docs/store_schema.md "SRO dates"). page = page carrying the effective/validity clause
# (or the date line when validity_basis = 'date_line').
SRO_FACTS = [
    dict(sro_number="1064(I)/2026", instrument_kind="RD", sro_date="2026-06-30",
         supersedes="1152(I)/2025", validity_basis="clause",
         valid_from="2026-07-01", valid_to=OPEN_END,
         source_file="202663017637155381064-2026.pdf", page=30,
         note="Clause 6: 'shall take effect from the 1st day of July, 2026'. No end date printed (owner reading, owner_tasks T4: effective 1 Jul 2026, end none), so valid_to stays 9999-12-31."),
    dict(sro_number="1152(I)/2025", instrument_kind="RD", sro_date="2025-06-30",
         supersedes="928(I)/2024", validity_basis="clause",
         valid_from="2025-07-01", valid_to="2026-06-30",
         source_file="202572975650649SRO.1152of2025.pdf", page=39,
         note="Clause 6: effect from 1 Jul 2025, 'shall remain in force till the 30th June, 2026' (owner reading, owner_tasks T5: effective 1 Jul 2025, end 30 Jun 2026, as printed)."),
    dict(sro_number="1063(I)/2026", instrument_kind="ACD", sro_date="2026-06-30",
         supersedes="1151(I)/2025", validity_basis="clause",
         valid_from="2026-07-01", valid_to=OPEN_END,
         source_file="20266301763307131063-2026.pdf", page=2,
         note="'shall take effect from the 1st day of July, 2026'. No end date printed. ACD rules loaded from data/processed/a3_acd_rules.csv."),
    dict(sro_number="1151(I)/2025", instrument_kind="ACD", sro_date="2025-06-30",
         supersedes="929(I)/2024", validity_basis="clause",
         valid_from="2025-07-01", valid_to="2026-06-30",
         source_file="202572975414701SRO1151OF2025.pdf", page=2,
         note="Effect from 1 Jul 2025; end date = day before SRO 1063(I)/2026 takes effect (superseded). ACD rules loaded from data/processed/a3_acd_rules.csv."),
    dict(sro_number="1898(I)/2025", instrument_kind="RD", sro_date="2025-10-01",
         supersedes=None, validity_basis="date_line",
         valid_from="2025-10-01", valid_to="2026-06-29",
         source_file="202510117101711806SRO-18982025.pdf", page=1,
         note="no effective-date clause printed; date line used. Owner reading (owner_tasks T2): date line 1st October 2025, no start or end wording printed. End = day before SRO 1065(I)/2026 date line, because para 1 of 1065 says 'in supersession of ... S.R.O. 1898(I)/2025 dated 1st October, 2025' (Claude reading of the scan image, 1065 p.1). 40% RD on commercial used vehicles, in addition to 1152(I)/2025 (para 2). Rules loaded into rd_rules (rule_group 1898(I)/2025)."),
    dict(sro_number="1065(I)/2026", instrument_kind="RD", sro_date="2026-06-30",
         supersedes="1898(I)/2025", validity_basis="date_line",
         valid_from="2026-06-30", valid_to=OPEN_END,
         source_file="202663020651815SRO1065 (1).pdf", page=1,
         note="no effective-date clause printed; date line used. Owner reading (owner_tasks T1): date line 30 June, 2026, no start or end wording printed. Para 2 makes it 'in addition to' 1064(I)/2026, which takes effect 1 Jul 2026, so 30 Jun 2026 itself is a one-day oddity (1152 still in force that day). 30% RD on commercial used vehicles. Rules loaded into rd_rules (rule_group 1065(I)/2026)."),
]
# superseded_by is derived from `supersedes` at load time.


# --------------------------------------------------------------------- tariff

def load_tariff(conn: sqlite3.Connection, key: str, path: Path | None = None) -> dict:
    """Load tariff_2026_27 or tariff_2025_26 JSON. Idempotent per fy."""
    fy = FY_META[key]
    data = json.loads((path or PROC / f"{key}.json").read_text(encoding="utf8"))
    cur = conn.cursor()
    cur.execute("DELETE FROM tariff_lines WHERE fy = ?", (fy,))
    cur.execute("DELETE FROM tariff_headings WHERE fy = ?", (fy,))
    n_head = n_lines = n_special = n_review = 0
    for h in data["headings"]:
        cur.execute(
            "INSERT INTO tariff_headings (fy, heading, text, valid_from, valid_to, source_file, page)"
            " VALUES (?,?,?,?,?,?,?)",
            (fy, h["heading"], h["text"], h["valid_from"], h["valid_to"], h["source_file"], h["page"]),
        )
        n_head += 1

    def insert(r, level, special):
        nonlocal n_review
        kind = r.get("cd_kind", "plain")
        spec = r.get("cd_specific")
        note = None
        status = "accepted"
        if special:
            raw0 = (r.get("cd_raw") or "").strip()
            if raw0 == "0":
                kind, rate, amt, unit = "plain", 0.0, None, None
            else:  # blank or odd cell text: keep as printed, do not guess
                kind, rate, amt, unit = "compound", None, None, None
                status = "needs_review"
                r = dict(r, cd_raw=raw0)
            note = "Chapter 99 special-purpose entry; text may continue on adjacent pages (one row per page fragment)"
        elif kind == "plain":
            rate, amt, unit = r["cd_plain"], None, None
        else:
            rate, amt, unit = None, spec["amount"], spec["unit"]
        if r.get("rotated") and kind == "specific":
            status = "needs_review"
            note = ("Rotated specific-duty cell; amount reassembled from wrapped text "
                    "(e.g. 'Rs.10550/MT'). Scale is an inference, owner must confirm on the spot-check sheet.")
        if status == "needs_review":
            n_review += 1
        cur.execute(
            "INSERT INTO tariff_lines (fy, code, code_norm, level, heading, description, cd_kind, cd_rate,"
            " cd_specific_amount, cd_specific_unit, cd_raw, rotated, note, status,"
            " valid_from, valid_to, source_file, page) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fy, r["code"], norm_code(r["code"]), level, r.get("heading"), r["description"], kind, rate,
             amt, unit, r.get("cd_raw"), 1 if r.get("rotated") else 0, note, status,
             r["valid_from"], r["valid_to"], r["source_file"], r["page"]),
        )

    for r in data["rows"]:
        insert(r, 8, False)
        n_lines += 1
    for r in data.get("special", []):
        insert(r, 4, True)
        n_special += 1
    conn.commit()
    return dict(fy=fy, headings=n_head, lines8=n_lines, special4=n_special, needs_review=n_review)


# ----------------------------------------------------------------------- SROs

def load_sros(conn: sqlite3.Connection, facts=None) -> int:
    facts = facts or SRO_FACTS
    sup_by = {f["supersedes"]: f["sro_number"] for f in facts if f.get("supersedes")}
    cur = conn.cursor()
    for f in facts:
        by = sup_by.get(f["sro_number"])
        cur.execute(
            "INSERT OR REPLACE INTO sros (sro_number, instrument_kind, sro_date, supersedes, superseded_by,"
            " validity_basis, sro_status, note, status, valid_from, valid_to, source_file, page)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f["sro_number"], f["instrument_kind"], f["sro_date"], f.get("supersedes"), by,
             f["validity_basis"], "superseded" if by else "in_force", f.get("note"),
             "needs_review" if f["validity_basis"] == "date_line" else "accepted",
             f["valid_from"], f["valid_to"], f["source_file"], f["page"]),
        )
    conn.commit()
    return len(facts)


# ------------------------------------------------------------------------- RD

_EXC_KW = re.compile(r"\b(except|excepting|excluding|other than)\b", re.I)
_ANY_CODE = re.compile(r"\d{4}\.\d{4}|(?<![\d.])\d{2}\.\d{2}(?!\d|\.\d)")


def parse_except(description: str) -> tuple[list[str], bool]:
    """Return (except tokens as digit strings, unparsed_text_flag).

    Tokens are the 8-digit codes and 4-digit headings printed AFTER the first
    except/excluding/other-than keyword. If a keyword is present but no code follows
    (e.g. 'other than swimwear'), the row carries a free-text qualifier the store cannot
    evaluate: flag=True and nothing is guessed.
    """
    m = _EXC_KW.search(description)
    if not m:
        return [], False
    tail = description[m.start():]
    toks = []
    for t in _ANY_CODE.findall(tail):
        n = norm_code(t)
        if n not in toks:
            toks.append(n)
    return toks, (len(toks) == 0)


# 'Respective headings' rows: the code column names no code. Owner read the description on the page image
# (owner_tasks T4/T5: S.No 686/692 = 'Plums (allocha)', S.No 687/693 = 'Cinematographic film'); the code is mapped by
# description match to the tariff (Claude): 'Plums (allocha)' is the only such line in both tariffs (0813.4050);
# 'Cinematographic film' is the description of heading 37.06 (3706.1000 and 3706.9000), so the rule is a heading rule.
# Rate units checked on the page images (1064 p.29, 1152 p.38): 686 = 20.0 (percent), 692 = 28 (percent),
# 687 = Rs.2400 per minute, 693 = Rs.3000 per minute.
RESPECTIVE_MAP = {
    ("1064(I)/2026", "686"): "0813.4050",
    ("1064(I)/2026", "687"): "37.06",
    ("1152(I)/2025", "692"): "0813.4050",
    ("1152(I)/2025", "693"): "37.06",
}
RESPECTIVE_NOTE = "description read by owner, code mapped by description match to the tariff"


def split_codes(raw: str) -> list[str]:
    """'8517.1390, 8517.1419' -> ['85171390','85171419']; '03.03' -> ['0303']; none -> []."""
    return [norm_code(t) for t in _ANY_CODE.findall(raw)]


def _rate_fields(row: dict) -> dict:
    raw = str(row["rate"]).strip()
    spec = row.get("rate_specific")
    if spec:
        return dict(rate_kind="specific", rate_pct=None, rate_specific_amount=float(spec["amount"]),
                    rate_specific_unit=spec["unit"], rate_raw=raw)
    try:
        return dict(rate_kind="percent", rate_pct=float(raw), rate_specific_amount=None,
                    rate_specific_unit=None, rate_raw=raw)
    except ValueError:
        return dict(rate_kind="conditional", rate_pct=None, rate_specific_amount=None,
                    rate_specific_unit=None, rate_raw=raw)


def _failure_keys(csv_path: Path) -> set[tuple[str, int]]:
    """(s_no, page) of unresolved failures: owner_decision blank."""
    out = set()
    with open(csv_path, encoding="utf8", newline="") as f:
        for r in csv.DictReader(f):
            if not (r.get("owner_decision") or "").strip():
                out.add((str(r["s_no"]).strip(), int(r["page"])))
    return out


def load_rd(conn: sqlite3.Connection, stem: str, sro_number: str, failures_csv: Path | None = None,
            path: Path | None = None) -> dict:
    """Load sro_1064_rd / sro_1152_rd. Multi-code rows are expanded to one row per code."""
    data = json.loads((path or PROC / f"{stem}.json").read_text(encoding="utf8"))
    fails = _failure_keys(failures_csv or PROC / f"{stem}_failures.csv")
    sro = conn.execute("SELECT * FROM sros WHERE sro_number = ?", (sro_number,)).fetchone()
    if sro is None:
        raise RuntimeError(f"load_sros first: {sro_number} missing")
    src = data["summary"]["source_file"]
    cur = conn.cursor()
    cur.execute("DELETE FROM rd_rules WHERE sro_number = ?", (sro_number,))
    counts = dict(source_rows=0, store_rows=0, needs_review=0, failures_matched=0, unmapped=0,
                  conditional=0, expanded_multi_code=0, with_except_codes=0, unparsed_except=0)
    matched_fail = set()
    for row in data["rows"]:
        counts["source_rows"] += 1
        key = (str(row["s_no"]).strip(), int(row["page"]))
        failed = key in fails
        if failed:
            matched_fail.add(key)
            counts["failures_matched"] += 1
        codes = split_codes(row["pct_code"])
        mapped = (sro_number, str(row["s_no"]).strip()) in RESPECTIVE_MAP
        if not codes and mapped:
            codes = split_codes(RESPECTIVE_MAP[(sro_number, str(row["s_no"]).strip())])
            counts["mapped_by_description"] = counts.get("mapped_by_description", 0) + 1
        elif not codes:
            codes = [None]
            counts["unmapped"] += 1
        elif len(codes) > 1:
            counts["expanded_multi_code"] += 1
        excepts, unparsed = parse_except(row["description"])
        rf = _rate_fields(row)
        issues = list(row.get("issues") or [])
        review = failed or row.get("status") == "review"
        if mapped:   # the only open issue on these rows was the missing code; owner read the description
            issues = [i for i in issues if "Respective headings" not in i] + [RESPECTIVE_NOTE]
            review = failed
        if rf["rate_kind"] == "conditional":
            issues.append("rate is conditional text, not a single number")
            counts["conditional"] += 1
            review = True
        if codes == [None]:
            issues.append("pct_code does not name a code or heading; needs manual mapping")
            review = True
        for c in codes:
            if c is None:
                level = "unmapped"
            elif len(c) == 8:
                level = "code8"
            elif len(c) == 4:
                level = "heading4"
            else:
                raise ValueError(f"unexpected code length in S.No {row['s_no']}: {row['pct_code']!r}")
            cur.execute(
                "INSERT INTO rd_rules (sro_number, s_no, raw_pct_code, description, clause, issues,"
                " code_norm, match_level, except_codes, unparsed_except_text, rule_group,"
                " rate_kind, rate_pct, rate_specific_amount, rate_specific_unit, rate_raw,"
                " status, valid_from, valid_to, source_file, page)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sro_number, str(row["s_no"]), row["pct_code"], row["description"],
                 f"Table S.No {row['s_no']}", "; ".join(issues) or None,
                 c, level, json.dumps(excepts), 1 if unparsed else 0, sro_number,
                 rf["rate_kind"], rf["rate_pct"], rf["rate_specific_amount"], rf["rate_specific_unit"],
                 rf["rate_raw"], "needs_review" if review else "accepted",
                 sro["valid_from"], sro["valid_to"], src, row["page"]),
            )
            counts["store_rows"] += 1
            counts["needs_review"] += 1 if review else 0
            counts["with_except_codes"] += 1 if excepts else 0
            counts["unparsed_except"] += 1 if unparsed else 0
    missing = fails - matched_fail
    if missing:
        raise RuntimeError(f"failure rows not found in {stem}.json: {sorted(missing)}")
    conn.commit()
    return counts


def load_rd_used_vehicles(conn: sqlite3.Connection) -> dict:
    """RD rules of the two one-paragraph notifications 1898(I)/2025 (40%) and 1065(I)/2026 (30%).

    Source: Claude vision readings in data/processed/sro_claude/*/p001.json (rate and text), cross-checked against
    the page image. Four heading rows each (8702, 8703, 8704, 8711). The condition (commercial import of used
    vehicles under clause (xvi) of S.No.10 of Appendix-C, Import Policy Order 2022) cannot be tested from the HS code,
    so it is written into the description and the rows are needs_review (dates come from the date line).
    Own rule_group = the SRO number, so these add to 1064/1152 and never replace them.
    """
    spec = [("1898(I)/2025", "202510117101711806SRO-18982025", 40.0),
            ("1065(I)/2026", "202663020651815SRO1065_1", 30.0)]
    cur = conn.cursor()
    counts = {}
    for sro_number, folder, rate in spec:
        sro = conn.execute("SELECT * FROM sros WHERE sro_number = ?", (sro_number,)).fetchone()
        if sro is None:
            raise RuntimeError(f"load_sros first: {sro_number} missing")
        data = json.loads((PROC / "sro_claude" / folder / "p001.json").read_text(encoding="utf8"))
        r0 = data["rates"][0]
        if float(r0["rate"]) != rate:
            raise RuntimeError(f"{sro_number}: reading says {r0['rate']}, expected {rate}")
        cur.execute("DELETE FROM rd_rules WHERE sro_number = ?", (sro_number,))
        desc = ("Commercial import of used vehicles, imported under clause (xvi) of S.No.10 of the Table of "
                "Appendix-C of the Import Policy Order, 2022, as per the condition stipulated therein; "
                "in addition to the RD under the main RD notification")
        for h in ("8702", "8703", "8704", "8711"):
            cur.execute(
                "INSERT INTO rd_rules (sro_number, s_no, raw_pct_code, description, clause, issues,"
                " code_norm, match_level, except_codes, unparsed_except_text, rule_group,"
                " rate_kind, rate_pct, rate_specific_amount, rate_specific_unit, rate_raw,"
                " status, valid_from, valid_to, source_file, page)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sro_number, "para 1", f"Heading {h}", desc, "para 1 (rate); para 2 (in addition)",
                 "no effective-date clause printed; date line used. Condition (commercial used vehicles under the "
                 "Import Policy Order) cannot be checked from the HS code: caller must ask. Rate read by vision model.",
                 h, "heading4", "[]", 0, sro_number, "percent", rate, None, None, str(r0["rate"]),
                 "needs_review", sro["valid_from"], sro["valid_to"], sro["source_file"], 1))
        counts[sro_number] = 4
    conn.commit()
    return counts


# ------------------------------------------------- generic CSV/JSON contract

TABLE_COLUMNS = {
    # table -> (required columns, optional columns). Fact columns are always required.
    "acd_rules": (["sro_number", "clause", "code_norm", "match_level", "rule_group", "rate_kind"],
                  ["slab_pct", "condition_text", "except_codes", "unparsed_except_text", "rate_pct",
                   "rate_specific_amount", "rate_specific_unit", "rate_raw", "status"]),
    "sales_tax_rules": (["instrument", "clause", "tax_kind", "code_norm", "match_level", "rule_group", "rate_kind"],
                        ["importer_status", "charged_on", "condition_text", "except_codes",
                         "unparsed_except_text", "rate_pct", "rate_specific_amount", "rate_specific_unit",
                         "rate_raw", "status"]),
    "income_tax_rules": (["instrument", "clause", "code_norm", "match_level", "rule_group", "rate_kind"],
                         ["importer_status", "importer_category", "charged_on", "condition_text", "except_codes",
                          "unparsed_except_text", "rate_pct", "rate_specific_amount", "rate_specific_unit",
                          "rate_raw", "status"]),
    "legal_notes": (["note_kind", "scope", "note_no", "text"], ["hs_edition", "status", "table_json"]),
    "fed_rules": (["row_id", "fy", "schedule", "table_no", "s_no", "description", "code_norm", "match_level", "rule_group",
                   "applies_to", "rate_kind"],
                  ["sub", "sub_desc", "heading_raw", "rate_basis", "rate_ref_s_no", "compound_rule", "cc_ge", "cc_gt", "cc_le",
                   "usd_gt", "usd_le", "condition_text", "effective_note", "amended_by", "issues", "except_codes",
                   "unparsed_except_text", "rate_pct", "rate_specific_amount", "rate_specific_unit", "rate_raw", "status"]),
}
FACT = ["valid_from", "valid_to", "source_file", "page"]


def load_table_file(conn: sqlite3.Connection, table: str, path: Path) -> int:
    """Load a CSV (header row) or JSON (list of objects) into one of the contract tables.

    Empty CSV cells become NULL (so a missing page/valid_from fails the NOT NULL check).
    Unknown or missing required columns raise ValueError. The load is all-or-nothing.
    """
    if table not in TABLE_COLUMNS:
        raise ValueError(f"no loader contract for {table!r}; allowed: {sorted(TABLE_COLUMNS)}")
    req, opt = TABLE_COLUMNS[table]
    path = Path(path)
    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf8"))
        if isinstance(rows, dict):
            rows = rows["rows"]
    else:
        with open(path, encoding="utf8", newline="") as f:
            rows = list(csv.DictReader(f))
    allowed = set(req) | set(opt) | set(FACT)
    cur = conn.cursor()
    n = 0
    try:
        for i, r in enumerate(rows, 1):
            missing = [c for c in req + FACT if c not in r]
            extra = [c for c in r if c not in allowed]
            if missing or extra:
                raise ValueError(f"{path.name} row {i}: missing columns {missing}, unknown columns {extra}")
            vals = {k: (None if (isinstance(v, str) and v.strip() == "") else v) for k, v in r.items()}
            if vals.get("match_level") == "all" and vals.get("code_norm") is None:
                vals["code_norm"] = ""  # 'all' = empty prefix; blank CSV cell is not NULL here
            if vals.get("code_norm") is not None:
                vals["code_norm"] = str(vals["code_norm"])
            if isinstance(vals.get("table_json"), (dict, list)):
                vals["table_json"] = json.dumps(vals["table_json"], ensure_ascii=False)
            if isinstance(vals.get("except_codes"), list):
                vals["except_codes"] = json.dumps(vals["except_codes"])
            vals = {k: v for k, v in vals.items() if not (v is None and k in ("except_codes", "status",
                    "unparsed_except_text", "importer_status", "hs_edition", "table_json",
                    "sub", "heading_raw", "issues"))}
            cols = list(vals)
            cur.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        [vals[c] for c in cols])
            n += 1
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return n


# ------------------------------------------------------- A3 instruments (sales tax / income tax / concessions)

# Concessions that have a printed end date but no 'valid_to' column in a3_instruments.csv (read from the SRO text).
INSTRUMENT_END = {"1386(I)/2025": "2026-07-31"}   # SRO 1386 clause: 1 Aug 2025 to 31 Jul 2026 (page 1)


def load_instruments(conn: sqlite3.Connection, path: Path | None = None) -> int:
    """Add the non-RD/ACD notifications of data/processed/a3_instruments.csv to `sros`.

    sro_status: rescinded / superseded come from the chain; 'amended' notifications are still in force.
    A rescinded notification ends the day before the rescinding one takes effect.
    Chain facts only; the rules themselves live in sales_tax_rules / income_tax_rules.
    """
    import datetime as dt
    rows = list(csv.DictReader(open(path or PROC / "a3_instruments.csv", encoding="utf8", newline="")))
    eff = {canon_sro(r["sro_number"]): r["effective_from"] for r in rows if re.search(r"\d+\s*\(I\)", r["sro_number"])}
    have = {r[0] for r in conn.execute("SELECT sro_number FROM sros")}
    cur = conn.cursor()
    n = 0
    for r in rows:
        if r["tax"] not in ("ST", "IT", "ST+IT", "CUSTOMS") or not re.search(r"\d+\s*\(I\)", r["sro_number"]):
            continue
        num = canon_sro(r["sro_number"])
        if num in have:
            continue
        status = {"rescinded": "rescinded", "superseded": "superseded"}.get(r["status"], "in_force")
        by = canon_sro(r["superseded_by"]) if (status != "in_force" and r["superseded_by"]) else None
        if status == "rescinded" and not by:   # a3_instruments lists the rescinding SRO in 'amended_or_superseded_by'? derive it
            by = next((canon_sro(x["sro_number"]) for x in rows if num in [canon_sro(t) for t in re.findall(r"\d+\s*\(I\)\s*/\s*\d{4}", x["amends_or_supersedes"])]
                       and "rescind" in x["effect"].lower()), None)
        vt = OPEN_END
        if by and by in eff:
            vt = (dt.date.fromisoformat(eff[by]) - dt.timedelta(days=1)).isoformat()
        if num in INSTRUMENT_END:
            vt = INSTRUMENT_END[num]
        basis = "clause" if r["effective_basis"].lower().startswith("clause") else "date_line"
        kind = {"ST": "ST", "IT": "IT", "ST+IT": "OTHER", "CUSTOMS": "CD"}[r["tax"]]
        note = f"{r['effect']}. {r['summary']}"[:900]
        cur.execute(
            "INSERT INTO sros (sro_number, instrument_kind, sro_date, supersedes, superseded_by, validity_basis,"
            " sro_status, note, status, valid_from, valid_to, source_file, page) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (num, kind, r["issue_date"], r["amends_or_supersedes"] or None, by, basis, status, note,
             "needs_review" if basis == "date_line" else "accepted", r["effective_from"], max(vt, r["effective_from"]),
             r["source_file"], int(r["page"] or 1)),
        )
        n += 1
    conn.commit()
    return n


# ------------------------------------------------------------------ A4 legal notes -> legal_notes table

NOTES_EDITION = "HS2022 (edition of the FBR tariff PDF; applicability to FY2025-26 and FY2026-27 assumed, not proven)"
NOTES_FROM, NOTES_TO = "2025-07-01", OPEN_END
_KIND = {"gri": "general_rule", "gri_pakistan": "general_rule", "section_note": "section_note",
         "chapter_note": "chapter_note", "subheading_note": "subheading_note"}


OWNER_OK_NOTES = [("chapter_note", "Chapter 74", "1"), ("subheading_note", "Chapter 74", "1"),
                  ("subheading_note", "Chapter 78", "1")]


def legal_notes_rows(path: Path | None = None) -> list[dict]:
    """Map data/processed/legal_notes.json (A4 output) onto the legal_notes contract. No text is changed.

    Dates: the notes carry no validity of their own. 2025-07-01 .. 9999-12-31 is a documented assumption
    (first day of the earliest in-scope fiscal year, open end), written into hs_edition so no one reads it as proven.
    """
    data = json.loads((path or PROC / "legal_notes.json").read_text(encoding="utf8"))
    out = []
    for r in data:
        scope = {"gri": "General Rules (GRI)", "gri_pakistan": "Pakistan Rules"}.get(r["kind"], r["section_or_chapter"])
        out.append(dict(
            note_kind=_KIND[r["kind"]], scope=scope, note_no=str(r["note_number"]), hs_edition=NOTES_EDITION,
            text=r["text"], status="needs_review" if r.get("flags") else "accepted",
            valid_from=NOTES_FROM, valid_to=NOTES_TO, source_file=r["source_file"], page=int(r["page"])))
    # structured tables (Claude reading of page images) and owner confirmations; the flattened text is kept as is
    for t in json.loads((PROC / "legal_notes_tables.json").read_text(encoding="utf8")):
        row = next(x for x in out if (x["note_kind"], x["scope"], x["note_no"]) == (t["note_kind"], t["scope"], t["note_no"]))
        row["table_json"] = t["table_json"]
        row["status"] = t["status"]
    for key in OWNER_OK_NOTES:   # owner_tasks N365-Chapter74-1, N366-Chapter74-1, N376-Chapter78-1: answer 'ok'
        row = next(x for x in out if (x["note_kind"], x["scope"], x["note_no"]) == key)
        row["status"] = "verified"
    return out
