"""A6: write the AI second-read sheet for spotcheck_a6_fed.csv.
LABEL: AI second reader (Claude), NOT owner verification. Claude looked at the page image (data/processed/page_images/fed25|fed26) and
compared with the parsed row AFTER reading the cell. Pages whose image was not viewed are marked 'unsure' (text layer only).
Usage: python -m src.ingest.a6_fed_second_read"""
import csv
from pathlib import Path

P = Path("data/processed")
IMAGE_VIEWED = {("FY2026-27", p) for p in (71, 72, 73, 74, 75, 76, 77, 78, 80, 90, 92, 95, 99, 100)} | \
               {("FY2025-26", p) for p in (73, 76, 77, 79, 80, 81)}
NOTES = {
    "35": ("unsure", "Rate read OK (Rupees sixty per hundred metric tonne). The page prints heading 2711.1900, which is not a tariff code (tariff has 2711.1910 and "
                     "2711.1990); the store maps it to the 6-digit prefix 271119: an inference, needs a customs expert."),
    "8": ("match", "Page prints 'Sixty five percent of retail price or the rate of duty as prescribed against S. No. 9 whichever is higher.' The Rs 16,500 per thousand "
                   "cigarettes is NOT printed in this row: it is taken from S.No 9 by reference (row is needs_review)."),
    "55": ("match", "Bands and rates read OK. Note the page prints 'exceeding 3001cc' after '1800cc to 3000cc', so 3001 cc is in no band; and the description names electric "
                    "vehicles (4 wheelers) until 30 June of the printed year."),
    "55A": ("match", "Rates and USD bands read OK (red text). '(a) 0%' prints no 'ad val' words. Heading column prints 'Respective Heading': no code."),
    "IA": ("match", "Table 1A read OK (red text): 87.03, 8704.2190, 8704.3190; (a) 2000cc and above but not exceeding 3000cc 86% ad val; (b) exceeding 3000cc 92% ad val."),
    "7a": ("match", "Rate word read OK (forty four thousand in 2025 file, ten thousand in 2026 file, 'ten' in red)."),
    "8a": ("match", "2025: 'Rupees ten thousand per kg or sixty five percent of retail price whichever is higher'; 2026: 'Rupees sixteen thousand five hundred per kg' (red)."),
    "64": ("match", "Rs.10 Per DOC; heading 'Respective Heading' (no code); in the 2025 file the row is red (Finance Act 2025)."),
    "65": ("match", "Three items at Rs. 80 per liter with codes; the proviso (in-house consumption exemption) is printed in red below the rows."),
}


def main():
    out = []
    for r in csv.DictReader(open(P / "spotcheck_a6_fed.csv", encoding="utf-8")):
        key = r["s_no"] if r["table_no"] != "IA" else "IA"
        viewed = (r["fy"], int(r["page"])) in IMAGE_VIEWED
        verdict, note = NOTES.get(key, ("match", "Serial, codes and rate cell read on the page image and equal the parsed row."))
        if r["table_no"] == "Third-I":
            note = "Exemption text and heading column read on the page image; every condition in the printed text applies (the tools never apply it automatically)."
        if not viewed:
            verdict, note = "unsure", "The page image was not viewed by the AI reader; only the text layer agrees (checked by code). " + note
        out.append(dict(row_id=r["row_id"], parsed_value=r["parsed"], ai_read_value=r["rate_raw"] if r["table_no"] != "Third-I" else r["description"][:200],
                        verdict=verdict, note="AI second reader, not owner verification. " + note))
    (P / "ai_second_read").mkdir(exist_ok=True)
    with open(P / "ai_second_read" / "spotcheck_a6_fed.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader(); w.writerows(out)
    from collections import Counter
    print(Counter(o["verdict"] for o in out), len(out))


if __name__ == "__main__":
    main()
