"""Turn the processed files into search documents (one list per index).

Every document is a dict with at least: id, index, text, source_file, page,
valid_from, valid_to, code (digits, may be ''), plus index-specific fields.
Nothing here edits the source files.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
OPEN_END = "9999-12-31"

_DASH_SPLIT = re.compile(r"(?<=[^\s-])\s+(?=-(?:\s*-)*\s+[A-Za-z(])")


def _dash_level(s: str) -> tuple[int, str]:
    m = re.match(r"^((?:-\s*)+)(.*)$", s.strip())
    if not m:
        return 0, s.strip()
    return m.group(1).count("-"), m.group(2).strip()


def _pieces(text: str) -> list[tuple[int, str]]:
    """Split a description into (dash level, text) pieces. The tariff parser glued
    the next sub-heading line ('- Of turkeys:') onto the end of the previous row."""
    return [_dash_level(p) for p in _DASH_SPLIT.split(text.strip()) if p.strip()]


def norm_code(code: str) -> str:
    return re.sub(r"\D", "", code or "")


def tariff_docs() -> list[dict]:
    docs: list[dict] = []
    for fy, fname in (("2026-27", "tariff_2026_27.json"), ("2025-26", "tariff_2025_26.json")):
        data = json.loads((PROC / fname).read_text(encoding="utf8"))
        by_heading: dict[str, list[dict]] = {}
        for r in data["rows"]:
            by_heading.setdefault(r["heading"], []).append(r)
        for h in data["headings"]:
            hp = _pieces(h["text"])
            title = hp[0][1] if hp else h["text"]
            docs.append({
                "id": f"tariff:{fy}:H{h['heading']}", "index": "tariff", "fy": fy, "kind": "heading",
                "code": norm_code(h["heading"]), "code_display": h["heading"],
                "text": f"Heading {h['heading']}: {h['text']}", "title": title,
                "source_file": h["source_file"], "page": h["page"],
                "valid_from": h["valid_from"], "valid_to": h["valid_to"],
            })
            stack: dict[int, str] = {}
            for lvl, txt in hp[1:]:
                stack = {k: v for k, v in stack.items() if k < lvl}
                stack[lvl] = txt
            for r in by_heading.get(h["heading"], []):
                ps = _pieces(r["description"])
                if not ps:
                    continue
                lvl, own = ps[0]
                stack = {k: v for k, v in stack.items() if k < lvl}
                chain = [title] + [stack[k] for k in sorted(stack)] + [own]
                stack[lvl] = own
                for l2, t2 in ps[1:]:  # sub-headings glued at the end apply to following rows
                    stack = {k: v for k, v in stack.items() if k < l2}
                    stack[l2] = t2
                docs.append({
                    "id": f"tariff:{fy}:{r['code']}:p{r['page']}", "index": "tariff", "fy": fy, "kind": "line",
                    "code": norm_code(r["code"]), "code_display": r["code"], "heading": r["heading"],
                    "text": f"{r['code']} " + " > ".join(c.rstrip(":") for c in chain),
                    "own_description": own, "cd_raw": r.get("cd_raw"),
                    "source_file": r["source_file"], "page": r["page"],
                    "valid_from": r["valid_from"], "valid_to": r["valid_to"],
                })
        for r in data.get("special", []):
            docs.append({
                "id": f"tariff:{fy}:S{r['code']}:p{r['page']}", "index": "tariff", "fy": fy, "kind": "special",
                "code": norm_code(r["code"]), "code_display": r["code"],
                "text": f"{r['code']} {r['description']}", "cd_raw": r.get("cd_raw"),
                "source_file": r["source_file"], "page": r["page"],
                "valid_from": r["valid_from"], "valid_to": r["valid_to"],
            })
    return docs


def notes_docs() -> list[dict]:
    """Legal notes. The notes file carries no validity dates of its own. It is the
    FBR HS2022-based tariff print used for both years in scope, so the window is
    FY2025-26 onward and the basis is recorded on every hit."""
    rows = json.loads((PROC / "legal_notes.json").read_text(encoding="utf8"))
    docs = []
    for r in rows:
        scope = r.get("section_or_chapter", "")
        docs.append({
            "id": f"note:{r['note_id']}", "index": "notes", "kind": r.get("kind"),
            "code": (re.search(r"Chapter (\d+)", scope).group(1).zfill(2) if re.search(r"Chapter (\d+)", scope) else ""),
            "scope": scope, "section": r.get("section", ""), "note_number": r.get("note_number"),
            "text": f"{r.get('kind', '')} {scope} note {r.get('note_number', '')}: {r['text']}",
            "source_file": r["source_file"], "page": r["page"],
            "valid_from": "2025-07-01", "valid_to": OPEN_END,
            "date_basis": "assumed: HS2022 notes apply to both FYs in scope (not read from a dated source)",
        })
    return docs


# SRO validity as stored in the legal store (docs/store_schema.md, "SRO dates").
SRO_META = {
    "1064": ("1064(I)/2026", "2026-07-01", OPEN_END),
    "1152": ("1152(I)/2025", "2025-07-01", "2026-06-30"),
    "1063": ("1063(I)/2026", "2026-07-01", OPEN_END),
    "1151": ("1151(I)/2025", "2025-07-01", "2026-06-30"),
    "1898": ("1898(I)/2025", "2025-10-01", "2026-06-29"),
    "1065": ("1065(I)/2026", "2026-06-30", OPEN_END),
}


def _sro_dir(num: str) -> Path:
    base = PROC / "sro_claude"
    return next(p for p in sorted(base.iterdir()) if num in p.name)


def sro_docs() -> list[dict]:
    docs: list[dict] = []
    for num, fname in (("1064", "sro_1064_rd.json"), ("1152", "sro_1152_rd.json")):
        label, vf, vt = SRO_META[num]
        data = json.loads((PROC / fname).read_text(encoding="utf8"))
        src = data["summary"]["source_file"] if "source_file" not in data else data["source_file"]
        for r in data["rows"]:
            code = r.get("pct_code") or ""
            docs.append({
                "id": f"sro:{num}:rd:{r['s_no']}:{r.get('idx', '')}", "index": "sro", "kind": "rd_row",
                "sro": label, "s_no": r["s_no"], "code": norm_code(code), "code_display": code,
                "rate_raw": r.get("rate"), "row_status": r.get("status"),
                "text": f"SRO {label} regulatory duty S.No {r['s_no']} PCT {code}: {r['description']} (RD {r.get('rate')}%)",
                "source_file": src, "page": r["page"], "valid_from": vf, "valid_to": vt,
            })
        docs += _clause_docs(num, _sro_dir(num))
    for num in ("1063", "1151", "1898", "1065"):
        docs += _clause_docs(num, _sro_dir(num))
    return docs


def _clause_docs(num: str, d: Path) -> list[dict]:
    label, vf, vt = SRO_META[num]
    out = []
    for f in sorted(d.glob("p*.json")):
        p = json.loads(f.read_text(encoding="utf8"))
        page = int(p["page"])
        parts = [p.get("preamble") or "", p.get("trailer") or "", p.get("text") or ""]
        text = " ".join(x for x in parts if x).strip()
        if not text:
            continue
        chunks = [text[i:i + 1200] for i in range(0, len(text), 1000)] if len(text) > 1200 else [text]
        for i, c in enumerate(chunks):
            out.append({
                "id": f"sro:{num}:clause:p{page}:{i}", "index": "sro", "kind": "clause", "sro": label,
                "code": "", "text": f"SRO {label} clause text (page {page}): {c}",
                "source_file": p["source_file"], "page": page, "valid_from": vf, "valid_to": vt,
                "note": "text read by a vision model from a scan; verify against the page image",
            })
    return out


RULINGS = [
    ("2025717157016485ValuationRuling2006-2025.pdf", "Valuation Ruling No. 2006 (dated 4 July 2025), Chlorinated Paraffin Wax",
     "2025-07-04", "owner read the scan (owner_answers.csv, 2026-10-14): number 2006, dated 4 July 2025"),
    ("202610212101254615VR2110.pdf", "Valuation Ruling No. 2110/2026 (massage chairs)",
     "2026-10-01", "owner read the scan (owner_answers.csv, 2026-10-14): number 2110, issued 1 October 2026, no effective wording printed"),
    ("2026991291422532PublicNotice60-2026.pdf", "Public Notice 60/2026, Collectorate of Customs Appraisement (classification of curing/drying chambers)",
     "2026-09-01", "owner read the scan (owner_answers.csv, 2026-10-14): number 60/2026, issued 1 September 2026, no effective wording printed"),
]


def rulings_docs() -> list[dict]:
    import pymupdf
    docs = []
    for fname, label, vf, basis in RULINGS:
        pdf = pymupdf.open(RAW / fname)
        for pno, page in enumerate(pdf, start=1):
            raw = page.get_text()
            paras = [re.sub(r"\s+", " ", x).strip() for x in
                     re.split(r"\n(?=\s*(?:\d+[.)]|[ivx]+\.|[a-z]\)|Subject|Brief|Therefore))", raw)]
            paras = [x for x in paras if len(x) > 3]
            buf, chunks = "", []
            for x in paras:
                if len(buf) + len(x) > 900 and buf:
                    chunks.append(buf)
                    buf = x
                else:
                    buf = f"{buf} {x}".strip()
            if buf:
                chunks.append(buf)
            for i, c in enumerate(chunks):
                if len(c) < 25:
                    continue
                docs.append({
                    "id": f"ruling:{fname[:12]}:p{pno}:{i}", "index": "rulings", "kind": "ruling_chunk",
                    "ruling": label, "code": "", "text": f"{label}. {c}",
                    "source_file": fname, "page": pno, "valid_from": vf, "valid_to": OPEN_END,
                    "date_basis": basis,
                    "note": "text layer of a scan, OCR is noisy; verify against the page image",
                })
    return docs


BUILDERS = {"tariff": tariff_docs, "notes": notes_docs, "sro": sro_docs, "rulings": rulings_docs}
