"""Citation grounding (C1, Verify check b).

Rule: every rate, money amount, SRO number, page number, PCT code and legal-note citation that appears in a piece of text
must also appear in the tool output, the retrieved evidence or the user's own message. Applied to (1) any text written by an LLM
before it can reach the user, and (2) the final answer, which is rendered by code from the tool output.

This is a mechanical check on strings, not a judgement. It cannot prove a claim is true; it proves the claim is not invented.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_SRO = re.compile(r"(\d{1,4})\s*\(\s*[iI]\s*\)\s*/\s*(\d{4})")
_CODE8 = re.compile(r"(?<![\d.])(\d{4})\.(\d{4})(?![\d])")
_RAW8 = re.compile(r"(?<![\d.,])(\d{8})(?![\d.,])")
_PAGE_RUN = re.compile(r"(?:\bpp?\.|\bpages?)\s*(\d{1,4}(?:\s*(?:,|and|to|-)\s*\d{1,4})*)", re.I)


def _norm_num(s: str) -> list[str]:
    s = s.replace(",", "").strip(".")
    out = [s]
    try:
        d = Decimal(s)
        out.append(format(d.normalize(), "f"))
    except InvalidOperation:
        pass
    return out


def _leaves(obj: Any, key: str | None = None):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaves(v, str(k))
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            yield from _leaves(v, key)
    elif obj is None or isinstance(obj, bool):
        return
    else:
        yield key, str(obj)


def _norm_scope(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


class Corpus:
    """Everything a statement may legitimately be taken from."""

    def __init__(self, *sources: Any):
        self.numbers: set[str] = set()
        self.sro: set[str] = set()
        self.codes: set[str] = set()
        self.pages: set[str] = set()
        self.notes: set[tuple[str, str]] = set()
        for src in sources:
            self.add(src)

    def add(self, src: Any) -> "Corpus":
        for key, s in _leaves(src):
            for n in _NUM.findall(s):
                self.numbers.update(_norm_num(n))
            for a, b in _SRO.findall(s):
                self.sro.add(f"{int(a)}(I)/{b}")
            for a, b in _CODE8.findall(s):
                self.codes.add(a + b)
            for c in _RAW8.findall(s):
                self.codes.add(c)
            if key in ("page", "page_end") and re.fullmatch(r"\d+", s.strip()):
                self.pages.add(str(int(s)))
            for run in _PAGE_RUN.findall(s):        # page references written inside text, e.g. "PDF pp. 28 and 25; FY2025-26 file p.27"
                for n in re.findall(r"\d{1,4}", run):
                    self.pages.add(str(int(n)))
        # legal notes: (scope, number) pairs from evidence entries
        notes = src.get("notes") if isinstance(src, dict) else None
        if isinstance(notes, list):
            for n in notes:
                if isinstance(n, dict) and n.get("scope"):
                    self.notes.add((_norm_scope(n["scope"]), str(n.get("number", ""))))
        return self

    def has_number(self, token: str) -> bool:
        return any(t in self.numbers for t in _norm_num(token))


def check_text(text: str, corpus: Corpus, allow: set[str] | None = None) -> list[dict]:
    """Return one issue per cited fact in `text` that the corpus does not contain. Empty list = everything is grounded.
    `allow`: literal substrings that are fine (for example a confidence figure printed by the renderer)."""
    allow = allow or set()
    t = text or ""
    for a in allow:
        t = t.replace(a, " ")
    issues: list[dict] = []

    def bad(kind: str, token: str):
        issues.append({"type": kind, "token": token})

    for a, b in _SRO.findall(t):
        if f"{int(a)}(I)/{b}" not in corpus.sro:
            bad("sro_number", f"{a}(I)/{b}")
    for m in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%", t):
        if not corpus.has_number(m.group(1)):
            bad("rate", m.group(0).strip())
    for m in re.finditer(r"(?:\bPKR|\bRs\.?|₨)\s*([\d,]+(?:\.\d+)?)", t, re.I):
        if m.group(1).strip(",.") and not corpus.has_number(m.group(1)):
            bad("amount", m.group(0).strip())
    for m in re.finditer(r"(?<![\d.,])(\d{1,3}(?:,\d{3})*\.\d{2})(?![\d])", t):
        if not corpus.has_number(m.group(1)):
            bad("amount", m.group(1))
    for m in re.finditer(r"(?:\bp\.|\bpp\.|\bpages?)\s*(\d{1,4})\b", t, re.I):
        if str(int(m.group(1))) not in corpus.pages:
            bad("page", m.group(0).strip())
    for a, b in _CODE8.findall(t):
        if a + b not in corpus.codes:
            bad("code", f"{a}.{b}")
    for m in re.finditer(r"\b(chapter|section)\s+([0-9]+|[ivxl]+)\s*,?\s*(?:sub-?heading\s+)?note\s+(\d+)", t, re.I):
        scope = _norm_scope(f"{m.group(1)} {m.group(2)}")
        if (scope, m.group(3)) not in corpus.notes:
            bad("note", m.group(0).strip())
    for m in re.finditer(r"\bnote\s+(\d+)\s+(?:to|of)\s+(chapter|section)\s+([0-9]+|[ivxl]+)", t, re.I):
        scope = _norm_scope(f"{m.group(2)} {m.group(3)}")
        if (scope, m.group(1)) not in corpus.notes:
            bad("note", m.group(0).strip())
    for m in re.finditer(r"\bs\.?\s*no\.?\s*(\d+)\b", t, re.I):
        if not corpus.has_number(m.group(1)):
            bad("serial", m.group(0).strip())
    return issues


def clean_llm_text(text: Any, corpus: Corpus, max_len: int = 400) -> tuple[str, list[dict]]:
    """Whitespace-normalised text from an LLM, or a placeholder when it cites anything the corpus does not contain."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(s) > max_len:
        s = s[: max_len - 3].rstrip() + "..."
    issues = check_text(s, corpus)
    if issues:
        return "(text withheld: it cited figures or sources that were not found in the retrieved material)", issues
    return s, []
