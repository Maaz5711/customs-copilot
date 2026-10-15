"""A6: spot-check sheet for the FED rules (well over 10% of rows: every vehicle, changed, specific/compound and exemption-sample row).
Usage: python -m src.ingest.a6_fed_spotcheck  -> data/processed/spotcheck_a6_fed.csv"""
import csv
from pathlib import Path

P = Path("data/processed")
KEEP_SNO = {"7", "7a", "8", "8a", "8b", "13", "32", "35", "41", "55", "55A", "55C", "61", "63", "64", "65", "1"}
THIRD = {"11", "17", "23", "28", "24"}


def main():
    rows = list(csv.DictReader(open(P / "a6_fed_rules.csv", encoding="utf-8")))
    seen, out = set(), []
    for r in rows:
        ok = (r["table_no"] in ("I", "IA") and r["s_no"] in KEEP_SNO) or (r["table_no"] == "Third-I" and r["s_no"] in THIRD)
        if not ok:
            continue
        key = (r["fy"], r["table_no"], r["s_no"], r["sub"])
        if key in seen:
            continue
        seen.add(key)
        img = f"data/processed/page_images/{'fed26' if r['fy'] == 'FY2026-27' else 'fed25'}/p{int(r['page']):03d}.png"
        parsed = (f"S.No {r['s_no']}{r['sub']} | codes {r['heading_raw']} | {r['rate_kind']} {r['rate_pct']}% {r['rate_basis']} "
                  f"| Rs {r['rate_specific_amount']} per {r['rate_specific_unit']} | cc {r['cc_ge']}/{r['cc_gt']}/{r['cc_le']} usd {r['usd_gt']}/{r['usd_le']}")
        out.append(dict(row_id=r["row_id"], fy=r["fy"], page=r["page"], table_no=r["table_no"], s_no=r["s_no"], sub=r["sub"],
                        description=r["description"], sub_desc=r["sub_desc"], parsed=parsed, rate_raw=r["rate_raw"],
                        page_image=img, **{"correct? (Y/N)": "", "true_value_if_N": ""}))
    with open(P / "spotcheck_a6_fed.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader(); w.writerows(out)
    print(len(out), "of", len(rows), "rows")


if __name__ == "__main__":
    main()
