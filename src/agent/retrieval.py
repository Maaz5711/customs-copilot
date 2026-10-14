"""Search node (C1): evidence for classification, gathered per index with a score floor.

`src.search` is called once per index (tariff, notes, sro, rulings), never as one merged search, because the merged search
puts an irrelevant ruling chunk in every result list. Each non-exact hit must reach the index's floor on the cross-encoder
`rerank_score` (calibration in docs/agent_notes.md: irrelevant hits sit at about -8 to -11 on every index, relevant rulings
at +5 to +8). Exact code lookups are deterministic and always kept.

Evidence is plain JSON (it is stored in the graph state). Labels T1.., N1.., S1.., R1.. are what the LLM must use to point at
a source; the code maps them back to ids, files and pages.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from .parsing import display_code, find_pct_codes

Retriever = Callable[[str, str, str, int], list]        # (query, index, as_of_date, k) -> hits
NotesLoader = Callable[[str], list]                      # (as_of_date) -> note docs valid on the date

DEFAULT_FLOORS = {"tariff": -9.0, "notes": -4.0, "sro": -3.0, "rulings": 0.0}
OPEN_END = "9999-12-31"
NOTE_CHARS = 700            # shown to the LLM per note
GRI_CHARS = 420


def default_retriever(query: str, index: str, as_of_date: str, k: int) -> list:
    from src.search import search      # heavy imports (numpy, fastembed) only when really searching

    return search(query, index=index, as_of_date=as_of_date, k=k, rerank=True)


_NOTES_CACHE: dict = {}


def default_notes_loader(as_of_date: str) -> list:
    """All legal-note documents valid on the date, straight from the built index file (484 docs). [] if the index is missing."""
    try:
        from src.search.engine import INDEX_DIR
    except Exception:
        return []
    p = Path(INDEX_DIR) / "notes" / "docs.jsonl"
    if not p.exists():
        return []
    if "docs" not in _NOTES_CACHE:
        _NOTES_CACHE["docs"] = [json.loads(line) for line in p.read_text(encoding="utf8").splitlines() if line.strip()]
    return [d for d in _NOTES_CACHE["docs"] if d["valid_from"] <= as_of_date <= d["valid_to"]]


def passes(hit: dict, floor: float) -> bool:
    if hit.get("method") == "exact_code":
        return True
    rr = hit.get("rerank_score")
    return rr is None or rr >= floor


def _short(text: str, n: int) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= n else t[: n - 3].rstrip() + "..."


def line_description(text: str) -> str:
    """'6109.1000 Heading title > Of cotton' -> 'Heading title > Of cotton' (the part after the code)."""
    return re.sub(r"^\s*\d{4}\.\d{4}\s*", "", text or "").strip()


def _line_view(hit: dict, rr: float | None) -> dict:
    code = hit.get("code") or ""
    return {
        "code": display_code(code), "norm": code, "text": hit.get("text", ""), "description": line_description(hit.get("text", "")),
        "page": hit.get("page"), "source_file": hit.get("source_file"), "id": hit.get("id"), "fy": hit.get("fy"),
        "heading": hit.get("heading"), "rr": rr, "method": hit.get("method"),
    }


def _note_view(hit: dict, rr: float | None) -> dict:
    return {
        "id": hit.get("id"), "kind": hit.get("kind"), "scope": hit.get("scope", ""), "number": str(hit.get("note_number") or ""),
        "section": hit.get("section", ""), "text": _short(hit.get("text", ""), 1500), "page": hit.get("page"),
        "source_file": hit.get("source_file"), "rr": rr, "chapter": hit.get("code", ""),
    }


def _chapter_of(code: str) -> str:
    return (code or "")[:2]


def gather(retriever: Retriever, notes_loader: NotesLoader, *, query: str, extra_queries: list[str] | None = None,
           user_codes: list[str] | None = None, as_of_date: str, floors: dict | None = None, k_tariff: int = 10,
           max_lines: int = 36, max_children: int = 30, max_notes_per_chapter: int = 8) -> dict:
    """Collect candidate tariff lines, legal notes, SRO excerpts and rulings for one product on one date. Pure retrieval, no LLM."""
    fl = {**DEFAULT_FLOORS, **(floors or {})}
    dropped = {"tariff": 0, "notes": 0, "sro": 0, "rulings": 0}
    queries = []
    for q in [query] + list(extra_queries or []):
        q = re.sub(r"\s+", " ", q or "").strip()
        if q and q not in queries:
            queries.append(q)
    queries = queries[:3]

    # ---- tariff: hybrid hits for every query, then exact hits for codes the user wrote
    best: dict[str, tuple[dict, float | None]] = {}
    order: list[str] = []

    def take(hit: dict):
        if hit.get("kind") == "special":        # Chapter 99 conditional regimes are not classification lines
            return
        rr = hit.get("rerank_score")
        if not passes(hit, fl["tariff"]):
            dropped["tariff"] += 1
            return
        hid = hit["id"]
        if hid not in best:
            best[hid] = (hit, rr)
            order.append(hid)
        elif rr is not None and (best[hid][1] is None or rr > best[hid][1]):
            best[hid] = (hit, rr)

    user_lines: list[dict] = []
    for c in user_codes or []:
        for h in retriever(c, "tariff", as_of_date, 40):
            if h.get("kind") == "line" and h.get("code", "").startswith(c) and h["id"] not in {x["id"] for x in user_lines}:
                user_lines.append(h)
    for q in queries:
        for h in retriever(q, "tariff", as_of_date, k_tariff):
            take(h)

    hits_lines = sorted([best[i] for i in order if best[i][0].get("kind") == "line"], key=lambda t: -(t[1] if t[1] is not None else 1e9))
    hits_heads = [best[i][0] for i in order if best[i][0].get("kind") == "heading"]

    # ---- expand the two best headings into their lines when the heading is small enough to list
    heads: list[str] = []
    for c in user_codes or []:                       # the user's own code first
        if len(c) >= 4 and c[:4] not in heads:
            heads.append(c[:4])
    for h, _ in hits_lines[:4]:
        hd = re.sub(r"\D", "", h.get("heading") or h.get("code", "")[:4])
        if hd and hd not in heads:
            heads.append(hd)
    for h in hits_heads[:2]:
        if h["code"] not in heads:
            heads.append(h["code"])
    expanded: list[dict] = []
    for hd in heads[:2]:
        kids = [h for h in retriever(hd, "tariff", as_of_date, 40) if h.get("kind") == "line" and h.get("code", "").startswith(hd)]
        if 0 < len(kids) <= max_children:
            expanded.extend(kids)

    # ---- rulings and SRO excerpts (semantic only; rates always come from the tools)
    sro, rulings = [], []
    if queries:
        for h in retriever(queries[0], "sro", as_of_date, 5):
            if passes(h, fl["sro"]):
                sro.append({"id": h["id"], "sro": h.get("sro"), "s_no": h.get("s_no"), "text": _short(h.get("text", ""), 500), "page": h.get("page"),
                            "source_file": h.get("source_file"), "rr": h.get("rerank_score"), "kind": h.get("kind")})
            else:
                dropped["sro"] += 1
        for h in retriever(queries[0], "rulings", as_of_date, 3):
            if passes(h, fl["rulings"]):
                rulings.append({"id": h["id"], "ruling": h.get("ruling"), "text": _short(h.get("text", ""), 600), "page": h.get("page"),
                                "source_file": h.get("source_file"), "rr": h.get("rerank_score"), "valid_from": h.get("valid_from"),
                                "date_basis": h.get("date_basis")})
            else:
                dropped["rulings"] += 1
    for i, s in enumerate(sro, 1):
        s["label"] = f"S{i}"
    for i, r in enumerate(rulings, 1):
        r["label"] = f"R{i}"

    # ---- codes quoted in a relevant ruling join the pool (a ruling is classification authority). Exact lookup validates them.
    ruling_lines: list[dict] = []
    known = {h["code"] for h, _ in hits_lines} | {h["code"] for h in user_lines} | {h["code"] for h in expanded}
    for r in rulings:
        for c in find_pct_codes(r["text"]):
            if len(c["code"]) != 8 or not c["trusted"] or c["code"] in known or len(ruling_lines) >= 6:
                continue
            for h in retriever(c["code"], "tariff", as_of_date, 5):
                if h.get("kind") == "line" and h.get("code") == c["code"]:
                    known.add(c["code"])
                    view = _line_view(h, None)
                    view["from_ruling"] = r["label"]
                    ruling_lines.append(view)
                    break

    lines: list[dict] = []
    seen: set[str] = set()
    for h in user_lines:
        if h["id"] not in seen:
            seen.add(h["id"])
            lines.append(_line_view(h, None))
    for h, rr in hits_lines:
        if h["id"] not in seen:
            seen.add(h["id"])
            lines.append(_line_view(h, rr))
    for v in ruling_lines:
        if v["id"] not in seen:
            seen.add(v["id"])
            lines.append(v)
    for h in expanded:
        if h["id"] not in seen:
            seen.add(h["id"])
            lines.append(_line_view(h, h.get("rerank_score")))
    lines = lines[:max_lines]
    for i, ln in enumerate(lines, 1):
        ln["label"] = f"T{i}"

    # ---- notes: chapter notes of the best chapters (deterministic), semantic notes above the floor, section notes, GRI
    chapters: list[str] = []
    for c in list(user_codes or []):
        if _chapter_of(c) and _chapter_of(c) not in chapters:
            chapters.append(_chapter_of(c))
    for ln in lines[:6]:
        if _chapter_of(ln["norm"]) not in chapters:
            chapters.append(_chapter_of(ln["norm"]))
    for ln in lines:
        if ln.get("from_ruling") and _chapter_of(ln["norm"]) not in chapters:
            chapters.append(_chapter_of(ln["norm"]))
    chapters = [c for c in chapters if c][:3]

    sem_notes: dict[str, float] = {}
    sem_hits: list[dict] = []
    for h in retriever(queries[0], "notes", as_of_date, 6) if queries else []:
        if passes(h, fl["notes"]):
            sem_hits.append(h)
            sem_notes[h["id"]] = h.get("rerank_score")
        else:
            dropped["notes"] += 1
    notes: list[dict] = []
    nseen: set[str] = set()
    sections: list[str] = []
    for ch in chapters:
        ch_hits = [h for h in retriever(ch + "00", "notes", as_of_date, 40) if h.get("method") == "exact_code"]
        ch_hits.sort(key=lambda h: (-(sem_notes.get(h["id"]) if sem_notes.get(h["id"]) is not None else -99.0), h.get("kind") != "chapter_note", int(re.sub(r"\D", "", str(h.get("note_number") or "0")) or 0)))
        for h in ch_hits[:max_notes_per_chapter]:
            if h["id"] not in nseen:
                nseen.add(h["id"])
                notes.append(_note_view(h, sem_notes.get(h["id"])))
            if h.get("section") and h["section"] not in sections:
                sections.append(h["section"])
    for h in sem_hits:
        if h["id"] not in nseen:
            nseen.add(h["id"])
            notes.append(_note_view(h, h.get("rerank_score")))
            if h.get("section") and h["section"] not in sections:
                sections.append(h["section"])
    docs = notes_loader(as_of_date) or []
    for d in docs:
        if d.get("kind") == "section_note" and d.get("scope") in sections and d["id"] not in nseen and len([n for n in notes if n["kind"] == "section_note"]) < 4:
            nseen.add(d["id"])
            notes.append(_note_view(d, None))
    for d in sorted((d for d in docs if d.get("kind") == "gri"), key=lambda d: int(re.sub(r"\D", "", str(d.get("note_number") or "0")) or 0)):
        if d["id"] not in nseen:
            nseen.add(d["id"])
            v = _note_view(d, None)
            v["text"] = _short(d.get("text", ""), 1500)
            notes.append(v)
    for i, n in enumerate(notes, 1):
        n["label"] = f"N{i}"

    return {"queries": queries, "lines": lines, "notes": notes, "sro": sro, "rulings": rulings, "chapters": chapters, "dropped": dropped,
            "as_of_date": as_of_date}


def offered_codes(evidence: dict) -> list[str]:
    return [ln["norm"] for ln in evidence.get("lines", [])]


def evidence_text(evidence: dict, *, include_sro: bool = True) -> str:
    """The evidence as labelled text for an LLM prompt."""
    out = ["CANDIDATE TARIFF LINES (the ONLY codes you may choose from). Lines are grouped under their heading."]
    groups: dict[str, list[dict]] = {}
    for ln in evidence.get("lines", []):
        groups.setdefault(re.sub(r"\D", "", ln.get("heading") or ln["norm"][:4]), []).append(ln)
    for hd, lns in groups.items():
        title = lns[0]["description"].split(" > ")[0]
        out.append(f"Heading {hd[:2]}.{hd[2:]}: {_short(title, 260)}")
        for ln in lns:
            parts = ln["description"].split(" > ")
            chain = " > ".join(parts[1:]) or parts[0]
            tag = f"  (code quoted in ruling {ln['from_ruling']})" if ln.get("from_ruling") else ""
            out.append(f"  [{ln['label']}] {ln['code']} | {_short(chain, 240)}{tag}")
    if not evidence.get("lines"):
        out.append("(none found)")
    out.append("")
    out.append("LEGAL NOTES (General Rules of Interpretation, section and chapter notes of the candidate chapters; HS 2022 text printed in the Pakistan tariff)")
    for n in evidence.get("notes", []):
        cap = GRI_CHARS if n.get("kind") == "gri" else NOTE_CHARS
        who = f"{n['scope']} note {n['number']}" if n.get("kind") != "gri" else f"GRI rule {n['number']}"
        out.append(f"[{n['label']}] {who} ({n.get('kind')}): {_short(n['text'], cap)}")
    if not evidence.get("notes"):
        out.append("(none found)")
    if include_sro and evidence.get("sro"):
        out.append("")
        out.append("SRO EXCERPTS (context only; do not quote rates)")
        for s in evidence["sro"]:
            out.append(f"[{s['label']}] {_short(s['text'], 300)}")
    if evidence.get("rulings"):
        out.append("")
        out.append("RULINGS AND PUBLIC NOTICES (text read from scans, may be noisy)")
        for r in evidence["rulings"]:
            out.append(f"[{r['label']}] {r['ruling']}: {_short(r['text'], 400)}")
    return "\n".join(out)
