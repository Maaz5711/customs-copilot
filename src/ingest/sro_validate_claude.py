"""A2 validators for SRO tables transcribed by Claude from page images.

Reads data/processed/sro_claude/<stem>/pNNN.json and checks every row. Nothing is fixed:
rows with issues get status "review" and appear in <name>_failures.csv with the page,
so the owner can look at the page image. A row is "accepted" only if it has no issues.

Checks: S.No continuity, code format, code exists in the matching tariff year (also
codes named in "except" clauses), rate format and range, the one-decimal rule (when the
SRO prints one decimal everywhere), rare rate values, code present in the PDF's embedded
OCR text (soft), and agreement with any Gemini read of the same page (second tool).

Usage: python -m src.ingest.sro_validate_claude <stem> <tariff_fy> <out_name> <one_decimal 0|1>
"""
import collections
import csv
import json
import re
import sys
from pathlib import Path

import pymupdf

OUT = Path("data/processed")
CODE8 = re.compile(r"\b\d{4}\.\d{4}\b")
CODE8_ONLY = re.compile(r"^\d{4}\.\d{4}$")
CODE4_ONLY = re.compile(r"^\d{2}\.\d{2}$")
NUM = re.compile(r"^\d+(?:\.\d+)?$")
ONE_DEC = re.compile(r"^\d{1,3}\.\d$")
SPECIFIC = re.compile(r"^Rs\.?\s*([\d,]+(?:\.\d+)?)\s*/\s*(.+)$", re.I)
GEMINI = ["gemini-3.5-flash", "gemini-3-flash-preview"]


def tariff_codes(fy):
    t = json.loads((OUT / f"tariff_{fy}.json").read_text(encoding="utf-8"))
    return {r["code"] for r in t["rows"]}, {h["heading"] for h in t["headings"]}


