"""Format raw report values for display in generated documents."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.reporting.models import ReportFormat


def format_money(value: int | float) -> str:
    """Convert integer cents to whole South African rand with grouping."""
    amount = _decimal_number(value, "money") / Decimal(100)
    rounded = amount.copy_abs().quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    return f"{sign}R{rounded:,.0f}"


def format_percent(value: int | float) -> str:
    """Format a percentage to one decimal place while retaining its sign."""
    number = _finite_number(value, "percent")
    return f"{number:.1f}%"


def format_integer(value: int | float) -> str:
    """Format a whole-number value using thousands separators."""
    number = _finite_number(value, "integer")
    if not number.is_integer():
        raise ValueError("integer format requires a whole-number value.")
    return f"{int(number):,}"


def format_text(value: str) -> str:
    """Return text unchanged for report display."""
    if not isinstance(value, str):
        raise TypeError("text format requires a string value.")
    return value


def format_value(value: Any, value_format: ReportFormat) -> str:
    """Dispatch a raw report value to its validated display formatter."""
    if value_format == "money":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("money format requires a numeric value in cents.")
        return format_money(value)
    if value_format == "percent":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("percent format requires a numeric value.")
        return format_percent(value)
    if value_format == "integer":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("integer format requires a numeric value.")
        return format_integer(value)
    return format_text(value)


def _finite_number(value: int | float, value_format: str) -> float:
    """Return a finite numeric value or raise a format-specific error."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{value_format} format requires a numeric value.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{value_format} format requires a finite value.")
    return number


def _decimal_number(value: int | float, value_format: str) -> Decimal:
    """Convert supported numeric values to Decimal without binary artifacts."""
    _finite_number(value, value_format)
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{value_format} format requires a finite value.") from exc
