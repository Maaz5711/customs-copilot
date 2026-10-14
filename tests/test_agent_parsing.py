"""Tests for src/agent/parsing.py and src/agent/facts.py (deterministic reading of amounts, dates, yes/no, codes)."""
import datetime as dt
from decimal import Decimal

import pytest

from src.agent.facts import apply_value, coerce, get_path, set_path, tool_args
from src.agent.parsing import (
    detect_currency, display_code, dec_str, find_pct_codes, is_unknown, norm_ws, parse_amount, parse_bool, parse_date_text,
    parse_enum, parse_number, parse_quantity, parse_registration, parse_vehicle_form, quote_in, says_today,
    unsupported_fiscal_year,
)

D = Decimal


@pytest.mark.parametrize("text,expected", [
    ("PKR 2,500,000", D(2500000)),
    ("Rs. 10,00,000", D(1000000)),            # Indian grouping
    ("2.5 million", D(2500000)),
    ("10 lakh", D(1000000)),
    ("1.2 crore", D(12000000)),
    ("500k", D(500000)),
    ("1800cc", D(1800)),                      # must not be cut to 180
    ("5,000 kg", D(5000)),                    # 'k' of 'kg' is not a multiplier
    ("2 MT", D(2)),
    ("value 10000000", D(10000000)),
    ("no digits here", None),
])
def test_parse_number(text, expected):
    got = parse_number(text)
    assert got == expected


def test_dec_str_is_plain():
    assert dec_str(parse_number("2.5 million")) == "2500000"
    assert dec_str(D("1800.00")) == "1800"
    assert dec_str(D("0.5")) == "0.5"


def test_currency_and_amount():
    assert detect_currency("$10,000 FOB") == "USD" and detect_currency("USD 5000") == "USD"
    assert detect_currency("Rs. 5 lakh") == "PKR" and detect_currency("PKR 100") == "PKR"
    assert detect_currency("EUR 3000") == "EUR" and detect_currency("5000") is None
    assert parse_amount("Rs 25 lakh") == (D(2500000), "PKR")


def test_parse_quantity_reads_number_and_unit():
    assert parse_quantity("5,000 kg") == (D(5000), "kg")
    assert parse_quantity("10 sets") == (D(10), "sets")
    assert parse_quantity("2 MT of oil") == (D(2), "mt")
    assert parse_quantity("1.5 lakh pieces") == (D(150000), "pieces")
    assert parse_quantity("nothing") == (None, None)


@pytest.mark.parametrize("text,expected", [
    ("yes", True), ("Yes, we are", True), ("y", True), ("haan", True), ("no", False), ("No, not a manufacturer", False),
    ("nahi", False), ("maybe", None), ("I don't know", None), ("yes and no", None),
])
def test_parse_bool(text, expected):
    assert parse_bool(text) is expected


def test_unknown_answers():
    for t in ("I don't know", "dont know", "not sure", "no idea", "skip", "I don’t know"):
        assert is_unknown(t), t
    assert not is_unknown("registered")


def test_registration_and_vehicle_form_and_enum():
    assert parse_registration("we are registered under sales tax") == "registered"
    assert parse_registration("unregistered") == "unregistered"
    assert parse_registration("not registered yet") == "unregistered"
    assert parse_registration("non-registered importer") == "unregistered"
    assert parse_registration("hello") is None
    assert parse_vehicle_form("it is CKD") == "CKD" and parse_vehicle_form("completely built unit, CBU") == "CBU"
    assert parse_vehicle_form("CKD or CBU") is None
    assert parse_enum("It is CBU please", ["CKD", "CBU"]) == "CBU"
    assert parse_enum("both CKD and CBU", ["CKD", "CBU"]) is None


@pytest.mark.parametrize("text,iso", [
    ("2026-07-15", "2026-07-15"), ("15/07/2026", "2026-07-15"), ("15-07-2026", "2026-07-15"), ("15.07.2026", "2026-07-15"),
    ("15 July 2026", "2026-07-15"), ("1st Jul 2026", "2026-07-01"), ("July 15, 2026", "2026-07-15"),
    ("on Sept 3 2025", "2025-09-03"), ("30th of June 2026", "2026-06-30"),
])
def test_parse_date_text(text, iso):
    assert parse_date_text(text) == dt.date.fromisoformat(iso)


def test_parse_date_text_rejects_partial_or_invalid():
    for t in ("July 2026", "15 July", "2026-13-45", "31/02/2026", "next month", "FY2026-27"):
        assert parse_date_text(t) is None, t


def test_says_today():
    assert says_today("duty for today please") and not says_today("duty for 2026-07-15")


