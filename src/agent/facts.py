"""What the agent knows about a question (facts) and how typed answers are read (C1).

`inputs` is the nested dict that is turned into compute_duty arguments:
    {"assessable_value_pkr": "2500000", "quantity": "5000", "quantity_unit": "kg",
     "importer": {"registration_status": "registered", "commercial_importer": True, ...},
     "goods": {"vehicle_form": "CBU", "engine_cc": "1300", ...}}
Field names are the same dotted names compute_duty uses in `missing_inputs[].field`, so an answer to a missing input is
written with `set_path(inputs, field, value)` and nothing has to be translated.

All parsing is deterministic (src/agent/parsing.py). Numbers are kept as strings (Decimal text) so they survive the
checkpointer and are never turned into floats.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from src.tools.rules import norm_unit

from .parsing import (
    dec_str, is_unknown, parse_amount, parse_bool, parse_date_text, parse_enum, parse_number, parse_quantity,
    parse_registration, parse_vehicle_form, says_today,
)


@dataclass
class Coerced:
    ok: bool
    value: Any = None
    error: str | None = None
    unknown: bool = False          # the user said they do not know


# type, and for numbers the allowed range (min exclusive flag via "gt")
SPECS: dict[str, dict] = {
    "as_of_date": {"type": "date"},
    "assessable_value_pkr": {"type": "money_pkr"},
    "quantity": {"type": "quantity"},
    "importer.registration_status": {"type": "registration"},
    "importer.commercial_importer": {"type": "bool"},
    "importer.active_taxpayer": {"type": "bool"},
    "importer.manufacturer_in_house_use": {"type": "bool"},
    "importer.licensed_oil_marketing_company": {"type": "bool"},
    "importer.registered_service_provider_in_house_use": {"type": "bool"},
    "goods.vehicle_form": {"type": "vehicle_form"},
    "goods.engine_cc": {"type": "number", "min": 10, "max": 20000, "what": "engine capacity in cc (for example 1300)"},
    "goods.used_vehicle_commercial_import_ipo": {"type": "bool"},
    "goods.plant_machinery_for_manufacturing": {"type": "bool"},
    "goods.c_and_f_value_usd_per_unit": {"type": "number", "gt": 0, "what": "C&F value in US dollars per unit"},
    "goods.retail_price_total_pkr": {"type": "money_pkr"},
    "goods.fed_quantity": {"type": "number", "gt": 0, "what": "quantity in the unit of the federal excise duty rate"},
    "goods.fan_not_meps_compliant": {"type": "bool"},
    "goods.running_time_minutes": {"type": "number", "gt": 0, "what": "running time in minutes"},
    "goods.age_years": {"type": "number", "min": 0, "max": 100, "what": "age in years"},
    "goods.origin_country": {"type": "text"},
    "goods.has_certificate_of_origin": {"type": "bool"},
    "goods.claim_china_fta": {"type": "bool"},
}


def get_path(inputs: dict, field: str):
    cur: Any = inputs
    for part in field.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def set_path(inputs: dict, field: str, value) -> None:
    parts = field.split(".")
    cur = inputs
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def spec_for(field: str, allowed: list | None = None) -> dict:
    """Registered spec, or one guessed from the tool's `allowed` list (so a new missing input still gets a sensible parser)."""
    if field in SPECS:
        return SPECS[field]
    if allowed and all(isinstance(a, bool) for a in allowed):
        return {"type": "bool"}
    if allowed:
        return {"type": "enum"}
    return {"type": "text"}


def coerce(field: str, text, *, allowed: list | None = None, unit: str | None = None, today: dt.date | None = None) -> Coerced:
    """Read the user's answer `text` for `field`. Never guesses: returns ok=False with a plain error message instead."""
    if isinstance(text, bool):
        text = "yes" if text else "no"
    text = "" if text is None else str(text)
    spec = spec_for(field, allowed)
    typ = spec["type"]
    if is_unknown(text):
        return Coerced(False, error="you said you do not know", unknown=True)
    if typ == "bool":
        b = parse_bool(text)
        return Coerced(True, b) if b is not None else Coerced(False, error="please answer yes or no")
    if typ == "registration":
        r = parse_registration(text)
        return Coerced(True, r) if r else Coerced(False, error="please answer 'registered' or 'unregistered' (under the Sales Tax Act)")
    if typ == "vehicle_form":
        v = parse_vehicle_form(text)
        return Coerced(True, v) if v else Coerced(False, error="please answer CKD or CBU")
    if typ == "enum":
        v = parse_enum(text, allowed or [])
        return Coerced(True, v) if v is not None else Coerced(False, error="please answer with one of: " + ", ".join(map(str, allowed or [])))
    if typ == "date":
        if says_today(text) and today:
            return Coerced(True, today.isoformat())
        d = parse_date_text(text)
        return Coerced(True, d.isoformat()) if d else Coerced(False, error="I could not read a full date; please write it like 2026-07-15 or 15 July 2026")
    if typ == "money_pkr":
        n, cur = parse_amount(text)
        if n is None:
            return Coerced(False, error="I could not find an amount; please give a number in PKR (for example 2500000 or 25 lakh)")
        if cur not in (None, "PKR"):
            return Coerced(False, error=f"the amount is in {cur}; I do not convert currencies, please give the value in PKR")
        if n <= 0:
            return Coerced(False, error="the amount must be greater than zero")
        return Coerced(True, dec_str(n))
    if typ == "number":
        n = parse_number(text)
        if n is None:
            return Coerced(False, error=f"I could not find a number for {spec.get('what', 'this')}")
        if "min" in spec and n < spec["min"] or "max" in spec and n > spec["max"] or "gt" in spec and n <= spec["gt"]:
            return Coerced(False, error=f"{dec_str(n)} is not a plausible {spec.get('what', 'value')}")
        return Coerced(True, dec_str(n))
    if typ == "quantity":
        n, u = parse_quantity(text)
        if n is None or n <= 0:
            return Coerced(False, error="please give the quantity as a number" + (f" in {unit}" if unit else ""))
        if unit and u and norm_unit(u) != norm_unit(unit):
            return Coerced(False, error=f"you gave the quantity in '{u}' but the rate is per {unit}; I do not convert units, please give it in {unit}")
        return Coerced(True, {"quantity": dec_str(n), "quantity_unit": unit or u})
    s = text.strip()
    return Coerced(True, s) if s else Coerced(False, error="empty answer")


def apply_value(inputs: dict, field: str, value) -> None:
    """Write a coerced value into `inputs` (a quantity also writes its unit)."""
    if field == "quantity" and isinstance(value, dict):
        inputs["quantity"] = value["quantity"]
        if value.get("quantity_unit"):
            inputs["quantity_unit"] = value["quantity_unit"]
        return
    set_path(inputs, field, value)


def tool_args(inputs: dict) -> dict:
    """compute_duty keyword arguments from `inputs` (only values that are set)."""
    importer = {k: v for k, v in (inputs.get("importer") or {}).items() if v is not None}
    goods = {k: v for k, v in (inputs.get("goods") or {}).items() if v is not None}
    # Fifth Schedule claims: the importer said "yes, I meet the conditions of this entry" (field claim.<rule_id>)
    claimed = sorted(k for k, v in (inputs.get("claim") or {}).items() if v is True)
    args = {
        "assessable_value_pkr": inputs.get("assessable_value_pkr"),
        "importer": importer or None,
        "goods": goods or None,
        "quantity": inputs.get("quantity"),
        "quantity_unit": inputs.get("quantity_unit"),
    }
    if claimed:
        args["claimed_rules"] = claimed
    return args
