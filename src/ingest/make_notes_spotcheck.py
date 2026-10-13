"""A4: build the spot-check sheet for legal notes (>= 10% of records).
All GRI/Pakistan rules, all flagged records, all multi-page notes, plus a seeded
random sample of the rest (about 15% overall)."""
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
recs = json.loads((ROOT / "data/processed/legal_notes.json").read_text("utf-8"))
random.seed(42)
must = [r for r in recs if r["kind"].startswith("gri") or r["flags"] or r["page_end"] != r["page"]]
rest = [r for r in recs if r not in must]
target = max(int(len(recs) * 0.15), len(must))
pick = must + random.sample(rest, max(0, target - len(must)))
pick.sort(key=lambda r: (r["page"], r["note_id"]))


def excerpt(t):
    t = t.replace("\n", " ")
    return t if len(t) <= 300 else t[:200] + " [...] " + t[-100:]


out = ROOT / "data/processed/spotcheck_legal_notes.csv"
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["page", "note_id", "text_excerpt", "correct? (Y/N)", "true_value_if_N"])
    for r in pick:
        w.writerow([r["page"], r["note_id"], excerpt(r["text"]), "", ""])
print(len(pick), "of", len(recs), f"({len(pick)/len(recs):.0%})")
