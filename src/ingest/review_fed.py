"""A6: ONE short owner page with the 15 FED rows that matter most (vehicles by engine capacity first). Full row text on every card.
Usage: python -m src.ingest.review_fed  -> data/processed/review/fed_15_cards.html"""
import csv
import html
from pathlib import Path

from src.ingest.review_pages import REV, build

P = Path("data/processed")
PICK = [  # (fy, table, s_no, why)
    ("FY2026-27", "I", "55", "Imported cars: the biggest FED rates. Are the four engine-capacity bands and rates right (note the page prints 1800-3000cc then 'exceeding 3001cc')?"),
    ("FY2026-27", "IA", "1", "New Special Excise Duty from 1 Jul 2026, on top of Table I. Are 86% and 92% and the 2000cc / 3000cc limits right?"),
    ("FY2026-27", "I", "55A", "New electric-car rates by USD value. Are 0% / 30% / 40% and the USD 75,000 / 110,000 limits right?"),
    ("FY2026-27", "I", "55C", "Imported double-cabin 4x4 pickups: 30%. Right rate and codes?"),
    ("FY2025-26", "I", "55", "Last year's car bands (same numbers; electric words say 'till 30 June 2026'). Right?"),
    ("FY2026-27", "I", "8", "Imported cigarettes: 65% of retail price or the S.No 9 rate, whichever is higher. Right wording?"),
    ("FY2026-27", "I", "9", "S.No 9 (the rate S.No 8 points to): Rs. 16,500 per thousand cigarettes. Right amount?"),
    ("FY2026-27", "I", "8a", "E-liquid changed to Rs. 16,500 per kg (red). Right?"),
    ("FY2026-27", "I", "7a", "Acetate tow changed to Rs. 10,000 per kg (red). Right?"),
    ("FY2026-27", "I", "13", "Cement: four rupees per kilogram. Right?"),
    ("FY2026-27", "I", "4", "Aerated waters: 20% of retail price. Right?"),
    ("FY2026-27", "I", "3", "Concentrates for aerated beverages: 50% ad val. Right?"),
    ("FY2026-27", "I", "65", "New: naphtha, white spirit, solvent oil Rs. 80 per liter. Right amounts and codes?"),
    ("FY2026-27", "I", "63", "Lubricating oil and base oils 5%: now four codes incl. 2710.1993. Right?"),
    ("FY2026-27", "I", "32", "LPG propane: 17 rupees 18 paisa per hundred cubic metres. Right?"),
]


def main():
    rows = list(csv.DictReader(open(P / "a6_fed_rules.csv", encoding="utf-8")))
    items = []
    for fy, tbl, sno, why in PICK:
        rs = [r for r in rows if r["fy"] == fy and r["table_no"] == tbl and r["s_no"] == sno]
        first = rs[0]
        subs, seen = [], set()
        for r in rs:
            k = (r["sub"], r["rate_raw"])
            if k not in seen:
                seen.add(k)
                subs.append(f"{html.escape(r['sub'])} {html.escape(r['sub_desc'] or '')} &rarr; <b>{html.escape(r['rate_raw'])}</b>")
        codes = html.escape(first["heading_raw"])
        line = (f"{fy}, file page {first['page']}, Table {tbl} S.No <b>{sno}</b>. Goods: {html.escape(first['description'])}<br>"
                f"Heading column as printed: <b>{codes}</b><br>" + "<br>".join(subs))
        if first["condition_text"]:
            line += f"<br><i>Condition text: {html.escape(first['condition_text'])}</i>"
        img_dir = "fed26" if fy == "FY2026-27" else "fed25"
        items.append({"id": f"{fy}-{tbl}-{sno}", "line": line, "plain": f"{fy} T{tbl} S.No {sno} p{first['page']} " + "; ".join(sorted(seen and [x[1] for x in seen])),
                      "img": f"../page_images/{img_dir}/p{int(first['page']):03d}.png", "why": html.escape(why)})
    REV.mkdir(parents=True, exist_ok=True)
    build("fed_15_cards", f"Federal excise duty: the {len(items)} rows that matter most",
          "Open the page image. Find the S.No. If the text on the card equals what the page prints, click Matches. If not, click Wrong and type what the page says. "
          "Not sure is fine. Page numbers are the page numbers printed at the bottom of the FED Act file.", items)
    print(len(items), "cards")


if __name__ == "__main__":
    main()
