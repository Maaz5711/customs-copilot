"""A1 fix: sub-group header lines (no code, no duty cell) belong to the rows printed AFTER them.

Checked against the page images (FY2026-27 pages 267, 214, 110; FY2025-26 pages 267, 214, 111).
The safety test compares codes, duties, pages and counts with the JSON committed before the fix.
"""
import json
import subprocess
from pathlib import Path

import pytest

from src.ingest import run_tariff
from src.ingest.tariff_description_changes import BASELINE_REV

PDFS = {fy: Path("data/raw") / run_tariff.TARIFFS[fy][0] for fy in ("2026_27", "2025_26")}
pytestmark = pytest.mark.skipif(not all(p.exists() for p in PDFS.values()), reason="raw tariff PDFs not present")


@pytest.fixture(scope="module", params=["2026_27", "2025_26"])
def parsed(request):
    fy = request.param
    h, r, s = run_tariff.run(fy)
    return fy, h, r, s


def _baseline(fy):
    try:
        out = subprocess.run(["git", "show", f"{BASELINE_REV}:data/processed/tariff_{fy}.json"],
                             capture_output=True, check=True).stdout
    except Exception:
        pytest.skip("git baseline not available")
    return json.loads(out.decode("utf-8"))


def test_codes_duties_pages_counts_unchanged(parsed):
    fy, h, r, s = parsed
    old = _baseline(fy)
    assert len(r) == len(old["rows"]) == (7605 if fy == "2026_27" else 7590)
    assert len(h) == len(old["headings"]) == 1228
    assert sum(1 for x in r if x["cd_kind"] == "specific") == 54
    keys = ["code", "heading", "cd_raw", "cd_plain", "cd_specific", "cd_kind", "rotated", "source_file", "page"]
    assert [{k: x[k] for k in keys} for x in r] == [{k: x[k] for k in keys} for x in old["rows"]]
    assert [(x["heading"], x["page"], x.get("derived_from_code")) for x in h] == \
        [(x["heading"], x["page"], x.get("derived_from_code")) for x in old["headings"]]
    assert [(x["code"], x["description"], x["cd_raw"], x["page"]) for x in s] == \
        [(x["code"], x["description"], x["cd_raw"], x["page"]) for x in old["special"]]


def test_new_fields_present(parsed):
    _, _, r, _ = parsed
    for x in r:
        assert x["own_description"] and x["full_description"].endswith(x["own_description"].rstrip(": "))
        assert isinstance(x["parent_chain"], list) and x["dash_depth"] >= 0
        assert x["description"].endswith(x["own_text"])


def _full(r):
    return {x["code"]: x["full_description"] for x in r}


@pytest.mark.parametrize("code,needle,other", [
    ("8703.4019", "not exceeding 850cc", "850cc but not exceeding 1000cc"),
    ("8703.4029", "exceeding 850cc but not exceeding 1000cc", "1,000cc but not exceeding 1,500cc"),
    ("8703.4039", "exceeding 1,000cc but not exceeding 1,500cc", "1,800 cc"),
    ("8703.4049", "exceeding 1,500 cc but not exceeding 1,800 cc", "1,000cc but not exceeding 1,500cc"),
    ("8703.4059", "exceeding 1,800cc but not exceeding 3,000 cc", "1,500 cc"),
    ("8703.4069", "exceeding 3,000cc", "1,800cc"),
    ("8415.1029", "Self contained or split type", "Window or wall"),
    ("8415.1039", "Tropical MPS multi system unit 5 tonnes capacity and above", "Self contained"),
    ("4011.2091", "Of a kind used on buses or lorries > Other > Radial", "light trucks"),
    ("4011.2011", "Of a kind used in light trucks > Radial", "> Other >"),
])
def test_corrected_descriptions(parsed, code, needle, other):
    _, _, r, _ = parsed
    d = _full(r)[code]
    assert needle in d
    assert other not in d


def test_8703_4019_is_up_to_850cc_not_850_to_1000(parsed):
    _, _, r, _ = parsed
    by = {x["code"]: x for x in r}
    assert by["8703.4019"]["parent_chain"][-1] == "Of a cylinder capacity not exceeding 850cc:"
    assert by["8703.4019"]["own_description"] == "Other"
    assert not by["8703.4019"]["description"].rstrip().endswith(":")  # no header glued to the end
    assert by["8703.4021"]["parent_chain"][-1].startswith("Of a cylinder capacity exceeding 850cc but not")


def test_header_with_no_children_still_attached(parsed):
    """8479.7100 is printed at the same dash depth as its header; the header must still apply."""
    _, _, r, _ = parsed
    assert _full(r)["8479.7100"].endswith("Passenger boarding bridges > Of a kind used in airports")


def test_wrapped_header_across_page_break(parsed):
    """A header can wrap onto the next page (FY2026-27 page 5/6); its text must not be lost."""
    _, _, r, _ = parsed
    d = _full(r)
    assert "Tilapias" in d["0302.7100"] or any("Tilapias" in v for v in d.values())


def test_headings_have_no_glued_subheaders(parsed):
    _, h, _, _ = parsed
    by = {x["heading"]: x for x in h}
    assert "Window or wall type" not in by["84.15"]["text"]
    assert by["84.15"]["text"].startswith("Air conditioning machines")
    assert by["02.05"]["text"].startswith("Meat of horses")
