"""Helpers for the importer GD extract (src/eval/gd_data.py). No private data needed."""
from src.eval.gd_data import clean_description, code8


def test_code_is_restored_from_a_spreadsheet_number():
    assert code8(8536.909) == "85369090" and code8(8531.8) == "85318000" and code8(8532.29) == "85322900" and code8(8516.9) == "85169000"
    assert code8(8507.2) == "85072000" and code8("0305.5200") == "03055200" and code8(305.52) == "03055200"
    assert code8("abc") is None and code8(None) is None


def test_quantity_tail_is_removed_but_product_words_are_kept():
    assert clean_description("PLATIC COVER PARTS FOR BREAKER QTY 4240 PCS ") == "PLATIC COVER PARTS FOR BREAKER"
    assert clean_description("CAPACITOR QTY: 653 KGS.") == "CAPACITOR"
    assert clean_description("SOLAR PANELS MODEL NO: 585MS ( 585 WATTS ) STC 2160 PCS").startswith("SOLAR PANELS MODEL NO: 585MS")
