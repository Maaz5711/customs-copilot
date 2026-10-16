"""Test helpers for the agent: a stub retriever (real tariff codes, so the real tools can price them), builders for scripted
LLM answers, and a toolbox that records calls. No network and no search index are needed.
"""
from __future__ import annotations

import re

from src.agent.toolbox import ToolBox

SRC = "20268251181330180Tariff-2026-27.pdf"


def _line(code: str, heading: str, chain: str, page: int) -> dict:
    disp = f"{code[:4]}.{code[4:]}"
    return {"id": f"tariff:2026-27:{disp}:p{page}", "index": "tariff", "kind": "line", "fy": "2026-27", "code": code, "code_display": disp, "heading": heading,
            "text": f"{disp} {chain}", "own_description": chain.split(" > ")[-1], "source_file": SRC, "page": page, "valid_from": "2026-07-01", "valid_to": "2027-06-30"}


LINES = [
    _line("61091000", "61.09", "T- shirts, singlets and other vests, knitted or crocheted. > Of cotton", 156),
    _line("61099090", "61.09", "T- shirts, singlets and other vests, knitted or crocheted. > Of other textile materials > Other", 156),
    _line("61051000", "61.05", "Men's or boys' shirts, knitted or crocheted. > Of cotton", 155),
    _line("84713010", "84.71", "Automatic data processing machines and units thereof; magnetic or optical readers. > Portable automatic data processing machines (laptops)", 233),
    _line("84713020", "84.71", "Automatic data processing machines and units thereof; magnetic or optical readers. > Portable automatic data processing machines (notebooks)", 233),
    _line("87032113", "87.03", "Motor cars and other motor vehicles principally designed for the transport of persons. > Of a cylinder capacity not exceeding 1,000 cc > Mini vans", 265),
]
BY_CODE = {ln["code"]: ln for ln in LINES}
NOTES = {
    "61": [("Chapter 61", "1", "This Chapter applies only to made up knitted or crocheted articles."),
           ("Chapter 61", "5", "Heading 61.09 does not cover garments with a drawstring, ribbed waistband or other means of tightening at the bottom of the garment.")],
    "84": [("Chapter 84", "6", "For the purposes of heading 84.71, the expression automatic data processing machines means machines capable of storing the processing program.")],
    "87": [("Chapter 87", "1", "This Chapter does not cover railway or tramway rolling stock.")],
}


def _note(ch: str, i: int, scope: str, num: str, text: str) -> dict:
    return {"id": f"note:chapter_note:C{ch}:{num}", "index": "notes", "kind": "chapter_note", "code": ch, "scope": scope, "note_number": num, "section": "Section XI" if ch == "61" else "Section XVI",
            "text": f"chapter_note {scope} note {num}: {text}", "source_file": "2022711271427852PakistanCustomsTariff.pdf", "page": 100 + i, "valid_from": "2025-07-01",
            "valid_to": "9999-12-31", "method": "exact_code", "score": 700.0}


class StubRetriever:
    """Callable with the retriever signature. Counts calls per index; deterministic; keyword match with decreasing rerank scores."""

    def __init__(self, lines=None, rulings=None):
        self.lines = list(lines if lines is not None else LINES)
        self.rulings = rulings or []
        self.calls: list[tuple] = []

    def __call__(self, query, index, as_of_date, k):
        self.calls.append((index, query))
        if index == "tariff":
            digits = re.sub(r"\D", "", query)
            if digits and not re.search(r"[A-Za-z]", query):
                hits = [dict(ln, method="exact_code", score=1000.0) for ln in self.lines if ln["code"].startswith(digits)]
                return hits[:k * 2]
            stem = lambda ws: {w.rstrip("s") for w in ws}                      # noqa: E731  (laptop == laptops)
            words = stem(re.findall(r"[a-z]{3,}", query.lower()))
            scored = [(len(words & stem(re.findall(r"[a-z]{3,}", ln["text"].lower()))), ln) for ln in self.lines]
            scored = [t for t in scored if t[0] > 0] or [(0, ln) for ln in self.lines[:3]]
            scored.sort(key=lambda t: -t[0])
            return [dict(ln, method="hybrid+rerank", score=0.3, rerank_score=4.0 - i * 0.5) for i, (_, ln) in enumerate(scored[:k])]
        if index == "notes":
            digits = re.sub(r"\D", "", query)
            if digits and not re.search(r"[A-Za-z]", query):
                return [_note(digits[:2], i, s, n, t) for i, (s, n, t) in enumerate(NOTES.get(digits[:2], []))]
            return []
        if index == "rulings":
            return self.rulings
        return []

    def count(self, index: str) -> int:
        return sum(1 for i, _ in self.calls if i == index)


def no_notes(date):          # notes_loader stub: no GRI / section notes
    return []


class RecordingTools(ToolBox):
    """The real exact tools, plus a record of every call (to prove a node did or did not call them)."""

    def __init__(self, db_path=None):
        super().__init__(db_path)
        self.calls: list[str] = []

    def lookup_code(self, code, as_of_date):
        self.calls.append("lookup_code")
        return super().lookup_code(code, as_of_date)

    def get_applicable_sros(self, code, as_of_date):
        self.calls.append("get_applicable_sros")
        return super().get_applicable_sros(code, as_of_date)

    def compute_duty(self, *a, **k):
        self.calls.append("compute_duty")
        return super().compute_duty(*a, **k)


# --------------------------------------------------------------------------------------------- scripted LLM answers
def understand(**kw) -> dict:
    base = {"goods_description": None, "intended_use": None, "material": None, "condition": None, "condition_quote": None, "vehicle_form": None, "vehicle_form_quote": None,
            "engine_text": None, "value_text": None, "quantity_text": None, "registration_status": None, "registration_quote": None, "commercial_importer": None,
            "commercial_quote": None, "manufacturer_in_house_use": None, "manufacturer_quote": None, "date_text": None, "codes_text": [], "multiple_products": False, "off_topic": False}
    base.update(kw)
    return base


def cand(code: str, conf: float = 0.9, reasons: str = "Wording of the heading and note fits.", evidence=("T1",)) -> dict:
    return {"code": code, "confidence": conf, "reasons": reasons, "evidence": list(evidence)}


def classify(*cands, ambiguous=False, questions=(), deciding=None, refined=()) -> dict:
    return {"candidates": list(cands), "ambiguous": ambiguous, "questions": [{"question": q, "why": "separates the candidates"} for q in questions],
            "deciding_info": deciding, "refined_queries": list(refined)}


def verify(fits=True, conf=0.9, notes=(), problems=(), hint=None, unsupported=()) -> dict:
    return {"fits": fits, "fit_confidence": conf, "contradicting_notes": [{"note": n, "why": "excluded by the note"} for n in notes], "unsupported_claims": list(unsupported),
            "problems": list(problems), "search_hint": hint}


IMPORTER_FULL = {"registration_status": "registered", "registration_quote": "registered importer", "commercial_importer": True, "commercial_quote": "commercial importer",
                "active_taxpayer": True, "active_taxpayer_quote": "filer"}
