"""A3: merge the component extractions into two store-ready files (exact columns of the B1 loader contract).

Inputs (data/processed): a3_st_*.csv, a3_sro_rules.csv, a3_it_*.csv.  Outputs:
  a3_sales_tax_rules.csv/json   -> table sales_tax_rules
  a3_income_tax_rules.csv/json  -> table income_tax_rules
  a3_customs_concessions.csv    (sugar and Afghanistan early-harvest concessions; out of v1 scope, not loaded)
  a3_build_report.json          counts and rows dropped (with the reason)
Nothing is invented here: only column mapping, and a downgrade to 'conditional' (with an issue note) when a rate
does not satisfy the store's CHECK constraints. Rows that end before 2025-07-01 are left out (scope rule).
Usage: python -m src.ingest.a3_build_rules
"""
import csv
import json
from collections import Counter
from pathlib import Path

P = Path("data/processed")
STORE_COLS_ST = ["instrument", "clause", "tax_kind", "importer_status", "charged_on", "condition_text", "code_norm", "match_level",
                 "except_codes", "unparsed_except_text", "rule_group", "rate_kind", "rate_pct", "rate_specific_amount",
                 "rate_specific_unit", "rate_raw", "status", "valid_from", "valid_to", "source_file", "page"]
STORE_COLS_IT = [c for c in STORE_COLS_ST if c != "tax_kind"]
STORE_COLS_IT.insert(3, "importer_category")
ST_FILES = ["a3_st_sixth_schedule", "a3_st_sixth_table3", "a3_st_third_schedule", "a3_st_eighth_schedule", "a3_st_fifth_schedule",
            "a3_st_ninth_schedule", "a3_st_twelfth_schedule"]
IT_FILES = ["a3_it_twelfth_schedule", "a3_it_s148_rates", "a3_it_s148_special_rules"]
# Schedule rows that name goods only by description (no PCT code). The extractors marked them match_level 'all'
# (empty prefix = every code). In the store that would make a Sixth Schedule exemption for, say, "Urine drainage bags"
# match EVERY code, so they are stored as 'unmapped' (never matched by code, still searchable by text). Not a rate change.
NO_CODE_GROUPS = {"ST-3RD", "ST-6TH-T1", "ST-6TH-T3", "ST-8TH-T1", "ST-12TH", "ST-12TH-EXCL", "ST-12TH-PROV"}
ACT_NAME = {"ST": "Sales Tax Act 1990", "IT": "Income Tax Ordinance 2001"}


def read(name):
    f = P / f"{name}.csv"
    return list(csv.DictReader(open(f, encoding="utf-8"))) if f.exists() else []


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fix_rate(r, notes):
    k = r["rate_kind"]
    pct, amt, unit, raw = num(r.get("rate_pct")), num(r.get("rate_specific_amount")), (r.get("rate_specific_unit") or "").strip(), (r.get("rate_raw") or "").strip()
    if k == "percent" and (pct is None or not 0 <= pct <= 100):
        notes.append("store: percent rate missing/out of range, stored as conditional")
        k = "conditional"
    if k == "specific" and (amt is None or amt < 0 or not unit):
        notes.append("store: specific rate missing amount/unit, stored as conditional")
        k = "conditional"
    if k == "conditional" and not raw:
        raw = (r.get("description") or "see source")[:200]
        notes.append("store: conditional rate had no rate_raw; filled from description")
    r["rate_kind"], r["rate_raw"] = k, raw
    r["rate_pct"] = pct if k == "percent" else ""
    r["rate_specific_amount"] = amt if k == "specific" else ""
    r["rate_specific_unit"] = unit if k == "specific" else ""
    return r


