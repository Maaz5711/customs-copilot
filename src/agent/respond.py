"""Respond node rendering (C1). Pure code: no LLM, no arithmetic.

Every number in an answer is copied from the tool output (formatted only with thousands separators). LLM-written text is limited to
the short candidate reasons, and those were checked by src/agent/ground.py before they got here.
"""
from __future__ import annotations

import re
from typing import Any

DISCLAIMER = ("This is decision support, not legal advice. The tariff code and every amount must be checked with Pakistan Customs "
              "(or a licensed customs agent) before you rely on them.")
OPEN_END = "9999-12-31"


def conf_text(c: float) -> str:
    """Confidence as 'NN out of 100' so it can never be mistaken for a rate or an amount."""
    return f"{round(float(c) * 100)} out of 100"


def fmt_money(s: Any) -> str:
    """'1000000.00' -> '1,000,000.00'. String formatting only (no float, no rounding)."""
    t = str(s)
    neg = t.startswith("-")
    ip, _, fp = t.lstrip("-").partition(".")
    if ip.isdigit():
        ip = f"{int(ip):,}"
    return ("-" if neg else "") + ip + ("." + fp if fp else "")


def _valid(vf: str | None, vt: str | None) -> str:
    return f"valid {vf} to {'no end date' if vt == OPEN_END else vt}"


def describe_line(ln: dict) -> str:
    r = ln.get("rate") or {}
    k = r.get("kind")
    if k == "percent":
        return f"{r.get('pct')}% of {fmt_money(ln.get('base_pkr'))} ({ln.get('base_label')})"
    if k == "specific":
        return f"Rs {fmt_money(r.get('amount_pkr'))} per {r.get('unit')} x {r.get('quantity')} {r.get('unit')}"
    if k == "exempt":
        return "exempt / not levied"
    return str(r)


def _line_block(i: int, ln: dict) -> list[str]:
    flags = [f for f in ln.get("flags", [])]
    out = [f"  {i}. {ln['label']} [{ln['tax']}]: {describe_line(ln)} = PKR {fmt_money(ln['amount_pkr'])}"]
    src = f"     Source: {ln.get('instrument')}, {ln.get('clause')}; {ln.get('source_file')} p.{ln.get('page')}; {_valid(ln.get('valid_from'), ln.get('valid_to'))}; status {ln.get('status')}"
    out.append(src)
    if flags:
        out.append("     Flags: " + ", ".join(flags))
    if ln.get("assumptions"):
        out.append("     Assumptions: " + ", ".join(ln["assumptions"]))
    if ln.get("note"):
        out.append(f"     Note: {ln['note']}")
    return out


def _status_counts(lines: list[dict]) -> dict:
    c: dict[str, int] = {}
    for ln in lines:
        c[ln.get("status", "?")] = c.get(ln.get("status", "?"), 0) + 1
    return c


def unverified_items(state: dict, duty: dict | None) -> list[str]:
    items = [
        "The tariff code was chosen by an AI model from retrieved tariff text and legal notes, then re-checked by a second AI call and by exact "
        "checks (the code exists on the date; every figure printed here comes from the calculation tool). No customs officer has confirmed it.",
        "The model's confidence figure is its own estimate; it has not been measured against real rulings yet.",
        "Tariff duty rates and the RD, ACD, sales tax and income tax rows were read from PDFs and scanned notifications by parsers and a vision "
        "model, then checked by automatic validators. Only rows with status 'verified' were confirmed by hand.",
        "The assessable value, quantity and importer details are exactly what you told me. I did not check them against customs valuation "
        "rulings, minimum values or your documents.",
    ]
    if duty:
        c = _status_counts(duty.get("lines", []))
        if c.get("needs_review"):
            items.insert(3, f"{c['needs_review']} line(s) of this bill are marked needs_review: the reading failed a check or is an unconfirmed inference. Treat them as doubtful.")
        ids = {a["id"] for a in duty.get("assumptions", [])}
        if "FED" in ids:
            items.append("Federal excise duty is NOT in this bill (its source law is not in the data). For vehicles and other excisable goods the real bill is higher.")
    items.append("Retrieved rulings and public notices (if any are listed under SOURCES) are shown for information and were not applied automatically.")
    return items


