"""lookup_code: the tariff line for a PCT code on a date (exact, no LLM)."""
from __future__ import annotations

import datetime as _dt
import re

from ._util import D, coverage, fmt, get_conn, norm_code, rows, to_iso


def _chain(description: str) -> list[str]:
    """Best-effort split of the flattened tariff description into its levels (dash markers). Heuristic, display only."""
    parts = [p.strip(" -") for p in re.split(r"\s+(?=-\s)", description or "") if p.strip(" -")]
    return parts or [description]


def cd_view(line: dict) -> dict:
    k = line["cd_kind"]
    out = {"kind": k, "raw": line["cd_raw"]}
    if k == "plain":
        out["rate_pct"] = fmt(D(line["cd_rate"]))
    elif k == "specific":
        out["amount_pkr"] = fmt(D(line["cd_specific_amount"]))
        out["unit"] = line["cd_specific_unit"]
    return out


def line_view(conn, line: dict, d: str) -> dict:
    flags = []
    if line["status"] == "needs_review":
        flags.append("tariff_row_needs_review")
    if line["rotated"]:
        flags.append("rotated_cell_amount_reassembled_from_wrapped_text")
    if line["cd_kind"] == "compound":
        flags.append("compound_or_unparsed_duty_cell_cannot_be_computed")
    heading = None
    if line["heading"]:
        h = rows(conn, "SELECT heading, text, page, source_file FROM tariff_headings WHERE fy=? AND heading=?", [line["fy"], line["heading"]])
        if h:
            heading = {"code": h[0]["heading"], "text": h[0]["text"], "page": h[0]["page"], "source_file": h[0]["source_file"]}
    return {
        "code": line["code"],
        "code_norm": line["code_norm"],
        "level": line["level"],
        "fy": line["fy"],
        "valid_from": line["valid_from"],
        "valid_to": line["valid_to"],
        "chapter": line["code_norm"][:2],
        "heading": heading,
        "description": line["description"],
        "description_levels": _chain(line["description"]),
        "cd": cd_view(line),
        "row_status": line["status"],
        "note": line["note"],
        "flags": flags,
        "source_file": line["source_file"],
        "page": line["page"],
    }


def lookup_code(code, as_of_date, db_path=None) -> dict:
    """Tariff line for `code` on `as_of_date`.

    Returns status 'found' (with the line), 'not_found' (with nearest codes), 'not_a_full_code' (4 or 6 digits given,
    with the 8-digit children) or 'invalid_input'. The CD column is the only duty printed in the tariff; RD, ACD, sales
    tax and income tax come from get_applicable_sros / compute_duty.
    """
    try:
        d = to_iso(as_of_date)
        c = norm_code(code)
    except (ValueError, TypeError) as e:
        return {"status": "invalid_input", "reason": str(e)}
    conn = get_conn(db_path)
    lo, hi = coverage(conn)
    base = {"query_code": str(code), "as_of_date": d}
    if not (lo <= d <= hi):
        return {**base, "status": "date_outside_store", "reason": f"the store covers {lo} to {hi} only (FY2025-26 and FY2026-27)"}
    if len(c) in (3, 5, 7) or len(c) > 8 or len(c) < 4:
        return {**base, "status": "invalid_input", "reason": f"a PCT code has 4, 6 or 8 digits, got {len(c)}"}
    fy = rows(conn, "SELECT DISTINCT fy FROM tariff_lines WHERE valid_from <= ? AND valid_to >= ?", [d, d])[0]["fy"]
    if len(c) == 8:
        lines = rows(conn, "SELECT * FROM tariff_lines WHERE fy=? AND code_norm=? ORDER BY page", [fy, c])
    else:
        lines = []
    if len(c) == 4 and not lines:
        lines = rows(conn, "SELECT * FROM tariff_lines WHERE fy=? AND code_norm=? AND level=4 ORDER BY page", [fy, c])
    if lines:
        res = {**base, "status": "found", "fy": fy, **line_view(conn, lines[0], d)}
        if len(lines) > 1:
            res["fragments"] = [{"page": x["page"], "description": x["description"], "cd": cd_view(x)} for x in lines]
            res["flags"].append("entry_spans_several_pages")
        if res["level"] == 4:
            res["flags"].append("chapter_99_entry_conditional_import_regime_not_computed_by_compute_duty")
        return res
    # not an exact line: children or nearest
    if len(c) in (4, 6):
        kids = rows(conn, "SELECT code, description, cd_kind, cd_rate, cd_specific_amount, cd_specific_unit, cd_raw, page FROM tariff_lines WHERE fy=? AND level=8 AND code_norm LIKE ? ORDER BY code_norm", [fy, c + "%"])
        if kids:
            return {
                **base, "status": "not_a_full_code", "fy": fy,
                "reason": f"{c} is a {len(c)}-digit heading/subheading; choose one of its {len(kids)} eight-digit lines",
                "children": [{"code": k["code"], "description": k["description"][:140], "page": k["page"]} for k in kids[:60]],
                "children_total": len(kids),
            }
    n = int(c.ljust(8, "0"))
    near = rows(
        conn,
        "SELECT code, description, cd_kind, cd_rate, cd_specific_amount, cd_specific_unit, page FROM tariff_lines "
        "WHERE fy=? AND level=8 ORDER BY abs(CAST(code_norm AS INTEGER) - ?), code_norm LIMIT 5",
        [fy, n],
    )
    other = rows(conn, "SELECT fy, code FROM tariff_lines WHERE code_norm=? AND fy != ?", [c, fy])
    res = {
        **base, "status": "not_found", "fy": fy,
        "reason": f"{c[:4]}.{c[4:]} is not a line of the {fy} tariff",
        "nearest_codes": [
            {"code": x["code"], "description": x["description"][:140], "cd": x["cd_rate"] if x["cd_kind"] == "plain" else x["cd_kind"], "page": x["page"]}
            for x in near
        ],
    }
    if other:
        res["exists_in_other_fy"] = [o["fy"] for o in other]
    return res
