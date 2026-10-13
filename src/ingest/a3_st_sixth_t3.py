"""A3: Sales Tax Act 1990, Sixth Schedule TABLE-3 Annexure (import of plant/machinery, 4 columns:
S.No / Description / PCT heading / Conditions).

Rerunnable:  .venv/Scripts/python src/ingest/a3_st_sixth_t3.py   (from repo root)
Outputs (data/processed/): a3_st_sixth_table3.csv/.json, a3_st_sixth_table3_failures.csv,
spotcheck_a3_st_sixth_table3.csv, a3_st_sixth_table3_vision_log.json (manual page-image check, read by this script).
Reuses the parsing helpers of a3_st_sixth.py (Table-1) and writes nothing to Table-1 files.
"""
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf  # noqa: E402
from a3_st_sixth_extract import SNAPSHOTS, RAW, split_page, parse_footnotes, cell_text, TOKEN_RE  # noqa: E402
import a3_st_sixth as t1  # noqa: E402

OUT = "data/processed/"
SNAPS = t1.SNAPS
SCHED = "Sixth Schedule Table-3 Annexure"
GROUP = "ST-6TH-T3"
OPEN = "9999-12-31"
X1, X2, X3 = 165.0, 296.0, 366.0      # column boundaries: S.No | description | PCT heading | conditions
VISION_FILE = OUT + "a3_st_sixth_table3_vision_log.json"

PAIR_CFG = {   # inner tables: item <-> PCT code on the same row (checked on the page images)
    "18": dict(header_before_first=True),
    "23": dict(header_before_first=True, tail_re=r"^Provided that"),
}
DATE_EVIDENCE = {   # key (snapshot, s_no) -> (valid_from, valid_to, basis); evidence read from the PDFs
    ("FY2026-27", "23"): ("2026-07-01", OPEN, "fn 976 'New serial numbers 23 and 24 added through Finance Act 2026' (Finance Act 2026 s.1(2) = 1 Jul 2026)"),
    ("FY2026-27", "24"): ("2026-07-01", OPEN, "fn 976 'New serial numbers 23 and 24 added through Finance Act 2026' (Finance Act 2026 s.1(2) = 1 Jul 2026)"),
}
FN_EXTRA = {("FY2026-27", "24"): ["976"]}
TOKEN3 = re.compile(r"(?<![\d.])(\d{1,3}[A-Z]{0,2})(?=\.|\s|$|\]|&)")


def find_pages(doc):
    first = last = None
    for i in range(len(doc)):
        tx = doc[i].get_text()
        if first is None and re.search(r"ANNEXURE", tx) and re.search(r"PCT heading", tx):
            first = i + 1
        if first and last is None and i + 1 > first:
            for b in doc[i].get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    t = "".join(s["text"] for s in l["spans"]).strip()
                    if re.fullmatch(r"\d{0,4}\[?\W?Annex-A", t):
                        last = i + 1
                        return first, last, l["bbox"][1]
    return first, last, None


