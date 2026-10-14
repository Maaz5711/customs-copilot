"""Owner review page for the 20-case ground-truth sample (real cases link to the public PDF).
Usage: python -m src.ingest.owner_review_cases   (writes data/processed/review/ground_truth_20_cards.html)
"""
import csv
import html
from pathlib import Path

from src.ingest.review_pages import REV, build

PIXEL = "data:image/gif;base64,R0lGODlhAQABAAAAACw="
SRC = Path("data/ground_truth/owner_review_sample.csv")


def items():
    out = []
    for r in csv.DictReader(open(SRC, encoding="utf-8-sig")):
        link = r["where_to_check"].strip()
        link_html = (f'<a href="{html.escape(link)}" target="_blank">Open the source PDF</a>'
                     if link.startswith("http") else html.escape(link))
        kind = "REAL case" if r["kind"] == "real" else "SYNTHETIC case (written by Claude, unverified)"
        line = (f"<b>#{r['sample_no']} {kind}</b> [{html.escape(r['case_id'])}], date {html.escape(r['as_of_date'])}<br>"
                f"Goods: <b>{html.escape(r['description'])}</b><br>"
                f"Expected: <b>{html.escape(r['expected_behavior'])}</b> code <b>{html.escape(r['expected_code'] or '-')}</b><br>"
                f"Basis: {html.escape(r['evidence_or_basis'])}<br>{link_html}")
        why = "What to check: " + html.escape(r["what_to_check"])
        out.append({"id": f"{r['sample_no']}-{r['case_id']}", "line": line,
                    "plain": f"{r['case_id']} {r['expected_code']}", "img": PIXEL, "why": why})
    return out


if __name__ == "__main__":
    REV.mkdir(parents=True, exist_ok=True)
    it = items()
    build("ground_truth_20_cards", f"Ground-truth sample: {len(it)} cases",
          "Real cases: open the source PDF (link on the card) and check that the goods and the code match what the notice decided. "
          "Synthetic cases: judge whether the expected code is right for the goods using your own knowledge or the tariff. "
          "Click Matches, Wrong (type the code you think is right) or Not sure.", it)
    print(len(it), "cards")
