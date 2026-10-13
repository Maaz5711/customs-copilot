"""Rule interpretation shared by get_applicable_sros and compute_duty (exact, no LLM, no rates).

Everything here decides WHICH stored row applies from facts the caller gave. The rates themselves are only ever read
from the store. Keys like 'sro_655_656_2006' are identifiers of regimes named in the SRO text, not rates.
"""
from __future__ import annotations

import re

from ._util import D

USED_VEHICLE_SROS = ("1898(I)/2025", "1065(I)/2026")  # "in addition to" the main RD SRO (their own rows say so)

# ACD para 3 clauses that only apply when the import is under a named regime (SRO text: "ONLY import under ...").
ACD_REGIME_BY_CLAUSE = {
    "3(iii)": "fifth_schedule",
    "3(iv)": "baggage_rules_2006",
    "3(v)": "sro_577_2005",
    "3(vi)": "sro_565_2006",
    "3(vii)": "sro_693_2006",
    "3(viii)": "sro_492_2009_temporary_importation",
    "3(ix)": "sro_678_2004_offshore",
}
SRO_655_656 = "sro_655_656_2006"

_SLAB = re.compile(r"^SLAB_(EQ|GE) ([0-9.]+)")


def as_bool(x):
    if x is None or isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    if s in ("yes", "y", "true", "1"):
        return True
    if s in ("no", "n", "false", "0"):
        return False
    return None


class Facts:
    """What the caller told us about the importer and the goods. None means 'not given'."""

    def __init__(self, importer=None, goods=None, claimed=None):
        self.importer = dict(importer or {})
        self.goods = dict(goods or {})
        self.claimed = set(claimed or [])

    def i(self, key):
        return self.importer.get(key)

    def g(self, key):
        return self.goods.get(key)

    def ib(self, key):
        return as_bool(self.importer.get(key))

    def gb(self, key):
        return as_bool(self.goods.get(key))

    def regimes(self):
        r = self.goods.get("import_regime") or []
        if isinstance(r, str):
            r = [r]
        return {str(x).strip().lower() for x in r}

    def vehicle(self):
        form = str(self.goods.get("vehicle_form") or "").strip().upper() or None
        if form not in ("CKD", "CBU"):
            form = None
        cc = self.goods.get("engine_cc")
        try:
            cc = D(cc) if cc is not None else None
        except Exception:
            cc = None
        return form, cc


# --------------------------------------------------------------------------- ACD
def acd_kind(r: dict):
    """Classify what an ACD row's condition depends on: slab | regime | ckd_levy | veh_exempt | pm | None (unconditional)."""
    cond = r.get("condition_text") or ""
    m = _SLAB.match(cond)
    if m:
        return "slab", (m.group(1), D(m.group(2)))
    if cond.startswith("ONLY goods imported under Notifications SRO 655"):
        return "regime", SRO_655_656
    if cond.startswith("ONLY cars, jeeps, light commercial vehicles in CKD"):
        return "ckd_levy", None
    if cond.startswith("ONLY import of cars, jeeps and light commercial vehicles in CKD"):
        return "veh_exempt", None
    if "plant and machinery" in cond and r.get("clause") == "3(i)":
        return "pm", None
    if cond.startswith("ONLY import under") or cond.startswith("ONLY imports under"):
        return "regime", ACD_REGIME_BY_CLAUSE.get(r.get("clause"))
    return None, None


def make_acd_prefilter(tariff_line: dict, facts: Facts | None, need: list):
    """Row filter for acd_rules. `facts is None` = informational mode (keep rows that depend on facts, but drop
    slab rows that do not fit the code's tariff CD). `need` collects fact names whose absence could change the answer."""
    cd_kind = tariff_line["cd_kind"]
    cd = D(tariff_line["cd_rate"]) if tariff_line["cd_kind"] == "plain" else None

    def f(r):
        kind, arg = acd_kind(r)
        if kind == "slab":
            op, n = arg
            if cd_kind == "compound":
                return "slab_cannot_be_tested_tariff_cd_is_compound"
            if op == "EQ":
                ok = cd is not None and cd == n
            else:  # GE: slab of n% and higher, as well as slabs of specific rates (A3 convention, docs/duty_formula.md section 5)
                ok = (cd is None) or cd >= n
            if not ok:
                have = "specific-rate slab" if cd is None else f"{cd}%"
                return f"slab_mismatch: row needs tariff CD {'=' if op == 'EQ' else '>='} {n}%, this code's tariff CD is {have}"
            return None
        if facts is None:
            return None  # informational: show, the caller decides
        if kind == "regime":
            if arg and arg in facts.regimes():
                return None
            return f"import_regime_not_claimed ({arg}); ordinary import assumed"
        if kind in ("ckd_levy", "veh_exempt"):
            form, cc = facts.vehicle()
            if form is None or cc is None:
                for k in ("goods.vehicle_form", "goods.engine_cc"):
                    if k not in need:
                        need.append(k)
                return "needs_fact: vehicle_form and engine_cc"
            if kind == "ckd_levy":
                ok = form == "CKD" and cc > 1000
            else:
                ok = (form == "CKD" and cc <= 1000) or (form == "CBU" and cc <= 850)
            return None if ok else f"vehicle_facts_do_not_match ({form}, {cc} cc)"
        if kind == "pm":
            v = facts.gb("plant_machinery_for_manufacturing")
            if v is None:
                if "goods.plant_machinery_for_manufacturing" not in need:
                    need.append("goods.plant_machinery_for_manufacturing")
                return "needs_fact: plant_machinery_for_manufacturing"
            return None if v else "not_plant_and_machinery_for_manufacturing"
        return None

    return f