def _note_citations(state: dict) -> list[dict]:
    ev = state.get("evidence") or {}
    by_label = {n["label"]: n for n in ev.get("notes", [])}
    cited: list[str] = []
    cand = (state.get("candidates") or [{}])[0]
    for lab in cand.get("evidence", []):
        if lab in by_label and lab not in cited:
            cited.append(lab)
    return [by_label[lab] for lab in cited]


def build_citations(state: dict, duty: dict | None, lookup: dict | None) -> list[dict]:
    out: list[dict] = []
    if lookup and lookup.get("status") == "found":
        out.append({"kind": "tariff", "code": lookup["code"], "fy": lookup.get("fy"), "source_file": lookup.get("source_file"),
                    "page": lookup.get("page"), "valid_from": lookup.get("valid_from"), "valid_to": lookup.get("valid_to")})
    for ln in (duty or {}).get("lines", []) + (duty or {}).get("optional_lines_not_in_total", []):
        if ln.get("tax") == "CD":
            continue            # same tariff row as above
        out.append({"kind": ln["tax"], "instrument": ln.get("instrument"), "clause": ln.get("clause"), "source_file": ln.get("source_file"),
                    "page": ln.get("page"), "valid_from": ln.get("valid_from"), "valid_to": ln.get("valid_to"), "status": ln.get("status"),
                    "rule_id": ln.get("rule_id")})
    for n in _note_citations(state):
        out.append({"kind": "note", "id": n["id"], "scope": n["scope"], "number": n["number"], "source_file": n["source_file"], "page": n["page"]})
    for r in (state.get("evidence") or {}).get("rulings", []):
        out.append({"kind": "ruling", "ruling": r["ruling"], "source_file": r["source_file"], "page": r["page"], "valid_from": r.get("valid_from"),
                    "note": "retrieved as possibly relevant; not applied automatically"})
    return out


def _citation_lines(cites: list[dict]) -> list[str]:
    out, seen = [], set()
    for c in cites:
        k = c["kind"]
        if k == "tariff":
            s = f"Tariff: Pakistan Customs Tariff {c.get('fy')}, PCT {c['code']}: {c['source_file']} p.{c['page']}"
        elif k == "note":
            s = f"Legal note: {c['scope']} note {c['number']}: {c['source_file']} p.{c['page']}"
        elif k == "ruling":
            s = f"Ruling (information only): {c['ruling']}: {c['source_file']} p.{c['page']}"
        else:
            s = f"{k}: {c.get('instrument')}, {c.get('clause')}: {c['source_file']} p.{c['page']}"
        if s not in seen:
            seen.add(s)
            out.append("  - " + s)
    return out


def _header(state: dict) -> list[str]:
    f = state.get("facts") or {}
    return [f"Goods: {f.get('goods_description') or '(see codes given)'}", f"Rules applied as of: {state.get('as_of_date')} ({state.get('date_source') or 'date given'})"]


def _candidate_lines(cands: list[dict], with_reasons: bool = True) -> list[str]:
    out = []
    for i, c in enumerate(cands[:3], 1):
        out.append(f"  {i}. {c['code']} - {c.get('description', '')}")
        out.append(f"     Model confidence: {conf_text(c['confidence'])} (its own estimate). Tariff p.{c.get('page')}, {c.get('source_file')}")
        if with_reasons and c.get("reasons"):
            out.append(f"     Why: {c['reasons']}")
    return out


