"""A8: spot-check sheet for the China FTA (SRO 1640(I)/2019) lines: every 8th line (12.5%) plus every 4th line that needs review, with the page image to compare against.
The owner fills the last two columns. Usage: python -m src.ingest.a8_cpfta_spotcheck"""
import csv
import glob
from pathlib import Path

import pymupdf

P = Path("data/processed")


def main():
    rows = list(csv.DictReader(open(P / "a8_cpfta_rows.csv", encoding="utf-8")))
    out, k, nr = [], 0, 0
    for r in rows:
        k += 1
        nr += r["status"] == "needs_review"
        if k % 8 == 0 or (r["status"] == "needs_review" and nr % 4 == 0):
            vals = [r[f"year_{i}"] for i in range(1, 16)]
            out.append(dict(sr_no=r["sr_no"], page=r["page"], code=r["code"], description_ocr=r["description_ocr"][:90], pattern=r["pattern"],
                            years_2025_2026_2027_loaded=" | ".join(vals[5:8]), all_15_years=" ".join(vals), cells_read=r["cells_read"], cells_agree=r["cells_agree"],
                            issues=r["issues"], page_image=f"data/processed/page_images/cpfta/p{int(r['page']):03d}.png",
                            **{"correct? (Y/N)": "", "true_value_if_N": ""}))
    with open(P / "spotcheck_a8_cpfta.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    pages = sorted({int(o["page"]) for o in out})
    d = Path("data/processed/page_images/cpfta")
    d.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(glob.glob("data/raw/cpfta/*.pdf")[0])
    for pn in pages:
        doc[pn - 1].get_pixmap(dpi=110).save(d / f"p{pn:03d}.png")
    print(len(out), "of", len(rows), "lines;", len(pages), "pages")


if __name__ == "__main__":
    main()
