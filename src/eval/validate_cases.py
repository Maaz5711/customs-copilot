"""Validate the ground-truth evaluation cases in data/ground_truth/ (C2-prep).

What it checks
- every expected_code exists in the tariff of the right fiscal year (chosen from as_of_date):
  8-digit codes must be exact tariff lines, 6-digit and 4-digit codes must be a prefix of at least one line
  (4-digit chapter 99 entries are looked up in the tariff's special-regime list);
- required columns, unique ids, date and fiscal-year consistency, level notes that match the code length;
- synthetic cases: verified must be false, the 'unverified' label must be present, the answer must not leak into the
  description, non-answer rows carry no code;
- the out-of-scope file: rows whose reason says the printed code is missing must really be missing from the tariff;
- the owner review sample: 10 real and 10 synthetic rows that exist in the case files.

Run:  python -m src.eval.validate_cases          (prints counts and problems, exit code 1 if any problem)
      python -m src.eval.validate_cases --store  (also cross-checks 8-digit answers with the lookup_code tool)

No LLM is used. Tariffs are read from data/processed/tariff_2025_26.json and tariff_2026_27.json (never from data/raw).
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GT_DIR = ROOT / "data" / "ground_truth"
PROC = ROOT / "data" / "processed"

# fiscal year -> (first day, last day, tariff json)
COVERAGE = {
    "FY2025-26": ("2025-07-01", "2026-06-30", "tariff_2025_26.json"),
    "FY2026-27": ("2026-07-01", "2027-06-30", "tariff_2026_27.json"),
}

REAL_FILE = "cases_real.csv"
OOS_FILE = "cases_real_outofscope.csv"
SYN_FILE = "cases_synthetic.csv"
SAMPLE_FILE = "owner_review_sample.csv"

REAL_COLS = ["id", "description", "expected_code", "expected_level_note", "as_of_date", "fiscal_year", "source", "source_url",
             "source_ref", "page_or_section", "notes"]
SYN_COLS = ["id", "description", "as_of_date", "fiscal_year", "expected_behavior", "expected_code", "expected_level_note",
            "alt_acceptable_codes", "candidate_headings", "hardness_tags", "basis", "tariff_page", "verified", "label", "notes"]
SAMPLE_COLS = ["sample_no", "kind", "case_id", "description", "as_of_date", "expected_code", "owner_agrees_Y_or_N", "owner_correction"]

SOURCES = {"ruling", "tribunal", "court", "other"}
BEHAVIORS = {"answer", "not_sure_or_clarify", "refuse"}
LABEL_TEXT = "synthetic, unverified, written by Claude, must be confirmed by a qualified person"
CODE_RE = re.compile(r"^\d{4}(\.\d{2}(\d{2})?)?$")
MAX_REAL_WORDS = 30


# ----------------------------------------------------------------------------- loading
def load_tariffs(proc_dir: Path | None = None) -> dict:
    """{fy: {"codes": set of 8-digit strings, "page": {code: page}, "desc": {code: text}, "special": {code: set of pages}}}."""
    import json

    proc_dir = proc_dir or PROC
    out = {}
    for fy, (_, _, fname) in COVERAGE.items():
        d = json.load(open(proc_dir / fname, encoding="utf-8"))
        codes, page, desc = set(), {}, {}
        for r in d["rows"]:
            c = r["code"].replace(".", "")
            codes.add(c)
            page.setdefault(c, r["page"])
            desc.setdefault(c, r["description"])
        special = {}
        for s in d.get("special", []):
            special.setdefault(s["code"], set()).add(s["page"])
        out[fy] = {"codes": codes, "page": page, "desc": desc, "special": special}
    return out


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def fy_for_date(iso: str) -> str | None:
    for fy, (lo, hi, _) in COVERAGE.items():
        if lo <= iso <= hi:
            return fy
    return None


def digits(code: str) -> str:
    return (code or "").replace(".", "").strip()


def code_exists(code: str, fy: str, tariffs: dict) -> bool:
    """8-digit: exact tariff line. 6- or 4-digit: prefix of a tariff line, or (4-digit) a chapter 99 special entry."""
    d = digits(code)
    t = tariffs[fy]
    if len(d) == 8:
        return d in t["codes"]
    if len(d) in (4, 6):
        return any(c.startswith(d) for c in t["codes"]) or (len(d) == 4 and d in t["special"])
    return False


def _valid_iso(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except (TypeError, ValueError):
        return False


def _missing_cols(rows: list[dict], needed: list[str]) -> list[str]:
    have = set(rows[0].keys()) if rows else set()
    return [c for c in needed if c not in have]


def _level_ok(code: str, note: str) -> bool:
    n = len(digits(code))
    return (note or "").startswith({8: "8-digit", 6: "6-digit", 4: "4-digit"}.get(n, "?"))


# ----------------------------------------------------------------------------- validators (return list of problem strings)
def validate_real(rows: list[dict], tariffs: dict) -> list[str]:
    p: list[str] = []
    miss = _missing_cols(rows, REAL_COLS)
    if miss:
        return [f"{REAL_FILE}: missing columns {miss}"]
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        p.append(f"{REAL_FILE}: duplicate ids")
    for r in rows:
        i = r["id"]
        if not r["description"].strip():
            p.append(f"{i}: empty description")
        elif len(r["description"].split()) > MAX_REAL_WORDS:
            p.append(f"{i}: description longer than {MAX_REAL_WORDS} words")
        if not CODE_RE.match(r["expected_code"] or ""):
            p.append(f"{i}: bad expected_code format {r['expected_code']!r}")
            continue
        if not _level_ok(r["expected_code"], r["expected_level_note"]):
            p.append(f"{i}: expected_level_note does not match the digits of {r['expected_code']}")
        if not _valid_iso(r["as_of_date"]):
            p.append(f"{i}: bad as_of_date {r['as_of_date']!r}")
            continue
        fy = fy_for_date(r["as_of_date"])
        if fy is None:
            p.append(f"{i}: as_of_date {r['as_of_date']} outside FY2025-26 and FY2026-27")
            continue
        if r["fiscal_year"] != fy:
            p.append(f"{i}: fiscal_year {r['fiscal_year']} does not match as_of_date ({fy})")
        if not code_exists(r["expected_code"], fy, tariffs):
            p.append(f"{i}: {r['expected_code']} is not in the {fy} tariff")
        if r["source"] not in SOURCES:
            p.append(f"{i}: source {r['source']!r} not in {sorted(SOURCES)}")
        if not re.match(r"^https?://", r["source_url"] or ""):
            p.append(f"{i}: source_url missing or not a URL")
        if not (r["source_ref"] or "").strip():
            p.append(f"{i}: source_ref empty")
        if not (r["page_or_section"] or "").strip():
            p.append(f"{i}: page_or_section empty")
        other = "FY2026-27" if fy == "FY2025-26" else "FY2025-26"
        if "code_also_in_other_fy" in r:
            want = "true" if code_exists(r["expected_code"], other, tariffs) else "false"
            if r["code_also_in_other_fy"] != want:
                p.append(f"{i}: code_also_in_other_fy is {r['code_also_in_other_fy']!r}, expected {want!r}")
    return p


def validate_outofscope(rows: list[dict], tariffs: dict) -> list[str]:
    p: list[str] = []
    miss = _missing_cols(rows, REAL_COLS + ["reason"])
    if miss:
        return [f"{OOS_FILE}: missing columns {miss}"]
    for r in rows:
        i = r["id"]
        if not (r["reason"] or "").strip():
            p.append(f"{i}: reason empty")
        fy = fy_for_date(r["as_of_date"]) if _valid_iso(r["as_of_date"]) else None
        if fy is None:
            p.append(f"{i}: as_of_date outside the two fiscal years")
            continue
        if r["reason"].startswith(("Printed code", "Auto check")) and code_exists(r["expected_code"], fy, tariffs):
            p.append(f"{i}: reason says {r['expected_code']} is missing from the {fy} tariff, but it exists")
        if not re.match(r"^https?://", r["source_url"] or ""):
            p.append(f"{i}: source_url missing")
    return p


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^[\s\-]+", "", (text or "").lower())).strip()


def validate_synthetic(rows: list[dict], tariffs: dict) -> list[str]:
    p: list[str] = []
    miss = _missing_cols(rows, SYN_COLS)
    if miss:
        return [f"{SYN_FILE}: missing columns {miss}"]
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        p.append(f"{SYN_FILE}: duplicate ids")
    for r in rows:
        i = r["id"]
        if r["verified"].strip().lower() != "false":
            p.append(f"{i}: verified must be false for synthetic cases")
        if LABEL_TEXT not in (r["label"] or ""):
            p.append(f"{i}: label must contain {LABEL_TEXT!r}")
        if r["expected_behavior"] not in BEHAVIORS:
            p.append(f"{i}: expected_behavior {r['expected_behavior']!r} not in {sorted(BEHAVIORS)}")
            continue
        if not r["description"].strip():
            p.append(f"{i}: empty description")
        if not (r["basis"] or "").strip():
            p.append(f"{i}: basis empty")
        if not _valid_iso(r["as_of_date"]):
            p.append(f"{i}: bad as_of_date")
            continue
        fy = fy_for_date(r["as_of_date"])
        if r["expected_behavior"] != "answer":
            if r["expected_code"].strip():
                p.append(f"{i}: non-answer rows must not carry an expected_code")
            if r["expected_behavior"] == "not_sure_or_clarify" and not r["candidate_headings"].strip():
                p.append(f"{i}: not_sure_or_clarify rows need candidate_headings")
            if fy is not None and r["fiscal_year"] != fy:
                p.append(f"{i}: fiscal_year does not match as_of_date")
            if fy is None and r["fiscal_year"] != "outside coverage":
                p.append(f"{i}: out-of-range date must have fiscal_year 'outside coverage'")
            continue
        # answer rows
        if not CODE_RE.match(r["expected_code"] or ""):
            p.append(f"{i}: bad expected_code format {r['expected_code']!r}")
            continue
        if fy is None:
            p.append(f"{i}: answer rows need an as_of_date inside the two fiscal years")
            continue
        if r["fiscal_year"] != fy:
            p.append(f"{i}: fiscal_year {r['fiscal_year']} does not match as_of_date ({fy})")
        if not _level_ok(r["expected_code"], r["expected_level_note"]):
            p.append(f"{i}: expected_level_note does not match the digits of {r['expected_code']}")
        if not code_exists(r["expected_code"], fy, tariffs):
            p.append(f"{i}: {r['expected_code']} is not in the {fy} tariff")
        for alt in [a.strip() for a in (r["alt_acceptable_codes"] or "").replace(",", ";").split(";") if a.strip()]:
            if not code_exists(alt, fy, tariffs):
                p.append(f"{i}: alt code {alt} is not in the {fy} tariff")
        d = digits(r["expected_code"])
        t = tariffs[fy]
        # tariff page must match the tariff data
        if r["tariff_page"].strip():
            pages = {t["page"].get(d)} if len(d) == 8 else set(t["special"].get(d, set()))
            if int(r["tariff_page"]) not in pages:
                p.append(f"{i}: tariff_page {r['tariff_page']} does not match the tariff page for {r['expected_code']}")
        else:
            p.append(f"{i}: answer rows need a tariff_page")
        # answer must not leak into the description
        text = r["description"].lower()
        if r["expected_code"].lower() in text or (len(d) == 8 and d in re.sub(r"[^0-9]", "", text)):
            p.append(f"{i}: description contains the expected code")
        if len(d) == 8:
            td = _norm(t["desc"].get(d, ""))
            if len(td) >= 25 and td in _norm(r["description"]):
                p.append(f"{i}: description copies the tariff line text")
    return p


def validate_sample(rows: list[dict], real_ids: set, syn_ids: set) -> list[str]:
    p: list[str] = []
    miss = _missing_cols(rows, SAMPLE_COLS)
    if miss:
        return [f"{SAMPLE_FILE}: missing columns {miss}"]
    kinds = Counter(r["kind"] for r in rows)
    if kinds != Counter({"real": 10, "synthetic": 10}):
        p.append(f"{SAMPLE_FILE}: expected 10 real + 10 synthetic rows, got {dict(kinds)}")
    for r in rows:
        pool = real_ids if r["kind"] == "real" else syn_ids
        if r["case_id"] not in pool:
            p.append(f"{SAMPLE_FILE}: case_id {r['case_id']} not found in the {r['kind']} file")
    return p


# ----------------------------------------------------------------------------- driver
def validate_all(gt_dir: Path | None = None, proc_dir: Path | None = None) -> tuple[list[str], dict]:
    gt_dir = gt_dir or GT_DIR
    tariffs = load_tariffs(proc_dir)
    real = read_csv(gt_dir / REAL_FILE)
    oos = read_csv(gt_dir / OOS_FILE)
    syn = read_csv(gt_dir / SYN_FILE)
    sample = read_csv(gt_dir / SAMPLE_FILE)
    problems = []
    problems += validate_real(real, tariffs)
    problems += validate_outofscope(oos, tariffs)
    problems += validate_synthetic(syn, tariffs)
    problems += validate_sample(sample, {r["id"] for r in real}, {r["id"] for r in syn})
    stats = {
        "real": len(real),
        "real_out_of_scope": len(oos),
        "synthetic": len(syn),
        "owner_review_sample": len(sample),
        "real_by_ruling_kind": dict(Counter(r.get("ruling_kind", "") for r in real)),
        "real_by_source": dict(Counter(r["source"] for r in real)),
        "real_by_fiscal_year": dict(Counter(r["fiscal_year"] for r in real)),
        "real_by_code_level": dict(Counter(f"{len(digits(r['expected_code']))}-digit" for r in real)),
        "synthetic_by_behavior": dict(Counter(r["expected_behavior"] for r in syn)),
        "synthetic_by_fiscal_year": dict(Counter(r["fiscal_year"] for r in syn)),
    }
    return problems, stats


def cross_check_store(gt_dir: Path | None = None) -> list[str]:
    """Optional: ask the exact lookup_code tool (dated store) about every 8-digit answer. Needs data/processed/legal_store.sqlite."""
    from src.tools import lookup_code

    gt_dir = gt_dir or GT_DIR
    p = []
    for fname, code_col in ((REAL_FILE, "expected_code"), (SYN_FILE, "expected_code")):
        for r in read_csv(gt_dir / fname):
            c = r[code_col]
            if r.get("expected_behavior", "answer") != "answer" or len(digits(c)) != 8:
                continue
            res = lookup_code(c, r["as_of_date"])
            if res.get("status") != "found":
                p.append(f"{r['id']}: lookup_code({c}, {r['as_of_date']}) -> {res.get('status')}")
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store", action="store_true", help="also cross-check 8-digit answers with lookup_code")
    args = ap.parse_args(argv)
    problems, stats = validate_all()
    if args.store:
        problems += cross_check_store()
    print("Ground-truth cases (sample sizes; the set is small and partly synthetic):")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for x in problems:
            print("  -", x)
        return 1
    print("\nAll checks passed: every expected_code exists in the tariff of its fiscal year.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
