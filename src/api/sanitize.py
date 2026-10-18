"""Safety net for user-facing text: remove internal repository references from API replies.

Users should see legal citations (Act, section, schedule, SRO), never repo paths such as docs/duty_formula.md or
data/raw, or internal file names (.md, .csv, .json, .py). The tool strings are written without them; this catches any
that come back from data or slip in later. Only the text changes; no number, code or key is touched.
PDF names in `source_file` are the FBR source documents (citations) and are kept.
"""
from __future__ import annotations

import re

# docs/ and src/ in any form; data/ only for the repo's own folders, so legal wording like "data/information" is kept
_PATH = (r"(?<![\w/])(?:(?:docs|src)/(?:[\w.\-()]*[\w]/?)*"
         r"|data/(?:raw|processed|ground_truth)\b(?:/[\w.\-()]*[\w])*/?)")
_FILE = r"[\w\-]+\.(?:md|csv|jsonl?|sqlite|py|ipynb)\b"
_REF = re.compile(rf"(?:{_PATH}|{_FILE})(?:\s+(?:step|section|§)\s*[\w.\-]+)?", re.IGNORECASE)


def clean_text(s: str) -> str:
    """Drop internal references and tidy the brackets and spaces they leave behind."""
    if not _REF.search(s):
        return s
    out = _REF.sub("", s)
    out = re.sub(r"\(\s*[,;]?\s*", "(", out)
    out = re.sub(r"\s*[,;]\s*\)", ")", out)
    out = re.sub(r"\s*\(\s*\)", "", out)
    out = re.sub(r"\s+([.,;:])", r"\1", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


def scrub(obj):
    """Clean every string value in a JSON-like reply (dict keys are left alone)."""
    if isinstance(obj, str):
        return clean_text(obj)
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [scrub(v) for v in obj]
    return obj