# --------------------------------------------------------------------------------------------- modes
def render_answer(state: dict, verification: dict | None = None) -> dict:
    duty, lookup = state["duty"], state["lookup"]
    cands = state.get("candidates") or []
    top = cands[0] if cands else {}
    status = "answer" if duty["status"] == "computed" else "cannot_compute"
    lines_out = ["RESULT: " + (f"duty bill for {lookup['code']}" if status == "answer" else f"partial duty bill for {lookup['code']} (some taxes could not be computed)")]
    if status == "answer":
        lines_out.append(f"SUMMARY: total payable PKR {fmt_money(duty['totals']['total_payable_pkr'])} on an assessable value of PKR {fmt_money(duty['inputs']['assessable_value_pkr'])}, "
                         f"rules as of {state.get('as_of_date')}. Read the flags and the list of what is not verified below.")
    lines_out.append("")
    lines_out += _header(state)
    desc = top.get("description") or lookup.get("description")
    lines_out.append(f"Tariff line: {lookup['code']} - {desc}")
    lines_out.append(f"  Source: Pakistan Customs Tariff {lookup.get('fy')}, {lookup.get('source_file')} p.{lookup.get('page')}")
    if state.get("user_code_only"):
        lines_out.append("  The code was given by you; I checked that it exists on that date.")
    elif top:
        lines_out.append(f"  Model confidence in this code: {conf_text(top['confidence'])} (the model's own estimate, not a measured accuracy)")
        if top.get("reasons"):
            lines_out.append(f"  Why this line: {top['reasons']}")
        others = [c for c in cands[1:3]]
        if others:
            lines_out.append("  Other candidates considered: " + "; ".join(f"{c['code']} ({conf_text(c['confidence'])})" for c in others))
    lines_out.append("")
    inp = duty.get("inputs", {})
    lines_out.append(f"DUTY BILL (PKR). Assessable value {fmt_money(inp.get('assessable_value_pkr'))}, as you gave it.")
    for i, ln in enumerate(duty.get("lines", []), 1):
        lines_out += _line_block(i, ln)
    if status == "answer":
        t = duty["totals"]
        lines_out.append(f"  TOTAL PAYABLE: PKR {fmt_money(t['total_payable_pkr'])}")
        lines_out.append(f"    customs duties (CD, RD, ACD): {fmt_money(t['customs_duties'])}; sales tax (ST and value addition tax): {fmt_money(t['sales_tax'])}; income tax: {fmt_money(t['income_tax'])}")
    else:
        lines_out.append("  NO TOTAL IS GIVEN because these items could not be computed:")
        for c in duty.get("cannot_compute", []):
            lines_out.append(f"    - {c['item']}: {c['reason']}")
            if c.get("owner_question"):
                lines_out.append(f"      Open question: {c['owner_question']}")
        lines_out.append(f"  Sum of the lines above that could be computed (NOT the amount payable): PKR {fmt_money(duty.get('partial_total_of_computed_lines_pkr'))}")
    opt = duty.get("optional_lines_not_in_total", [])
    if opt:
        lines_out.append("  NOT in the total (the law's text leaves this open):")
        for ln in opt:
            lines_out.append(f"    - {ln['label']}: {describe_line(ln)} = PKR {fmt_money(ln['amount_pkr'])}. {ln.get('note', '')}".rstrip())
        t = duty.get("totals") or {}
        if t.get("total_if_open_items_apply_pkr"):
            lines_out.append(f"    Total if these also applied: PKR {fmt_money(t['total_if_open_items_apply_pkr'])}")
    lines_out.append("")
    rf = state.get("rules_in_force")
    if rf:
        lines_out.append("NOTIFICATIONS IN FORCE ON THAT DATE (from the rules tool): " + "; ".join(f"{k}: {', '.join(v)}" for k, v in rf.items() if v))
        lines_out.append("")
    if duty.get("flags"):
        lines_out.append("FLAGS FROM THE CALCULATION (needs_review means unconfirmed or failed a check):")
        lines_out += [f"  - {f}" for f in duty["flags"]]
        lines_out.append("")
    if duty.get("assumptions"):
        lines_out.append("ASSUMPTIONS MADE BY THE CALCULATION:")
        lines_out += [f"  - [{a['id']}] {a['text']}" for a in duty["assumptions"]]
        lines_out.append("")
    if duty.get("possible_rules_not_applied"):
        lines_out.append("RULES THAT MIGHT APPLY BUT WERE NOT APPLIED (their conditions are not confirmed):")
        for p in duty["possible_rules_not_applied"]:
            lines_out.append(f"  - {p.get('instrument')} {p.get('clause')}: {p.get('condition') or p.get('why_not_applied')}")
        lines_out.append("")
    if duty.get("notes"):
        lines_out.append("NOTES FROM THE CALCULATION:")
        lines_out += [f"  - {n}" for n in duty["notes"]]
        lines_out.append("")
    lines_out.append("NOT APPLIED / OUT OF SCOPE:")
    lines_out += [f"  - {n}" for n in duty.get("not_applied", [])]
    lines_out.append("")
    cites = build_citations(state, duty, lookup)
    lines_out.append("SOURCES:")
    lines_out += _citation_lines(cites)
    ev = state.get("evidence") or {}
    if ev.get("notes"):
        scopes = sorted({n["scope"] for n in ev["notes"] if n.get("kind") != "gri"}) + (["GRI 1-6"] if any(n.get("kind") == "gri" for n in ev["notes"]) else [])
        lines_out.append("  - Legal notes available to the classifier (HS 2022 text from the Pakistan tariff; applicability to FY2025-26 / FY2026-27 assumed, not proven): " + ", ".join(scopes))
    lines_out.append("")
    unv = unverified_items(state, duty)
    lines_out.append("WHAT IS NOT VERIFIED:")
    lines_out += [f"  - {u}" for u in unv]
    if verification:
        lines_out.append("")
        lines_out.append("CHECKS RUN: " + verification.get("summary", ""))
        for w in verification.get("warnings", []):
            lines_out.append(f"  - warning: {w}")
    lines_out.append("")
    lines_out.append(DISCLAIMER)
    return {"status": status, "text": "\n".join(lines_out), "code": lookup["code"], "description": desc, "as_of_date": state.get("as_of_date"),
            "confidence": top.get("confidence"), "candidates": cands[:3], "bill": {"lines": duty.get("lines", []), "totals": duty.get("totals"),
            "optional_lines_not_in_total": opt, "partial_total_of_computed_lines_pkr": duty.get("partial_total_of_computed_lines_pkr")},
            "citations": cites, "flags": duty.get("flags", []), "assumptions": duty.get("assumptions", []), "unverified": unv,
            "verification": verification, "disclaimer": DISCLAIMER}


