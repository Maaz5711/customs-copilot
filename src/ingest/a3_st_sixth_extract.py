"""A3 helper: coordinate-based extraction of Sales Tax Act 1990 Sixth Schedule, Table-1.

Produces, per snapshot, one record per printed serial number with raw description,
raw code cell, footnote references and footnote texts, and page range.
Pure extraction; no interpretation (see a3_st_sixth.py for parsing/dating/validation).
"""
import re
import pymupdf

RAW = "data/raw/"
SNAPSHOTS = {
    "FY2025-26": dict(file="202586148252375SalesTaxActupdatedupto2025-26.pdf"),
    "FY2026-27": dict(file="20267171373418951SalesTaxAct1990updatedupto30.06.2026.pdf"),
}
X_DESC = 185.0   # description column starts ~190
X_CODE = 349.0   # code column starts ~353 (words at x0 >= this are col 3)
TOKEN_RE = re.compile(r"(?<![\d.])(\d{1,3}[A-Z]{0,2})(?=\.|\s|$|\])")


def page_spans(page, pn=0):
    out = []
    for bi, b in enumerate(page.get_text("dict")["blocks"]):
        for li, l in enumerate(b.get("lines", [])):
            for s in l["spans"]:
                out.append(dict(text=s["text"], size=round(s["size"], 1), x0=s["bbox"][0], blk=bi, ln=li, pg=pn, by=s["origin"][1],
                                x1=s["bbox"][2], y0=s["bbox"][1], y1=s["bbox"][3]))
    return out


def find_table_pages(doc):
    """Return (first_page, last_page) 1-based of Table-1 and (t2_first, t2_last_guess)."""
    first = None
    t2 = None
    for i in range(len(doc)):
        txt = doc[i].get_text()
        if first is None and "SIXTH SCHEDULE" in txt and "Table-1" in txt and "(Imports or Supplies)" in txt:
            first = i + 1
        if first and t2 is None and i + 1 > first and re.search(r"Table-2\s*\n\s*\(Local", txt):
            t2 = i + 1
    return first, t2


def split_page(page, pn=0):
    """Return dict(body=spans in table body, foot=footnote spans, header_bottom, foot_top)."""
    sp = page_spans(page, pn)
    # header bottom: line with "(3)" token
    hb = None
    for s in sp:
        if s["text"].strip() == "(3)" and s["y0"] < 200:
            hb = s["y1"]
    if hb is None:
        hb = 62.0  # pages w/o column header
    # footnote start: first span of size <=5 (footnote numbers) below the body
    ft = min([s["y0"] for s in sp if s["size"] <= 7.5 and s["x0"] <= 130 and s["y0"] > 300
              and re.match(r"\s*\d{1,4}(\s|$)", s["text"])] or [10_000])
    # the "spaces" separator line (size 14, blank) sits just above; ignore (blank text)
    body = [s for s in sp if hb - 1 <= s["y0"] < ft - 1 and s["y0"] < 715 and s["text"].strip()]
    foot = [s for s in sp if s["y0"] >= ft - 1 and s["y0"] < 715]
    from collections import Counter
    c = Counter()
    for t in body:
        if t["size"] in (14.0,):
            continue
        c[t["size"]] += len(t["text"])
    dom = c.most_common(1)[0][0] if c else 10.0
    for t in body + foot:
        t["sup"] = t["size"] < dom * 0.75
    return dict(body=body, foot=foot, hb=hb, ft=ft, all=sp, dom=dom)


def parse_footnotes(foot_spans):
    """Footnote number spans (size<=7.5, x0<=130) start a footnote; a footnote's text follows in
    reading order (origin y, x). A line may hold several footnotes glued together: split them
    again at a token equal to previous number + 1 followed by a capital/quote."""
    fns = {}
    cur = None
    order = []
    for s in sorted(foot_spans, key=lambda t: (round(t["by"] - (2.0 if t["size"] <= 4.6 else 0.0), 0), t["x0"])):
        t = s["text"].strip()
        if not t:
            continue
        m = re.match(r"^(\d{1,4})(?:\s+(.*))?$", t)
        if m and s["x0"] <= 130 and s["size"] <= 7.5:
            cur = m.group(1)
            order.append(cur)
            fns[cur] = (m.group(2) or "")
        elif cur is not None:
            fns[cur] = (fns[cur] + " " + t).strip()
    for n in list(order):
        text = re.sub(r"\s+", " ", fns[n])
        text = re.sub(r"(\d) (st|nd|rd|th)", lambda m: m.group(1) + m.group(2), text)
        cur = n
        while True:
            nxt = str(int(cur) + 1)
            mm = re.search(r"(?<![\d.,/])" + nxt + r"\s+(?=[A-Z“\"(\[a-z])", text)
            if mm and mm.start() > 0 and nxt not in fns:
                fns[cur] = text[:mm.start()].strip()
                cur = nxt
                text = text[mm.end():]
            else:
                break
        fns[cur] = text.strip()
    return fns