def extract(snap):
    doc = pymupdf.open(RAW + SNAPSHOTS[snap]["file"])
    first, last, cut_y = find_pages(doc)
    serials, fns, cur = [], {}, None
    pages = {}
    for pn in range(first, last + 1):
        page = doc[pn - 1]
        sp = split_page(page, pn)
        fns.update(parse_footnotes(sp["foot"]))
        dom = sp["dom"]
        hb = None
        for t in sp["all"]:
            if t["text"].strip() == "(4)":
                hb = t["y1"]
        if hb is None:
            hb = 62.0
        body = [t for t in sp["all"] if t["y0"] >= hb - 1 and t["y0"] < sp["ft"] - 1 and t["y0"] < 715 and t["text"].strip()]
        if pn == last and cut_y is not None:
            body = [t for t in body if t["y0"] < cut_y - 1]
        for t in body:
            t["sup"] = t["size"] < dom * 0.75
        pages[pn] = dict(n=len(body), ft=sp["ft"])
        c1 = sorted([t for t in body if t["x0"] < X1], key=lambda t: (t["y0"], t["x0"]))
        marks = []
        for t in c1:
            tx = t["text"].replace(" ", " ")
            if (t["sup"] and re.fullmatch(r"\s*\d{1,4}\s*", tx)) or re.fullmatch(r"\s*\d{3,4}\[?\s*", tx):
                continue
            tx = re.sub(r"(\d)\s+([A-Z])\b", r"\1\2", tx)
            if re.fullmatch(r"\s*[A-Z]{1,2}\s*", tx) and marks and t["y0"] - marks[-1][0] < 22 and re.fullmatch(r"\d{1,3}", marks[-1][1]):
                marks[-1] = (marks[-1][0], marks[-1][1] + tx.strip())
                continue
            for m in TOKEN3.finditer(tx):
                marks.append((t["y0"], m.group(1)))
        groups = []
        for y, sno in sorted(marks):
            if groups and abs(groups[-1][0] - y) <= 3.0:
                groups[-1][1].append(sno)
            else:
                groups.append([y, [sno]])
        bounds = [g[0] - 5.0 for g in groups]

        def bucket(y):
            idx = -1
            for i, b in enumerate(bounds):
                if y >= b:
                    idx = i
            return idx
        cells = {}
        for t in body:
            col = 1 if t["x0"] < X1 else 2 if t["x0"] < X2 else 3 if t["x0"] < X3 else 4
            cells.setdefault(bucket(t["y0"]), {1: [], 2: [], 3: [], 4: []})[col].append(t)
        if -1 in cells and cur is not None:
            for c in (2, 3, 4):
                cur["geo"][c] += cells[-1][c]
            cur["pages"].add(pn)
        for i, (y, snos) in enumerate(groups):
            c = cells.get(i, {1: [], 2: [], 3: [], 4: []})
            for sno in snos:
                cur = dict(s_no=sno, col1=cell_text(c[1]), geo={2: list(c[2]), 3: list(c[3]), 4: list(c[4])},
                           pages={pn}, first_page=pn, shared=len(snos) > 1)
                serials.append(cur)
    for s in serials:
        s["desc_raw"] = cell_text(s["geo"][2])
        s["code_raw"] = cell_text(s["geo"][3])
        s["cond_raw"] = cell_text(s["geo"][4])
        s["desc_geo"], s["code_geo"] = s["geo"][2], s["geo"][3]
        for g in s["code_geo"]:        # "8417. 8000" printed with a space
            pass
        s["pages"] = sorted(s["pages"])
    return dict(first=first, last=last, serials=serials, footnotes=fns, pages=pages, cut_y=cut_y)


def omitted(s):
    return t1.is_omitted(s) if (s["desc_raw"].strip() or True) else True


def fnrefs(s):
    allt = s["col1"] + " " + s["desc_raw"] + " " + s["code_raw"] + " " + s["cond_raw"]
    return sorted(set(re.findall(r"\{fn:(\d{3,4})\}", allt)), key=int)


def fntext(d, s):
    return " | ".join("%s: %s" % (r, d["footnotes"][r]) for r in fnrefs(s) if r in d["footnotes"])


def fix_spaced_codes(spans):
    """'8417. 8000' -> '8417.8000' (returns True if any fixed)"""
    fixed = False
    for sp in spans:
        n = re.sub(r"(\d{4}\.)\s+(\d{4})", r"\1\2", sp["text"])
        if n != sp["text"]:
            sp["text"] = n
            fixed = True
    return fixed


