"""A3 tests on the store-ready sales tax / income tax files (load through the B1 loader, spot facts from the source pages)."""
import csv
from collections import Counter
from pathlib import Path

import pytest

from src.store import connect, init_db
from src.store.loaders import load_table_file

P = Path("data/processed")


def rows(name):
    return list(csv.DictReader(open(P / name, encoding="utf-8")))


@pytest.fixture(scope="module")
def conn():
    c = init_db(connect(":memory:"))
    load_table_file(c, "sales_tax_rules", P / "a3_sales_tax_rules.csv")
    load_table_file(c, "income_tax_rules", P / "a3_income_tax_rules.csv")
    yield c
    c.close()


def test_files_load_into_store_with_all_constraints(conn):
    assert conn.execute("select count(*) from sales_tax_rules").fetchone()[0] >= 861
    assert conn.execute("select count(*) from income_tax_rules").fetchone()[0] == 652


def test_twelfth_schedule_parts_and_glycerol():
    it = rows("a3_income_tax_rules.csv")
    c = Counter(r["rule_group"] for r in it if r["rule_group"].startswith("IT-12TH"))
    assert c == {"IT-12TH-P1": 106, "IT-12TH-P2": 478, "IT-12TH-P3": 1}
    g = [r for r in it if r["code_norm"] == "1520" or r["code_norm"] == "15200000"]
    assert len(g) == 1 and g[0]["valid_from"] == "2026-07-01"   # added by Finance Act 2026 s.5(48)


def test_s148_class_rates_and_mobile_change():
    it = rows("a3_income_tax_rules.csv")
    cls = {(r["rule_group"], r["importer_category"]): float(r["rate_pct"]) for r in it if r["rule_group"] in
           ("IT-S148-RATE-P1", "IT-S148-RATE-P2", "IT-S148-RATE-P3")}
    assert sorted(cls.values()) == [1.0, 2.0, 3.5, 5.5, 6.0]
    mob = [r for r in it if r["rule_group"] == "IT-S148-MOBILE" and "S.No 3, column (3)" in r["clause"]]
    assert {(float(r["rate_specific_amount"]), r["valid_from"]) for r in mob} == {(930.0, "2025-07-01"), (100.0, "2026-07-01")}


def test_sales_tax_standard_rate_and_dates():
    st = rows("a3_sales_tax_rules.csv")
    std = [r for r in st if r["clause"].startswith("Sales Tax Act s.3(1)(b)")]
    assert len(std) == 1 and float(std[0]["rate_pct"]) == 18.0
    for r in st:
        assert r["valid_from"] and r["valid_to"] >= r["valid_from"] and r["source_file"] and int(r["page"]) >= 1


def test_sixth_schedule_changes_between_snapshots():
    st = [r for r in rows("a3_sales_tax_rules.csv") if r["rule_group"] == "ST-6TH-T1"]
    s157 = {r["valid_to"] for r in st if "S.No 157" in r["clause"]}
    assert "2026-06-30" in s157 and "2027-06-30" in s157
    assert any("27A" in r["clause"] for r in st)
