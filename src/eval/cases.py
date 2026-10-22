"""Load the ground-truth cases (data/ground_truth) into one common shape for the evaluation (C2).

Real and synthetic cases are never mixed in a number: every Case carries `kind` ('real' or 'synthetic').
Real cases are scored on code only (they have no refusal behaviour). Synthetic cases also carry expected_behavior.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

GT = Path("data/ground_truth")


@dataclass
class Case:
    id: str
    kind: str                      # 'real' | 'synthetic'
    description: str
    as_of_date: str
    behavior: str                  # 'answer' | 'not_sure_or_clarify' | 'refuse'
    expected: str = ""             # digits only, 4, 6 or 8 long ('' when no code is expected)
    alt_codes: list[str] = field(default_factory=list)
    source_file: str = ""          # real cases: basename of the ruling PDF the case came from (leak control)
    ruling_kind: str = ""
    candidate_headings: list[str] = field(default_factory=list)
    split: str = ""                 # catalogue cases only: 'dev' (tune on it) or 'test' (report on it, never tune)
    confidence: str = ""            # catalogue cases only: writer's confidence in the label, 'H' or 'M'

    @property
    def level(self) -> int:
        return len(self.expected)


def digits(code: str) -> str:
    return re.sub(r"\D", "", code or "")


def _basename(url: str) -> str:
    return (url or "").rstrip("/").split("/")[-1]


def load_cases(kinds=("real", "synthetic"), gt_dir: Path = GT) -> list[Case]:
    out: list[Case] = []
    if "real" in kinds:
        for r in csv.DictReader(open(gt_dir / "cases_real.csv", encoding="utf-8")):
            out.append(Case(id=r["id"], kind="real", description=r["description"], as_of_date=r["as_of_date"], behavior="answer",
                            expected=digits(r["expected_code"]), source_file=_basename(r["source_url"]), ruling_kind=r["ruling_kind"]))
    if "catalog" in kinds and (gt_dir / "cases_catalog.csv").exists():
        for r in csv.DictReader(open(gt_dir / "cases_catalog.csv", encoding="utf-8")):
            out.append(Case(id=r["id"], kind="catalog", description=r["description"], as_of_date=r["as_of_date"], behavior="answer",
                            expected=digits(r["expected_code"]), split=r["split"], confidence=r["label_confidence"]))
    if "synthetic" in kinds:
        for r in csv.DictReader(open(gt_dir / "cases_synthetic.csv", encoding="utf-8")):
            alts = [digits(x) for x in re.split(r"[;|,\s]+", r["alt_acceptable_codes"] or "") if digits(x)]
            heads = [digits(x) for x in re.split(r"[;|,\s]+", r["candidate_headings"] or "") if digits(x)]
            out.append(Case(id=r["id"], kind="synthetic", description=r["description"], as_of_date=r["as_of_date"],
                            behavior=r["expected_behavior"], expected=digits(r["expected_code"]), alt_codes=alts,
                            candidate_headings=heads))
    return out


def load_duty_cases(gt_dir: Path = GT) -> list[Case]:
    """Hand-computed bills (duty_cases.csv). behavior 'answer'; `expected` is the code; the expected total is read by report.py."""
    out = []
    f = gt_dir / "duty_cases.csv"
    if f.exists():
        for r in csv.DictReader(open(f, encoding="utf-8")):
            out.append(Case(id=r["id"], kind="duty", description=r["question"], as_of_date=r["as_of_date"], behavior="answer",
                            expected=digits(r["expected_code"])))
    return out


IMPORTER_CASES = Path("data/raw/importer_data/cases_importer.csv")        # private (gitignored): derived from an importer's GD extract, see src/eval/gd_data.py


def load_importer_cases(path: Path = IMPORTER_CASES) -> list[Case]:
    """Real cleared Goods Declaration lines (Chapter 85, Feb 2026): description as typed by the clearing agent, the declared 8-digit code, the GD date."""
    out = []
    if path.exists():
        for r in csv.DictReader(open(path, encoding="utf-8")):
            out.append(Case(id=r["id"], kind="importer", description=r["description"], as_of_date=r["as_of_date"], behavior="answer", expected=digits(r["expected_code"])))
    return out
