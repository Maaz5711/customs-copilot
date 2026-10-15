"""Citation correctness (C2): does each citation point at a real fact row on the answer's date?

Checked against the exact tools and the dated store, never by an LLM:
* tariff citation -> lookup_code(code, date) finds the line with the same source_file and page
* SRO / tax / note citations -> the file and page exist in some store table row
* ruling citations are 'information only' and are not scored
This proves the pointer is real. It does NOT prove the legal claim is right.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from src.tools.lookup import lookup_code

DB = Path("data/processed/legal_store.sqlite")
TABLES = ("rd_rules", "acd_rules", "sales_tax_rules", "income_tax_rules", "fed_rules", "legal_notes", "tariff_lines")


def _store_has(conn: sqlite3.Connection, source_file, page) -> bool:
    if not source_file or page in (None, ""):
        return False
    for t in TABLES:
        if conn.execute(f"SELECT 1 FROM {t} WHERE source_file=? AND page=? LIMIT 1", (source_file, int(page))).fetchone():
            return True
    return False


def score_citations(citations: list[dict], as_of_date: str, db: Path = DB) -> dict:
    """-> {checked, correct, wrong: [citation + reason]}"""
    conn = sqlite3.connect(db)
    checked = correct = 0
    wrong = []
    try:
        for c in citations:
            kind = c.get("kind")
            if kind == "ruling":
                continue
            checked += 1
            if kind == "tariff":
                lk = lookup_code(c.get("code"), as_of_date)
                found = lk.get("status") == "found"
                pages = ({lk.get("page")} | {f.get("page") for f in lk.get("fragments", [])}) if found else set()
                ok = found and lk.get("source_file") == c.get("source_file") and c.get("page") in pages
                reason = "" if ok else f"lookup_code says {lk.get('status')} {lk.get('source_file')} p{lk.get('page')}"
            else:
                ok = _store_has(conn, c.get("source_file"), c.get("page"))
                reason = "" if ok else "no store row with this file and page"
            if ok:
                correct += 1
            else:
                wrong.append({**c, "reason": reason})
    finally:
        conn.close()
    return dict(checked=checked, correct=correct, wrong=wrong)
