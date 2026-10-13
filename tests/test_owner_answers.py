"""Owner answers (owner_tasks-results.csv) applied to the store. Expected values come from the page images / owner reading."""
import json
from pathlib import Path

import pytest

from src.store import connect, get_rule_on_date
from src.store.build import build

PROC = Path("data/processed")


@pytest.fixture(scope="module")
def c(tmp_path_factory):
    path = tmp_path_factory.mktemp("own") / "store.sqlite"
    build(path)
    conn = connect(path)
    yield conn
    conn.close()


def q(c, sql, *a):
    return [tuple(r) for r in c.execute(sql, a)]


def test_sro_dates(c):
    r = {x[0]: x[1:] for x in q(c, "select sro_number, valid_from, valid_to, status, validity_basis from sros")}
    assert r["1065(I)/2026"] == ("2026-06-30", "9999-12-31", "needs_review", "date_line")
    assert r["1898(I)/2025"] == ("2025-10-01", "2026-06-29", "needs_review", "date_line")   # day before 1065 (supersession, para 1)
    assert r["1064(I)/2026"][:2] == ("2026-07-01", "9999-12-31")
    assert r["1152(I)/2025"][:2] == ("2025-07-01", "2026-06-30")
    note = q(c, "select note from sros where sro_number='1065(I)/2026'")[0][0]
    assert "no effective-date clause printed; date line used" in note


def test_used_vehicle_rules(c):
    rows = q(c, "select sro_number, code_norm, rate_pct, status, valid_from, valid_to from rd_rules "
                "where sro_number in ('1898(I)/2025','1065(I)/2026') order by 1,2")
    assert len(rows) == 8
    assert {(r[0], r[2]) for r in rows} == {("1898(I)/2025", 40.0), ("1065(I)/2026", 30.0)}
    assert {r[1] for r in rows} == {"8702", "8703", "8704", "8711"}
    assert all(r[3] == "needs_review" for r in rows)
    on = get_rule_on_date(c, "rd_rules", "87032190", "2026-07-15")
    groups = {x["rule_group"] for x in on}
    assert "1065(I)/2026" in groups and "1898(I)/2025" not in groups      # in addition to 1064, replaces 1898
    assert "1898(I)/2025" in {x["rule_group"] for x in get_rule_on_date(c, "rd_rules", "87032190", "2026-01-15")}


def test_respective_headings_mapped(c):
    rows = q(c, "select sro_number, s_no, code_norm, match_level, rate_kind, rate_pct, rate_specific_amount, rate_specific_unit, status, issues "
                "from rd_rules where s_no in ('686','687','692','693') and description in ('Plums (allocha)','Cinematographic film') order by 1,2")
    assert [(r[0], r[1], r[2], r[3]) for r in rows] == [
        ("1064(I)/2026", "686", "08134050", "code8"), ("1064(I)/2026", "687", "3706", "heading4"),
        ("1152(I)/2025", "692", "08134050", "code8"), ("1152(I)/2025", "693", "3706", "heading4")]
    assert rows[0][4:6] == ("percent", 20.0) and rows[2][4:6] == ("percent", 28.0)
    assert rows[1][4:8] == ("specific", None, 2400.0, "per minute") and rows[3][6:8] == (3000.0, "per minute")
    assert all(r[8] == "accepted" and "description read by owner" in r[9] for r in rows)
    assert q(c, "select count(*) from rd_rules where match_level='unmapped'") == [(0,)]


def test_plums_unique_in_both_tariffs(c):
    for fy in ("FY2025-26", "FY2026-27"):
        assert q(c, "select code from tariff_lines where fy=? and description like '%Plums (allocha)%'", fy) == [("0813.4050",)]


def test_twelfth_schedule_5503(c):
    rows = q(c, "select code_norm, clause from income_tax_rules where clause like '%Twelfth Schedule Part II%' and (code_norm in ('54032010','55032010'))")
    assert [r[0] for r in rows] == ["55032010"]
    assert "5503.2010" in rows[0][1]
    assert q(c, "select count(*) from tariff_lines where code_norm='55032010' and fy='FY2026-27'") == [(1,)]
    assert q(c, "select count(*) from income_tax_rules where code_norm='7204'") == [(1,)]


def test_note_tables(c):
    def tj(kind, scope, no):
        t, st = q(c, "select table_json, status from legal_notes where note_kind=? and scope=? and note_no=?", kind, scope, no)[0]
        return json.loads(t), st
    t, st = tj("chapter_note", "Chapter 11", "2")
    assert t["rows"][3] == ["Maize (corn) and grain sorghum", 45, 2, None, 90] and st == "accepted"
    t, _ = tj("subheading_note", "Chapter 48", "1")
    assert t["rows"] == [[115, 393], [125, 417], [200, 637], [300, 824], [400, 961]]
    t, st = tj("subheading_note", "Chapter 48", "2")
    assert [r[1] for r in t["rows"]] == [700, 830, 965, 1230, 1425] and t["source_typo"]["printed"] == "12,30" and st == "needs_review"
    # the flattened original text is kept
    assert "12,30" in q(c, "select text from legal_notes where scope='Chapter 48' and note_kind='subheading_note' and note_no='2'")[0][0]
    assert q(c, "select count(*) from legal_notes where status='verified'") == [(3,)]
