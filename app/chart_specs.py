"""Build chart specifications directly from successful business-tool results."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from app.state import ToolResult

ChartSpec = dict[str, Any]


def build_chart_specs(tool_results: Sequence[ToolResult]) -> list[ChartSpec]:
    """Create up to three supported chart specs from returned tool results."""
    charts: list[ChartSpec] = []
    for index, tool_result in enumerate(tool_results, start=1):
        if not tool_result.get("success"):
            continue
        result = tool_result.get("result")
        if not isinstance(result, dict):
            continue
        if tool_result.get("tool_name") == "query_business_data":
            chart = _department_employee_chart(tool_result, result, index)
            if chart is not None:
                charts.append(chart)
            if len(charts) == 3:
                break
            continue
        if tool_result.get("tool_name") != "run_analysis":
            continue
        analysis = result.get("analysis")
        if not isinstance(analysis, str):
            continue

        chart = _chart_for_analysis(result, analysis, tool_result, index)
        if chart is not None:
            charts.append(chart)
        if len(charts) == 3:
            break
    return charts


def _department_employee_chart(
    tool_result: ToolResult,
    result: dict[str, Any],
    index: int,
) -> ChartSpec | None:
    """Chart complete department headcount or payroll query results."""
    arguments = tool_result.get("arguments")
    if (
        not isinstance(arguments, dict)
        or arguments.get("dataset") != "employees"
        or arguments.get("group_by") != ["department"]
        or result.get("dataset") != "employees"
    ):
        return None

    aggregate = arguments.get("aggregate")
    if aggregate not in {None, "sum_salary_cents"}:
        return None
    value_field = "salary_cents_sum" if aggregate == "sum_salary_cents" else "count"
    title = (
        "Total payroll by department"
        if aggregate == "sum_salary_cents"
        else "Headcount by department"
    )
    subtitle = (
        "Total salary · integer cents"
        if aggregate == "sum_salary_cents"
        else "Employee count · grouped by department"
    )
    unit = "money_cents" if aggregate == "sum_salary_cents" else "count"
    rows = result.get("rows")
    total_groups = result.get("total_groups")
    returned_rows = result.get("returned_rows")
    if (
        not isinstance(rows, list)
        or not rows
        or isinstance(total_groups, bool)
        or not isinstance(total_groups, int)
        or total_groups != len(rows)
        or isinstance(returned_rows, bool)
        or not isinstance(returned_rows, int)
        or returned_rows != len(rows)
    ):
        return None
    series: list[dict[str, Any]] = []
    seen_departments: set[str] = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("department"), str)
            or not row["department"]
            or isinstance(row.get(value_field), bool)
            or not isinstance(row.get(value_field), int)
            or row[value_field] < 0
            or row["department"] in seen_departments
        ):
            return None
        seen_departments.add(row["department"])
        series.append(
            {"label": row["department"], "value": row[value_field]}
        )

    call_id = tool_result.get("call_id")
    result_id = (
        call_id if isinstance(call_id, str) else f"query-{index}"
    )
    highlight = max(series, key=lambda item: item["value"])["label"]
    return {
        "id": result_id,
        "type": "ranking_bars",
        "title": title,
        "subtitle": subtitle,
        "unit": unit,
        "series": series,
        "highlight": highlight,
        "annotations": [],
        "source": {
            "analysis": "query_business_data",
            "result_id": result_id,
            "as_of": "",
        },
        "alt_text": (
            "Horizontal bars comparing "
            + (
                "total payroll"
                if aggregate == "sum_salary_cents"
                else "employee headcount"
            )
            + " across returned departments."
        ),
    }


def _chart_for_analysis(
    result: dict[str, Any],
    analysis: str,
    tool_result: ToolResult,
    index: int,
) -> ChartSpec | None:
    """Build the default chart for a recognized analysis result."""
    if analysis in {"revenue_by_category", "revenue_by_product", "top_customers"}:
        return _ranking_chart(result, analysis, tool_result, index)
    if analysis == "revenue_by_period":
        return _period_chart(result, tool_result, index)
    if analysis == "period_change":
        return _comparison_chart(result, tool_result, index)
    if analysis == "trend":
        return _trend_chart(result, tool_result, index)
    return None


def _chart_source(
    result: dict[str, Any],
    tool_result: ToolResult,
    index: int,
) -> dict[str, str]:
    """Identify the analysis call and its reported end date."""
    analysis = result["analysis"]
    call_id = tool_result.get("call_id")
    period = result.get("period")
    as_of = period.get("end") if isinstance(period, dict) else None
    if not isinstance(as_of, str):
        as_of = ""
    return {
        "analysis": analysis,
        "result_id": call_id if isinstance(call_id, str) else f"analysis-{index}",
        "as_of": as_of,
    }


def _period_subtitle(result: dict[str, Any]) -> str:
    """Describe the exact period returned by an analysis."""
    period = result.get("period")
    if not isinstance(period, dict):
        return "Completed orders · money in cents"
    start = period.get("start")
    end = period.get("end")
    if isinstance(start, str) and isinstance(end, str):
        return f"{start} to {end} · Completed orders · money in cents"
    return "Completed orders · money in cents"


def _ranking_chart(
    result: dict[str, Any],
    analysis: str,
    tool_result: ToolResult,
    index: int,
) -> ChartSpec | None:
    """Build a revenue ranking using only category, product, or customer rows."""
    label_field, title, alt_text = {
        "revenue_by_category": (
            "category",
            "Revenue by category",
            "Horizontal bars comparing returned category revenue.",
        ),
        "revenue_by_product": (
            "product_name",
            "Revenue by product",
            "Horizontal bars comparing returned product revenue.",
        ),
        "top_customers": (
            "customer_name",
            "Top customers by revenue",
            "Horizontal bars comparing returned customer revenue.",
        ),
    }[analysis]
    rows = result.get("data")
    if not isinstance(rows, list):
        return None
    series = [
        {"label": row[label_field], "value": row["revenue_cents"]}
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get(label_field), str)
        and _is_number(row.get("revenue_cents"))
    ]
    if not series:
        return None
    series.sort(key=lambda item: item["value"], reverse=True)
    return {
        "id": _chart_source(result, tool_result, index)["result_id"],
        "type": "ranking_bars",
        "title": title,
        "subtitle": _period_subtitle(result),
        "unit": "money_cents",
        "series": series,
        "highlight": series[0]["label"],
        "annotations": [],
        "source": _chart_source(result, tool_result, index),
        "alt_text": alt_text,
    }


def _period_chart(
    result: dict[str, Any],
    tool_result: ToolResult,
    index: int,
) -> ChartSpec | None:
    """Build a time-series chart only when at least two periods are present."""
    rows = result.get("data")
    if not isinstance(rows, list):
        return None
    series = [
        {"label": row["period"], "value": row["revenue_cents"]}
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("period"), str)
        and _is_number(row.get("revenue_cents"))
    ]
    if len(series) < 2:
        return None
    series.sort(key=lambda item: item["label"])
    source = _chart_source(result, tool_result, index)
    return {
        "id": source["result_id"],
        "type": "line",
        "title": "Revenue by period",
        "subtitle": _period_subtitle(result),
        "unit": "money_cents",
        "series": series,
        "highlight": series[-1]["label"],
        "annotations": [],
        "source": source,
        "alt_text": "Line chart showing returned revenue for each period.",
    }


def _comparison_chart(
    result: dict[str, Any],
    tool_result: ToolResult,
    index: int,
) -> ChartSpec | None:
    """Build a two-period chart from a single supported comparison result."""
    rows = result.get("data")
    periods = result.get("period")
    if (
        not isinstance(rows, list)
        or len(rows) != 1
        or not isinstance(rows[0], dict)
        or not isinstance(periods, dict)
    ):
        return None
    row = rows[0]
    metric = row.get("metric")
    if metric not in {"revenue", "orders", "units"}:
        return None
    previous_value = row.get("previous_value")
    current_value = row.get("current_value")
    absolute_change = row.get("absolute_change")
    previous_period = periods.get("previous")
    current_period = periods.get("current")
    if (
        not all(
            _is_number(value)
            for value in (previous_value, current_value, absolute_change)
        )
        or not isinstance(previous_period, dict)
        or not isinstance(current_period, dict)
    ):
        return None
    previous_label = _period_label(previous_period)
    current_label = _period_label(current_period)
    if not previous_label or not current_label or previous_label == current_label:
        return None
    unit = "money_cents" if metric == "revenue" else "count"
    measure = "Revenue" if metric == "revenue" else metric.title()
    direction = (
        "increased"
        if absolute_change > 0
        else "decreased"
        if absolute_change < 0
        else "was unchanged"
    )
    source = _chart_source(result, tool_result, index)
    return {
        "id": source["result_id"],
        "type": "compare_bars",
        "title": f"{measure} {direction} across the selected periods",
        "subtitle": f"{previous_label} vs {current_label} · {unit}",
        "unit": unit,
        "series": [
            {"label": previous_label, "value": previous_value},
            {"label": current_label, "value": current_value},
        ],
        "highlight": current_label,
        "annotations": [{"label": "Change", "value": absolute_change}],
        "source": source,
        "alt_text": f"Comparison of {measure.lower()} for {previous_label} and {current_label}.",
    }


def _trend_chart(
    result: dict[str, Any],
    tool_result: ToolResult,
    index: int,
) -> ChartSpec | None:
    """Build a line chart from the exact period values returned by trend."""
    rows = result.get("data")
    if (
        not isinstance(rows, list)
        or len(rows) != 1
        or not isinstance(rows[0], dict)
    ):
        return None
    row = rows[0]
    metric = row.get("metric")
    period_values = row.get("period_values")
    if metric not in {"revenue", "orders", "units"} or not isinstance(period_values, list):
        return None
    series = [
        {"label": point["period"], "value": point["value"]}
        for point in period_values
        if isinstance(point, dict)
        and isinstance(point.get("period"), str)
        and _is_number(point.get("value"))
    ]
    if len(series) < 2:
        return None
    series.sort(key=lambda item: item["label"])
    source = _chart_source(result, tool_result, index)
    unit = "money_cents" if metric == "revenue" else "count"
    return {
        "id": source["result_id"],
        "type": "line",
        "title": f"{metric.title()} trend",
        "subtitle": (
            f"{_period_subtitle(result)} · "
            f"{row.get('granularity', 'period')} trend"
        ),
        "unit": unit,
        "series": series,
        "highlight": series[-1]["label"],
        "annotations": [],
        "source": source,
        "alt_text": f"Line chart showing returned {metric} values over time.",
    }


def _period_label(period: dict[str, Any]) -> str:
    """Format a returned period as its month label when it is a valid date."""
    end = period.get("end")
    if not isinstance(end, str):
        return ""
    try:
        return date.fromisoformat(end).strftime("%B %Y")
    except ValueError:
        return end


def _is_number(value: Any) -> bool:
    """Accept finite numeric tool values while rejecting booleans."""
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool)
    )