def test_find_pct_codes_trusted_and_untrusted():
    f = find_pct_codes("duty on 6109.1000 please")
    assert f == [{"code": "61091000", "trusted": True}]
    # raw 8 digits could be an amount: untrusted unless introduced by a code word
    assert find_pct_codes("value 10000000 rupees") == [{"code": "10000000", "trusted": False}]
    assert find_pct_codes("HS code 61091000")[0]["trusted"] is True
    assert find_pct_codes("heading 87.03")[0] == {"code": "8703", "trusted": True}
    assert find_pct_codes("code: 6109.1000") == [{"code": "61091000", "trusted": True}]   # no stray 4-digit prefix
    assert find_pct_codes("8703.21 cars")[0] == {"code": "870321", "trusted": False}
    assert find_pct_codes("nothing here, 2026 and 15 July") == []
    assert display_code("61091000") == "6109.1000" and display_code("8703") == "8703"


def test_unsupported_fiscal_year():
    assert unsupported_fiscal_year("duty in FY2024-25") == "2024-25"
    assert unsupported_fiscal_year("financial year 2023/24") == "2023-24"
    assert unsupported_fiscal_year("for 2022-23") == "2022-23"
    assert unsupported_fiscal_year("FY2026-27 rates") is None
    assert unsupported_fiscal_year("FY 25-26") is None
    assert unsupported_fiscal_year("on 2026-07-15") is None      # an ISO date is not a fiscal year
    assert unsupported_fiscal_year("on 2025-06-30") is None


def test_quote_in_is_whitespace_and_case_insensitive():
    msg = "I want to import  men's T-shirts,\n  value PKR 2,500,000"
    assert quote_in("value pkr 2,500,000", msg) and quote_in("T-shirts", msg)
    assert not quote_in("PKR 3,000,000", msg) and not quote_in("", msg) and not quote_in(None, msg)
    assert norm_ws("It’s – here") == "it's - here"


# ------------------------------------------------------------------------------------- facts.coerce
def test_coerce_money_rejects_other_currency_and_nonsense():
    assert coerce("assessable_value_pkr", "Rs 25 lakh").value == "2500000"
    c = coerce("assessable_value_pkr", "$10,000")
    assert not c.ok and "USD" in c.error and "do not convert" in c.error
    assert not coerce("assessable_value_pkr", "a lot").ok
    assert not coerce("assessable_value_pkr", "0").ok


def test_coerce_numbers_have_plausibility_ranges():
    assert coerce("goods.engine_cc", "1300 cc").value == "1300"
    assert not coerce("goods.engine_cc", "1.8").ok            # litres, not cc: refused, not converted
    assert coerce("goods.age_years", "7").value == "7"
    assert not coerce("goods.age_years", "500").ok


def test_coerce_quantity_checks_the_unit_but_never_converts():
    ok = coerce("quantity", "2 MT", unit="MT")
    assert ok.ok and ok.value == {"quantity": "2", "quantity_unit": "MT"}
    assert coerce("quantity", "5", unit="MT").value == {"quantity": "5", "quantity_unit": "MT"}   # no unit given: the required one is used
    bad = coerce("quantity", "2000 kg", unit="MT")
    assert not bad.ok and "do not convert units" in bad.error
    assert coerce("quantity", "10 sets", unit="set").ok and coerce("quantity", "3 kgs", unit="Kg").ok


def test_coerce_enum_bool_date_and_unknown():
    assert coerce("importer.registration_status", "unregistered").value == "unregistered"
    assert coerce("importer.commercial_importer", "yes").value is True
    assert coerce("importer.commercial_importer", "no").value is False       # False is a real answer
    assert not coerce("importer.commercial_importer", "perhaps").ok
    assert coerce("goods.vehicle_form", "CBU").value == "CBU"
    assert coerce("as_of_date", "15 July 2026").value == "2026-07-15"
    assert coerce("as_of_date", "today", today=dt.date(2026, 7, 20)).value == "2026-07-20"
    assert not coerce("as_of_date", "today").ok                               # no clock given: never assumed
    u = coerce("goods.engine_cc", "I don't know")
    assert not u.ok and u.unknown
    # a field the registry does not know is read from the tool's own `allowed` list
    assert coerce("goods.new_flag", "yes", allowed=[True, False]).value is True
    assert coerce("goods.new_thing", "blue", allowed=["red", "blue"]).value == "blue"


def test_paths_and_tool_args():
    inputs = {}
    set_path(inputs, "importer.registration_status", "registered")
    set_path(inputs, "goods.engine_cc", "1300")
    apply_value(inputs, "quantity", {"quantity": "2", "quantity_unit": "MT"})
    inputs["assessable_value_pkr"] = "1000000"
    assert get_path(inputs, "importer.registration_status") == "registered" and get_path(inputs, "goods.nope") is None
    args = tool_args(inputs)
    assert args == {"assessable_value_pkr": "1000000", "importer": {"registration_status": "registered"}, "goods": {"engine_cc": "1300"},
                    "quantity": "2", "quantity_unit": "MT"}
    assert tool_args({}) == {"assessable_value_pkr": None, "importer": None, "goods": None, "quantity": None, "quantity_unit": None}
