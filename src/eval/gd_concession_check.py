"""Check the stored concession rates (China FTA SRO 1640(I)/2019, Fifth Schedule) against the customs duty Customs actually charged on the
importer's Goods Declaration lines (data/raw/importer_data, PRIVATE). Only aggregates are printed or written: no per-line file, no identity column.

For every home-consumption line whose SRO columns name SRO 1640(I)/2019 (or the Fifth Schedule) we compute, with the exact tools, the customs
duty the concession would give on the line's assessable value (IV) and compare it with the CD column (tolerance 2 PKR).
 * China FTA: the option of the code on the GD date (origin China, Form E assumed because the SRO is on the line).
 * Fifth Schedule: the line matches if ANY Fifth Schedule option of that code (any serial) gives the charged CD; lines whose goods are named only
   in words ("Respective Headings") have no code option and are counted separately.
Usage: python -m src.eval.gd_concession_check  -> docs/gd_concession_check.md
"""
from __future__ import annotations

import collections
from decimal import Decimal
from pathlib import Path

from src.tools._util import get_conn, rows
from src.tools.concessions import fifth_block, fta_block

from .gd_data import load, num

TOL = Decimal(2)
OUT = Path("docs/gd_concession_check.md")


def trow_of(conn, code, d):
    fy = "FY2026-27" if d >= "2026-07-01" else "FY2025-26"
    r = rows(conn, "SELECT * FROM tariff_lines WHERE fy=? AND code_norm=? ORDER BY page", [fy, code])
    return r[0] if r else None


def main():
    conn = get_conn()
    data = [r for r in load() if r.get("TYPE") == "HC" and r["code8"] and num(r["IV"]) > 0]
    fta = collections.Counter()
    fifth = collections.Counter()
    fta_rate_miss = collections.Counter()
    for r in data:
        s = " ".join(str(r.get(k) or "") for k in ("SRO1", "SRO2", "SRO3", "SRO4")).lower()
        is_fta, is_fifth = "1640" in s, "5th" in s
        if not (is_fta or is_fifth):
            continue
        tr = trow_of(conn, r["code8"], r["date"])
        if tr is None:
            continue
        iv, cd = Decimal(str(num(r["IV"]))), Decimal(str(num(r["CD"])))
        if is_fta:
            blk = fta_block(conn, r["code8"], r["date"], tr, {"origin_country": "CN", "has_certificate_of_origin": True})
            opts = [o for o in blk["options"] if o["_effective"] is not None]
            if not opts:
                fta["no_row_for_code_on_date"] += 1
                continue
            eff = opts[0]["_effective"]
            ours = iv * eff / 100
            ok = abs(ours - cd) <= TOL
            fta["match" if ok else "mismatch"] += 1
            tag = opts[0].get("category") or ""
            fta[f"{'match' if ok else 'mismatch'}:{tag}:{opts[0]['status']}"] += 1
            if not ok:
                fta_rate_miss[("our_rate_ge_charged" if (ours > cd) else "our_rate_lt_charged")] += 1
        if is_fifth:
            fb = fifth_block(conn, r["code8"], r["date"], tr)
            opts = [o for o in fb["options"] if o["_effective"] is not None]
            if not opts:
                fifth["no_code_option(respective headings or code absent)"] += 1
                continue
            hit = any(abs(iv * o["_effective"] / 100 - cd) <= TOL for o in opts)
            fifth["some_option_matches" if hit else "no_option_matches"] += 1
            if not hit:
                fifth["no_option_matches_but_charged_cd_is_normal_tariff_cd"] += int(abs(iv * Decimal(str(tr["cd_rate"] or 0)) / 100 - cd) <= TOL) if tr["cd_kind"] == "plain" else 0
    nf = sum(v for k, v in fta.items() if ":" not in k)
    lines = ["# Concession rates against the importer's Goods Declaration lines (aggregates only)", "",
             "Source: the private GD extract (Chapter 85, February 2026, FY2025-26 rules). No line-level data is stored here. Script: `python -m src.eval.gd_concession_check`.", "",
             "## China FTA (SRO 1640(I)/2019 named on the line)",
             f"Lines checked: {nf}. Expected CD = IV x min(normal CD, SRO rate of the 1-Jan-2026 column) (tolerance 2 PKR)."]
    for k in ("match", "mismatch", "no_row_for_code_on_date"):
        lines.append(f"* {k}: {fta.get(k, 0)}" + (f" ({100 * fta.get(k, 0) / nf:.1f}%)" if nf else ""))
    lines.append("* by category and row status: " + ", ".join(f"{k}={v}" for k, v in sorted(fta.items()) if ":" in k))
    lines.append("* mismatches by direction: " + ", ".join(f"{k}={v}" for k, v in fta_rate_miss.items()))
    nfi = sum(fifth.values()) - fifth.get("no_option_matches_but_charged_cd_is_normal_tariff_cd", 0)
    lines += ["", "## Fifth Schedule (named on the line)", f"Lines checked: {nfi}."]
    for k, v in fifth.items():
        lines.append(f"* {k}: {v}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
