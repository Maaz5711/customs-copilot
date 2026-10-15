"""A6: map 'Respective heading(s)' FED rows to tariff codes by description match (NOT owner verified).

The Federal Excise Act prints 'Respective heading(s)' for 54 rows, so they were stored unmapped (they never match a code).
This module maps only the First Schedule Table I goods whose description names a tariff line or heading unambiguously, in
the right fiscal year, and lists every row it leaves unmapped with the reason.

Outputs (written by `python -m src.ingest.a6_fed_mapping`):
  data/processed/a6_fed_mapping.csv       fed_row_id, description, mapped_code, tariff_description, confidence, reason, ...
  data/processed/a6_fed_rules_mapped.json derived rows (copies of the unmapped rows with a code), loaded by src.store.build
The original unmapped rows stay in a6_fed_rules.csv unchanged. Mapped rows get status needs_review.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
NOTE = "mapped by description match to tariff, owner has not verified (a6_fed_mapping.csv)"
FY_FILE = {"FY2025-26": "tariff_2025_26", "FY2026-27": "tariff_2026_27"}

# serial -> [(code, confidence, reason)]. Codes are 8-digit lines or 4-digit headings (as in the tariff).
MAP = {
    "7a": [("55021000", "high", "'Acetate tow' = heading 55.02 artificial filament tow, line 'Of cellulose acetate'")],
    "8a": [("24041200", "medium", "e-liquid for e-cigarettes = 2404 'Products intended for inhalation without combustion', line 'Other, containing nicotine'"),
           ("24041900", "medium", "nicotine-free e-liquid would fall in 'Other' of the same group; description 'by whatsoever name called' is wide")],
    "8b": [("24021000", "high", "'Cigars, cheroots and cigarillos' = line 2402.1000 (exact words). More specific than S.No 8 (heading 2402), so cigars no longer take the cigarette row")],
    "8c": [("24041100", "medium", "tobacco mixture for electrically heated product, consumed without combustion = 2404.1100 'inhalation without combustion, containing tobacco'")],
    "8d": [("24049100", "medium", "nicotine pouches are nicotine products for oral application = 2404.9100; the tariff text does not say 'pouch'")],
    "60": [(c, "medium", "'fans' = 8414.51 table, floor, wall, window, ceiling or roof fans <= 125 W. The serial applies only to fans that do not meet the MEPS (PSQCA): caller must confirm")
           for c in ("84145110", "84145120", "84145130", "84145140", "84145190")],
    "62": [(h, "high", "'Fertilizers' = Chapter 31 heading " + h[:2] + "." + h[2:] + " (Chapter 31 is 'Fertilisers')") for h in ("3101", "3102", "3103", "3104", "3105")],
    "64": [("01051100", "high", "'Day Old Chick' = 0105.1100 live fowls Gallus domesticus weighing not more than 185 g; turkeys, ducks, geese, guinea fowls not mapped")],
}
# unmapped Table I / III serials left alone, with the reason
LEFT = {
    "6": "aerated waters made wholly from juices/pulp: defined by recipe, several headings (2009, 2202) could apply",
    "55A": "electric cars and SUVs: OQ-A6-1 (S.No 55 EV words, S.No 55A and Table IA overlap); compute_duty refuses instead of guessing",
    "56": "'Filter rod for cigarettes': no tariff line names it; 5502.9090, 5601.xxxx or 2403/2404 are all possible",
    "59": "sugary juices, syrups, squashes, waters with exclusions: several headings (2009, 2106, 2202) and sugar content decide",
    "III:2": "supply of sugar to manufacturers: local supply, not an import",
}
THIRD = "Third Schedule exemption by importer, project or purpose, not by goods: no tariff code can be assigned"


def _tariff(fy):
    d = json.loads((PROC / f"{FY_FILE[fy]}.json").read_text(encoding="utf-8"))
    lines = {r["code"].replace(".", ""): r for r in d["rows"]}
    heads = {h["heading"].replace(".", ""): h for h in d["headings"]}
    return lines, heads


def build_mapping():
    rules = list(csv.DictReader(open(PROC / "a6_fed_rules.csv", encoding="utf-8", newline="")))
    tar = {fy: _tariff(fy) for fy in FY_FILE}
    out, derived, unmapped_left = [], [], []
    for r in rules:
        if r["match_level"] != "unmapped":
            continue
        key = r["s_no"] if r["table_no"] == "I" else ("III:" + r["s_no"] if r["table_no"] == "III" else None)
        spec = MAP.get(key) if r["table_no"] == "I" else None
        base = {"fed_row_id": r["row_id"], "fy": r["fy"], "table_no": r["table_no"], "s_no": r["s_no"], "sub": r["sub"],
                "description": r["description"], "heading_raw": r["heading_raw"]}
        if not spec:
            reason = THIRD if r["table_no"] == "Third-I" else (LEFT.get(key) or "ambiguous")
            out.append({**base, "mapped_code": "", "match_level": "", "tariff_description": "", "confidence": "none",
                        "reason": "left unmapped: " + reason})
            unmapped_left.append(r["row_id"])
            continue
        lines, heads = tar[r["fy"]]
        for code, conf, why in spec:
            if len(code) == 8:
                t = lines.get(code)
                if not t:
                    raise ValueError(f"{code} not in tariff {r['fy']}")
                tdesc, level = t["full_description"], "code8"
            else:
                t = heads.get(code)
                if not t:
                    raise ValueError(f"heading {code} not in tariff {r['fy']}")
                tdesc, level = t["text"], "heading4"
            shown = code if level == "heading4" else f"{code[:4]}.{code[4:]}"
            out.append({**base, "mapped_code": shown, "match_level": level, "tariff_description": tdesc[:200], "confidence": conf,
                        "reason": why})
            d = dict(r)
            d.update(row_id=r["row_id"].replace(":unmapped", ":" + code), code_norm=code, match_level=level, status="needs_review",
                     heading_raw=r["heading_raw"],
                     issues=(r["issues"] + " " if r["issues"] else "") + f"{NOTE}: {shown} ({conf}); original heading column '{r['heading_raw']}' kept;")
            derived.append(d)
    return out, derived, unmapped_left


def main():
    out, derived, left = build_mapping()
    cols = ["fed_row_id", "fy", "table_no", "s_no", "sub", "description", "heading_raw", "mapped_code", "match_level",
            "tariff_description", "confidence", "reason"]
    with open(PROC / "a6_fed_mapping.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    (PROC / "a6_fed_rules_mapped.json").write_text(json.dumps(derived, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"mapping rows {len(out)}; derived store rows {len(derived)}; fed rows left unmapped {len(left)}")


if __name__ == "__main__":
    main()
