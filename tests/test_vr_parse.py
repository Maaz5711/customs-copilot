"""FBR valuation ruling parser: repairs scan look-alikes, keeps only real tariff codes, never invents a code."""
from src.ingest.vr_parse import items_near, product_of, read_codes

KNOWN = {"29093000", "90183920", "15131910", "151319", "69111010", "85161010", "12060000"}


def codes(text):
    return [(c["code"], c["repaired"]) for c in read_codes(text, KNOWN)]


def test_plain_codes_are_read_and_price_like_numbers_are_ignored():
    assert codes("Phenyl ether 2909.3000 US$ 9.8/Kg, price 1234.5678, page 2.50") == [("29093000", False)]


def test_scan_lookalikes_are_repaired_and_flagged():
    assert codes("Sunflower seeds I206.0000 and ceramic 69r1.1010") == [("12060000", True), ("69111010", True)]
    assert codes("heater 85l6.1010") == [("85161010", True)]


def test_a_repair_that_lands_on_no_real_code_is_dropped_not_guessed():
    assert codes("9999.9999 and 29O9.3001 and 1234.56") == []


def test_sub_heading_only_codes_are_kept_at_six_digits():
    assert codes("Coconut oil HS 1513.1900 proposed 1513.1900.1000") == [("151319", False)]


def test_duplicates_are_listed_once_in_order():
    assert [c for c, _ in codes("9018.3920 then 2909.3000 then 9018.3920")] == ["90183920", "29093000"]


def test_product_name_is_cut_out_of_the_listing_title():
    assert product_of('DETERMINATION OF CUSTOMS VALUE OF "COCONUT OIL" UNDER SECTION 25A OF THE CUSTOMS ACT, 1969') == "COCONUT OIL"
    assert product_of("Publication Determination of Customs Values of Carbon Steel Seamless Pipes under section 25A of the Customs Act, 1969") == "Carbon Steel Seamless Pipes"
    assert product_of("Valuation Ruling on Honey") == "Valuation Ruling on Honey"          # unknown wording is kept, not guessed


def test_item_snippets_drop_table_header_junk():
    text = "S. No Description of Goods PCT Origin Customs Values (C&F) US$/Kg 1 Infusion Giving Set without Burette 9018.3920 China 0.065"
    cs = read_codes(text, KNOWN)
    got = items_near(text, cs)
    assert got and "Infusion Giving Set" in got[0] and "Origin" not in got[0] and "Customs Values" not in got[0]