def build():
    T = t1.load_tariff()
    data = {s: extract(s) for s in SNAPS}
    val = dict(gaps={}, dups={}, omitted={}, page_counts={})
    maps = {}
    for snap in SNAPS:
        m = {}
        for s in data[snap]["serials"]:
            m.setdefault(s["s_no"], []).append(s)
        maps[snap] = m
        nums = sorted({int(re.match(r"\d+", k).group(0)) for k in m})
        val["gaps"][snap] = [n for n in range(1, nums[-1] + 1) if not any(re.match(r"%d(?!\d)" % n, k) for k in m)]
        val["dups"][snap] = [k for k, v in m.items() if len(v) > 1]
        val["omitted"][snap] = [s["s_no"] for s in data[snap]["serials"] if omitted(s)]
        import pdfplumber
        with pdfplumber.open(RAW + SNAPSHOTS[snap]["file"]) as pl:
            d = data[snap]
            for pn in range(d["first"], d["last"] + 1):
                parsed = sum(1 for s in d["serials"] if s["first_page"] == pn)
                page = pl.pages[pn - 1]
                n = 0
                lo = 0 if pn != d["first"] else 0
                for w in page.extract_words(extra_attrs=["size"]):
                    if w["x0"] >= X1 or w["top"] > 715 or w["top"] >= d["pages"][pn]["ft"] - 1 or re.fullmatch(r"\d{3,4}", w["text"]) or w["top"] > (d["cut_y"] - 1 if (pn == d["last"] and d["cut_y"]) else 10 ** 6):
                        continue
                    if pn == d["first"] and w["top"] < 400:
                        continue
                    if w["size"] < 8.0 and not re.match(r"^\d{1,4}\[", w["text"]):
                        continue
                    core = re.sub(r"^\d{1,4}(?=\[)", "", w["text"])
                    if re.fullmatch(r"\[?\d{1,3}[A-Z]{0,2}[.&]?\]?", core) or re.fullmatch(r"\[?\d{3}\d{1,3}[A-Z]{0,2}\.?\]?", core):
                        n += 1
                val["page_counts"].setdefault(snap, {})[pn] = (parsed, n)
    # plan
    keys = []
    for snap in SNAPS:
        for s in data[snap]["serials"]:
            if s["s_no"] not in keys:
                keys.append(s["s_no"])
    keys.sort(key=lambda k: (int(re.match(r"\d+", k).group(0)), re.sub(r"\d", "", k)))
    plan = []
    for k in keys:
        a = next((x for x in maps["FY2025-26"].get(k, []) if not omitted(x)), None)
        b = next((x for x in maps["FY2026-27"].get(k, []) if not omitted(x)), None)
        if not a and not b:
            continue
        if a and b:
            full_a = a["desc_raw"] + " " + a["cond_raw"]
            full_b = b["desc_raw"] + " " + b["cond_raw"]
            r1, t1_ = t1.same_text(full_a, full_b)
            r2, t2_ = t1.same_text(a["code_raw"], b["code_raw"])
            if r1 == "same" and r2 == "same":
                plan.append((k, ["both"], a, b, "same", []))
            elif "changed" not in (r1, r2):
                plan.append((k, ["both"], a, b, "label_diff", t1_ + t2_))
            else:
                plan.append((k, ["FY2025-26", "FY2026-27"], a, b, "changed", t1_ + t2_))
        elif a:
            plan.append((k, ["FY2025-26"], a, None, "only25", []))
        else:
            plan.append((k, ["FY2026-27"], None, b, "only26", []))
    rows, serial_rows = [], []
    for snap in SNAPS:
        for s in data[snap]["serials"]:
            serial_rows.append(dict(snapshot=snap, s_no=s["s_no"], omitted=int(omitted(s)),
                                    raw_description=t1.strip_fn(s["desc_raw"]), raw_code_cell=t1.strip_fn(s["code_raw"]),
                                    raw_conditions=t1.strip_fn(s["cond_raw"]),
                                    pages="%d-%d" % (min(s["pages"]), max(s["pages"])), footnote=fntext(data[snap], s),
                                    source_file=SNAPSHOTS[snap]["file"]))
    for k, snaps, a, b, rel, toks in plan:
        for sn in snaps:
            if sn == "both":
                src, sf, label, alt = b, "FY2026-27", "both", a
            else:
                src = a if sn == "FY2025-26" else b
                sf, label, alt = sn, sn, None
            sd = data[sf]
            if sn == "both":
                ev = DATE_EVIDENCE.get(("FY2026-27", k))
                vf, vt, basis = ev if ev else ("2025-07-01", OPEN, "snapshot")
            else:
                ev = DATE_EVIDENCE.get((sn, k))
                vf, vt, basis = ev if ev else (("2025-07-01", "2026-06-30", "snapshot") if sn == "FY2025-26" else ("2026-07-01", OPEN, "snapshot"))
            if rel == "label_diff":
                basis += "; snapshots differ only in %s" % toks
            desc = t1.strip_fn(src["desc_raw"])
            cond = t1.strip_fn(src["cond_raw"])
            fixed_norms = {m.replace(".", "").replace(" ", "") for sp in src["code_geo"] for m in re.findall(r"\d{4}\.\s+\d{4}", sp["text"])}
            fixed = fix_spaced_codes(src["code_geo"])
            code_all = " ".join(sp["text"] for sp in src["code_geo"])
            ents0, cissues = t1.parse_codes(cell_text([dict(sp, sup=sp.get("sup")) for sp in src["code_geo"]]))
            ents = [dict(tok=e[0], norm=e[1], lvl=e[2], desc=desc, extra=[]) for e in ents0]
            if k in PAIR_CFG:
                pe = t1.pair_entries(src, PAIR_CFG[k])
                A = {(e["norm"], e["lvl"]) for e in pe if e["norm"]}
                B = {(e[1], e[2]) for e in ents0 if e[1]}
                if A != B:
                    cissues.append("pairing_mismatch: inner-table pairing differs from flat parse in %d codes" % len(A ^ B))
                else:
                    ents = pe
            exc_codes, exc_phrase = t1.parse_except(src["desc_raw"])
            sn_iss = list(cissues)
            for e in ents0:
                pass
            m_ch = re.search(r"(?i)chapter\s+(\d{1,2})", exc_phrase or "")
            if m_ch:
                exc_codes = exc_codes + [m_ch.group(1).zfill(2)]
            if exc_phrase and not exc_codes:
                sn_iss.append("except_not_code_expressible: %r" % exc_phrase)
            if rel == "label_diff":
                sn_iss.append("snapshot_text_diff: %s" % toks)
            if not ents:
                ents = [dict(tok="", norm="", lvl="all", desc=desc, extra=[])]
                sn_iss.append("code_cell_empty: scope taken from description only")
            mixed = any(e["lvl"] == "all" and e["tok"] for e in ents) and len(ents) > 1
            fnt = fntext(sd, src)
            for r_ in FN_EXTRA.get((sf, k), []):
                if r_ in sd["footnotes"] and r_ not in fnrefs(src):
                    fnt = (fnt + " | " if fnt else "") + "%s: %s" % (r_, sd["footnotes"][r_])
            if alt is not None:
                fa = fntext(data["FY2025-26"], alt)
                fnt = ("FY2026-27: " + fnt + " || FY2025-26: " + fa) if fa else fnt
            ver = {"both": "b", "FY2025-26": "25", "FY2026-27": "26"}[sn]
            for i, ent in enumerate(ents, 1):
                tok, norm, lvl = ent["tok"], ent["norm"], ent["lvl"]
                iss = list(sn_iss) + list(ent["extra"])
                if norm in fixed_norms and tok:
                    iss.append("code_format: printed with a space ('%s' in the PDF text); normalised to %s" % (tok, norm))
                if lvl == "all" and mixed and tok:
                    iss.append("respective_headings_mixed_with_codes")
                if lvl != "all":
                    miss = []
                    for cs in (["FY2025-26", "FY2026-27"] if sn == "both" else [sn]):
                        if lvl == "heading4" and norm.startswith("99") and cs == "FY2025-26":
                            continue
                        if not t1.code_in_tariff(T, cs, norm, lvl):
                            miss.append(cs)
                    if miss:
                        iss.append("code_not_in_tariff: %s absent from tariff %s" % (tok or norm, "+".join(miss)))
                rows.append(dict(
                    rule_id="%s-%s-%s-%s-%s" % (GROUP, k, ver, norm or "ALL", i), tax="ST", schedule_or_section=SCHED, s_no=k,
                    description=ent["desc"], code_raw=tok if tok else ("" if ent["extra"] else t1.strip_fn(src["code_raw"])),
                    code_norm=norm, match_level=lvl, except_codes=json.dumps(exc_codes),
                    unparsed_except_text=int(bool(exc_phrase and not exc_codes)), rule_group=GROUP, rate_kind="exempt",
                    rate_pct="", rate_specific_amount="", rate_specific_unit="",
                    rate_raw="Exempt from the whole of sales tax (Sixth Schedule Table-3, subject to general conditions (i)-(iii) and column 4)",
                    condition_text=cond, charged_on="", valid_from=vf, valid_to=vt, date_basis=basis, snapshot=label, footnote=fnt,
                    source_file=SNAPSHOTS[sf]["file"], page=src["pages"][0],
                    clause="Sixth Schedule, Table-3, Annexure S.No %s, col 3 (entry %d of %d)%s" % (
                        k, i, len(ents), "; FY2025-26 file p.%d" % alt["pages"][0] if alt is not None else ""),
                    status="accepted", issues="", extraction_method="text_layer(coordinate columns)+vision_check",
                    _issues=iss, _pages=src["pages"]))
    return data, rows, serial_rows, val, plan


