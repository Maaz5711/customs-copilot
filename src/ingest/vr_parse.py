"""Turn the downloaded FBR valuation rulings into small search documents (goods + illustrative PCT codes).

Input : data/raw/fbr_valuation_rulings/pdf/*.pdf (originals, never edited) and data/processed/vr/manifest.csv
Output: data/processed/vr/vr_docs.json (one document per ruling that shows at least one valid tariff code)
        data/processed/vr/parse_report.json (counts and every skipped ruling with the reason; nothing is fixed silently)

What a valuation ruling is: FBR's Directorate General of Customs Valuation fixes customs VALUES for named goods. Each ruling's table
lists the goods and "HS/PCT codes mentioned for illustrative purposes". So a ruling is weaker evidence for classification than a
Classification Committee decision, but it is an official FBR statement of which code the goods are normally cleared under, and it
covers ordinary goods (food, tyres, cables, electronics) that the Committee notices rarely do.

Reading rules (scans, OCR noise):
* a code token is `dddd.dddd` where a few look-alike letters may stand for digits (O/o->0, l/I/i/|/r->1, S->5, B->8, Z->2, g->9);
* it is kept only when the repaired code is an 8-digit line of the tariff of either fiscal year (so a misread that lands on another
  real code is possible, which is why the document says "illustrative" and the classifier must still justify the line);
* a repaired token is flagged `ocr_repaired` in the document.

    python -m src.ingest.vr_parse
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
PDF_DIR = ROOT / "data" / "raw" / "fbr_valuation_rulings" / "pdf"
OUT = ROOT / "data" / "processed" / "vr"
DB = ROOT / "data" / "processed" / "legal_store.sqlite"
OPEN_END = "9999-12-31"
LOOKALIKE = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "i": "1", "|": "1", "r": "1", "S": "5", "B": "8", "Z": "2", "g": "9", "q": "9"})
TOKEN = re.compile(r"(?<![\w.])([0-9OolIi|rSBZgq]{4})\s?[.,]\s?([0-9OolIi|rSBZgq]{4})(?![\w])")
BOILER = re.compile(r"^\s*(?:publication\s+)?(?:determination|re-?determination|revision)\s+of\s+(?:the\s+)?customs?\s+values?\s+(?:of|for|on)?\s*", re.I)
TAIL = re.compile(r"\s*(?:under|u/s|in terms of)\s+section.*$", re.I)


def product_of(title: str) -> str:
    t = re.sub(r"\s+", " ", title or "").strip().strip('"“”')
    t = TAIL.sub("", BOILER.sub("", t)).strip(' ."“”')
    return t or re.sub(r"\s+", " ", title or "").strip()


def valid_codes(db: Path = DB) -> set[str]:
    """8-digit lines of the tariff plus their 6-digit sub-headings (a ruling may quote only the sub-heading, for example 1513.1900
    where the Pakistan tariff splits the line further)."""
    c = sqlite3.connect(db)
    lines = {r[0] for r in c.execute("select distinct code_norm from tariff_lines where level=8 and status='accepted'")}
    return lines | {x[:6] for x in lines}


def read_codes(text: str, known: set[str]) -> list[dict]:
    """[{'code': '15131900', 'raw': '15r3.r900', 'repaired': True, 'pos': 123}] in order, no duplicates, only known tariff lines."""
    out, seen = [], set()
    for m in TOKEN.finditer(text):
        raw = m.group(1) + "." + m.group(2)
        digits = (m.group(1) + m.group(2)).translate(LOOKALIKE)
        if not digits.isdigit():
            continue
        if digits not in known:
            if digits.endswith("00") and digits[:6] in known:         # sub-heading only
                digits = digits[:6]
            else:
                continue
        if digits in seen:
            continue
        # a plain-digit token that is not a code (a price like 1234.5678) is dropped by the `known` test above
        seen.add(digits)
        out.append({"code": digits, "raw": raw, "repaired": not re.fullmatch(r"\d{4}\.\d{4}", raw), "pos": m.start()})
    return out


HEADER_JUNK = re.compile(r"webo[cC]|origin|customs? values?|c&f|us\$|usd|\(\d\)|s\. ?no|proposed", re.I)


def items_near(text: str, codes: list[dict], width: int = 170) -> list[str]:
    """Short readable snippets of the table text just before each code (the goods description sits there)."""
    out = []
    for c in codes[:6]:
        seg = text[max(0, c["pos"] - width): c["pos"]]
        seg = re.sub(r"\s+", " ", seg)
        seg = re.split(r"(?:Description of Goods|Item Description|Description|S\. ?No\.?|PCT|HS Code|Origins?|Customs? Values?|\(C&F\)|US\$ ?/? ?\w+|USD ?/? ?\w+|\(\d\))\s*", seg)[-1].strip(" :;-.,")
        seg = re.sub(r"^[\W\d_]{0,6}", "", seg).strip()
        if len(seg) >= 4 and not HEADER_JUNK.search(seg) and sum(ch.isalpha() for ch in seg) >= 0.6 * len(seg):
            out.append(seg[:140])
    return list(dict.fromkeys(out))


def build(limit: int | None = None) -> dict:
    known = valid_codes()
    man = list(csv.DictReader(open(OUT / "manifest.csv", encoding="utf-8")))
    docs, skipped = [], []
    stats = {"pdfs": 0, "no_text_layer": 0, "no_valid_code": 0, "docs": 0, "codes": 0, "repaired_codes": 0, "failed_download": 0}
    for m in man[: limit or len(man)]:
        if m.get("status") != "ok":
            stats["failed_download"] += 1
            skipped.append({"file": m["file"], "label": m["label"], "reason": f"download {m.get('status')}"})
            continue
        stats["pdfs"] += 1
        try:
            doc = pymupdf.open(PDF_DIR / m["file"])
            pages = [p.get_text() for p in doc]
        except Exception as e:                      # a broken PDF is reported, not skipped silently
            skipped.append({"file": m["file"], "label": m["label"], "reason": f"cannot open: {type(e).__name__}"})
            continue
        text = "\n".join(pages)
        if len(re.sub(r"\s", "", text)) < 300:
            stats["no_text_layer"] += 1
            skipped.append({"file": m["file"], "label": m["label"], "reason": "no text layer (image-only scan)"})
            continue
        codes = read_codes(text, known)
        if not codes:
            stats["no_valid_code"] += 1
            skipped.append({"file": m["file"], "label": m["label"], "reason": "no valid tariff code found in the text"})
            continue
        page_of = {}
        for pno, ptxt in enumerate(pages, 1):
            for c in read_codes(ptxt, known):
                page_of.setdefault(c["code"], pno)
        product = product_of(m["title"])
        shown = ", ".join((f"{c['code'][:4]}.{c['code'][4:]}" if len(c["code"]) == 8 else f"sub-heading {c['code'][:4]}.{c['code'][4:]}") for c in codes[:8])
        items = items_near(text, codes)
        label = f"Valuation Ruling {m['number']}" if m.get("number") else m["label"]
        body = (f"FBR {label} (Directorate General of Customs Valuation, {m['date']}): customs values of {product}. "
                f"Illustrative PCT code(s) shown for these goods: {shown}.")
        if items:
            body += " Items: " + " | ".join(items) + "."
        stats["codes"] += len(codes)
        stats["repaired_codes"] += sum(c["repaired"] for c in codes)
        docs.append({
            "id": f"vr:{m['file'][:16]}", "index": "rulings", "kind": "valuation_ruling", "ruling": f"{label} (valuation ruling, codes illustrative)", "code": "",
            "text": body, "source_file": m["file"], "page": min(page_of.values()) if page_of else 1, "valid_from": m["date"], "valid_to": OPEN_END,
            "date_basis": "date FBR listed the ruling on its Customs Valuation page; the printed date was not read",
            "codes": [c["code"] for c in codes], "ocr_repaired": [c["raw"] for c in codes if c["repaired"]], "product": product,
            "note": "FBR valuation ruling, text layer of a scan (OCR noise possible); the PCT codes are printed 'for illustrative purposes' only",
        })
        stats["docs"] += 1
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "vr_docs.json").write_text(json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8")
    report = {"stats": stats, "skipped": skipped}
    (OUT / "parse_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    r = build()
    print(json.dumps(r["stats"], indent=1))
    reasons: dict[str, int] = {}
    for s in r["skipped"]:
        reasons[s["reason"]] = reasons.get(s["reason"], 0) + 1
    print("skipped by reason:", reasons)
