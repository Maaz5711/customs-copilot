"""Tests for the dated legal store (B1)."""
import json
import sqlite3
from pathlib import Path

import pytest

from src.store import connect, get_rule_on_date, init_db
from src.store.build import build
from src.store.loaders import (load_table_file, parse_except, split_codes, PROC)
from src.store.resolve import canon_sro, norm_code

FACT = dict(valid_from="2026-07-01", valid_to="2027-06-30", source_file="x.pdf", page=1)


@pytest.fixture()
def conn():
    c = init_db(connect(":memory:"))
    yield c
    c.close()


def rd(conn, code, level, rate=4.0, group="G1", excepts=None, status="accepted", **over):
    row = dict(sro_number=over.pop("sro_number", group), s_no=over.pop("s_no", "1"), raw_pct_code=code or "x",
               description="d", code_norm=code, match_level=level,
               except_codes=json.dumps(excepts or []), rule_group=group,
               rate_kind="percent", rate_pct=rate, status=status, **FACT)
    row.update(over)
    cols = list(row)
    conn.execute(f"INSERT INTO rd_rules ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                 [row[c] for c in cols])


# ---------------------------------------------------------------- hard rule
@pytest.mark.parametrize("missing", ["valid_from", "valid_to", "source_file", "page"])
def test_insert_without_fact_column_fails(conn, missing):
    fact = {k: v for k, v in FACT.items() if k != missing}
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            f"INSERT INTO rd_rules (sro_number,s_no,raw_pct_code,description,code_norm,match_level,rule_group,"
            f"rate_kind,rate_pct,{','.join(fact)}) VALUES ('S','1','x','d','01012100','code8','S','percent',4,"
            f"{','.join('?' * len(fact))})", list(fact.values()))


@pytest.mark.parametrize("bad", [
    dict(valid_from=None), dict(valid_to=None), dict(source_file=None), dict(page=None),
    dict(source_file="   "), dict(page=0), dict(page="abc"), dict(valid_from="2026-13-01"),
    dict(valid_from="07/01/2026"), dict(valid_to="2026-06-30"),  # valid_to before valid_from
])
def test_bad_fact_values_rejected_in_every_fact_table(conn, bad):
    row = dict(FACT, **bad)
    with pytest.raises(sqlite3.IntegrityError):
        rd(conn, "01012100", "code8", **row)


def test_all_fact_tables_enforce_not_null():
    c = init_db(connect(":memory:"))
    for table in ["tariff_headings", "tariff_lines", "sros", "rd_rules", "acd_rules", "sales_tax_rules",
                  "income_tax_rules", "legal_notes"]:
        info = {r["name"]: r for r in c.execute(f"PRAGMA table_info({table})")}
        for col in ["valid_from", "valid_to", "source_file", "page"]:
            assert info[col]["notnull"] == 1, f"{table}.{col} must be NOT NULL"


def test_other_constraints(conn):
    with pytest.raises(sqlite3.IntegrityError):  # percent rate out of range
        rd(conn, "01012100", "code8", rate=140)
    with pytest.raises(sqlite3.IntegrityError):  # level / code length mismatch
        rd(conn, "0101", "code8")
    with pytest.raises(sqlite3.IntegrityError):  # bad status
        rd(conn, "01012100", "code8", status="maybe")
    with pytest.raises(sqlite3.IntegrityError):  # specific rate needs a unit
        rd(conn, "01012100", "code8", rate_kind="specific", rate_pct=None, rate_specific_amount=5)


# --------------------------------------------------------------- resolution
def test_most_specific_wins_exact_over_heading(conn):
    rd(conn, "0105", "heading4", 4.0, s_no="2")
    rd(conn, "01051100", "code8", 8.0, s_no="3")
    rows = get_rule_on_date(conn, "rd_rules", "0105.1100", "2026-07-01")
    assert [r["rate_pct"] for r in rows] == [8.0] and rows[0]["_resolution"] == "exact"
    rows = get_rule_on_date(conn, "rd_rules", "0105.9900", "2026-07-01")
    assert [r["rate_pct"] for r in rows] == [4.0]
    assert rows[0]["_resolution"] == "prefix:heading4"
    assert "matched_by_prefix_not_exact_code" in rows[0]["_flags"]


def test_except_clause_removes_heading_row_for_that_code(conn):
    rd(conn, "0105", "heading4", 4.0, excepts=["01051100", "01059400"])
    assert get_rule_on_date(conn, "rd_rules", "0105.1100", "2026-07-01") == []   # carved out, no own row
    assert len(get_rule_on_date(conn, "rd_rules", "0105.9900", "2026-07-01")) == 1