def to_store(r, tax, dropped, src):
    if r.get("in_scope") == "0":
        dropped.append((src, r.get("rule_id"), "in_scope=0 (expired before scope)"))
        return None
    if r["valid_to"] < "2025-07-01":
        dropped.append((src, r.get("rule_id"), "ends before 2025-07-01"))
        return None
    notes = []
    r = fix_rate(dict(r), notes)
    if tax == "ST":
        tk = (r.get("tax_kind") or "sales_tax")
        r["tax_kind"] = tk if tk in ("sales_tax", "further_tax", "extra_tax", "withholding") else "sales_tax"
        st = (r.get("importer_status") or "any")
        r["importer_status"] = st if st in ("any", "registered", "unregistered") else "any"
    else:
        r["importer_status"] = r.get("importer_status") or "any"
        r["importer_category"] = r.get("importer_category") or ""
    r["instrument"] = r.get("instrument") or f"{ACT_NAME[tax]}, {r['schedule_or_section']}"
    if not r.get("rule_group"):
        r["rule_group"] = src
    info = []
    if r["match_level"] == "all" and r["rule_group"] in NO_CODE_GROUPS:
        r["match_level"] = "unmapped"
        info.append("store: row names goods by description only; extractor said match_level=all (every code), stored as unmapped so it cannot match unrelated codes")
    if r["match_level"] == "unmapped":
        r["code_norm"] = ""
    r["except_codes"] = r.get("except_codes") or "[]"
    r["unparsed_except_text"] = r.get("unparsed_except_text") or 0
    if tax == "ST" and not r["rule_group"].startswith("ST-SRO297-T2"):
        txt = ((r.get("description") or "") + " " + (r.get("condition_text") or "")).lower()
        if any(k in txt for k in ("locally manufactured", "local suppl", "if supplied locally", "supply of locally")):
            r["condition_text"] = "[LOCAL SUPPLY WORDING, probably not an import rule: lead's keyword flag, a human must confirm] " + (r.get("condition_text") or "")
            notes.append("flag: local-supply wording in description/condition")
    iss = "; ".join(x for x in [r.get("issues", "")] + notes + info if x)
    if notes:
        r["status"] = "needs_review"
    r["status"] = r["status"] if r["status"] in ("accepted", "needs_review", "verified") else "needs_review"
    r["_issues"] = iss
    r["_rule_id"] = r.get("rule_id", "")
    return r


def build(tax, files, cols, name, dropped):
    out, extra = [], []
    for f in files:
        for r in read(f):
            if r.get("tax") not in (tax, None, ""):
                if r.get("tax") == "CUSTOMS":
                    extra.append(r)
                continue
            if f == "a3_sro_rules":
                pass
            s = to_store(r, tax, dropped, f)
            if s:
                out.append(s)
    return out, extra


def write(name, rows, cols):
    keep = [{c: r.get(c, "") for c in cols} for r in rows]
    with open(P / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(keep)
    (P / f"{name}.json").write_text(json.dumps({"meta": {"rows": len(keep), "columns": "B1 loader contract"}, "rows": keep}, indent=1, ensure_ascii=False), encoding="utf-8")


def main():
    dropped = []
    st, it = [], []
    for f in ST_FILES:
        for r in read(f):
            s = to_store(r, "ST", dropped, f)
            if s:
                st.append(s)
    sro = read("a3_sro_rules")
    concessions = []
    for r in sro:
        if r["tax"] == "CUSTOMS":
            concessions.append(r)
        elif r["tax"] == "ST":
            s = to_store(r, "ST", dropped, "a3_sro_rules")
            if s:
                st.append(s)
        elif r["tax"] == "IT":
            dropped.append(("a3_sro_rules", r["rule_id"], "IT sugar clause (9AD): the a3_it_s148_special_rules rows cover it"))
    for f in IT_FILES:
        for r in read(f):
            s = to_store(r, "IT", dropped, f)
            if s:
                it.append(s)
    write("a3_sales_tax_rules", st, STORE_COLS_ST)
    write("a3_income_tax_rules", it, STORE_COLS_IT)
    # a sidecar with the issues and source ids, so nothing the extractors flagged is lost
    for name, rows in (("a3_sales_tax_rules", st), ("a3_income_tax_rules", it)):
        with open(P / f"{name}_issues.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["row_no", "source_rule_id", "clause", "source_file", "page", "status", "issues"])
            for i, r in enumerate(rows, 1):
                if r["_issues"] or r["status"] != "accepted":
                    w.writerow([i, r["_rule_id"], r["clause"], r["source_file"], r["page"], r["status"], r["_issues"]])
    if concessions:
        cols = list(concessions[0].keys())
        with open(P / "a3_customs_concessions.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(concessions)
    rep = {"sales_tax_rows": len(st), "income_tax_rows": len(it), "concession_rows": len(concessions),
           "st_status": Counter(r["status"] for r in st), "it_status": Counter(r["status"] for r in it),
           "st_by_group": Counter(r["rule_group"] for r in st), "it_by_group": Counter(r["rule_group"] for r in it),
           "dropped": dropped}
    (P / "a3_build_report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=dict), encoding="utf-8")
    print({k: v for k, v in rep.items() if k != "dropped"})
    print("dropped", len(dropped))


if __name__ == "__main__":
    main()
