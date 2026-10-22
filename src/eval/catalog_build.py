"""Build data/ground_truth/cases_catalog.csv from catalog_descriptions.tsv.

The TSV holds one everyday importer-style description per sampled tariff line (written by Claude, see catalog_sample.py).
This script checks every code against the store (FY2026-27, 8-digit, accepted), adds the tariff wording as `basis`, the page,
the chapter and the dev/test split (by 4-digit heading), and writes the case file. Nothing here is verified by a person.

    python -m src.eval.catalog_build
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from .catalog_sample import FY, load_lines, split_of, tidy

GT = Path("data/ground_truth")
SRC = GT / "catalog_descriptions.tsv"
OUT = GT / "cases_catalog.csv"
AS_OF = "2026-09-15"
LABEL = "synthetic, unverified, written by Claude from a random category sample of the tariff, must be confirmed by a qualified person"
FIELDS = ["id", "description", "as_of_date", "fiscal_year", "expected_behavior", "expected_code", "label_confidence", "split", "chapter",
          "basis", "tariff_page", "verified", "label"]


def build() -> list[dict]:
    lines = {ln["code_norm"]: ln for ln in load_lines()}
    rows, seen = [], set()
    for r in csv.DictReader(open(SRC, encoding="utf-8"), delimiter="\t"):
        code = r["code"].strip()
        norm = code.replace(".", "")
        ln = lines.get(norm)
        if ln is None:
            raise SystemExit(f"{code}: not an accepted 8-digit line of {FY}")
        if norm in seen:
            raise SystemExit(f"{code}: written twice")
        seen.add(norm)
        desc = r["description"].strip()
        if not desc or "\t" in desc:
            raise SystemExit(f"{code}: bad description")
        rows.append({"id": "", "description": desc, "as_of_date": AS_OF, "fiscal_year": FY, "expected_behavior": "answer", "expected_code": ln["code"],
                     "label_confidence": r["label_confidence"].strip() or "M", "split": split_of(norm[:4]), "chapter": norm[:2],
                     "basis": (ln.get("heading_text", "") + " > " + tidy(ln["description"]))[:400], "tariff_page": ln["page"], "verified": "false", "label": LABEL})
    rows.sort(key=lambda x: x["expected_code"])
    for i, row in enumerate(rows, 1):
        row["id"] = f"C{i:03d}"
    return rows


def main() -> None:
    rows = build()
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    dev = sum(r["split"] == "dev" for r in rows)
    high = sum(r["label_confidence"] == "H" for r in rows)
    print(f"{len(rows)} cases in {len({r['chapter'] for r in rows})} chapters -> {OUT} (dev {dev}, test {len(rows) - dev}; confidence H {high}, M {len(rows) - high})")


if __name__ == "__main__":
    sys.exit(main())
