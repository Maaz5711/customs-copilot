"""search_codes: the "I know roughly what it is called" mode (what the free lookup sites offer), with our dated store behind it. No LLM, no API key.

    python -m src.tools.code_lookup "laptop computer" --date 2026-10-18 --chapter 84 -k 8
    python -m src.tools.code_lookup 8471.3010

* A code (4, 6 or 8 digits, with or without the dot) goes straight to `lookup_code` (the exact line, or the 8-digit lines under a heading).
* Words go to the tariff index (BM25 + dense + reranker, the same search the agent uses); every hit is re-read from the store so the description,
  customs duty (CD), page and flags come from the dated row, never from the search text.
* The result says what it is: a keyword search, not a classification. The agent (describe the product, answer questions) is the way to a
  confident code and a full bill; `agent_hint` points to it.
"""
from __future__ import annotations

import argparse
import json
import re

from decimal import Decimal, InvalidOperation

from ._util import norm_code, to_iso
from .lookup import lookup_code

CODE_RE = re.compile(r"^\d{4}(?:\.?\d{2}(?:\.?\d{2})?)?$")
HINT = ("This is a keyword search over the tariff wording, not a classification. For a code you can rely on, and for the full bill (regulatory duty, "
        "additional duty, sales tax, income tax), describe the product to the agent: it asks the questions the tariff notes require and shows its sources.")


def default_retriever(query: str, as_of_date: str, k: int) -> list[dict]:
    from src.search import search      # heavy imports (numpy, fastembed) only when really searching

    return search(query, index="tariff", as_of_date=as_of_date, k=k, rerank=True)


def _row(rank: int, view: dict) -> dict:
    cd = view["cd"]
    heading = (view.get("heading") or {}).get("text") or ""
    path = " > ".join(x for x in [heading[:90]] + list(view.get("description_levels") or []) if x)
    return {"rank": rank, "code": view["code"], "description": path or view["description"], "chapter": view["chapter"], "cd": cd,
            "cd_text": (cd.get("rate_pct") + "%") if cd.get("rate_pct") is not None else (cd.get("raw") or "see tariff"),
            "fy": view["fy"], "source_file": view["source_file"], "page": view["page"], "flags": view["flags"]}


def search_codes(query: str, as_of_date, k: int = 10, chapter: str | None = None, cd_pct: str | None = None, *, retriever=None, db_path=None) -> dict:
    """Keyword or code lookup. `chapter` ('84') and `cd_pct` ('11') narrow the keyword results the way the other sites' filters do."""
    try:
        d = to_iso(as_of_date)
    except (ValueError, TypeError) as e:
        return {"status": "invalid_input", "reason": str(e)}
    q = (query or "").strip()
    if not q:
        return {"status": "invalid_input", "reason": "type a product name or a code"}
    if CODE_RE.match(q.replace(" ", "")):
        r = lookup_code(norm_code(q), d, db_path=db_path)
        return {"status": r["status"], "mode": "code", "as_of_date": d, "result": r, "agent_hint": HINT}
    retr = retriever or default_retriever
    want = max(k, 1) * (6 if (chapter or cd_pct) else 2)
    hits = retr(q, d, want)
    try:
        want_cd = Decimal(str(cd_pct)) if cd_pct is not None else None
    except InvalidOperation:
        return {"status": "invalid_input", "reason": "cd_pct must be a number such as 11"}
    out, seen = [], set()
    for h in hits:
        code = h.get("code") or ""
        if h.get("kind") != "line" or len(code) != 8 or code in seen:
            continue
        seen.add(code)
        r = lookup_code(code, d, db_path=db_path)
        if r.get("status") != "found":
            continue
        if chapter and r["chapter"] != str(chapter).zfill(2):
            continue
        if want_cd is not None and (r["cd"].get("rate_pct") is None or Decimal(r["cd"]["rate_pct"]) != want_cd):
            continue
        out.append(_row(len(out) + 1, r))
        if len(out) >= k:
            break
    return {"status": "ok" if out else "no_match", "mode": "keyword", "as_of_date": d, "query": q, "results": out,
            "note": None if out else "No tariff line matched. Try other words (the tariff uses formal names), or describe the product to the agent.",
            "agent_hint": HINT}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("--date", default="2026-10-18")
    ap.add_argument("--chapter")
    ap.add_argument("--cd")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    r = search_codes(a.query, a.date, a.k, a.chapter, a.cd)
    if a.json:
        print(json.dumps(r, indent=1, ensure_ascii=False))
        return
    if r.get("mode") == "code":
        res = r["result"]
        print(f"{res.get('status')}: {res.get('code', '')} {res.get('description', res.get('reason', ''))[:150]}  CD {res.get('cd', {}).get('rate_pct', '?')}%  (p.{res.get('page')})")
    else:
        for x in r.get("results", []):
            print(f"{x['rank']:>2}. {x['code']}  CD {x['cd_text']:<8} {x['description'][:110]}  (p.{x['page']})")
        if r.get("note"):
            print(r["note"])
    print("\n" + HINT)


if __name__ == "__main__":
    main()
