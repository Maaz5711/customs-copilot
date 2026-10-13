"""Build ONE short review page with only the rows that matter most (owner time is limited).

Picks: unanswered rows from earlier review runs, high-impact tax rates (income tax s.148, sales tax headline rates),
and a small sample of the rest. Everything else goes to an independent AI second reader (not owner-verified).
Usage: python -m src.ingest.review_crucial
"""
import csv
import html
from pathlib import Path

import pymupdf

from src.ingest.review_pages import REV, P, build, sro_items, tariff_items

RAW = Path("data/raw")
IMG = P / "page_images" / "crucial"


def page_img(pdf_name, page, dpi=110):
    IMG.mkdir(parents=True, exist_ok=True)
    stem = Path(pdf_name).stem[:40]
    f = IMG / f"{stem}_p{int(page):04d}.png"
    if not f.exists():
        doc = pymupdf.open(RAW / pdf_name)
        doc[int(page) - 1].get_pixmap(dpi=dpi).save(f)
    return f"../page_images/crucial/{f.name}"


def unanswered_1152():
    done = {r["id"] for r in csv.DictReader(open(P / "review_results/sro_1152_rd_failures-results.csv", encoding="utf-8"))
            if r["answer"]}
    return [i for i in sro_items(P / "sro_1152_rd_failures.csv", True) if i["id"] not in done]


def sample_1064(n=12):
    items = [i for i in sro_items(P / "spotcheck_sro_1064_rd.csv", False) if int(i["id"].split("-")[0][1:]) >= 11]
    odd = [i for i in items if not i["plain"].endswith((".0", "10", "20"))]
    pick = (odd + items)[:n * 3]
    seen, out = set(), []
    for i in pick:
        if i["id"] not in seen:
            seen.add(i["id"]); out.append(i)
    return out[:n]


def tax_rows():
    items = []
    for r in csv.DictReader(open(P / "a3_it_s148_rates.csv", encoding="utf-8")):
        items.append({"id": "it-" + r["rule_id"], "line": f"Income tax s.148, S.No <b>{r['s_no']}</b>: <b>{html.escape(r['rate_raw'][:140])}</b> "
                      f"(rate {r['rate_pct']}%, {html.escape(r['importer_status'] or r['importer_category'])})",
                      "plain": f"IT s148 S.No {r['s_no']} rate {r['rate_pct']} {r['importer_category']}",
                      "img": page_img(r["source_file"], r["page"]), "why": "Headline income-tax rate: is the % and who it applies to right?"})
    for r in csv.DictReader(open(P / "a3_sales_tax_rules.csv", encoding="utf-8")):
        head = r["instrument"] == "Sales Tax Act 1990" and r["rate_pct"]
        phase = "Eighth Schedule" in r["instrument"] and r["rate_pct"] in ("12.0", "14.0", "16.0")
        if head or phase:
            items.append({"id": "st-" + r["clause"][:30] + r["valid_from"] + r["rate_pct"],
                          "line": f"{html.escape(r['instrument'])}, {html.escape(r['clause'][:60])}: <b>{r['rate_pct']}%</b> from <b>{r['valid_from']}</b> ({html.escape(r['tax_kind'])}, {html.escape(r['importer_status'])})",
                          "plain": f"{r['instrument']} {r['clause']} {r['rate_pct']} {r['valid_from']}",
                          "img": page_img(r["source_file"], r["page"]), "why": "Headline sales-tax rate: check the % and the start date."})
    return items


if __name__ == "__main__":
    REV.mkdir(parents=True, exist_ok=True)
    items = unanswered_1152() + sample_1064() + tax_rows() + tariff_items()[::5][:10]
    build("crucial_review", f"Crucial rows only ({len(items)})",
          "Only the rows that change a duty bill. Find the row on the image; if it matches click Matches, otherwise Wrong and type what the page says. Not sure is fine.",
          items)
    print(len(items), "cards")
