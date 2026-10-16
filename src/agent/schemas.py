"""Lenient validation of what the LLM returns (C1). Wrong types are coerced or dropped; a missing required shape raises SchemaError.

Nothing here trusts the model: codes are checked against the tariff in nodes.py, quotes against the user's message in nodes.py,
figures against the tools in ground.py.
"""
from __future__ import annotations

import re
from typing import Any


class SchemaError(ValueError):
    """The LLM answer does not have the required shape."""


def as_str(x: Any, max_len: int = 600) -> str | None:
    if x is None or isinstance(x, (dict, list)):
        return None
    s = re.sub(r"\s+", " ", str(x)).strip()
    if not s or s.lower() in ("null", "none", "n/a", "not stated", "unknown"):
        return None
    return s[:max_len]


def as_bool(x: Any) -> bool | None:
    if isinstance(x, bool):
        return x
    if isinstance(x, str):
        s = x.strip().lower()
        if s in ("true", "yes"):
            return True
        if s in ("false", "no"):
            return False
    return None


def as_conf(x: Any) -> float:
    try:
        v = float(str(x).strip().rstrip("%"))
    except (TypeError, ValueError):
        return 0.0
    if v > 1.0:           # '85' meaning 85%
        v = v / 100.0
    return max(0.0, min(1.0, v))


def as_list(x: Any) -> list:
    return x if isinstance(x, list) else []


def _need_dict(d: Any, what: str) -> dict:
    if not isinstance(d, dict):
        raise SchemaError(f"{what}: expected a JSON object, got {type(d).__name__}")
    return d


def validate_understand(d: Any) -> dict:
    d = _need_dict(d, "understand")
    enum = lambda v, allowed: (str(v).strip().upper() if str(v).strip().upper() in allowed else None) if v is not None else None  # noqa: E731
    cond = as_str(d.get("condition"))
    reg = as_str(d.get("registration_status"))
    return {
        "goods_description": as_str(d.get("goods_description")), "intended_use": as_str(d.get("intended_use")), "material": as_str(d.get("material")),
        "condition": cond.lower() if cond and cond.lower() in ("new", "used") else None, "condition_quote": as_str(d.get("condition_quote")),
        "vehicle_form": enum(d.get("vehicle_form"), ("CKD", "CBU")), "vehicle_form_quote": as_str(d.get("vehicle_form_quote")),
        "engine_text": as_str(d.get("engine_text")), "value_text": as_str(d.get("value_text")), "quantity_text": as_str(d.get("quantity_text")),
        "registration_status": reg.lower() if reg and reg.lower() in ("registered", "unregistered") else None, "registration_quote": as_str(d.get("registration_quote")),
        "commercial_importer": as_bool(d.get("commercial_importer")), "commercial_quote": as_str(d.get("commercial_quote")),
        "active_taxpayer": as_bool(d.get("active_taxpayer")), "active_taxpayer_quote": as_str(d.get("active_taxpayer_quote")),
        "manufacturer_in_house_use": as_bool(d.get("manufacturer_in_house_use")), "manufacturer_quote": as_str(d.get("manufacturer_quote")),
        "date_text": as_str(d.get("date_text")), "codes_text": [s for s in (as_str(c, 40) for c in as_list(d.get("codes_text"))) if s],
        "multiple_products": bool(as_bool(d.get("multiple_products"))), "off_topic": bool(as_bool(d.get("off_topic"))),
        "misdeclaration_intent": bool(as_bool(d.get("misdeclaration_intent"))), "misdeclaration_quote": as_str(d.get("misdeclaration_quote")),
    }


def validate_classify(d: Any) -> dict:
    d = _need_dict(d, "classify")
    cands = d.get("candidates")
    if not isinstance(cands, list):
        raise SchemaError("classify: 'candidates' must be a list")
    out = []
    for c in cands[:6]:
        if not isinstance(c, dict):
            continue
        code = as_str(c.get("code"), 40)
        if not code:
            continue
        out.append({"code": code, "confidence": as_conf(c.get("confidence")), "reasons": as_str(c.get("reasons"), 600) or "",
                    "evidence": [e for e in (as_str(x, 12) for x in as_list(c.get("evidence"))) if e]})
    qs = []
    for q in as_list(d.get("questions"))[:3]:
        if isinstance(q, dict):
            text = as_str(q.get("question"), 300)
            why = as_str(q.get("why"), 300)
        else:
            text, why = as_str(q, 300), None
        if text:
            qs.append({"question": text, "why": why})
    return {"candidates": out, "ambiguous": bool(as_bool(d.get("ambiguous"))), "questions": qs, "deciding_info": as_str(d.get("deciding_info"), 400),
            "refined_queries": [s for s in (as_str(x, 200) for x in as_list(d.get("refined_queries"))[:3]) if s]}


def validate_verify(d: Any) -> dict:
    d = _need_dict(d, "verify")
    fits = as_bool(d.get("fits"))
    if fits is None:
        raise SchemaError("verify: 'fits' must be true or false")
    notes = []
    for n in as_list(d.get("contradicting_notes"))[:6]:
        if isinstance(n, dict) and as_str(n.get("note"), 12):
            notes.append({"note": as_str(n.get("note"), 12), "why": as_str(n.get("why"), 300) or ""})
    return {"fits": fits, "fit_confidence": as_conf(d.get("fit_confidence", 1.0 if fits else 0.0)), "contradicting_notes": notes,
            "unsupported_claims": [s for s in (as_str(x, 300) for x in as_list(d.get("unsupported_claims"))[:5]) if s],
            "problems": [s for s in (as_str(x, 300) for x in as_list(d.get("problems"))[:6]) if s], "search_hint": as_str(d.get("search_hint"), 200)}


def validate_map(d: Any, ids: list[str]) -> dict:
    d = _need_dict(d, "map_answers")
    ans = d.get("answers") if isinstance(d.get("answers"), dict) else d
    return {i: as_str(ans.get(i), 300) for i in ids}
