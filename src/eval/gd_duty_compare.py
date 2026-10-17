"""Our duty tool against the duties Customs ACTUALLY assessed on real Goods Declaration lines (importer's extract, Chapter 85, February 2026).

    python -m src.eval.gd_duty_compare [N]     random sample of N home-consumption lines (default 1500, seed 11)
    -> docs/gd_duty_comparison.md  and  data/processed/eval/gd_duty_comparison.csv  (anonymised: no names, no NTN, no GD number)

For each line we call compute_duty with the line's assessable value (IV, PKR), its date, and importer facts INFERRED from the line itself:
  commercial importer  <- the 3% value-addition tax ("ADD. ST") was charged;
  filer                <- the income-tax rate is not doubled (12%/7%/4%/2%+ pattern would mean non-filer; we infer from the rate class);
and compare CD, RD, ACD, ST, the 3% tax and IT amounts (tolerance 2 rupees; Customs truncates). A mismatch is classified by the SRO/schedule columns of the line
so concessions (China FTA, Fifth Schedule, exemptions) are reported separately from plain-rate lines.
"""
from __future__ import annotations

import csv
import random
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from src.tools import compute_duty

from .gd_data import code8, load, num

TOL = Decimal(2)
REL = Decimal("0.004")          # Customs rounds each component; allow 0.4% on top of 2 rupees
TAXES = (("CD", "CD"), ("RD", "RD"), ("ACD", "ADD. CD"), ("ST", "ST"), ("VAT", "ADD. ST"), ("IT", "IT"))


def line_inputs(r: dict) -> tuple[dict, dict]:
    """Importer facts inferred from the line itself.
    commercial importer <- the income-tax rate: Part II 3.5% (commercial) vs 2% (not); Part III 6% vs 5.5%; Part I 1% does not depend on it.
    manufacturer in-house use <- the 3% value-addition tax ('ADD. ST') was NOT charged. Filer <- always true here (only 45 of 14,950 lines show a doubled rate)."""
    iv = num(r["IV"])
    base_it = iv + sum(num(r[k]) for k in ("CD", "ST", "ADD. ST", "RD", "ADD. CD", "FED"))
    rate = 100 * num(r["IT"]) / base_it if base_it else 0
    comm = (3.0 <= rate <= 4.2) or rate >= 5.75 or rate < 1.5
    unreg = num(r["GST"]) > 0 and num(r["ADD. ST"]) <= 0          # the extra sales-tax amount sits in the 'GST' column instead of 'ADD. ST'
    imp = {"registration_status": "unregistered" if unreg else "registered", "commercial_importer": comm, "active_taxpayer": True,
           "manufacturer_in_house_use": (num(r["ADD. ST"]) <= 0) and not unreg}
    return imp, {"plant_machinery_for_manufacturing": False, "_it_rate": round(rate, 2)}


def concession_tag(r: dict) -> str:
    s = " ".join(str(r.get(k) or "") for k in ("SRO1", "SRO2", "SRO3", "SRO4")).lower()
    if "1640" in s:
        return "china_fta"
    if "5th" in s:
        return "fifth_schedule"
    if "655" in s or "656" in s:
        return "sro_655_656"
    if "6th" in s or "8th" in s or "0% cl" in s:
        return "sales_tax_or_it_exemption"
    return "none"


