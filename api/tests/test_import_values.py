"""Cell parsing rules (CLAUDE.md §5)."""

from decimal import Decimal

import pytest

from app.imports.values import (
    CellValueError,
    asin_is_valid,
    code_text,
    gtin_is_valid,
    is_empty,
    money,
    whole_number,
)


@pytest.mark.parametrize("v", [None, "", " ", "   ", "#N/A", "#n/a", "#VALUE!", "#REF!"])
def test_empty_values(v: object) -> None:
    assert is_empty(v)


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        (4033766024122.0, "4033766024122"),  # Excel number: strip .0
        ("4033766024122.0", "4033766024122"),  # same, as text
        (4033766024122, "4033766024122"),
        ("0012345678905", "0012345678905"),  # leading zeros kept
        (" 4033766024122 ", "4033766024122"),
        ("#N/A", None),
        (" ", None),
    ],
)
def test_code_text(cell: object, expected: str | None) -> None:
    assert code_text(cell) == expected


@pytest.mark.parametrize(
    ("code", "ok"),
    [
        ("4033766024122", True),  # EAN-13 from the samples
        ("96385074", True),  # EAN-8
        ("036000291452", True),  # UPC-A (GTIN-12)
        ("10614141000415", True),  # GTIN-14
        ("4033766024123", False),  # wrong check digit
        ("43917996264", False),  # 11 digits: the one invalid value in both samples
        ("40337660241AB", False),
    ],
)
def test_gtin_check_digit(code: str, ok: bool) -> None:
    assert gtin_is_valid(code) is ok


@pytest.mark.parametrize(
    ("asin", "ok"),
    [("B003QQ37HI", True), ("3440174530", True), ("b003qq37hi", False), ("B003QQ37H", False)],
)
def test_asin(asin: str, ok: bool) -> None:
    assert asin_is_valid(asin) is ok


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        (78.11261999999999, Decimal("78.1126")),  # float noise from Excel, rounded half-up
        (2231.3300000000004, Decimal("2231.3300")),
        (115.62, Decimal("115.6200")),
        (125, Decimal("125.0000")),
        ("1.234,56", Decimal("1234.5600")),
        ("1,234.56", Decimal("1234.5600")),
        ("12,5", Decimal("12.5000")),
        ("€ 10.00", Decimal("10.0000")),
        (0.00005, Decimal("0.0001")),
        (None, None),
        ("#N/A", None),
    ],
)
def test_money_is_decimal_never_float(cell: object, expected: Decimal | None) -> None:
    result = money(cell)
    assert result == expected
    assert result is None or isinstance(result, Decimal)


@pytest.mark.parametrize("cell", ["abc", "1.2.3", True, 10**15])
def test_money_rejects_non_numbers(cell: object) -> None:
    with pytest.raises(CellValueError):
        money(cell)


@pytest.mark.parametrize(("cell", "expected"), [("3", 3), (3.0, 3), (24, 24), (None, None)])
def test_whole_numbers(cell: object, expected: int | None) -> None:
    assert whole_number(cell) == expected


@pytest.mark.parametrize("cell", ["2.5", -1, "x"])
def test_whole_number_rejects(cell: object) -> None:
    with pytest.raises(CellValueError):
        whole_number(cell)
