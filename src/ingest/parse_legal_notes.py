"""A4: extract legal notes (GRI, Section, Chapter, Subheading notes) from the FBR
First Schedule PDF (HS 2022 edition, text layer).

These are the legal texts of the Pakistan Customs Tariff itself. WCO Explanatory Notes
are NOT copied (cite by reference only).
Output: data/processed/legal_notes.json and legal_notes.csv
"""
import csv
import json
import re
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "raw" / "2022711271427852PakistanCustomsTariff.pdf"
OUT = ROOT / "data" / "processed"
SRC_NAME = SRC.name

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII",
         "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI"]
SEC_RE = re.compile(r"^\s*(?:SECTION|Section)\s+([IVX]+)\s*$")
CH_RE = re.compile(r"^\s*Chapter\s+(\d+)\s*$")
NOTE_HDR = re.compile(r"^\s*Notes?\.?\s*$")
SUB_HDR = re.compile(r"^\s*Sub-?\s?heading\s+Notes?\.?\s*$", re.I)
ITEM_RE = re.compile(r"^\s*(\d{1,2})\s*(?:\.\s*-?|-)(?![\d%])\s*(.*)$")
SUBCH_RE = re.compile(r"^\s*SUB-?\s?CHAPTER\s*-?\s*([IVX]+)\s*\.?\s*$", re.I)
PCT_RE = re.compile(r"^\s*PCT(\s+CODE)?\s*$")
SUBITEM_RE = re.compile(r"^\s*\(([a-z]{1,2}|[ivx]+|[A-Z])\)")

FIRST_NOTES_PAGE = 10   # Section I starts here (PDF page, 1-based)
LAST_NOTES_PAGE = 585   # Chapter 99 notes are on this page


def fix_chars(s):
    """Repair U+FFFD (lost curly quotes / degree signs) heuristically."""
    if "�" not in s:
        return s, False
    s = re.sub(r"(?<![A-Za-z0-9])�(?=[A-Za-z0-9])", "“", s)
    s = re.sub(r"(?<=[A-Za-z0-9.,;])�(?=\s|$|[.,;:)])", "”", s)
    s = re.sub(r"(?<=[A-Za-z])�(?=[A-Za-z])", "'", s)
    s = re.sub(r"(?<=\d)\s*�(?=\s*C\b)", "°", s)
    return s, True


def tidy(lines):
    out = []
    for l in lines:
        l = l.strip()
        if not l:
            continue
        out.append(("\n" + l) if (SUBITEM_RE.match(l) and out) else l)
    txt = " ".join(out)
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r" ?\n ?", "\n", txt)
    return txt.strip()


def flags_for(text):
    f = []
    if re.search(r"(?:[\d.,%-]+\s+){9,}[\d.,%-]+\s*$", text) or re.search(r"(?:\s[\d.,%-]+){12,}", text):
        f.append("table_flattened")
    if not re.search(r"[.;:,)\]”\"]\s*$", text) and "table_flattened" not in f:
        f.append("odd_ending")
    if len(text) < 45:
        f.append("very_short")
    return f


def make_rec(kind, scope, num, lines, page, section, page_end=None):
    text, repaired = fix_chars(tidy(lines))
    text = re.sub(r"\s*_{5,}\s*$", "", text)  # trailing rule line
    return dict(kind=kind, section_or_chapter=scope, section=section, note_number=num,
                text=text, page=page, page_end=page_end or page, source_file=SRC_NAME,
                char_repaired=repaired, flags=flags_for(text))


def parse_gri(pages):
    """General Rules, PDF pages 8-9."""
    recs, cur, last, mode = [], None, 0, "gri"

    def flush():
        nonlocal cur
        if cur:
            recs.append(make_rec(cur["kind"], cur["scope"], str(cur["n"]), cur["lines"], cur["page"], ""))
        cur = None

    for pno in (8, 9):
        for l in pages[pno - 1].split("\n")[1:]:
            if l.strip().lower().startswith("pakistan rules"):
                flush(); mode = "pk"; last = 0
                continue
            m = ITEM_RE.match(l)
            if m and int(m.group(1)) == last + 1:
                flush(); last = int(m.group(1))
                kind, scope = ("gri", "GRI") if mode == "gri" else ("gri_pakistan", "Pakistan Rules")
                cur = dict(kind=kind, scope=scope, n=last, page=pno, lines=[m.group(2)])
            elif cur:
                cur["lines"].append(l)
    flush()
    return recs