def load_claude(stem):
    rows, uncertain = [], []
    for f in sorted((OUT / "sro_claude" / stem).glob("p*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for u in d.get("uncertain", []):
            uncertain.append({**u, "page": d["page"]})
        for i, r in enumerate(d.get("rows", [])):
            rows.append({**r, "page": d["page"], "idx": i})
    return rows, uncertain


def merge_continuations(rows):
    """A row with no s_no, code and rate continues the previous row's description."""
    out = []
    for r in rows:
        if not (r.get("s_no") or "").strip() and not (r.get("pct_code") or "").strip() and not (r.get("rate") or "").strip():
            if out:
                out[-1]["description"] = (out[-1]["description"] + " " + r["description"]).strip()
                out[-1].setdefault("continued_on_page", r["page"])
            continue
        out.append(dict(r))
    return out


def gemini_rates(stem):
    res = {}
    for m in GEMINI:
        for f in (OUT / "sro_vision" / stem / m).glob("p*.json"):
            d = json.loads(f.read_text(encoding="utf-8"))
            for r in d.get("rows", []):
                if (r.get("s_no") or "").strip():
                    res.setdefault(m, {})[r["s_no"].strip()] = (r["pct_code"].strip(), r["rate"].strip())
    return res


def validate(stem, fy, one_decimal):
    pdf = next(Path("data/raw").glob(f"*{stem}*.pdf"))
    codes8, heads4 = tariff_codes(fy)
    raw, uncertain = load_claude(stem)
    rows = merge_continuations(raw)
    with pymupdf.open(pdf) as d:
        embedded = re.sub(r"\s+", "", " ".join(p.get_text() for p in d))
    gem = gemini_rates(stem)
    rate_counts = collections.Counter((r.get("rate") or "").strip() for r in rows)
    unc_by = collections.defaultdict(list)
    for u in uncertain:
        unc_by[(u["page"], str(u.get("row_s_no", "")))].append(u)
    prev, out, gem_agree, gem_dis = 0, [], 0, 0
    for r in rows:
        issues = []
        s = (r.get("s_no") or "").strip().rstrip(".")  # some pages print "444."
        r["s_no"] = s
        soft = []
        if s.isdigit():
            n = int(s)
            if n != prev + 1:
                issues.append(f"s_no jump {prev}->{n}")
            prev = n
        else:
            issues.append(f"s_no not a number: {s!r}")
        cell = (r.get("pct_code") or "").strip()
        parts = [p for p in re.split(r"[,\s]+", cell) if p]
        kind = "codes"
        if not parts or not all(CODE8_ONLY.match(p) or CODE4_ONLY.match(p) for p in parts):
            kind = "text"
            if cell.lower().startswith("respective"):
                issues.append("pct_code is 'Respective headings' (rule applies to headings named elsewhere): needs manual mapping")
            else:
                issues.append(f"bad code cell {cell!r}")
        else:
            for p in parts:
                if CODE8_ONLY.match(p) and p not in codes8:
                    issues.append(f"code {p} not in tariff {fy}")
                if CODE4_ONLY.match(p) and p not in heads4:
                    issues.append(f"heading {p} not in tariff {fy}")
        for c in CODE8.findall(r.get("description") or ""):
            if c not in codes8:
                issues.append(f"except-clause code {c} not in tariff {fy}")
        rate = (r.get("rate") or "").strip()
        if NUM.match(rate):
            v = float(rate)
            if not 0 < v <= 100:
                issues.append(f"rate out of range {rate}")
            if one_decimal and not ONE_DEC.match(rate):
                issues.append(f"rate {rate!r} breaks the one-decimal rule (possible dropped decimal)")
            if rate_counts[rate] <= 2:
                issues.append(f"rare rate value {rate!r} (appears {rate_counts[rate]}x): confirm on page")
        elif SPECIFIC.match(rate):
            m = SPECIFIC.match(rate)
            r["rate_specific"] = {"amount": float(m.group(1).replace(",", "")), "unit": m.group(2).strip()}
            soft.append(f"specific rate {rate!r} parsed as {r['rate_specific']}")
        else:
            issues.append(f"non-numeric rate {rate!r}")
        for p in parts if kind == "codes" else []:
            if p not in embedded and re.sub(r"\.", "", p) not in embedded:
                soft.append(f"code {p} not in embedded OCR text")
        for m, g in gem.items():
            if s in g and len(parts) == 1:
                if g[s] == (cell, rate):
                    gem_agree += 1
                    continue
                gem_dis += 1
                issues.append(f"{m} read ({g[s][0]}, {g[s][1]}) vs Claude ({cell}, {rate})")
        for u in unc_by.get((r["page"], s), []):
            issues.append(f"reader flagged uncertain: {u.get('field')} read_as {u.get('read_as')!r} alt {u.get('alternative')!r}: {u.get('why')}")
        out.append({**r, "soft_notes": soft, "issues": issues, "status": "accepted" if not issues else "review"})
    gem_pages = {m: len(g) for m, g in gem.items()}
    summary = {"source_file": pdf.name, "rows": len(out), "last_s_no": prev,
               "accepted": sum(o["status"] == "accepted" for o in out),
               "review": sum(o["status"] == "review" for o in out),
               "uncertain_flags_from_reader": len(uncertain), "gemini_agreements": gem_agree, "gemini_disagreements": gem_dis, "gemini_rows_compared": gem_pages,
               "rate_histogram_top": rate_counts.most_common(12)}
    return out, summary


if __name__ == "__main__":
    stem, fy, name, one_dec = sys.argv[1:5]
    rows, summ = validate(stem, fy, one_dec == "1")
    (OUT / f"{name}.json").write_text(json.dumps({"summary": summ, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    img = lambda pg: f"data/processed/page_images/{stem.replace(' ', '_').replace('(', '').replace(')', '')}/p{pg:03d}.png"
    with open(OUT / f"{name}_failures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "page_image", "s_no", "pct_code", "rate", "issues", "owner_decision", "correct_value"])
        for r in rows:
            if r["issues"]:
                w.writerow([r["page"], img(r["page"]), r["s_no"], r["pct_code"], r["rate"], " | ".join(r["issues"]), "", ""])
    import random
    ok = [r for r in rows if not r["issues"]]
    with open(OUT / f"spotcheck_{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "page_image", "s_no", "pct_code", "rate", "correct? (Y/N)", "true_value_if_N"])
        for r in sorted(random.Random(2026).sample(ok, max(1, len(rows) // 10)), key=lambda r: int(r["s_no"])):
            w.writerow([r["page"], img(r["page"]), r["s_no"], r["pct_code"], r["rate"], "", ""])
    print(json.dumps(summ, indent=1))
