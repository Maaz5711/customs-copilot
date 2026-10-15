"""Metrics for the evaluation (C2). Pure functions, no network.

* top-k at 4, 6 and 8 digits: a prediction hits at level L if one of the first k predicted codes shares the first L digits with the
  expected code (or an accepted alternative). A case whose expected code is shorter than L is not scored at L (n differs per level).
* citation correctness: each citation points at a real fact row (tariff line on the date, or a store row for that file and page).
  This checks that the pointer is real, not that the legal claim is right.
* duty match: the system's bill totals equal a hand-computed bill, to the paisa.
* refusal quality: for 'not_sure_or_clarify' and 'refuse' cases: did the system pick the right behaviour, did a not-sure answer show
  candidates that include the expected heading, and did an 'answer' case wrongly refuse/hedge.
"""
from __future__ import annotations

from decimal import Decimal
from math import sqrt


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for k successes in n trials. (0, 0) when n == 0."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def hit_at(pred_codes: list[str], expected: list[str], level: int, k: int) -> bool | None:
    """None = not scorable (expected code shorter than the level). expected = [main] + accepted alternatives."""
    exp = [e for e in expected if e]
    if not exp or len(exp[0]) < level:
        return None
    want = {e[:level] for e in exp if len(e) >= level}
    return any(c[:level] in want for c in pred_codes[:k] if len(c) >= level)


def code_metrics(rows: list[dict]) -> dict:
    """rows: [{'expected': [..], 'pred': [..]}] -> {(k, level): (hits, n)}."""
    out = {}
    for k in (1, 5):
        for level in (4, 6, 8):
            hits = n = 0
            for r in rows:
                h = hit_at(r["pred"], r["expected"], level, k)
                if h is None:
                    continue
                n += 1
                hits += bool(h)
            out[(k, level)] = (hits, n)
    return out


def refusal_metrics(rows: list[dict]) -> dict:
    """rows: [{'expected_behavior', 'behavior', 'pred', 'candidate_headings'}]. behavior in answer / not_sure_or_clarify / refuse."""
    res = {}
    for exp in ("not_sure_or_clarify", "refuse", "answer"):
        sub = [r for r in rows if r["expected_behavior"] == exp]
        ok = sum(1 for r in sub if r["behavior"] == exp)
        res[exp] = (ok, len(sub))
    ns = [r for r in rows if r["expected_behavior"] == "not_sure_or_clarify" and r["behavior"] == "not_sure_or_clarify" and r.get("candidate_headings")]
    shown = sum(1 for r in ns if any(c[:4] in {h[:4] for h in r["candidate_headings"]} for c in r["pred"][:3]))
    res["not_sure_shows_right_heading"] = (shown, len(ns))
    return res


def duty_match(system_totals: dict | None, truth_total: str, tol: Decimal = Decimal("0.01")) -> bool:
    if not system_totals:
        return False
    got = system_totals.get("total_payable_pkr") or system_totals.get("total")
    try:
        return abs(Decimal(str(got)) - Decimal(truth_total)) <= tol
    except Exception:
        return False
