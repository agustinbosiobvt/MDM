"""Wizard suggestions: header row, data start, field / price / currency suggestions."""

from datetime import date

from app.imports.detect import (
    currency_from_header,
    detect_data_start,
    detect_header_row,
    suggest_mapping,
    suggest_valid_from,
)

AMAZON_TOP = [
    (1, ("Quote Sheet Template - Direct Imports Parity", None, None)),
    (2, ("Y", "Y", "-", "Y")),
    (3, (1, 2, 3, 4)),
    (4, ("ASIN", "Destination country", "EAN", "Brand Name")),
    (5, ("Mandatory", "Mandatory", "Recommended", "Mandatory")),
    (6, ("10-digit code", "List", "Input a number", "Text")),
    (7, ("B003QQ37HI", "MX", 4033766024122, "Nobby")),
]


def test_header_row_and_data_start() -> None:
    assert detect_header_row(AMAZON_TOP) == 4  # not the title, flags or column numbers
    assert detect_data_start(AMAZON_TOP, 4) == 7  # instruction rows 5-6 skipped


def test_currency_from_header() -> None:
    assert currency_from_header("Import Cost (USD)") == "USD"
    assert currency_from_header("PRICE\n€") == "EUR"
    assert currency_from_header("MX RRP (MXN)") == "MXN"
    assert currency_from_header("Recommended Retail Price (In local currency)") is None


def test_price_currency_from_a_matching_currency_column() -> None:
    sug = suggest_mapping(
        ("EAN", "RRP", "RRP Currency", "Import Cost (USD)", "Margin", "OUR MARGIN")
    )
    prices = {p["header"]: p for p in sug["prices"]}
    assert set(prices) == {
        "RRP",
        "Import Cost (USD)",
    }  # margins and the currency column are not prices
    assert prices["RRP"]["currency"] == {
        "mode": "column",
        "col": 2,
        "header": "RRP Currency",
        "suggested": True,
    }
    assert prices["Import Cost (USD)"]["currency"]["value"] == "USD"


def test_amazon_local_currency_price() -> None:
    headers = (
        "ASIN",
        "Import Cost (USD)",
        "Recommended Retail Price  Currency",
        "Recommended Retail Price (In local currency)",
        "Deal: Percentage-off Recommended Retail Price",
    )
    sug = suggest_mapping(headers)
    assert [p["price_type"] for p in sug["prices"]] == ["import_cost", "rrp"]
    assert sug["prices"][1]["currency"]["col"] == 2


def test_no_guess_without_a_hint() -> None:
    sug = suggest_mapping(("EAN", "Price"))
    assert sug["prices"][0]["currency"] == {"mode": "fixed", "value": None, "suggested": False}


def test_valid_from_suggestion() -> None:
    assert suggest_valid_from([["valid from 15.08.2025", "MX to USD", "0.054"]]) == date(
        2025, 8, 15
    )
    assert suggest_valid_from([["nothing here"]]) is None


def test_english_description_wins_regardless_of_column_order() -> None:
    for headers, expected in (
        (("Description ES", "Description EN", "Description"), 1),
        (("Description", "Description ES", "Description EN"), 2),
        (("Description EN", "Description ES", "Description"), 0),
        (("Description", "English Description"), 1),
        (("Description ES", "Description (EN)"), 1),
    ):
        assert suggest_mapping(headers)["fields"]["description"]["col"] == expected


def test_spanish_description_is_not_suggested_as_english() -> None:
    assert "description" not in suggest_mapping(("EAN", "Description ES"))["fields"]
