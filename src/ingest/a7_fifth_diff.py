"""A7: difference between the Fifth Schedule FY2025-26 file and the FY2026-27 file (rows, rates, conditions).

Key of a row: (part, table, serial, code) for rows with a code, (part, table, serial, description) for rows named by words.
Output: data/processed/a7_fifth_diff_2025_26_vs_2026_27.csv (every difference; nothing is judged here) + a summary json.
Usage: python -m src.ingest.a7_fifth_diff
"""
import csv
import json
import re
from collections import Counter
from pathlib import Path

P = Path("data/processed")


def load(name):
    out = {}
    for r in csv.DictReader(open(P / name, encoding="utf-8")):
        key = (r["part"], r["table"], r["s_no"], r["code_norm"] or re.sub(r"\W+", " ", r["description"].lower())[:60])
        out.setdefault(key, []).append(r)
    return out


def norm_rate(r):
    return re.sub(r"\s+", "", r["rate_raw"])


def main():
    a, b = load("a7_fifth_rules_2025_26.csv"), load("a7_fifth_rules.csv")
    diffs = []
    for k in sorted(set(a) | set(b)):
        ra, rb = a.get(k), b.get(k)
        if ra and not rb:
            diffs.append(dict(change="only_in_2025_26", part=k[0], table=k[1], s_no=k[2], key=k[3], rate_2025_26=norm_rate(ra[0]), rate_2026_27="", page_2025_26=ra[0]["page"], page_2026_27="", description=ra[0]["description"][:100]))
        elif rb and not ra:
            diffs.append(dict(change="only_in_2026_27", part=k[0], table=k[1], s_no=k[2], key=k[3], rate_2025_26="", rate_2026_27=norm_rate(rb[0]), page_2025_26="", page_2026_27=rb[0]["page"], description=rb[0]["description"][:100]))
        else:
            r1, r2 = {norm_rate(x) for x in ra}, {norm_rate(x) for x in rb}
            if r1 != r2:
                diffs.append(dict(change="rate_changed", part=k[0], table=k[1], s_no=k[2], key=k[3], rate_2025_26="|".join(sorted(r1)), rate_2026_27="|".join(sorted(r2)), page_2025_26=ra[0]["page"], page_2026_27=rb[0]["page"], description=ra[0]["description"][:100]))
            elif re.sub(r"\W+", "", ra[0]["conditions"].lower()) != re.sub(r"\W+", "", rb[0]["conditions"].lower()):
                diffs.append(dict(change="conditions_text_differs", part=k[0], table=k[1], s_no=k[2], key=k[3], rate_2025_26="|".join(sorted(r1)), rate_2026_27="|".join(sorted(r2)), page_2025_26=ra[0]["page"], page_2026_27=rb[0]["page"], description=ra[0]["description"][:100]))
    with open(P / "a7_fifth_diff_2025_26_vs_2026_27.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(diffs[0]))
        w.writeheader()
        w.writerows(diffs)
    summ = {"rows_2025_26": sum(map(len, a.values())), "rows_2026_27": sum(map(len, b.values())), "keys_2025_26": len(a), "keys_2026_27": len(b),
            "differences": dict(Counter(d["change"] for d in diffs)), "by_part": dict(Counter((d["part"], d["change"]) for d in diffs).most_common()).__repr__()}
    json.dump(summ, open(P / "a7_fifth_diff_summary.json", "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
