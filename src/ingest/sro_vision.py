"""A2: read scanned SRO table pages with a vision model.

Each page is rendered to a PNG and sent to Gemini. We keep exactly what is
printed (rate as text, code as text) and never fix anything here. Validators
and the two-model diff live in sro_validate.py. Results are cached per
(pdf, model, page) so reruns cost nothing.

Usage: python -m src.ingest.sro_vision <pdf> <model> [first_page last_page]
"""
import base64
import json
import os
import sys
import time
from pathlib import Path

import pymupdf
import requests
from dotenv import load_dotenv

load_dotenv()
OUT = Path("data/processed/sro_vision")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """You are transcribing one page of a Pakistani government SRO (customs notification) exactly as printed.
Return JSON: {"preamble": str, "rows": [...], "trailer": str}.
- rows: every table row on the page, in order. Each row: {"s_no": str, "pct_code": str, "description": str, "rate": str}.
  Copy s_no, pct_code and rate EXACTLY as printed, character for character (keep decimal points, e.g. "4.0", "20.0"; never round or fix).
  A PCT code is either 8-digit like 0101.2100 or a 4-digit heading like 01.05; keep the dots as printed.
  description: the full text of column (3), including any "except ..." clauses.
  If a row continues from the previous page without an S.No, use s_no "".
- preamble: any text above the table (title, legal wording); empty string if none.
- trailer: any text below the table (notes, provisos, signatures); empty string if none.
If a character is unreadable, write "?" for it. Do not invent content."""


CORE_PROMPT = """Transcribe ONLY columns (1), (2) and (4) of the table on this page, exactly as printed.
Return JSON: {"rows": [{"s_no": str, "pct_code": str, "rate": str, "except_codes": [str]}]}.
Copy s_no, pct_code and rate character for character (keep decimal points such as "4.0"). A PCT code is 8-digit like
0101.2100 or a 4-digit heading like 01.05. except_codes: any PCT codes named after the word "except" in column (3), else [].
Do not transcribe descriptions. Use "?" for unreadable characters. Do not invent content."""


def render(pdf: Path, page: int, dpi: int = 160) -> bytes:
    with pymupdf.open(pdf) as d:
        return d[page - 1].get_pixmap(dpi=dpi).tobytes("png")


def call(model: str, png: bytes) -> dict:
    """Retry on quota errors and on empty answers (for example finishReason RECITATION).
    If every try fails, return an error record so the validator flags the page."""
    reason = "no response"
    for attempt in range(5):
        body = {
            "contents": [{"parts": [
                {"text": PROMPT if attempt < 3 else CORE_PROMPT},
                {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}}]}],
            "generationConfig": {"temperature": 0 if attempt < 3 else 0.2, "responseMimeType": "application/json"},
        }
        try:
            r = requests.post(URL.format(model=model), json=body, timeout=300,
                              headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
        except requests.RequestException as e:
            reason = f"network: {type(e).__name__}"
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code != 200:
            reason = f"http {r.status_code}"
            time.sleep(10 * (attempt + 1))
            continue
        cand = r.json()["candidates"][0]
        parts = cand.get("content", {}).get("parts")
        if parts:
            try:
                res = json.loads(parts[0]["text"])
                if attempt >= 3:
                    res.setdefault("preamble", "")
                    res["trailer"] = ""
                    res["description_missing"] = True
                    for row in res.get("rows", []):
                        row["description"] = ""
                return res
            except json.JSONDecodeError:
                reason = "bad json"
                continue
        reason = cand.get("finishReason", "empty")
    return {"preamble": "", "rows": [], "trailer": "", "error": f"extraction failed: {reason}"}


def extract(pdf: Path, model: str, page: int) -> dict:
    cache = OUT / pdf.stem / model / f"p{page:03d}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    res = call(model, render(pdf, page))
    res["page"], res["source_file"], res["model"] = page, pdf.name, model
    if "error" in res:  # do not cache failures, so a rerun tries again
        return res
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    return res


if __name__ == "__main__":
    pdf, model = Path(sys.argv[1]), sys.argv[2]
    n = len(pymupdf.open(pdf))
    a, b = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (1, n)
    for p in range(a, b + 1):
        r = extract(pdf, model, p)
        print(pdf.name, model, "page", p, "rows", len(r.get("rows", [])), flush=True)
