"""Tests for the Step 2 report value formatters."""

from __future__ import annotations

import pytest

from app.reporting.formatting import (
    format_integer,
    format_money,
    format_percent,
    format_text,
    format_value,
)


@pytest.mark.parametrize(
    ("cents", "expected"),
    [
        (18_420_000, "R184,200"),
        (3_140_000, "R31,400"),
        (-2_511_800, "-R25,118"),
        (1_842_049, "R18,420"),
        (1_842_050, "R18,421"),
        (-1_842_050, "-R18,421"),
        (0, "R0"),
    ],
)
def test_money_converts_cents_to_rounded_rand(
    cents: int,
    expected: str,
) -> None:
    """Money is interpreted as cents and rounded to whole rand."""
    assert format_money(cents) == expected


def test_percent_formats_to_one_decimal_place() -> None:
    """Percentages retain a minus sign and round to one decimal place."""
    assert format_percent(-12.04) == "-12.0%"
    assert format_percent(12.06) == "12.1%"


def test_integer_formats_with_thousands_separators() -> None:
    """Integer values use grouped digits without decimal places."""
    assert format_integer(1234567) == "1,234,567"


def test_text_is_returned_unchanged() -> None:
    """Text format preserves the original label value."""
    assert format_text("Oak Dining Table") == "Oak Dining Table"


def test_generic_formatter_dispatches_by_format() -> None:
    """The shared formatter selects the requested display function."""
    assert format_value(18_420_000, "money") == "R184,200"
    assert format_value(-12.04, "percent") == "-12.0%"
    assert format_value(1200, "integer") == "1,200"
    assert format_value("Sales", "text") == "Sales"


def test_money_rejects_non_finite_values() -> None:
    """Invalid numeric values fail rather than producing a misleading amount."""
    with pytest.raises(ValueError, match="finite"):
        format_money(float("nan"))


def test_integer_rejects_fractional_values() -> None:
    """Integer formatting refuses to silently truncate a decimal."""
    with pytest.raises(ValueError, match="whole-number"):
        format_integer(2.5)
