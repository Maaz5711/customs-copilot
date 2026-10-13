"""Exact (no LLM) lookup of which rule applied on a given date.

get_rule_on_date(conn, table, key, on_date) -> list[dict]

Resolution order for code-keyed rule tables (rd_rules, acd_rules, sales_tax_rules,
income_tax_rules). Documented in docs/store_schema.md section "Resolution order":

 1. Keep rows valid on the date (valid_from <= date <= valid_to, both inclusive).
 2. Keep rows whose code_norm is a prefix of the 8-digit target code
    (code8 = exact, code6, heading4, chapter2, 'all' = empty prefix).
 3. Drop rows with an 'except' list that covers the target (any except token is a
    prefix of the target). Such a row does not apply to that code at all.
 4. Within each rule_group (e.g. one SRO), the longest matching prefix wins
    (most specific wins). Rows of the same specificity are ALL returned (for
    example several C&F-value tiers for 8517.1390); the caller must pick by
    condition. Different rule_groups are independent (cumulative) and are all returned.
 5. If the winning rows carry unparsed_except_text=1 or status='needs_review',
    that is surfaced in the _flags list. Nothing is silently fixed.
"""
from __future__ import annotations

import datetime as _dt
import json
import re

HIER_TABLES = ("rd_rules", "acd_rules", "sales_tax_rules", "income_tax_rules")
KEY_COLUMNS = {
    "tariff_lines": "code_norm",
    "tariff_headings": "heading",
    "sros": "sro_number",
    "legal_notes": "scope",
}
ALL_TABLES = tuple(KEY_COLUMNS) + HIER_TABLES

_LEVEL_LEN = {"code8": 8, "code6": 6, "heading4": 4, "chapter2": 2, "all": 0}


def norm_code(code: str) -> str:
    """'8703.2115' / '87.03' / '87032115' -> digits only."""
    digits = re.sub(r"[^0-9]", "", str(code))
    if not digits:
        raise ValueError(f"not a code: {code!r}")
    return digits


def canon_sro(s: str) -> str:
    """'S.R.O. 1064 (I)/2026' -> '1064(I)/2026'."""
    m = re.search(r"(\d+)\s*\(\s*[Il1]\s*\)\s*/\s*(\d{4})", str(s))
    if not m:
        raise ValueError(f"not an SRO number: {s!r}")
    return f"{m.group(1)}(I)/{m.group(2)}"


def _to_iso(d) -> str:
    if isinstance(d, _dt.datetime):
        return d.date().isoformat()
    if isinstance(d, _dt.date):
        return d.isoformat()
    if isinstance(d, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        _dt.date.fromisoformat(d)  # raises on impossible dates
        return d
    raise ValueError(f"date must be a date or 'YYYY-MM-DD', got {d!r}")


def _rows(conn, sql, params):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_rule_on_date(conn, table: str, key: str, on_date, statuses=None) -> list[dict]:
    """Rows of `table` for `key` that were valid on `on_date`.

    key: tariff_lines/tariff_headings -> code or heading; sros -> SRO number;
         legal_notes -> scope; rule tables -> a full 8-digit code.
    statuses: optional iterable, e.g. ('accepted','verified') to hide needs_review rows.
    Returns plain dicts. Rule tables add '_resolution' and '_flags'.
    """
    if table not in ALL_TABLES:
        raise ValueError(f"unknown table {table!r}; allowed: {ALL_TABLES}")
    d = _to_iso(on_date)
    status_sql, status_params = "", []
    if statuses is not None and table != "tariff_headings":
        statuses = list(statuses)
        status_sql = f" AND status IN ({','.join('?' * len(statuses))})"
        status_params = statuses

    if table in KEY_COLUMNS:
        col = KEY_COLUMNS[table]
        if table == "tariff_lines":
            k = norm_code(key)
        elif table == "sros":
            k = canon_sro(key)
        else:
            k = str(key)
        return _rows(
            conn,
            f"SELECT * FROM {table} WHERE {col} = ? AND valid_from <= ? AND valid_to >= ?"
            f"{status_sql} ORDER BY valid_from, id",
            [k, d, d] + status_params,
        )

    target = norm_code(key)
    if len(target) != 8:
        raise ValueError(f"rule tables are looked up by an 8-digit code, got {key!r}")
    cands = _rows(
        conn,
        f"SELECT * FROM {table} WHERE valid_from <= ? AND valid_to >= ? "
        f"AND code_norm IS NOT NULL AND ? LIKE code_norm || '%'{status_sql} ORDER BY id",
        [d, d, target] + status_params,
    )
    return resolve_candidates(cands, target)


def resolve_candidates(cands: list[dict], target: str) -> list[dict]:
    """Apply steps 3-5 of the resolution order to date-and-prefix-matched rows."""
    kept = []
    for r in cands:
        excepts = json.loads(r["except_codes"] or "[]")
        if any(target.startswith(t) for t in excepts):
            continue  # an except clause carves this code out of the row
        kept.append(r)

    best: dict[str, int] = {}
    for r in kept:
        n = _LEVEL_LEN[r["match_level"]]
        g = r["rule_group"]
        if n > best.get(g, -1):
            best[g] = n

    out = []
    for r in kept:
        if _LEVEL_LEN[r["match_level"]] != best[r["rule_group"]]:
            continue
        flags = []
        if r["match_level"] != "code8":
            flags.append("matched_by_prefix_not_exact_code")
        if r["unparsed_except_text"]:
            flags.append("description_has_unparsed_exception_text")
        if r["status"] == "needs_review":
            flags.append("row_needs_review")
        if r.get("rate_kind") == "conditional":
            flags.append("rate_is_conditional_choose_manually")
        r = dict(r)
        r["_resolution"] = "exact" if r["match_level"] == "code8" else "prefix:" + r["match_level"]
        r["_flags"] = flags
        out.append(r)
    # several rows of the same specificity in one group: caller must choose by condition
    counts: dict[str, int] = {}
    for r in out:
        counts[r["rule_group"]] = counts.get(r["rule_group"], 0) + 1
    for r in out:
        if counts[r["rule_group"]] > 1:
            r["_flags"].append("multiple_rows_same_specificity_choose_by_condition")
    return out