def test_except_by_heading_prefix(conn):
    rd(conn, "0303", "heading4", 14.0, excepts=["0304"])  # an except can name a whole heading
    assert get_rule_on_date(conn, "rd_rules", "0304.3100", "2026-07-01") == []
    assert len(get_rule_on_date(conn, "rd_rules", "0303.1100", "2026-07-01")) == 1


def test_excepted_code_with_own_row_gets_own_rate(conn):
    rd(conn, "0105", "heading4", 4.0, excepts=["01051100"])
    rd(conn, "01051100", "code8", 8.0)
    rows = get_rule_on_date(conn, "rd_rules", "0105.1100", "2026-07-01")
    assert [r["rate_pct"] for r in rows] == [8.0]


def test_chapter_and_all_levels(conn):
    rd(conn, "01", "chapter2", 1.0)
    rd(conn, "0105", "heading4", 2.0)
    rd(conn, "", "all", 0.5, group="G2")
    rows = get_rule_on_date(conn, "rd_rules", "0105.1100", "2026-07-01")
    assert sorted(r["rate_pct"] for r in rows) == [0.5, 2.0]  # G1 -> heading wins; G2 independent


def test_groups_are_independent_not_substitutive(conn):
    rd(conn, "0105", "heading4", 4.0, group="1064(I)/2026")
    rd(conn, "01051100", "code8", 40.0, group="1898(I)/2025")
    rows = get_rule_on_date(conn, "rd_rules", "0105.1100", "2026-07-01")
    assert sorted(r["rate_pct"] for r in rows) == [4.0, 40.0]


def test_same_specificity_rows_all_returned_and_flagged(conn):
    rd(conn, "85171390", "code8", rate_kind="specific", rate_pct=None, rate_specific_amount=240,
       rate_specific_unit="set", s_no="550")
    rd(conn, "85171390", "code8", rate_kind="specific", rate_pct=None, rate_specific_amount=2400,
       rate_specific_unit="set", s_no="551")
    rows = get_rule_on_date(conn, "rd_rules", "8517.1390", "2026-07-01")
    assert len(rows) == 2
    assert all("multiple_rows_same_specificity_choose_by_condition" in r["_flags"] for r in rows)


def test_date_boundaries_inclusive(conn):
    rd(conn, "01012100", "code8", 5.0, group="old", valid_from="2025-07-01", valid_to="2026-06-30")
    rd(conn, "01012100", "code8", 4.0, group="new", valid_from="2026-07-01", valid_to="9999-12-31")
    f = lambda d: [r["rate_pct"] for r in get_rule_on_date(conn, "rd_rules", "0101.2100", d)]
    assert f("2026-06-30") == [5.0]
    assert f("2026-07-01") == [4.0]
    assert f("2025-07-01") == [5.0]
    assert f("2025-06-30") == []
    assert f("2040-01-01") == [4.0]
    import datetime
    assert f(datetime.date(2026, 7, 1)) == [4.0]


def test_status_filter_and_flags(conn):
    rd(conn, "01012100", "code8", status="needs_review", unparsed_except_text=1)
    r = get_rule_on_date(conn, "rd_rules", "0101.2100", "2026-07-01")
    assert "row_needs_review" in r[0]["_flags"] and "description_has_unparsed_exception_text" in r[0]["_flags"]
    assert get_rule_on_date(conn, "rd_rules", "0101.2100", "2026-07-01", statuses=["accepted", "verified"]) == []


def test_bad_inputs(conn):
    with pytest.raises(ValueError):
        get_rule_on_date(conn, "rd_rules; drop table sros", "01012100", "2026-07-01")
    with pytest.raises(ValueError):
        get_rule_on_date(conn, "rd_rules", "0101.2100", "2026-02-30")
    with pytest.raises(ValueError):
        get_rule_on_date(conn, "rd_rules", "0101", "2026-07-01")
    with pytest.raises(ValueError):
        get_rule_on_date(conn, "rd_rules", "0101.2100", "1 July 2026")


