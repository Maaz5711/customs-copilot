"""A2 validators for SRO table extractions. Nothing is fixed silently.

Per row we record `issues` (hard failures that need a human) and `agree`
(both vision models gave the same code and rate). A row is `accepted` only
when it has no issues and both models agree; everything else goes to review.

Usage: python -m src.ingest.sro_validate <pdf stem> <modelA> <modelB> <rate_name>
"""
import csv
import difflib
import json
import re
import sys
from pathlib import Path

import pymupdf

OUT = Path("data/processed")
CODE8 = re.compile(r"^\d{4}\.\d{4}$")
CODE4 = re.compile(r"^\d{2}\.\d{2}$")
RATE = re.compile(r"^\d{1,3}\.\d$")  # one-decimal rule: printed as 4.0, 20.0 ...


def load_tariff(fy="2026_27"):
    t = json.loads((OUT / f"tariff_{fy}.json").read_text(encoding="utf-8"))
    return {r["code"] for r in t["rows"]}, {h["heading"] for h in t["headings"]}


def load_rows(stem: str, model: str):
    rows = []
    for f in sorted((OUT / "sro_vision" / stem / model).glob("p*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for i, r in enumerate(d["rows"]):
            rows.append({**r, "page": d["page"], "idx": i})
    return rows


def norm(s):
    return re.sub(r"\W+", "", (s or "").lower())


def validate(stem: str, model_a: str, model_b: str, max_rate=100.0):
    pdf = next(Path("data/raw").glob(f"*{stem}*.pdf"))
    codes8, heads4 = load_tariff()
    A, B = load_rows(stem, model_a), load_rows(stem, model_b)
    with pymupdf.open(pdf) as d:
        embedded = re.sub(r"\s+", "", " ".join(p.get_text() for p in d))
    byB = {(r["page"], r["idx"]): r for r in B}
    out, prev = [], 0
    for r in A:
        issues = []
        b = byB.get((r["page"], r["idx"]))
        s = (r["s_no"] or "").strip()
        if s.isdigit():
            n = int(s)
            if n != prev + 1:
                issues.append(f"s_no jump {prev}->{n}")
            prev = n
        else:
            issues.append(f"s_no not a number: {s!r}")
        code, rate = (r["pct_code"] or "").strip(), (r["rate"] or "").strip()
        if CODE8.match(code):
            if code not in codes8:
                issues.append("8-digit code not in tariff FY2026-27")
        elif CODE4.match(code):
            if code not in heads4:
                issues.append("4-digit heading not in tariff FY2026-27")
        else:
            issues.append(f"bad code format {code!r}")
        if not RATE.match(rate):
            issues.append(f"rate not one-decimal: {rate!r}")
        elif float(rate) > max_rate:
            issues.append(f"rate out of range: {rate}")
        if "?" in code or "?" in rate:
            issues.append("unreadable character marked by model")
        if code and re.sub(r"\s+", "", code) not in embedded:
            issues.append("code not found in embedded OCR text (soft check)")
        agree = bool(b) and (b["pct_code"].strip(), b["rate"].strip(), (b["s_no"] or "").strip()) == (code, rate, s)
        desc_sim = difflib.SequenceMatcher(None, norm(r["description"]), norm(b["description"])).ratio() if b else 0
        if not agree:
            issues.append(f"models disagree: {model_a}=({code},{rate}) {model_b}=({b['pct_code'] if b else None},{b['rate'] if b else None})")
        out.append({**r, "model_b_description_similarity": round(desc_sim, 3), "agree": agree,
                    "issues": issues, "status": "accepted" if not issues else "review"})
    summary = {"rows_a": len(A), "rows_b": len(B), "last_s_no": prev,
               "accepted": sum(o["status"] == "accepted" for o in out),
               "review": sum(o["status"] == "review" for o in out),
               "source_file": pdf.name}
    return out, summary


if __name__ == "__main__":
    stem, ma, mb, name = sys.argv[1:5]
    rows, summ = validate(stem, ma, mb)
    (OUT / f"{name}.json").write_text(json.dumps({"summary": summ, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(OUT / f"{name}_failures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "s_no", "pct_code", "rate", "issues"])
        for r in rows:
            if r["issues"]:
                w.writerow([r["page"], r["s_no"], r["pct_code"], r["rate"], " | ".join(r["issues"])])
    print(summ)