def render_not_sure(state: dict) -> dict:
    cands = state.get("candidates") or []
    lines = ["I'm not sure about the tariff code for this product, so I am NOT giving a duty bill.", ""]
    lines += _header(state)
    lines.append("")
    why = state.get("not_sure_reason") or "my checks did not reach enough confidence"
    lines.append(f"Why I stopped: {why}.")
    if state.get("retries"):
        lines.append(f"I re-searched and re-checked {state['retries']} time(s) before giving up.")
    lines.append("")
    if cands:
        lines.append("Top candidates (closest first; confidence is the model's own estimate):")
        lines += _candidate_lines(cands)
    else:
        near = [ln for ln in (state.get("evidence") or {}).get("lines", [])[:3]]
        if near:
            lines.append("No candidate passed the checks. The closest tariff lines found by search (not classified, not checked) are:")
            for i, ln in enumerate(near, 1):
                lines.append(f"  {i}. {ln['code']} - {ln['description']} (tariff p.{ln.get('page')}, {ln.get('source_file')})")
        else:
            lines.append("No tariff line matched the description well enough to suggest one.")
    issues = (state.get("verification") or {}).get("issues") or []
    if issues:
        lines.append("")
        lines.append("What the checks found:")
        lines += [f"  - {i}" for i in issues[:6]]
    decide = state.get("deciding_info")
    lines.append("")
    lines.append("What would help me decide: " + (decide if decide else "more detail about the product (material, composition, what it is used for, new or used, size or power)."))
    lines.append("Please check with Pakistan Customs (or a licensed customs agent) before importing.")
    lines.append("")
    lines.append(DISCLAIMER)
    cites = []
    for c in cands[:3]:
        cites.append({"kind": "tariff", "code": c["code"], "source_file": c.get("source_file"), "page": c.get("page")})
    return {"status": "not_sure", "text": "\n".join(lines), "code": None, "as_of_date": state.get("as_of_date"), "confidence": cands[0]["confidence"] if cands else None,
            "candidates": cands[:3], "bill": None, "citations": cites, "flags": [], "assumptions": [], "unverified": ["No answer was given: the code is uncertain."],
            "verification": state.get("verification"), "disclaimer": DISCLAIMER}