def test_helpers():
    assert norm_code("87.03") == "8703" and norm_code("8703.2115") == "87032115"
    assert canon_sro("S.R.O. 1064 (I)/2026") == "1064(I)/2026"
    assert split_codes("8517.1390, 8517.1419") == ["85171390", "85171419"]
    assert split_codes("8517.1390 8517.1419") == ["85171390", "85171419"]
    assert split_codes("03.03") == ["0303"]
    assert split_codes("Respective Headings") == []
    d = "Poultry (except Grandparent stock, PCT codes 0105.1100 and 0105.9400) )."
    assert parse_except(d) == (["01051100", "01059400"], False)
    assert parse_except("Fish, excluding fillets of heading 03.04.") == (["0304"], False)
    assert parse_except("Celery other than celeriac") == ([], True)
    assert parse_except("Pure-bred breeding animals") == ([], False)


# --------------------------------------------------------- generic loader
def test_loader_contract_rejects_missing_fact(conn, tmp_path):
    p = tmp_path / "st.csv"
    p.write_text("instrument,clause,tax_kind,code_norm,match_level,rule_group,rate_kind,rate_pct,"
                 "valid_from,valid_to,source_file,page\n"
                 "Act,6th Sch 1,sales_tax,01012100,code8,g,percent,18,2026-07-01,2027-06-30,a.pdf,\n",
                 encoding="utf8")
    with pytest.raises(sqlite3.IntegrityError):
        load_table_file(conn, "sales_tax_rules", p)
    assert conn.execute("select count(*) from sales_tax_rules").fetchone()[0] == 0


def test_loader_contract_accepts_good_csv_and_json(conn, tmp_path):
    p = tmp_path / "st.csv"
    p.write_text("instrument,clause,tax_kind,code_norm,match_level,rule_group,rate_kind,rate_pct,"
                 "valid_from,valid_to,source_file,page\n"
                 "Act,6th Sch 1,sales_tax,,all,g,percent,18,2026-07-01,2027-06-30,a.pdf,3\n", encoding="utf8")
    assert load_table_file(conn, "sales_tax_rules", p) == 1
    rows = get_rule_on_date(conn, "sales_tax_rules", "0101.2100", "2026-07-01")
    assert rows[0]["rate_pct"] == 18 and rows[0]["match_level"] == "all"
    j = tmp_path / "n.json"
    j.write_text(json.dumps([dict(note_kind="chapter_note", scope="Chapter 87", note_no="1", text="t",
                                  valid_from="2022-01-01", valid_to="9999-12-31", source_file="n.pdf", page=2)]))
    assert load_table_file(conn, "legal_notes", j) == 1
    assert get_rule_on_date(conn, "legal_notes", "Chapter 87", "2026-07-01")[0]["note_no"] == "1"


def test_loader_rejects_unknown_columns(conn, tmp_path):
    j = tmp_path / "bad.json"
    j.write_text(json.dumps([dict(note_kind="chapter_note", scope="C", note_no="1", text="t", bogus=1,
                                  valid_from="2022-01-01", valid_to="9999-12-31", source_file="n.pdf", page=2)]))
    with pytest.raises(ValueError):
        load_table_file(conn, "legal_notes", j)


# ------------------------------------------------------------- real data
needs_data = pytest.mark.skipif(not (PROC / "tariff_2026_27.json").exists(), reason="processed data missing")


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "store.sqlite"
    report = build(path)
    c = connect(path)
    yield c, report
    c.close()


@needs_data
def test_counts_loaded(real):
    c, rep = real
    q = lambda s: c.execute(s).fetchone()[0]
    assert q("select count(*) from tariff_lines where fy='FY2026-27' and level=8") == 7605
    assert q("select count(distinct code_norm) from tariff_lines where fy='FY2026-27' and level=8") == 7605
    assert q("select count(*) from tariff_lines where fy='FY2025-26' and level=8") == 7590
    assert q("select count(*) from tariff_headings where fy='FY2026-27'") == 1017
    assert q("select count(*) from tariff_lines where fy='FY2026-27' and cd_kind='specific'") == 54
    assert q("select count(distinct s_no) from rd_rules where sro_number='1064(I)/2026'") == 687
    assert q("select count(distinct s_no) from rd_rules where sro_number='1152(I)/2025'") == 693
    assert q("select count(*) from acd_rules") == 0


@needs_data
def test_six_vehicle_codes_are_single_rows(real):
    c, _ = real
    for code in ["8703.2115", "8703.2193", "8703.3225", "8704.3130", "8704.3150", "8704.3190"]:
        rows = get_rule_on_date(c, "tariff_lines", code, "2026-07-01")
        assert len(rows) == 1, code  # the 'duplicates' were mentions in notes, not table rows