def general_conditions(snap):
    doc = pymupdf.open(RAW + SNAPSHOTS[snap]["file"])
    txt = ""
    for pn in range(190, 195):
        tx = doc[pn - 1].get_text()
        if re.search(r"TABLE-3", tx):
            i = tx.index("TABLE-3")
            txt = tx[i:]
            nxt = doc[pn].get_text()
            txt += " " + nxt[:nxt.find("Explanation")] if "Explanation" in nxt else ""
            break
    return re.sub(r"\s+", " ", re.sub(r"\n\d{3,4} [^\n]*", "", txt))[:2500]


def write(data, rows, serial_rows, val, plan):
    vlog = json.load(open(VISION_FILE, encoding="utf-8")) if os.path.exists(VISION_FILE) else []
    viewed = {(v["snapshot"], v["page"]) for v in vlog}
    mism = [v for v in vlog if not v["result"].startswith("ok")]
    f2s = {SNAPSHOTS[x]["file"]: x for x in SNAPS}
    for r in rows:
        for v in mism:
            if v["s_no"] in ("*", r["s_no"]) and v["page"] in r["_pages"]:
                r["_issues"].append("vision_mismatch: " + v["result"])
        r["issues"] = "; ".join(dict.fromkeys(r["_issues"]))
        r["status"] = "needs_review" if r["issues"] else "accepted"
        assert r["valid_to"] >= r["valid_from"]
    assert len({r["rule_id"] for r in rows}) == len(rows)
    cols = ["rule_id", "tax", "schedule_or_section", "s_no", "description", "code_raw", "code_norm", "match_level", "except_codes",
            "unparsed_except_text", "rule_group", "rate_kind", "rate_pct", "rate_specific_amount", "rate_specific_unit", "rate_raw",
            "condition_text", "charged_on", "valid_from", "valid_to", "date_basis", "snapshot", "footnote", "source_file", "page",
            "clause", "status", "issues", "extraction_method"]
    with open(OUT + "a3_st_sixth_table3.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    meta = dict(
        table="Sales Tax Act 1990, Sixth Schedule TABLE-3 Annexure (import of plant/machinery; cols S.No, Description, PCT heading, Conditions)",
        structure="Table-1 (Imports or Supplies) pp.153-181 FY26 / 142-180 FY25; Table-2 'Local Supplies only' from p.188 / 187; "
                  "TABLE-3 preamble pp.192-193, Annexure follows; Annex-A/B forms after the Annexure are not rules",
        snapshots={s: dict(file=SNAPSHOTS[s]["file"], pages="%d-%d" % (data[s]["first"], data[s]["last"]),
                           serial_lines=len(data[s]["serials"]), omitted=len(val["omitted"][s]),
                           live=len(data[s]["serials"]) - len(val["omitted"][s])) for s in SNAPS},
        rows_total=len(rows), rows_needs_review=sum(r["status"] == "needs_review" for r in rows),
        vision=dict(pages_viewed=len(viewed), mismatches=len(mism),
                    rows_on_viewed_pages=sum(1 for r in rows if (f2s[r["source_file"]], r["page"]) in viewed)),
        table3_general_conditions={s: general_conditions(s) for s in SNAPS},
        method="pymupdf span coordinates (4 columns), footnotes from page footer; dated by snapshot diff + footnote/text evidence")
    pub = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    json.dump(dict(meta=meta, rows=pub), open(OUT + "a3_st_sixth_table3.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(OUT + "a3_st_sixth_table3_serials.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(serial_rows[0].keys()))
        w.writeheader()
        w.writerows(serial_rows)

    def img(r):
        return "data/processed/page_images/%s/p%03d.png" % (r["source_file"][:-4], r["page"])
    with open(OUT + "a3_st_sixth_table3_failures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "page_image", "s_no", "code_raw", "rate_raw", "issues"])
        for r in rows:
            if r["issues"]:
                w.writerow([r["page"], img(r), r["s_no"], r["code_raw"], r["rate_raw"], r["issues"]])
    sp = {r["rule_id"]: r for r in rows if r["issues"] or r["unparsed_except_text"]}
    for i, r in enumerate(sorted(rows, key=lambda r: (r["source_file"], r["page"], r["rule_id"]))):
        if i % 3 == 0:
            sp[r["rule_id"]] = r
    with open(OUT + "spotcheck_a3_st_sixth_table3.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "page_image", "s_no", "pct_code", "rate", "correct? (Y/N)", "true_value_if_N"])
        for r in sorted(sp.values(), key=lambda r: (r["source_file"], r["page"], r["rule_id"])):
            w.writerow([r["page"], img(r), r["s_no"], r["code_raw"], r["rate_raw"], "", ""])
    return meta, len(sp)


def main():
    data, rows, serial_rows, val, plan = build()
    meta, nsp = write(data, rows, serial_rows, val, plan)
    print(json.dumps({k: meta[k] for k in ("snapshots", "rows_total", "rows_needs_review", "vision")}, indent=1))
    print("spotcheck", nsp, "gaps", val["gaps"], "dups", val["dups"])
    print("page count mismatches", {s: {p: v for p, v in val["page_counts"][s].items() if v[0] != v[1]} for s in SNAPS})
    for p in plan:
        print(" ", p[0], p[4], p[5][:8])


if __name__ == "__main__":
    main()
