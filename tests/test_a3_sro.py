"""A3 tests: SRO chain and SRO-derived sales tax / income tax rows (counts are from the page images and OCR text)."""
import csv
import json
from collections import Counter
from pathlib import Path

P = Path("data/processed")


def rules():
    return list(csv.DictReader(open(P / "a3_sro_rules.csv", encoding="utf-8")))


def instruments():
    return {r["sro_number"]: r for r in csv.DictReader(open(P / "a3_instruments.csv", encoding="utf-8"))}


def test_every_row_has_dates_source_page():
    for r in rules():
        assert r["valid_from"] and r["valid_to"] and r["source_file"] and int(r["page"]) >= 1, r["rule_id"]
        assert r["valid_to"] >= r["valid_from"], r["rule_id"]
        assert r["clause"], r["rule_id"]


def test_sro297_table1_counts():
    t1 = [r for r in rules() if r["rule_group"] == "ST-SRO297-T1"]
    assert len({r["s_no"] for r in t1}) == 36            # serials 1..36 all present
    c = Counter(r["match_level"] for r in t1)
    assert c == {"code8": 468, "chapter2": 4, "heading4": 4, "unmapped": 2}
    assert all(float(r["rate_pct"]) == 25.0 for r in t1)
    # S.No 18 keeps the two 'except' codes as exceptions, not as rule rows
    s18 = [r for r in t1 if r["s_no"] == "18"]
    assert len(s18) == 1 and json.loads(s18[0]["except_codes"]) == ["08011910", "08011200"]


def test_sro297_known_printing_problems_are_flagged_not_fixed():
    flagged = {r["code_raw"]: r["issues"] for r in rules() if r["rule_group"] == "ST-SRO297-T1" and r["issues"]}
    assert "code_format" in flagged["8703,3139"]
    assert "code_not_in_tariff" in flagged["7234.2900"]
    assert "code_not_in_tariff" in flagged["9403.5030"]
    assert "code_not_in_tariff" in flagged["9004.9000"]
    assert "84145190" in flagged and "84182190" in flagged
    assert "1704.9010" in flagged and "page image prints" in flagged["1704.9010"]


def test_chain_links_exist_and_663_rescinds_455_and_527():
    ins = instruments()
    assert ins["663(I)/2026"]["amends_or_supersedes"] == "455(I)/2026; 527(I)/2026"
    assert ins["455(I)/2026"]["status"] == "rescinded" and ins["527(I)/2026"]["status"] == "rescinded"
    assert ins["1832(I)/2025"]["amends_or_supersedes"] == "1217(I)/2025"
    assert ins["1833(I)/2025"]["amends_or_supersedes"] == "1216(I)/2025"
    assert ins["370(I)/2024"]["amends_or_supersedes"] == "297(I)/2023"
    assert ins["1525(I)/2026"]["issue_date"] == "2026-09-13"
    assert ins["1065(I)/2026"]["amends_or_supersedes"] == "1898(I)/2025"


def test_sugar_chain_dates():
    r = {x["rule_group"] + x["valid_from"]: x for x in rules() if x["rule_group"] in ("ST-SRO1217-SUGAR", "IT-9AD-SUGAR", "CU-1215-SUGAR")}
    a = r["ST-SRO1217-SUGAR2025-07-08"]       # SRO 1217 as issued: cut-off 30 Sep 2025, window ends the day before SRO 1832 (22 Sep)
    assert a["valid_to"] == "2025-09-21" and a["rate_pct"] == "0.25" and a["status"] == "accepted"
    b = r["ST-SRO1217-SUGAR2025-09-22"]       # SRO 1832: 'September' -> 'November' (cut-off 30 Nov 2025)
    assert b["valid_to"] == "2025-11-30" and b["status"] == "accepted"
    c = r["ST-SRO1217-SUGAR2026-03-19"]       # SRO 527 issued 19 Mar 2026 (after its own cut-off), rescinded 22 Apr 2026
    assert c["valid_to"] == "2026-04-21" and c["status"] == "needs_review" and "DOUBTFUL" in c["issues"]
    d = r["ST-SRO1217-SUGAR2026-04-22"]
    assert d["valid_to"] == "9999-12-31" and d["rate_kind"] == "conditional" and d["status"] == "needs_review"
    assert (r["IT-9AD-SUGAR2025-07-08"]["valid_to"], r["IT-9AD-SUGAR2025-09-22"]["valid_to"]) == ("2025-09-21", "2025-11-30")
    assert (r["CU-1215-SUGAR2025-07-08"]["valid_to"], r["CU-1215-SUGAR2025-09-22"]["valid_to"]) == ("2025-09-21", "2025-11-30")
    assert not [k for k in r if k.startswith("CU-1215-SUGAR2025-12") or k.startswith("CU-1215-SUGAR2026")]   # no customs extension in data/raw


def test_table2_is_local_supply_only_and_split_at_sro_1525():
    t2 = [r for r in rules() if r["rule_group"] == "ST-SRO297-T2"]
    assert len(t2) == 6
    assert {r["valid_to"] for r in t2} == {"2026-09-12", "9999-12-31"}
    assert all("LOCAL SUPPLY ONLY" in r["condition_text"] for r in t2)
