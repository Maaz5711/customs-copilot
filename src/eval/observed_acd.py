"""Codes where real assessed duties show an additional customs duty (ACD) that no notification in our documents explains.

    python -m src.eval.observed_acd     ->  data/ground_truth/observed_acd_exceptions.csv  (aggregate only: code, observed rate, number of lines, share)

Evidence used (both are observations, not legal sources):
  * the importer's Goods Declaration extract (Chapter 85, Feb 2026): plain-rate home-consumption lines (no concession SRO on the line) whose ACD, as a share of the assessable value, is
    11% on at least 60% of at least 3 lines of the code;
  * the WeBOC duty calculator captured on 2026-10-16 (data/ground_truth/weboc_calculator_2026-10-16.json): ACD 11% printed for the code.
compute_duty reads the CSV and, for these codes, adds a "might apply, not applied" entry to its answer. The main bill still follows the notifications as printed.
"""
from __future__ import annotations

import collections
import csv
import json
from pathlib import Path

from .gd_data import load, num

OUT = Path("data/ground_truth/observed_acd_exceptions.csv")
WEBOC = Path("data/ground_truth/weboc_calculator_2026-10-16.json")


def concession_on_line(r: dict) -> bool:
    s = " ".join(str(r.get(k) or "") for k in ("SRO1", "SRO2", "SRO3", "SRO4")).lower()
    return any(x in s for x in ("1640", "5th", "655", "656", "6th", "8th", "0% cl"))


def build() -> list[dict]:
    seen = collections.defaultdict(list)
    for r in load():
        if r.get("TYPE") == "HC" and r["code8"] and num(r["IV"]) > 0 and not concession_on_line(r):
            seen[r["code8"]].append(round(100 * num(r["ADD. CD"]) / num(r["IV"])))
    out = []
    for code, rates in seen.items():
        n11 = sum(1 for x in rates if x == 11)
        if len(rates) >= 3 and n11 / len(rates) >= 0.6:
            out.append({"code": code, "observed_acd_pct": 11, "lines": len(rates), "share": round(n11 / len(rates), 2), "evidence": "importer GD extract Feb 2026 (aggregate)"})
    known = {x["code"] for x in out}
    if WEBOC.exists():
        for code, (_u, _d, raw) in ((k, v) for k, v in json.loads(WEBOC.read_text(encoding="utf-8")).items() if not k.startswith("_")):
            cells = raw.split("|")
            if "Additional Custom Duty" in cells and cells[cells.index("Additional Custom Duty") + 1] == "11%" and code not in known:
                out.append({"code": code, "observed_acd_pct": 11, "lines": 0, "share": 1.0, "evidence": "WeBOC duty calculator 2026-10-16 (FY2026-27)"})
    return sorted(out, key=lambda x: x["code"])


if __name__ == "__main__":
    rows = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "observed_acd_pct", "lines", "share", "evidence"])
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "codes ->", OUT)
