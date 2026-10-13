"""get_applicable_sros: every rule (RD, ACD, sales tax, income tax) that applies to a code on a date, and what was excluded."""
from __future__ import annotations

from ._util import (
    collect, coverage, excluded_view, get_conn, group_rows, norm_code, rows, rule_view, sros_of_kind, to_iso,
)
from .lookup import lookup_code
from .rules import acd_kind, income_tax_class, make_acd_prefilter, make_st_prefilter, st_benign_condition

MAX_EXCLUDED = 60


def _kind_block(table, kind, app, exc, extra_flags=None):
    views = []
    for r in app:
        v = rule_view(table, r, kind)
        if extra_flags:
            v["flags"].extend(extra_flags(r))
        views.append(v)
    exc = sorted(exc, key=lambda x: x[1].startswith("not_in_force_on_date"))  # reasons about the code first, date-only last
    ex = [excluded_view(table, r, why, kind) for r, why in exc]
    return {"applicable": views, "excluded": ex[:MAX_EXCLUDED], "excluded_total": len(ex)}


def get_applicable_sros(code, as_of_date, db_path=None) -> dict:
    """Rules that apply to `code` on `as_of_date`, by tax, with SRO number, clause, rate, conditions, source, page, status.

    'applicable' = valid on the date, matches the code (exact, 6-digit, heading, chapter or general rule), not removed by an
    'except' clause, and the most specific row of its rule group. A row with `condition` or a flag
    'condition_must_be_checked' depends on facts only the importer knows; compute_duty asks for them.
    'excluded' lists every row that matched the code by prefix but does not apply, with the reason (date, except clause,
    shadowed by a more specific row, tariff-CD slab mismatch, local-supply rule, ...).
    """
    try:
        d = to_iso(as_of_date)
        c = norm_code(code)
    except (ValueError, TypeError) as e:
        return {"status": "invalid_input", "reason": str(e)}
    tl = lookup_code(c, d, db_path)
    if tl["status"] != "found" or tl["level"] != 8:
        return {"status": "not_found" if tl["status"] != "invalid_input" else "invalid_input", "lookup": tl}
    conn = get_conn(db_path)
    trow = rows(conn, "SELECT * FROM tariff_lines WHERE fy=? AND code_norm=? ORDER BY page", [tl["fy"], c])[0]
    out = {"status": "ok", "code": tl["code"], "as_of_date": d, "fy": tl["fy"], "tariff": {"cd": tl["cd"], "source_file": tl["source_file"], "page": tl["page"], "row_status": tl["row_status"], "flags": tl["flags"]}}

    # RD
    rd_app, rd_exc = collect(conn, "rd_rules", c, d)
    out["rd"] = _kind_block("rd_rules", "RD", rd_app, rd_exc, lambda r: ["used_vehicle_rd_in_addition_condition_must_be_checked"] if r["rule_group"].startswith(("1898", "1065")) else [])
    out["rd"]["notifications"] = dict(zip(("in_force_on_date", "not_in_force_on_date"), sros_of_kind(conn, "RD", d)))

    # ACD
    need: list[str] = []
    acd_app, acd_exc = collect(conn, "acd_rules", c, d, prefilter=make_acd_prefilter(trow, None, need))
    out["acd"] = _kind_block("acd_rules", "ACD", acd_app, acd_exc, lambda r: ["condition_must_be_checked"] if acd_kind(r)[0] not in (None, "slab") else [])
    out["acd"]["tariff_cd_slab"] = tl["cd"]
    out["acd"]["notifications"] = dict(zip(("in_force_on_date", "not_in_force_on_date"), sros_of_kind(conn, "ACD", d)))

    # sales tax (+ value addition tax general rule)
    st_app, st_exc = collect(conn, "sales_tax_rules", c, d, prefilter=make_st_prefilter(None))
    out["sales_tax"] = _kind_block("sales_tax_rules", "ST", st_app, st_exc,
                                   lambda r: ["condition_must_be_checked"] if (r["rule_group"] in ("ST-6TH-T1", "ST-6TH-T3", "ST-8TH-T1", "ST-5TH", "ST-12TH-EXCL") and not st_benign_condition(r)) else [])
    out["sales_tax"]["general_rules_by_group"] = [rule_view("sales_tax_rules", r, "ST") for r in group_rows(conn, "sales_tax_rules", "ST-12TH", d)]
    out["sales_tax"]["notifications"] = dict(zip(("in_force_on_date", "not_in_force_on_date"), sros_of_kind(conn, "ST", d)))

    # income tax
    it_app, it_exc = collect(conn, "income_tax_rules", c, d)
    cls, cls_row, problem = income_tax_class(it_app)
    out["income_tax"] = _kind_block("income_tax_rules", "IT", it_app, it_exc)
    out["income_tax"]["twelfth_schedule_class"] = {"part": cls, "entry": rule_view("income_tax_rules", cls_row, "IT") if cls_row else None,
                                                   "note": problem or ("Part III is the residual class: no Part I or II entry matched the code" if cls == 3 else None)}
    out["income_tax"]["notifications"] = dict(zip(("in_force_on_date", "not_in_force_on_date"), sros_of_kind(conn, "IT", d)))

    out["concessions"] = {
        "applicable": [],
        "note": "Customs concessions are not in the dated store. The only concession rows read (A3) are the sugar SROs 1215/1834 and Early Harvest SRO 1386(I)/2025; they name no PCT code and are out of v1 duty scope.",
    }
    flags = []
    if c.startswith("1701"):
        flags.append("sugar: SRO 1215/1217/1832/527/663 and the income-tax twins name no PCT code; they are not matched by code (OQ-A3-3)")
    if c.startswith(("8702", "8703", "8704", "8711")):
        flags.append("vehicle: used-vehicle RD (SRO 1898/1065), CKD/CBU and engine size matter; FED not in the store (OPEN-1)")
    out["flags"] = flags
    return out
