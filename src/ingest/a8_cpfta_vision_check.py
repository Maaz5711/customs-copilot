"""A8: independent second reader for a few pages of SRO 1640(I)/2019: DeepSeek flash vision (paid, tokens counted and reported).

The page image is sent once; the model returns, for every table row, Sr.No, PCT code and the Year 6/7/8 columns (1-Jan-25, 1-Jan-26,
1-Jan-27: the calendar years of FY2025-26 and FY2026-27). The answer is compared with the OCR-based reading (a8_cpfta_rows.csv) row by row.
It is a spot reader for a handful of pages, NOT a replacement of the OCR (cost per page is given in the report).
Results are cached in data/processed/cpfta_vision/p<NNN>.json. Usage: python -m src.ingest.a8_cpfta_vision_check 17 100 130
"""
from __future__ import annotations

import base64
import csv
import glob
import json
import os
import sys
from pathlib import Path

import pymupdf
import requests
from dotenv import load_dotenv

load_dotenv(".env")
PROC = Path("data/processed")
OUT = PROC / "cpfta_vision"
PDF = glob.glob("data/raw/cpfta/*.pdf")[0]
URL = "https://api.deepseek.com/chat/completions"
PROMPT = ("This is one page of a scanned table from a Pakistani customs notification (SRO 1640(I)/2019). Columns: Sr.No, PCT code (8 digits), "
          "Description, then 15 yearly duty columns Year 1 (1-Jan-20) to Year 15 (1-Jan-34), each a number with two decimals. "
          "Return JSON {\"rows\": [{\"sr_no\": int, \"code\": \"8 digits\", \"y6\": \"value under 1-Jan-25 (Year 6)\", \"y7\": \"value under 1-Jan-26 (Year 7)\", "
          "\"y8\": \"value under 1-Jan-27 (Year 8)\"}]} with one entry for EVERY table row on the page, in order, copied exactly as printed. "
          "Use \"?\" for a character you cannot read. Do not invent rows.")


def read_page(pno: int) -> dict:
    f = OUT / f"p{pno:03d}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    doc = pymupdf.open(PDF)
    png = doc[pno - 1].get_pixmap(dpi=150).tobytes("png")
    body = {"model": os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"), "max_tokens": 12000, "temperature": 0, "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT},
                                                      {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}]}]}
    r = requests.post(URL, headers={"Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"]}, json=body, timeout=300)
    r.raise_for_status()
    j = r.json()
    text = j["choices"][0]["message"]["content"]
    res = {"page": pno, "model": body["model"], "usage": j.get("usage"), "image_bytes": len(png), "rows": json.loads(text).get("rows", [])}
    OUT.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return res


def compare(pno: int):
    vis = read_page(pno)
    ours = {r["code"]: r for r in csv.DictReader(open(PROC / "a8_cpfta_rows.csv", encoding="utf-8")) if r["page"] == str(pno) and r["code"]}
    rows = []
    for v in vis["rows"]:
        c = str(v.get("code", "")).replace(".", "")
        o = ours.get(c)
        if o is None:
            rows.append((c, "code_not_in_ocr_reading", v, None))
            continue
        diffs = [f"y{y}: vision {v.get('y' + str(y))} vs ocr {o['year_' + str(y)]}" for y in (6, 7, 8)
                 if str(v.get("y" + str(y), "")).strip() not in ("", "?") and abs(float(str(v["y" + str(y)]).replace(",", ".")) - float(o["year_" + str(y)] or -1)) > 0.015]
        rows.append((c, "differs" if diffs else "agrees", v, diffs))
    return vis, rows, len(ours)


def main(pages):
    summary = []
    for p in pages:
        vis, rows, nours = compare(p)
        n = len(rows)
        agree = sum(1 for r in rows if r[1] == "agrees")
        u = vis.get("usage") or {}
        summary.append(dict(page=p, vision_rows=n, ocr_rows_with_code=nours, agree=agree,
                            code_not_in_ocr=[r[0] for r in rows if r[1] == "code_not_in_ocr_reading"],
                            differences=[(r[0], r[3]) for r in rows if r[1] == "differs"], prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens")))
    return summary


if __name__ == "__main__":
    print(json.dumps(main([int(x) for x in sys.argv[1:]]), indent=1))
