# A4 findings: legal notes (GRI, Section, Chapter, Subheading)

Source: `data/raw/2022711271427852PakistanCustomsTariff.pdf` (602 pages, text layer, "The First Schedule (Pakistan Customs Tariff)"). Parser: `src/ingest/parse_legal_notes.py`. Output: `data/processed/legal_notes.json` and `.csv`, structure map `legal_notes_structure.json`, spot-check sheet `spotcheck_legal_notes.csv`. Tests: `tests/test_legal_notes.py`.

These are the legal texts printed in the Pakistan tariff itself. No WCO Explanatory Notes were copied. The tariff's own "Pakistan Rules" name the Explanatory Notes as an authentic source of interpretation; cite them by reference only.

## Counts (484 records)
| kind | records | scopes |
|---|---|---|
| gri (Rules 1-6) | 6 | pp. 8-9 |
| gri_pakistan (Pakistan Rules 1-2) | 2 | p. 9 |
| section_note | 45 | 9 sections: I(2), II(1), IV(1), VI(4), VII(2), XI(15), XV(9), XVI(6), XVII(5) |
| chapter_note | 355 | 86 chapters of 1-97, plus Chapter 99 (3 notes) and Chapter 99 Sub-chapter I (1 note) |
| subheading_note | 76 | 36 chapters plus Section XI (2 notes) |

Record fields: `note_id, kind, section_or_chapter, section, note_number, text, page, page_end, source_file, char_repaired, flags`. `page` is the PDF page (1-based) where the note starts.

## Completeness
- Structure: all 21 section headers and all chapter headers 1-99 were found in order. Chapter 77 is printed as "Reserved". Chapters 98 and 99 are Pakistan-specific.
- Sections with no notes in this PDF: III, V, VIII, IX, X, XII, XIII, XIV, XVIII, XIX, XX, XXI. The PDF's own table of contents lists "Section Note(s)" for exactly the nine sections we extracted (I, II, IV, VI, VII, XI, XV, XVI, XVII), so these are not parser misses.
- Chapters 1-97 with no chapter notes: 43, 50, 52, 53, 75, 76, 77 (reserved), 78, 79, 80, 81. Chapters 52, 75, 76, 78, 79, 80 have subheading notes only. I believe this matches the WCO HS 2022 text, but I did not have the WCO text to compare. Maaz should check this list.
- Numbering is continuous (1, 2, 3 ... no gap) in every scope; a test enforces it. An earlier run missed items written as "3 - " and inline "4.-"; this was fixed, and Chapter 85 went from 3 to 12 notes. A scan for the next expected number inside each note text found no other hidden items.

## Things that look wrong or fragile (all are in the spot-check sheet)
- 5 notes contain tables that the text layer flattens into a stream of numbers (flag `table_flattened`): Chapter 11 note 2 (milling yields, p. 50), Chapter 48 subheading notes 1 and 2 (paper strength tables, p. 231), Chapter 74 note 1 (pp. 365-366), Chapter 78 subheading note 1 (refined lead limits, p. 376). The prose is fine. The table values are NOT reliable. Do not use those numbers without checking the PDF page.
- Chapter 37 note 1 is a real one-liner (flagged `very_short` only because of its length).
- 67 notes span two or more pages and are joined across the page break (page number lines dropped). Section XV note 9, Chapter 72 note 1 and Chapter 85 note 2 are very long (up to about 7,500 characters). Lists inside notes keep "(a)", "(b)" on new lines.
- Chapter 99 notes are Pakistan-specific conditions, not WCO text. Only the chapter notes and the Sub-chapter I note on p. 585 were extracted. Later sub-chapter conditions (privileged persons, baggage, and so on) sit inside the tables on pp. 586-602 and were NOT extracted (out of A4 scope).
- Chapter 98 (Services, p. 580) has no notes and no CD rates.
- Quote marks, degree signs and superscripts came out as correct Unicode in this PDF (no replacement characters found).

## Edition check: is this HS 2022?
Yes, with high confidence. Evidence in the PDF itself:
- Heading 24.04 (products for inhalation without combustion, nicotine products) exists and Section IV's title includes it. This heading is new in HS 2022.
- Chapter 85 note 5 defines "smartphones" for heading 85.17 and note 6 defines solid-state storage devices for 85.23. These are HS 2022 notes.
- Chapter 15 mentions "microbial fats and oils", and heading 15.19 is shown deleted as "[15.19]". Both are HS 2022 changes.
- The PDF never prints "HS 2022" or a Finance Act year. File metadata shows creation date 2023-07-29 (producer PDFium); the filename prefix suggests an upload on 2022-07-11. CLAUDE.md calls it the FY2022-23 tariff. So the print year is uncertain. It is a Pakistan tariff built on HS 2022. Treat "FY2022-23" as unconfirmed.

## Relation to the FY2026-27 and FY2025-26 tariffs
- The FY2026-27 and FY2025-26 tariff PDFs contain only rate tables. They have no GRI, Section Notes or Chapter Notes. So there is nothing to diff note by note; this older PDF is the only source of notes for both years.
- Hard rule 1 needs `valid_from` and `valid_to`. Proposal: store these notes as "edition HS 2022, applicability to FY2025-26 and FY2026-27 assumed, not proven". Maaz to decide the dates.
- Nomenclature comparison (codes printed in the notes PDF vs `tariff_2026_27.csv`): 4-digit headings agree (the old PDF has 6 extra: 98.01 to 98.05 services, and 11.03, see the bug below). The old PDF has 7,615 eight-digit codes (including chapter 98); FY2026-27 has 7,605. 14 old codes are gone and 42 new codes appear, in chapters 11, 12, 27, 29, 32, 38, 39, 44, 48, 55, 63, 84, 85, 87, 90, 94 (plus 38 chapter 98 service codes only in the old PDF). They look like Pakistan national subdivisions of 8-digit lines (for example 1201.1000 became 1201.1010, .1020, .1090; 6309.0000 became 6309.1010, .1020, .1090). Apart from those splits the HS 6-digit structure is the same, so the edition is the same.
- Chapters whose notes may have changed since this PDF: none can be proven from our files. Two things to check by hand: (1) any Finance Act 2023-2026 amendment to First Schedule notes (a keyword search of Finance Acts 2025 and 2026 found none, but that search is weak); (2) the WCO HS 2027 amendments, which I understand are due to take effect on 1 January 2027, inside FY2026-27. Whether Pakistan adopts them mid-year is not stated in any file we hold, and I did not verify it. Check the FBR website. If Pakistan does adopt HS 2027, many notes and codes change.
- If notes were revised, the first chapters to look at are those with national code changes: 11, 12, 27, 29, 32, 38, 39, 44, 48, 55, 63, 84, 85, 87, 90, 94.

## Bug seen in A1 data (not fixed here, not an A4 file)
In `data/processed/tariff_2026_27.csv`, codes 1103.1100, 1103.1300, 1103.1900 and 1103.2000 carry heading `11.02`, and heading `11.03` is missing. Worth checking in A1.

## What Maaz must check
1. Open `data/processed/spotcheck_legal_notes.csv` (80 rows, 17% of records: all GRI, all flagged notes, all multi-page notes, plus a seeded random sample). Fill "correct? (Y/N)".
2. Check the 5 table notes against PDF pages 50, 231, 365-366 and 376.
3. Check the lists of sections and chapters without notes against the WCO HS 2022 text.
4. Decide the validity dates for the notes (see above).
5. Decide whether the Chapter 99 sub-chapter conditions (pp. 586-602) are in scope.