@needs_data
def test_failures_are_flagged_not_dropped(real):
    """Every failure row stays in the store. Rows without an owner decision stay needs_review;
    rows the owner confirmed are no longer flagged only because of the failures list."""
    c, _ = real
    import csv
    for stem, sro in [("sro_1064_rd", "1064(I)/2026"), ("sro_1152_rd", "1152(I)/2025")]:
        with open(PROC / f"{stem}_failures.csv", encoding="utf8", newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            n = c.execute("select count(*) from rd_rules where sro_number=? and s_no=? and page=?",
                          (sro, r["s_no"], int(r["page"]))).fetchone()[0]
            assert n >= 1, (sro, r["s_no"])  # never dropped
            if not r["owner_decision"].strip():
                k = c.execute("select count(*) from rd_rules where sro_number=? and s_no=? and page=? "
                              "and status='needs_review'", (sro, r["s_no"], int(r["page"]))).fetchone()[0]
                assert k >= 1, (sro, r["s_no"])


@needs_data
def test_boundary_1_july_2026_real(real):
    c, _ = real
    # tariff: FY2025-26 row on 30 Jun 2026, FY2026-27 row on 1 Jul 2026
    a = get_rule_on_date(c, "tariff_lines", "0101.2100", "2026-06-30")
    b = get_rule_on_date(c, "tariff_lines", "0101.2100", "2026-07-01")
    assert [r["fy"] for r in a] == ["FY2025-26"] and [r["fy"] for r in b] == ["FY2026-27"]
    # RD: 1152 on 30 Jun 2026, 1064 on 1 Jul 2026 (never both)
    a = get_rule_on_date(c, "rd_rules", "0105.1100", "2026-06-30")
    b = get_rule_on_date(c, "rd_rules", "0105.1100", "2026-07-01")
    assert [(r["sro_number"], r["rate_pct"]) for r in a] == [("1152(I)/2025", 10.0)]
    assert [(r["sro_number"], r["rate_pct"]) for r in b] == [("1064(I)/2026", 8.0)]
    # before 1152 starts: nothing
    assert get_rule_on_date(c, "rd_rules", "0105.1100", "2025-06-30") == []
    # SRO chain
    s = get_rule_on_date(c, "sros", "1152(I)/2025", "2026-06-30")[0]
    assert s["superseded_by"] == "1064(I)/2026" and s["sro_status"] == "superseded"
    assert get_rule_on_date(c, "sros", "1152(I)/2025", "2026-07-01") == []


@needs_data
def test_real_except_and_heading_resolution(real):
    c, _ = real
    # 01.05 heading row (4%) with except 0105.1100 / 0105.9400, which have their own 8% rows
    rows = get_rule_on_date(c, "rd_rules", "0105.9900", "2026-07-01")
    assert [(r["s_no"], r["rate_pct"]) for r in rows] == [("2", 4.0)]
    rows = get_rule_on_date(c, "rd_rules", "0105.9400", "2026-07-01")
    assert [(r["s_no"], r["rate_pct"]) for r in rows] == [("4", 8.0)]
    # 03.04 row says 'except 0304.6200', which has its own row (S.No 12)
    rows = get_rule_on_date(c, "rd_rules", "0304.6200", "2026-07-01")
    assert [r["_resolution"] for r in rows] == ["exact"]
    # 03.03 excludes heading 03.04 via 'excluding ... heading 03.04'
    assert get_rule_on_date(c, "rd_rules", "0303.1100", "2026-07-01")[0]["s_no"] == "10"
    # specific-rate tiers come back together and flagged
    rows = get_rule_on_date(c, "rd_rules", "8517.1390", "2026-07-01")
    assert len(rows) >= 5 and all(r["rate_kind"] == "specific" for r in rows)


@needs_data
def test_specific_tariff_rows_flagged(real):
    c, _ = real
    r = get_rule_on_date(c, "tariff_lines", "1507.1000", "2026-07-01")[0]
    assert r["cd_kind"] == "specific" and r["cd_specific_amount"] == 10550.0
    assert r["status"] == "needs_review"


def test_null_cannot_slip_through_table_checks(conn):
    with pytest.raises(sqlite3.IntegrityError):  # 'all' with NULL code_norm
        rd(conn, None, "all")
    with pytest.raises(sqlite3.IntegrityError):  # percent rate with NULL rate_pct
        rd(conn, "01012100", "code8", rate=None)
