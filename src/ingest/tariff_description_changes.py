"""List every tariff row whose description changed when the header-attachment bug was fixed.

Old = the JSON committed before the fix (git revision BASELINE_REV). New = the current
data/processed/tariff_<fy>.json. Writes data/processed/tariff_description_changes.csv.

change_type:
  glued_header_removed  old text ended with the header of the NEXT group (the bug); new text does not
  parent_header_added   old text was the row's own text only; new text also carries its enclosing headers
  wrapped_text_changed  anything else (for example wrapped text across a page break was recovered)

Usage: python -m src.ingest.tariff_description_changes
"""
import csv
import json
import subprocess
from pathlib import Path

BASELINE_REV = "9b0e07e"
PROC = Path("data/processed")
FYS = ("2026_27", "2025_26")


def old_json(fy: str) -> dict:
    out = subprocess.run(["git", "show", f"{BASELINE_REV}:data/processed/tariff_{fy}.json"],
                         capture_output=True, check=True).stdout
    return json.loads(out.decode("utf-8"))


def classify(old: str, row: dict) -> str:
    own = row["own_text"]
    if old == own:
        return "parent_header_added"
    if old.startswith(own):
        return "glued_header_removed"
    return "wrapped_text_changed"


def changes() -> list[dict]:
    out = []
    for fy in FYS:
        old = {(r["code"], r["page"]): r for r in old_json(fy)["rows"]}
        new = json.loads((PROC / f"tariff_{fy}.json").read_text(encoding="utf-8"))["rows"]
        for r in new:
            o = old[(r["code"], r["page"])]
            if o["description"] == r["description"]:
                continue
            out.append({
                "fy": fy, "code": r["code"], "page": r["page"],
                "change_type": classify(o["description"], r),
                "old_description": o["description"], "new_description": r["description"],
                "new_own_description": r["own_description"], "new_full_description": r["full_description"],
            })
    return out


if __name__ == "__main__":
    rows = changes()
    path = PROC / "tariff_description_changes.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    import collections
    print(len(rows), "rows changed;", dict(collections.Counter((r["fy"], r["change_type"]) for r in rows)))