# --------------------------------------------------------------------------- sales tax
_BENIGN = {"", "nil", "none"}
LOCAL_SUPPLY_PREFIX = "[LOCAL SUPPLY"


def st_benign_condition(r: dict) -> bool:
    """True when the row has no condition to check (empty / 'Nil'), or only the SRO 297 standing note about the Eighth Schedule."""
    cond = (r.get("condition_text") or "").strip()
    if cond.lower() in _BENIGN:
        return True
    if r["rule_group"] == "ST-SRO297-T1":
        return True  # the only text is 'Not applicable to goods specified in the Eighth Schedule' (handled by precedence)
    return False


def make_st_prefilter(facts: Facts | None):
    def f(r):
        g = r["rule_group"]
        cond = (r.get("condition_text") or "").strip()
        if cond.startswith(LOCAL_SUPPLY_PREFIX):
            return "local_supply_wording_probably_not_an_import_rule (row needs_review: a human must confirm)"
        if g.startswith("ST-SRO297-T2") or g == "ST-SRO297-T2-1525-HYBRID":
            return "SRO 297 Table-II is a rule for the supply of locally made vehicles, not an import rule (docs/duty_formula.md section 5)"
        if facts is None:
            return None
        if f"sales_tax_rules:{r['id']}" in facts.claimed:
            return None
        if g in ("ST-6TH-T3", "ST-5TH") or (g in ("ST-6TH-T1", "ST-8TH-T1") and not st_benign_condition(r)):
            return f"conditional_rule_not_claimed: {cond[:160]}"
        return None

    return f


# --------------------------------------------------------------------------- RD / misc parsing
def tier_bounds(desc: str):
    """C&F value tier from an RD description: returns (low_exclusive, high_inclusive) in US$, or None if not a tier."""
    d = desc or ""
    m = re.search(r"above US\$\s*([\d,\.]+)[^()]*?not exceeding US\$\s*([\d,\.]+)", d, re.I)
    if m:
        return D(m.group(1)), D(m.group(2))
    m = re.search(r"up to US\$\s*([\d,\.]+)", d, re.I)
    if m:
        return D(0), D(m.group(1))
    m = re.search(r"above US\$\s*([\d,\.]+)", d, re.I)
    if m:
        return D(m.group(1)), None
    return None


_AGE = re.compile(
    r"([\d.]+)%\s*\(\s*(\d+)\s*to\s*(\d+)\s*years old\s*\)\s*and\s*([\d.]+)%\s*\(\s*Above\s*(\d+)\s*years old\s*\)", re.I
)


def age_rate(raw: str, age):
    """Parse '10% (5 to 10 years old) and 20% (Above 10 years old)'. Returns percent Decimal or None if the age is not covered."""
    m = _AGE.search(raw or "")
    if not m or age is None:
        return None
    lo, hi, r1, r2, over = D(m.group(2)), D(m.group(3)), D(m.group(1)), D(m.group(4)), D(m.group(5))
    a = D(age)
    if lo <= a <= hi:
        return r1
    if a > over:
        return r2
    return None


def norm_unit(u: str | None) -> str:
    u = (u or "").strip().lower()
    u = re.sub(r"^(rs\.?\s*)?(per\s+)?", "", u)
    return {"kgs": "kg", "kilogram": "kg", "kilograms": "kg", "sets": "set", "mts": "mt", "tonne": "mt",
            "meters": "meter", "metre": "meter", "metres": "meter", "minutes": "minute", "mins": "minute"}.get(u, u)


# --------------------------------------------------------------------------- income tax class
def income_tax_class(it_app: list[dict]):
    """Twelfth Schedule class from the rows that matched the code: (class 1|2|3|None, row, problem).

    Part I and Part II are tested first; the most specific entry wins; a tie between Part I and Part II is a problem
    (not guessed). No match at all = Part III, the residual class (docs/duty_formula.md OPEN-9)."""
    p = {1: [r for r in it_app if r["rule_group"] == "IT-12TH-P1"], 2: [r for r in it_app if r["rule_group"] == "IT-12TH-P2"]}
    lvl = {n: max((len(r["code_norm"]) for r in p[n]), default=-1) for n in (1, 2)}
    if lvl[1] < 0 and lvl[2] < 0:
        return 3, None, None
    if lvl[1] == lvl[2]:
        return None, None, "the code matches both Twelfth Schedule Part I and Part II at the same level"
    cls = 1 if lvl[1] > lvl[2] else 2
    return cls, max(p[cls], key=lambda r: len(r["code_norm"])), None
