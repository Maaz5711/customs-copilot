"""A7: Fifth Schedule rows in the dated legal store."""
import csv
import sqlite3
from pathlib import Path

import pytest

from src.store import connect, get_rule_on_date, init_db
from src.store.build import build

PROC = Path("data/processed")
pytestmark = pytest.mark.skipif(not (PROC / "a7_fifth_rules.csv").exists(), reason="A7 files not built")


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("a7") / "store.sqlite"
    report = build(path)
    c = connect(path)
    yield c, report
    c.close()


def test_count_matches_csv(db):
    c, rep = db
    n = len(list(csv.DictReader(open(PROC / "a7_fifth_rules.csv", encoding="utf-8"))))
    assert rep["fifth_schedule_rules"] == n == c.execute("SELECT count(*) FROM fifth_schedule_rules").fetchone()[0]


def test_lookup_by_code_and_date(db):
    c, _ = db
    # Part I S.No 1 C(1): 8413.7011 submersible pumps, 0%, Fifth Schedule page 3
    rows = get_rule_on_date(c, "fifth_schedule_rules", "8413.7011", "2026-08-01")
    r = [x for x in rows if x["part"] == "I" and x["s_no"] == "1"]
    assert r and r[0]["rate_kind"] == "percent" and r[0]["page"] == 3 and r[0]["valid_from"] == "2026-07-01"
    # before 1 Jul 2026 the FY2026-27 schedule is not in force and the FY2025-26 version is not in the store
    assert [x for x in get_rule_on_date(c, "fifth_schedule_rules", "8413.7011", "2026-06-30") if x["part"] == "I"] == []


def test_unmapped_rows_never_match_a_code(db):
    c, _ = db
    n = c.execute("SELECT count(*) FROM fifth_schedule_rules WHERE match_level='unmapped'").fetchone()[0]
    assert n > 100
    assert c.execute("SELECT count(*) FROM fifth_schedule_rules WHERE match_level='unmapped' AND code_norm IS NOT NULL").fetchone()[0] == 0


def test_hard_rule_enforced_in_fifth_table():
    c = init_db(connect(":memory:"))
    base = dict(rule_id="x", part="I", table_no="main", s_no="1", code_norm="84137011", match_level="code8",
                rule_group="g", rate_kind="percent", rate_pcts='["0"]', valid_from="2026-07-01", valid_to="9999-12-31",
                source_file="f.pdf", page=3)

    def ins(**over):
        row = dict(base, **over)
        row = {k: v for k, v in row.items() if v is not None}
        c.execute(f"INSERT INTO fifth_schedule_rules ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))

    ins()
    for bad in (dict(rule_id="y", page=None), dict(rule_id="y", source_file=None), dict(rule_id="y", valid_from=None),
                dict(rule_id="y", valid_to=None), dict(rule_id="y", page=0), dict(rule_id="y", rate_pcts="[]"),
                dict(rule_id="y", rate_kind="fraction_of_first_schedule", rate_pcts="[]")):
        with pytest.raises(sqlite3.IntegrityError):
            ins(**bad)
