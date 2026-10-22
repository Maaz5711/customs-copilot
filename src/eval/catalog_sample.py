"""Draw a reproducible, category-balanced sample of real 8-digit tariff lines (FY2026-27) to write test cases against.

Why: the 79 real cases are mostly disputes and the 60 synthetic ones were hand-picked. A catalogue case set walks the whole
tariff by category, so one number says how the agent does on ordinary goods in every chapter, not only on contested ones.

Method (fixed seed, no LLM): for every chapter 01-97 keep lines that are 8-digit, `accepted`, plain or specific duty rows;
chapter quota = round(share * sqrt(lines in chapter)), at least 2; lines are drawn at random inside the chapter but never two
from the same 6-digit sub-heading. A surplus is drawn (a person writing the cases may skip a line that has no natural product).
The split into dev and test is by 4-digit heading (hash), so no heading is in both sets: tune on dev, report on test.

    python -m src.eval.catalog_sample --total 420 --out data/processed/eval/catalog_candidates.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import random
import re
import sqlite3
from pathlib import Path

DB = Path("data/processed/legal_store.sqlite")
FY = "FY2026-27"
SEED = 20261022


def split_of(heading4: str) -> str:
    """'dev' or 'test' from the 4-digit heading only (stable across runs and machines): 70% dev, 30% test."""
    h = int(hashlib.sha256(f"catalog-split-v1:{heading4}".encode()).hexdigest(), 16) % 10
    return "test" if h >= 7 else "dev"


def tidy(desc: str) -> str:
    """One readable line from the stored description (parents joined by ':' with leading dashes)."""
    parts = [re.sub(r"^[\s\-–]+", "", p).strip() for p in re.split(r"\s:\s|:\s(?=-)", desc or "")]
    parts = [p for p in parts if p]
    return " > ".join(parts)


def load_lines(db: Path = DB, fy: str = FY) -> list[dict]:
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    heads = {r["heading"]: r["text"] for r in c.execute("select heading, text from tariff_headings where fy=?", (fy,))}
    rows = c.execute("select code, code_norm, heading, description, page from tariff_lines where fy=? and level=8 and status='accepted' order by code_norm", (fy,)).fetchall()
    seen, out = set(), []
    for r in rows:
        if r["code_norm"] in seen:           # the 6 duplicated vehicle codes are kept out of the sample
            continue
        seen.add(r["code_norm"])
        out.append({**dict(r), "heading_text": re.sub(r"\s+", " ", heads.get(r["heading"], "")).strip()})
    return [x for x in out if len(x["code_norm"]) == 8 and not x["code_norm"].startswith(("98", "99"))]


def sample(total: int, seed: int = SEED, lines: list[dict] | None = None) -> list[dict]:
    lines = lines or load_lines()
    by_ch: dict[str, list[dict]] = {}
    for ln in lines:
        by_ch.setdefault(ln["code_norm"][:2], []).append(ln)
    weights = {ch: math.sqrt(len(v)) for ch, v in by_ch.items()}
    scale = total / sum(weights.values())
    rng = random.Random(seed)
    out = []
    for ch in sorted(by_ch):
        quota = max(2, round(weights[ch] * scale))
        pool = by_ch[ch][:]
        rng.shuffle(pool)
        taken, six = [], set()
        for ln in pool:
            if ln["code_norm"][:6] in six:
                continue
            six.add(ln["code_norm"][:6])
            taken.append(ln)
            if len(taken) >= quota:
                break
        out += sorted(taken, key=lambda x: x["code_norm"])
    for ln in out:
        ln["chapter"] = ln["code_norm"][:2]
        ln["split"] = split_of(ln["code_norm"][:4])
        ln["tariff_text"] = tidy(ln["description"])
        ln["heading_text"] = ln.get("heading_text", "")
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--total", type=int, default=420)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", type=Path, default=Path("data/processed/eval/catalog_candidates.csv"))
    a = ap.parse_args(argv)
    rows = sample(a.total, a.seed)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["code", "code_norm", "chapter", "split", "page", "heading_text", "tariff_text"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    n_dev = sum(r["split"] == "dev" for r in rows)
    print(f"{len(rows)} candidate lines in {len({r['chapter'] for r in rows})} chapters -> {a.out} (dev {n_dev}, test {len(rows) - n_dev})")


if __name__ == "__main__":
    main()