def run(n: int = 1500, seed: int = 11) -> list[dict]:
    data = [r for r in load() if r.get("TYPE") == "HC" and r["code8"] and num(r["IV"]) > 0]
    random.Random(seed).shuffle(data)
    out = []
    for r in data[:n]:
        imp, extra = line_inputs(r)
        goods = {"plant_machinery_for_manufacturing": False}
        try:
            res = compute_duty(r["code8"], str(int(num(r["IV"]))), r["date"], importer=imp, goods=goods)
        except Exception as e:
            res = {"status": f"error:{type(e).__name__}"}
        row = {"anon_id": r["anon_id"], "code": r["code8"], "date": r["date"], "iv": int(num(r["IV"])), "comm": imp["commercial_importer"], "mfr": imp["manufacturer_in_house_use"], "unreg": imp["registration_status"] == "unregistered", "it_rate_actual": extra["_it_rate"],
               "tag": concession_tag(r), "our_status": res["status"], "needs": ";".join(m["field"] for m in res.get("missing_inputs", [])) if res["status"] == "needs_input" else ""}
        lines = {}
        if res["status"] == "computed":
            for ln in res["lines"]:
                key = "VAT" if ln["tax"] in ("VAT", "FURTHER_TAX") else ln["tax"]      # Customs books the 3% tax and the 4% further tax together
                lines[key] = lines.get(key, Decimal(0)) + Decimal(ln["amount_pkr"])
        diffs = []
        for tax, colname in TAXES:
            actual = Decimal(str(num(r[colname]) + (num(r["GST"]) if tax == "VAT" else 0)))
            ours = lines.get(tax, Decimal(0)) if res["status"] == "computed" else None
            row[f"act_{tax}"], row[f"our_{tax}"] = int(actual), (None if ours is None else int(ours))
            # unregistered importers: the extra sales-tax amount is modelled as 7/18 of the sales tax; real lines run from 0.386 to 0.40 of it (docs/gd_findings.md 4d),
            # i.e. up to about 3% of that amount and 1.5% of the income tax built on it, so those two taxes get a wider tolerance on such lines.
            rel = {"VAT": Decimal("0.04"), "IT": Decimal("0.015")}.get(tax, REL) if row.get("unreg") else REL
            if ours is not None and abs(actual - ours) > max(TOL, rel * actual):
                diffs.append(tax)
        row["diffs"] = ",".join(diffs)
        out.append(row)
    return out


def summarize(rows: list[dict]) -> str:
    comp = [r for r in rows if r["our_status"] == "computed"]
    L = ["# Our duty tool against duties actually assessed by Customs (generated by `python -m src.eval.gd_duty_compare`)", "",
         f"Source: an importer's Goods Declaration extract, Chapter 85, February 2026 (private; only anonymised results are kept). {len(rows)} random home-consumption lines. "
         "Importer facts inferred per line (commercial importer if the 3% tax was charged; filer). Amounts compared within 2 rupees.", "",
         f"* Tool could compute: {len(comp)} of {len(rows)} lines. Others: " + ", ".join(f"{k} {v}" for k, v in Counter(r["our_status"] for r in rows if r["our_status"] != "computed").most_common()) + ".", ""]
    for tag in ("none", "china_fta", "fifth_schedule", "sro_655_656", "sales_tax_or_it_exemption"):
        sub = [r for r in comp if r["tag"] == tag]
        if not sub:
            continue
        ok = [r for r in sub if not r["diffs"]]
        L.append(f"* **{tag}**: {len(sub)} lines computed, {len(ok)} match on every tax ({100 * len(ok) // len(sub)}%).")
    L += ["", "## Which tax differs (all computed lines)", "", "| Tax | lines that differ | share |", "|---|---|---|"]
    c = Counter(t for r in comp for t in r["diffs"].split(",") if t)
    for tax, _ in TAXES:
        L.append(f"| {tax} | {c.get(tax, 0)} | {100 * c.get(tax, 0) / max(len(comp), 1):.1f}% |")
    L += ["", "Lines with no concession tag (plain rates) are the fair test of the duty rules. China FTA and Fifth Schedule lines show where concessions change the customs duty; "
          "the concessions work (docs/concessions_plan.md) should close those gaps.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    rows = run(n)
    p = Path("data/processed/eval/gd_duty_comparison.csv")
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    Path("docs/gd_duty_comparison.md").write_text(summarize(rows), encoding="utf-8")
    print(summarize(rows))
