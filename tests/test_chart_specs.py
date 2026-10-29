"""Tests for chart specifications derived from analysis tool results."""

from __future__ import annotations

from typing import Any

from app.chart_specs import build_chart_specs
from app.state import ToolResult


def _result(
    analysis: str,
    data: list[dict[str, Any]],
    *,
    period: dict[str, Any] | None = None,
    call_id: str = "analysis-call",
    success: bool = True,
) -> ToolResult:
    """Create one deterministic analysis result for chart-builder tests."""
    result: dict[str, Any] = {"analysis": analysis, "data": data}
    if period is not None:
        result["period"] = period
    return {
        "call_id": call_id,
        "tool_name": "run_analysis",
        "arguments": {},
        "result": result,
        "success": success,
    }


def test_category_ranking_chart_uses_source_values_and_order() -> None:
    """A category analysis produces highlighted bars from its returned values."""
    chart = build_chart_specs(
        [
            _result(
                "revenue_by_category",
                [
                    {"category": "Electronics", "revenue_cents": 12000},
                    {"category": "Furniture", "revenue_cents": 8000},
                ],
                period={"start": "2024-11-01", "end": "2024-11-30"},
                call_id="category-call",
            )
        ]
    )[0]

    assert chart["type"] == "ranking_bars"
    assert chart["unit"] == "money_cents"
    assert chart["series"] == [
        {"label": "Electronics", "value": 12000},
        {"label": "Furniture", "value": 8000},
    ]
    assert chart["highlight"] == "Electronics"
    assert chart["source"] == {
        "analysis": "revenue_by_category",
        "result_id": "category-call",
        "as_of": "2024-11-30",
    }


def test_single_month_revenue_total_does_not_create_misleading_trend() -> None:
    """One monthly total is not presented as a time-series chart."""
    result = _result(
        "revenue_by_period",
        [{"period": "2024-11", "revenue_cents": 4017949, "units": 251}],
        period={"start": "2024-11-01", "end": "2024-11-30"},
    )

    assert build_chart_specs([result]) == []


def test_revenue_by_period_creates_a_line_with_latest_period_highlighted() -> None:
    """A multi-period result creates a line chart in chronological order."""
    result = _result(
        "revenue_by_period",
        [
            {"period": "2024-12", "revenue_cents": 1000},
            {"period": "2024-11", "revenue_cents": 2000},
        ],
        period={"start": "2024-11-01", "end": "2024-12-31"},
    )

    chart = build_chart_specs([result])[0]

    assert chart["type"] == "line"
    assert chart["series"] == [
        {"label": "2024-11", "value": 2000},
        {"label": "2024-12", "value": 1000},
    ]
    assert chart["highlight"] == "2024-12"


def test_period_change_creates_two_period_comparison_chart() -> None:
    """Comparison charts preserve values, units, and supplied change."""
    result = _result(
        "period_change",
        [
            {
                "metric": "revenue",
                "previous_value": 4017949,
                "current_value": 1574792,
                "absolute_change": -2443157,
                "percent_change": -60.8,
            }
        ],
        period={
            "previous": {"start": "2024-11-01", "end": "2024-11-30"},
            "current": {"start": "2024-12-01", "end": "2024-12-31"},
        },
    )

    chart = build_chart_specs([result])[0]

    assert chart["type"] == "compare_bars"
    assert chart["series"] == [
        {"label": "November 2024", "value": 4017949},
        {"label": "December 2024", "value": 1574792},
    ]
    assert chart["annotations"] == [
        {"label": "Change", "value": -2443157}
    ]
    assert chart["highlight"] == "December 2024"


def test_unsuccessful_analyses_never_produce_charts() -> None:
    """Failed MCP results cannot be used as chart data."""
    result = _result(
        "revenue_by_category",
        [{"category": "Electronics", "revenue_cents": 12000}],
        success=False,
    )

    assert build_chart_specs([result]) == []
