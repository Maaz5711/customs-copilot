"""Run A1: parse a tariff PDF and write data/processed/tariff_<fy>.{json,csv}
and a spot-check sheet for the rows that need a human look.

Usage: python -m src.ingest.run_tariff
"""
import csv
import json
from pathlib import Path

from src.ingest.tariff import load_pages, parse_pages

RAW = Path("data/raw")
OUT = Path("data/processed")

# fiscal year -> (pdf name, valid_from, valid_to). Pakistan's FY runs 1 Jul to 30 Jun.
TARIFFS = {
    "2026_27": ("20268251181330180Tariff-2026-27.pdf", "2026-07-01", "2027-06-30"),
    "2025_26": ("20258111683941732Tariff-2025-26.pdf", "2025-07-01", "2026-06-30"),
}


def run(fy: str):
    pdf_name, valid_from, valid_to = TARIFFS[fy]
    pdf = RAW / pdf_name
    pages = load_pages(pdf, OUT / "cache" / f"tariff_{fy}_pages.json")
    headings, rows, special = parse_pages(pages, pdf_name)
    for r in headings + rows + special:
        r["valid_from"], r["valid_to"] = valid_from, valid_to
    (OUT / f"tariff_{fy}.json").write_text(
        json.dumps({"headings": headings, "rows": rows, "special": special}, indent=1), encoding="utf-8")
    with open(OUT / f"tariff_{fy}.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["code", "heading", "description", "cd_kind", "cd_plain", "cd_raw",
                "valid_from", "valid_to", "source_file", "page"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    # spot-check: every non-plain row (needs eyes) + a seeded 10% sample of the rest
    import random
    rnd = random.Random(2026)
    plain = [r for r in rows if r["cd_kind"] == "plain"]
    check = [r for r in rows if r["cd_kind"] != "plain"] + rnd.sample(plain, k=len(plain) // 10)
    check.sort(key=lambda r: r["code"])
    with open(OUT / f"spotcheck_tariff_{fy}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code", "page", "description", "parsed_cd", "reason", "correct? (Y/N)", "true_value_if_N"])
        for r in check:
            parsed = r["cd_plain"] if r["cd_kind"] == "plain" else r["cd_raw"]
            reason = "sample" if r["cd_kind"] == "plain" else "specific/compound duty"
            w.writerow([r["code"], r["page"], r["description"][:80], parsed, reason, "", ""])
    return headings, rows, special


if __name__ == "__main__":
    import sys
    for fy in (sys.argv[1:] or ["2026_27"]):
        h, r, s = run(fy)
        print(f"{fy}: headings={len(h)} rows={len(r)} special={len(s)}")
