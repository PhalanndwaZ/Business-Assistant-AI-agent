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


def test_employee_department_query_creates_headcount_chart() -> None:
    """A successful department-grouped employee query creates a count chart."""
    result: ToolResult = {
        "call_id": "employee-departments",
        "tool_name": "query_business_data",
        "arguments": {
            "dataset": "employees",
            "fields": ["department"],
            "group_by": ["department"],
        },
        "result": {
            "dataset": "employees",
            "fields": ["department", "count"],
            "total_matches": 15,
            "total_groups": 3,
            "returned_rows": 3,
            "rows": [
                {"department": "HR", "count": 5},
                {"department": "Operations", "count": 5},
                {"department": "Sales", "count": 5},
            ],
        },
        "success": True,
    }

    chart = build_chart_specs([result])[0]

    assert chart["type"] == "ranking_bars"
    assert chart["title"] == "Headcount by department"
    assert chart["unit"] == "count"
    assert chart["series"] == [
        {"label": "HR", "value": 5},
        {"label": "Operations", "value": 5},
        {"label": "Sales", "value": 5},
    ]
    assert chart["source"]["analysis"] == "query_business_data"
    assert chart["source"]["result_id"] == "employee-departments"


def test_employee_department_payroll_query_creates_money_chart() -> None:
    """Authorized salary sums render as cents-valued department bars."""
    result: ToolResult = {
        "call_id": "department-payroll",
        "tool_name": "query_business_data",
        "arguments": {
            "dataset": "employees",
            "fields": ["department"],
            "group_by": ["department"],
            "aggregate": "sum_salary_cents",
        },
        "result": {
            "dataset": "employees",
            "fields": ["department", "salary_cents_sum"],
            "total_matches": 15,
            "total_groups": 3,
            "returned_rows": 3,
            "rows": [
                {"department": "HR", "salary_cents_sum": 150_000_000},
                {
                    "department": "Operations",
                    "salary_cents_sum": 250_000_000,
                },
                {"department": "Sales", "salary_cents_sum": 350_000_000},
            ],
        },
        "success": True,
    }

    chart = build_chart_specs([result])[0]

    assert chart["type"] == "ranking_bars"
    assert chart["title"] == "Total payroll by department"
    assert chart["unit"] == "money_cents"
    assert chart["series"] == [
        {"label": "HR", "value": 150_000_000},
        {"label": "Operations", "value": 250_000_000},
        {"label": "Sales", "value": 350_000_000},
    ]
    assert chart["highlight"] == "Sales"


def test_employee_department_chart_rejects_malformed_group_rows() -> None:
    """Partial grouped data must not be presented as a complete chart."""
    result: ToolResult = {
        "tool_name": "query_business_data",
        "arguments": {
            "dataset": "employees",
            "group_by": ["department"],
        },
        "result": {
            "dataset": "employees",
            "total_groups": 2,
            "returned_rows": 2,
            "rows": [
                {"department": "HR", "count": 5},
                {"department": "Sales", "count": "unknown"},
            ],
        },
        "success": True,
    }

    assert build_chart_specs([result]) == []


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