def render_refusal(state: dict) -> dict:
    ref = state.get("refusal") or {}
    lo, hi = ref.get("supported", ("2025-07-01", "2027-06-30"))
    lines = ["I can't answer this question.", "", f"Reason: {ref.get('reason', 'out of scope')}", "",
             f"I only cover dates from {lo} to {hi} (FY2025-26 and FY2026-27), because the tariff, the SROs and the tax rules I use stop there. "
             "I did not search or calculate anything.", "", DISCLAIMER]
    return {"status": "refused", "text": "\n".join(lines), "code": None, "as_of_date": state.get("as_of_date"), "confidence": None, "candidates": [],
            "bill": None, "citations": [], "flags": [], "assumptions": [], "unverified": [], "verification": None, "disclaimer": DISCLAIMER, "refusal": ref}


def render_error(state: dict) -> dict:
    err = state.get("error") or {}
    lines = ["I could not finish this question.", "", f"Problem: {err.get('message', 'unknown error')}", ""]
    cands = state.get("candidates") or []
    if cands:
        lines.append("What I had so far (NOT verified, so no bill is given):")
        lines += _candidate_lines(cands, with_reasons=False)
        lines.append("")
    lines.append("Nothing was computed or presented as a result. Your conversation is saved; you can ask again later in the same thread.")
    lines.append("")
    lines.append(DISCLAIMER)
    return {"status": "error", "text": "\n".join(lines), "code": None, "as_of_date": state.get("as_of_date"), "confidence": None, "candidates": cands[:3],
            "bill": None, "citations": [], "flags": [], "assumptions": [], "unverified": ["Not verified: the run stopped before the checks finished."],
            "verification": None, "disclaimer": DISCLAIMER, "error": err}


def render_needs_input(state: dict) -> dict:
    miss = state.get("unresolved") or []
    lines = ["I can't give a duty bill yet because some details are still missing.", ""]
    lines += _header(state)
    if state.get("chosen_code"):
        lines.append(f"Tariff line being worked on: {state['chosen_code']}")
    lines.append("")
    lines.append("Still needed (the rules cannot be applied without them):")
    for m in miss:
        lines.append(f"  - {m.get('question')}" + (f" (needed because: {m['why']})" if m.get("why") else ""))
    lines.append("")
    lines.append("Ask your clearing agent or the importer for these, then ask again.")
    lines.append("")
    lines.append(DISCLAIMER)
    return {"status": "needs_input", "text": "\n".join(lines), "code": state.get("chosen_code"), "as_of_date": state.get("as_of_date"), "confidence": None,
            "candidates": (state.get("candidates") or [])[:3], "bill": None, "citations": [], "flags": [], "assumptions": [], "unverified": [],
            "verification": None, "disclaimer": DISCLAIMER, "missing": miss}
