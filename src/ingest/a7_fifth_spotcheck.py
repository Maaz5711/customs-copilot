"""A7: spot-check sheet for the Fifth Schedule rules (well over 10% of rows) + page images (gitignored).

Selection: every row with an issue/needs_review, every row of the small parts (IV, V, VI), every 3rd row of Part I, every
8th row of Part II (pharma lists), every 4th row of Part III and every 8th row of Part VIII. The owner fills the last two columns.
Usage: python -m src.ingest.a7_fifth_spotcheck  -> data/processed/spotcheck_a7_fifth.csv
"""
import csv
from pathlib import Path

import pymupdf

P = Path("data/processed")
RAW = Path("data/raw/2026825118858478FifthSchedule2026-27.pdf")
EVERY = {"I": 3, "II": 8, "III": 4, "VIII": 8}


def main():
    rules = list(csv.DictReader(open(P / "a7_fifth_rules.csv", encoding="utf-8")))
    counters, out = {}, []
    for r in rules:
        part = r["part"]
        counters[part] = counters.get(part, 0) + 1
        pick = r["status"] == "needs_review" or part not in EVERY or counters[part] % EVERY[part] == 0
        if not pick:
            continue
        img = f"data/processed/page_images/fifth/p{int(r['page']):02d}.png"
        parsed = (f"Part {r['part']} Table {r['table']} S.No {r['s_no']} {r['sub_ref']} | code {r['code_raw'] or '(none: named by description)'}"
                  f" | duty {r['rate_raw']} | conditions: {r['conditions'][:140]}")
        out.append(dict(rule_id=r["rule_id"], page=r["page"], part=r["part"], table=r["table"], s_no=r["s_no"],
                        description=r["description"][:160], parsed=parsed, issues=r["issues"], page_image=img,
                        **{"correct? (Y/N)": "", "true_value_if_N": ""}))
    with open(P / "spotcheck_a7_fifth.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    pages = sorted({int(o["page"]) for o in out})
    (P / "page_images" / "fifth").mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(RAW)
    for pn in pages:
        doc[pn - 1].get_pixmap(dpi=100).save(P / "page_images" / "fifth" / f"p{pn:02d}.png")
    print(len(out), "of", len(rules), "rules in the sheet;", len(pages), "page images")


if __name__ == "__main__":
    main()
