"""Label consensus for the importer GD cases, computed in memory from the private extract (no importer identity is written anywhere).

A case's label is `consensus` if its normalised description was typed by at least two different importers and all of them used the same 8-digit code;
`conflicted` if at least two importers used different codes for it; `single` if only one importer (or one line) used these words.
The consensus subset is the most trustworthy part of the answer key: independent importers agreed, and no AI is involved.
"""
from __future__ import annotations

import collections
import re

from .gd_data import load


def normalise(text: str) -> str:
    t = re.sub(r"^\(?\d+\)?[.\-\s]+", "", str(text).upper())
    t = re.sub(r"[^A-Z ]+", " ", t)
    t = re.sub(r"\b(NET|WT|WEIGHT|APPROX|PCS|KGS|KG|QTY|SET|SETS|NO|NOS|MODEL|SPARE|PARTS|PART)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def label_status() -> dict[str, str]:
    """normalised description -> 'consensus' | 'conflicted' | 'single'."""
    groups: dict[str, list[tuple]] = collections.defaultdict(list)
    for r in load():
        if r.get("TYPE") == "HC" and r["code8"]:
            k = normalise(r["desc_clean"])
            if len(k) >= 8:
                groups[k].append((r["NTN"], r["code8"]))
    out = {}
    for k, v in groups.items():
        if len({n for n, _ in v}) < 2:
            out[k] = "single"
        else:
            out[k] = "consensus" if len({c for _, c in v}) == 1 else "conflicted"
    return out


def case_status(descriptions: dict[str, str]) -> dict[str, str]:
    """{case id: raw description} -> {case id: status}; an unknown description counts as 'single'."""
    st = label_status()
    return {cid: st.get(normalise(re.sub(r"\s+", " ", d)), "single") for cid, d in descriptions.items()}