def parse_notes(pages):
    recs = []
    struct = {"sections": [], "chapters": []}
    sec, ch = None, 0
    in_ch = False   # a chapter header has been seen since the last section header
    zone = False    # between a header and the first PCT table header
    target, cur, last = None, None, 0
    subch = None

    def flush():
        nonlocal cur
        if cur:
            recs.append(make_rec(cur["kind"], cur["scope"], cur["num"], cur["lines"], cur["page"], cur["section"], cur.get("end")))
        cur = None

    for pno in range(FIRST_NOTES_PAGE, LAST_NOTES_PAGE + 1):
        ls = pages[pno - 1].split("\n")
        if ls and ls[0].strip().isdigit():
            ls = ls[1:]
        for l in ls:
            m = SEC_RE.match(l)
            if m and ROMAN.index(m.group(1)) == (0 if sec is None else sec + 1):
                flush(); sec = ROMAN.index(m.group(1)); struct["sections"].append({"section": "Section " + ROMAN[sec], "page": pno}); in_ch = False; zone = True; target = None; last = 0
                continue
            m = CH_RE.match(l)
            # accept only the next chapter in sequence (tables mention "Chapter 87" etc.)
            if m and int(m.group(1)) == ch + 1:
                flush(); ch = int(m.group(1)); struct["chapters"].append({"chapter": ch, "section": "Section " + ROMAN[sec], "page": pno}); in_ch = True; zone = True; target = None; last = 0
                continue
            if PCT_RE.match(l):
                flush(); zone = False; target = None
                continue
            if not zone:
                continue
            m = SUBCH_RE.match(l)
            if m and ch == 99:
                flush(); target = None; last = 0; subch = "Sub-chapter " + m.group(1).upper()
                continue
            if NOTE_HDR.match(l) or SUB_HDR.match(l):
                flush(); last = 0
                sub = bool(SUB_HDR.match(l))
                if in_ch:
                    scope = "Chapter %d" % ch + (", " + subch if (ch == 99 and subch) else "")
                    target = ("subheading_note" if sub else "chapter_note", scope)
                else:
                    target = ("subheading_note" if sub else "section_note", "Section " + ROMAN[sec])
                continue
            if target is None:
                continue
            m = ITEM_RE.match(l)
            sect = "Section " + ROMAN[sec]
            if m and int(m.group(1)) == last + 1:
                flush(); last = int(m.group(1))
                cur = dict(kind=target[0], scope=target[1], num=str(last), page=pno,
                           lines=[m.group(2)], section=sect)
            elif cur:
                cur["lines"].append(l)
                if l.strip():
                    cur["end"] = pno
            elif l.strip():
                cur = dict(kind=target[0], scope=target[1], num="unnumbered", page=pno,
                           lines=[l], section=sect)
    flush()
    return recs, struct


def make_id(r):
    sc = r["section_or_chapter"].replace("Section ", "S").replace("Chapter ", "C").replace(" ", "")
    return f"{r['kind']}:{sc}:{r['note_number']}"


def main():
    pages = [p.get_text() for p in pymupdf.open(SRC)]
    notes, struct = parse_notes(pages)
    recs = parse_gri(pages) + notes
    (OUT / "legal_notes_structure.json").write_text(json.dumps(struct, indent=1), "utf-8")
    for r in recs:
        r["note_id"] = make_id(r)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "legal_notes.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1), "utf-8")
    cols = ["note_id", "kind", "section_or_chapter", "section", "note_number", "page", "page_end",
            "source_file", "char_repaired", "flags", "text"]
    with open(OUT / "legal_notes.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            w.writerow({**r, "text": r["text"].replace("\n", " | ")})
    print(len(recs), "records")


if __name__ == "__main__":
    main()
