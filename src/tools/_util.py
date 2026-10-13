"""Shared helpers for the exact tools: Decimal handling, dates, store access, rule collection.

No LLM and no rate is written here. Rates always come from the dated store (data/processed/legal_store.sqlite).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import threading
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, getcontext
from pathlib import Path

from src.store.db import DEFAULT_DB_PATH
from src.store.resolve import norm_code, resolve_candidates

getcontext().prec = 50

_LOCK = threading.Lock()
_CONN: dict[str, object] = {}


# --------------------------------------------------------------------------- store access
def get_conn(db_path=None):
    """One shared read-only style connection per database path. Builds the store if it is missing."""
    path = Path(db_path or os.environ.get("CUSTOMS_DB") or DEFAULT_DB_PATH)
    key = str(path)
    with _LOCK:
        if key in _CONN:
            return _CONN[key]
        if not path.exists():
            from src.store.build import build  # rebuild from data/processed (never touches data/raw)

            build(path)
        # tools run in MCP worker threads; the connection is only used for reads
        import sqlite3

        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _CONN[key] = conn
        return conn


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, list(params)).fetchall()]


# --------------------------------------------------------------------------- numbers
def D(x) -> Decimal:
    """Exact Decimal from int / str / Decimal / float (floats go through repr, so 0.1 -> Decimal('0.1'))."""
    if isinstance(x, Decimal):
        return x
    if isinstance(x, bool):
        raise InvalidOperation("bool is not a number")
    if isinstance(x, float):
        return Decimal(repr(x))
    return Decimal(str(x).replace(",", "").strip())


def fmt(d: Decimal, places: int | None = None) -> str:
    """Plain (non-scientific) string. places=None strips trailing zeros (rates); places=2 keeps paisa."""
    if places is not None:
        return format(d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP), "f")
    n = d.normalize()
    out = format(n, "f")
    return out


def money(d: Decimal, rounding: str = "paisa") -> Decimal:
    """Rounding convention (documented in docs/tools.md): ROUND_HALF_UP to 0.01, or to 1 for rounding='rupee'.

    No source document states a rounding rule (docs/duty_formula.md OPEN-5): this is a flagged assumption.
    """
    q = Decimal("1") if rounding == "rupee" else Decimal("0.01")
    return d.quantize(q, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- dates
def to_iso(d) -> str:
    if d is None:
        raise ValueError("as_of_date is required (YYYY-MM-DD)")
    if isinstance(d, _dt.datetime):
        return d.date().isoformat()
    if isinstance(d, _dt.date):
        return d.isoformat()
    if isinstance(d, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.strip()):
        _dt.date.fromisoformat(d.strip())
        return d.strip()
    raise ValueError(f"as_of_date must be a date or 'YYYY-MM-DD', got {d!r}")


def coverage(conn) -> tuple[str, str]:
    r = conn.execute("SELECT min(valid_from), max(valid_to) FROM tariff_lines").fetchone()
    return r[0], r[1]


# --------------------------------------------------------------------------- rule collection
def collect(conn, table: str, code8: str, d: str, prefilter=None, max_not_in_force: int = 40):
    """Rows of a code-keyed rule table that apply to `code8` on date `d`, plus every row that does NOT, with the reason.

    applicable : same result as src.store.resolve.get_rule_on_date (date, prefix, except, longest prefix per rule_group),
                 after an optional caller `prefilter(row) -> reason | None` has removed rows whose stated condition is not met.
    excluded   : list of (row, reason) where reason is one of
                 'not_in_force_on_date', 'excluded_by_except_clause', 'shadowed_by_more_specific_row_in_same_rule_group',
                 or whatever the prefilter returned.
    """
    allrows = rows(
        conn,
        f"SELECT * FROM {table} WHERE code_norm IS NOT NULL AND ? LIKE code_norm || '%' ORDER BY id",
        [code8],
    )
    valid, excluded = [], []
    for r in allrows:
        if r["valid_from"] <= d <= r["valid_to"]:
            valid.append(r)
        else:
            excluded.append((r, f"not_in_force_on_date (valid {r['valid_from']} to {r['valid_to']})"))
    excluded = excluded[:max_not_in_force]
    pre = []
    for r in valid:
        reason = prefilter(r) if prefilter else None
        if reason:
            excluded.append((r, reason))
        else:
            pre.append(r)
    applicable = resolve_candidates(pre, code8)
    keep = {r["id"] for r in applicable}
    for r in pre:
        if r["id"] in keep:
            continue
        toks = [t for t in json.loads(r["except_codes"] or "[]") if code8.startswith(t)]
        if toks:
            excluded.append((r, f"excluded_by_except_clause {toks}"))
        else:
            excluded.append((r, "shadowed_by_more_specific_row_in_same_rule_group"))
    return applicable, excluded


def group_rows(conn, table: str, group: str, d: str):
    """All rows of one rule_group valid on date d (for general rules that name no code, e.g. s.3 standard rate)."""
    return rows(
        conn,
        f"SELECT * FROM {table} WHERE rule_group = ? AND valid_from <= ? AND valid_to >= ? ORDER BY id",
        [group, d, d],
    )


# --------------------------------------------------------------------------- views
def _num(x):
    return fmt(D(x)) if x is not None else None


def rate_view(r: dict) -> dict:
    k = r["rate_kind"]
    out = {"kind": k, "raw": r.get("rate_raw")}
    if k == "percent":
        out["pct"] = _num(r["rate_pct"])
    elif k == "specific":
        out["amount_pkr"] = _num(r["rate_specific_amount"])
        out["unit"] = r["rate_specific_unit"]
    return out


def rule_view(table: str, r: dict, kind: str) -> dict:
    ident = r.get("sro_number") or r.get("instrument")
    v = {
        "rule_id": f"{table}:{r['id']}",
        "kind": kind,
        "instrument": ident,
        "clause": r.get("clause") or r.get("s_no"),
        "rate": rate_view(r),
        "condition": r.get("condition_text"),
        "description": r.get("description"),
        "rule_group": r["rule_group"],
        "matched_on": r.get("_resolution") or ("general" if r["match_level"] == "all" else r["match_level"]),
        "code_norm": r.get("code_norm"),
        "valid_from": r["valid_from"],
        "valid_to": r["valid_to"],
        "source_file": r["source_file"],
        "page": r["page"],
        "status": r["status"],
        "flags": list(r.get("_flags", [])),
    }
    if r.get("importer_status") and r["importer_status"] != "any":
        v["importer_status"] = r["importer_status"]
    if r.get("importer_category"):
        v["importer_category"] = r["importer_category"]
    if r.get("charged_on"):
        v["charged_on"] = r["charged_on"]
    if r.get("issues"):
        v["issues"] = r["issues"]
    return v


def excluded_view(table: str, r: dict, reason: str, kind: str) -> dict:
    v = rule_view(table, r, kind)
    v["excluded_because"] = reason
    return v


def sro_info(conn, number: str | None):
    if not number:
        return None
    r = conn.execute("SELECT * FROM sros WHERE sro_number = ?", [number]).fetchone()
    if not r:
        return None
    r = dict(r)
    return {
        "sro_number": r["sro_number"],
        "kind": r["instrument_kind"],
        "valid_from": r["valid_from"],
        "valid_to": r["valid_to"],
        "sro_status": r["sro_status"],
        "superseded_by": r["superseded_by"],
        "supersedes": r["supersedes"],
        "validity_basis": r["validity_basis"],
        "status": r["status"],
        "note": r["note"],
        "source_file": r["source_file"],
        "page": r["page"],
    }


def sros_of_kind(conn, kind: str, d: str):
    """Notifications of one kind: those in force on date d, and those that are not (with the reason)."""
    out_in, out_not = [], []
    for r in rows(conn, "SELECT * FROM sros WHERE instrument_kind = ? ORDER BY sro_date", [kind]):
        info = sro_info(conn, r["sro_number"])
        (out_in if r["valid_from"] <= d <= r["valid_to"] else out_not).append(info)
    return out_in, out_not


def code8_of(code) -> str:
    c = norm_code(code)
    return c
