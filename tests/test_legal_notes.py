"""A4 tests: legal notes from the FBR First Schedule PDF (HS 2022). Skip if the PDF is absent."""
import collections
from pathlib import Path

import pymupdf
import pytest

from src.ingest import parse_legal_notes as P

pytestmark = pytest.mark.skipif(not P.SRC.exists(), reason="raw legal-notes PDF not present")

NO_CHAPTER_NOTES = {43, 50, 52, 53, 75, 76, 77, 78, 79, 80, 81}  # 77 is reserved
SECTIONS_WITH_NOTES = {"Section " + s for s in ["I", "II", "IV", "VI", "VII", "XI", "XV", "XVI", "XVII"]}


@pytest.fixture(scope="module")
def parsed():
    pages = [p.get_text() for p in pymupdf.open(P.SRC)]
    notes, struct = P.parse_notes(pages)
    return P.parse_gri(pages), notes, struct


def test_gri(parsed):
    gri, _, _ = parsed
    assert [r["note_number"] for r in gri if r["kind"] == "gri"] == ["1", "2", "3", "4", "5", "6"]
    assert len([r for r in gri if r["kind"] == "gri_pakistan"]) == 2
    assert all(r["page"] in (8, 9) for r in gri)


def test_structure(parsed):
    _, _, struct = parsed
    assert len(struct["sections"]) == 21
    assert [c["chapter"] for c in struct["chapters"]] == list(range(1, 100))


def test_section_notes(parsed):
    _, notes, _ = parsed
    sec = collections.Counter(r["section_or_chapter"] for r in notes if r["kind"] == "section_note")
    assert set(sec) == SECTIONS_WITH_NOTES
    assert sum(sec.values()) == 45
    assert sec["Section XI"] == 15 and sec["Section XV"] == 9


def test_chapter_notes(parsed):
    _, notes, _ = parsed
    ch = {r["section_or_chapter"] for r in notes if r["kind"] == "chapter_note"}
    have = {int(c.split()[1].rstrip(",")) for c in ch}
    assert {c for c in range(1, 98)} - have == NO_CHAPTER_NOTES
    assert 99 in have
    counts = collections.Counter(r["section_or_chapter"] for r in notes if r["kind"] == "chapter_note")
    assert counts["Chapter 85"] == 12 and counts["Chapter 84"] == 11 and counts["Chapter 39"] == 11


def test_numbering_is_continuous(parsed):
    _, notes, _ = parsed
    by = collections.defaultdict(list)
    for r in notes:
        by[(r["kind"], r["section_or_chapter"])].append(r["note_number"])
    for k, v in by.items():
        assert v == [str(i) for i in range(1, len(v) + 1)], k


def test_no_empty_text(parsed):
    gri, notes, _ = parsed
    assert all(len(r["text"]) > 30 for r in gri + notes if "very_short" not in r["flags"])
    assert all(r["source_file"] == P.SRC_NAME and r["page"] >= 8 for r in gri + notes)