def cell_text(spans):
    """Join spans (already filtered to a cell) into text. Superscript footnote refs are
    emitted as {fn:NNN}. Lines are joined by space; a trailing hyphen joins directly."""
    # stream order: keep the PDF's own block/line order so multi-column cells stay together
    lines = []
    for s in sorted(spans, key=lambda t: (t["pg"], t["blk"], t["ln"], t["x0"])):
        if lines and lines[-1][0] == (s["pg"], s["blk"], s["ln"]):
            lines[-1][1].append(s)
        else:
            lines.append([(s["pg"], s["blk"], s["ln"]), [s]])
    out = []
    for _, ln in lines:
        ln.sort(key=lambda t: t["x0"])
        parts = []
        for s in ln:
            t = s["text"]
            if s.get("sup") and re.fullmatch(r"\s*\d{1,4}\s*", t):
                parts.append("{fn:%s}" % t.strip())
            else:
                parts.append(t)
        out.append(re.sub(r"\s+", " ", "".join(parts)).strip())
    txt = ""
    for l in out:
        if not l:
            continue
        if txt.endswith("-") and not txt.endswith(" -"):
            txt += l
        else:
            txt += (" " if txt else "") + l
    return txt


def extract_snapshot(snap):
    doc = pymupdf.open(RAW + SNAPSHOTS[snap]["file"])
    first, t2 = find_table_pages(doc)
    last = t2 - 1
    for i in range(first + 10, t2):
        body = sorted(split_page(doc[i - 1])["body"], key=lambda t: (t["y0"], t["x0"]))
        head = " ".join(t["text"] for t in body[:3])
        if re.search(r"Annex-", head):
            last = i - 1
            break
    serials = []   # dicts
    all_fns = {}
    cur = None
    page_info = {}
    for pn in range(first, last + 1):
        page = doc[pn - 1]
        sp = split_page(page, pn)
        fns = parse_footnotes(sp["foot"])
        all_fns.update({k: v for k, v in fns.items()})
        page_info[pn] = dict(fns=fns, hb=sp["hb"], ft=sp["ft"], dom=sp["dom"])
        body = sp["body"]
        # skip the Sixth Schedule/Table-1 title block on the first page: start after "(3)"
        c1 = [s for s in body if s["x0"] < X_DESC - 3]
        # serial markers: col1 non-superscript spans matching serial pattern
        marks = []
        for s in sorted(c1, key=lambda t: (t["y0"], t["x0"])):
            t = s["text"].replace(" ", " ")
            if re.fullmatch(r"\s*[A-Z]{1,2}\s*", t) and marks and s["y0"] - marks[-1][0] < 22                     and re.fullmatch(r"\d{1,3}", marks[-1][1]):
                marks[-1] = (marks[-1][0], marks[-1][1] + t.strip())  # letter wrapped to next line
                continue
            if s["sup"] and re.fullmatch(r"\s*\d{1,4}\s*", t):
                continue  # footnote ref
            t = re.sub(r"(\d)\s+([A-Z])", r"", t)
            for m in TOKEN_RE.finditer(t):
                marks.append((s["y0"], m.group(1)))
        marks.sort(key=lambda m: m[0])
        # group tokens that share a visual row (same y within 3pt) -> shared cell
        groups = []
        for y, sno in marks:
            if groups and abs(groups[-1][0] - y) <= 3.0:
                groups[-1][1].append(sno)
            else:
                groups.append([y, [sno]])
        bounds = [(g[0] - 2.0) for g in groups]
        def bucket(y):
            idx = -1
            for i, b in enumerate(bounds):
                if y >= b:
                    idx = i
            return idx
        cells = {}
        for s in body:
            if s["x0"] < X_DESC - 3:
                col = 1
            elif s["x0"] < X_CODE:
                col = 2
            else:
                col = 3
            idx = bucket(s["y0"])
            cells.setdefault(idx, {1: [], 2: [], 3: []})[col].append(s)
        # continuation (idx -1)
        if -1 in cells and cur is not None:
            cur["desc_spans"] += cells[-1][2]
            cur["code_spans"] += cells[-1][3]
            cur["pages"].add(pn)
        for i, (y, snos) in enumerate(groups):
            c = cells.get(i, {1: [], 2: [], 3: []})
            col1_text = cell_text(c[1])
            for sno in snos:
                cur = dict(s_no=sno, col1=col1_text, desc_spans=list(c[2]), code_spans=list(c[3]),
                           pages={pn}, first_page=pn, col1_spans=list(c[1]), shared=len(snos) > 1)
                serials.append(cur)
    for s in serials:
        s["desc_raw"] = cell_text(s["desc_spans"])
        s["code_raw"] = cell_text(s["code_spans"])
        s["pages"] = sorted(s["pages"])
        s["desc_geo"] = s.pop("desc_spans")     # kept for inner-table pairing (code <-> item by y position)
        s["code_geo"] = s.pop("code_spans")
        del s["col1_spans"]
    return dict(first=first, last=last, t2=t2, serials=serials, footnotes=all_fns, pages=page_info)


if __name__ == "__main__":
    import sys, json
    snap = sys.argv[1]
    r = extract_snapshot(snap)
    print(r["first"], r["last"], len(r["serials"]))
    for s in r["serials"]:
        print("=== ", s["s_no"], s["pages"], "|COL1:", s["col1"])
        print("  D:", s["desc_raw"][:300])
        print("  C:", s["code_raw"][:300])
