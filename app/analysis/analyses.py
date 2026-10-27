"""Named, deterministic Pandas analyses over the approved JSON datasets."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

import numpy as np
import pandas as pd

from app.analysis.rules import calculate_revenue_cents, eligible_orders
from app.data_access.json_loader import JsonDataStore

VALID_GRANULARITIES = frozenset({"day", "week", "month"})
VALID_METRICS = frozenset({"revenue", "orders", "units"})


def _iso_date(value: date | str) -> date:
    """Normalize a date argument and reject invalid date inputs."""
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Date must use ISO 8601 format: {value!r}.") from exc


def _validate_range(start: date | str, end: date | str) -> tuple[date, date]:
    """Normalize inclusive start and end dates and validate their order."""
    start_date = _iso_date(start)
    end_date = _iso_date(end)
    if start_date > end_date:
        raise ValueError("start must be on or before end.")
    return start_date, end_date


def _validate_positive_integer(name: str, value: int) -> None:
    """Reject booleans, non-integers, and non-positive count parameters."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")


def _sales_rows(
    store: JsonDataStore,
    start: date | str,
    end: date | str,
) -> tuple[pd.DataFrame, date, date]:
    """Join completed order items to their business dimensions and dates."""
    start_date, end_date = _validate_range(start, end)
    orders = eligible_orders(store.get_frame("orders"))
    orders = orders.loc[
        orders["order_date"].between(
            pd.Timestamp(start_date), pd.Timestamp(end_date)
        )
    ]
    items = store.get_frame("order_items")
    products = store.get_frame("products").rename(columns={"name": "product_name"})
    customers = store.get_frame("customers").rename(
        columns={"name": "customer_name"}
    )
    sales = (
        items.merge(orders, on="order_id", how="inner")
        .merge(products, on="product_id", how="left")
        .merge(customers, on="customer_id", how="left")
    )
    sales["revenue_cents"] = calculate_revenue_cents(sales)
    return sales, start_date, end_date


def _result(
    analysis: str,
    data: list[dict[str, Any]],
    start: date,
    end: date,
    filters: dict[str, Any] | None = None,
    assumptions: list[str] | None = None,
) -> dict[str, Any]:
    """Package an analysis result with its effective inputs and assumptions."""
    return {
        "analysis": analysis,
        "data": data,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "filters": filters or {},
        "assumptions": assumptions
        or [
            "Only completed orders are included.",
            "Revenue is quantity multiplied by unit price in integer cents.",
        ],
    }


def revenue_by_product(
    store: JsonDataStore,
    start: date | str,
    end: date | str,
    top_n: int = 10,
) -> dict[str, Any]:
    """Rank products by completed-order revenue for an inclusive date range."""
    _validate_positive_integer("top_n", top_n)
    sales, start_date, end_date = _sales_rows(store, start, end)
    grouped = (
        sales.groupby(["product_id", "product_name", "category"], as_index=False)
        .agg(revenue_cents=("revenue_cents", "sum"), units=("quantity", "sum"))
        .sort_values(["revenue_cents", "product_id"], ascending=[False, True])
        .head(top_n)
    )
    return _result(
        "revenue_by_product",
        grouped.to_dict(orient="records"),
        start_date,
        end_date,
        {"top_n": top_n},
    )


def revenue_by_category(
    store: JsonDataStore,
    start: date | str,
    end: date | str,
) -> dict[str, Any]:
    """Summarize completed-order revenue by product category."""
    sales, start_date, end_date = _sales_rows(store, start, end)
    grouped = (
        sales.groupby("category", as_index=False)
        .agg(revenue_cents=("revenue_cents", "sum"), units=("quantity", "sum"))
        .sort_values(["revenue_cents", "category"], ascending=[False, True])
    )
    result = _result(
        "revenue_by_category",
        grouped.to_dict(orient="records"),
        start_date,
        end_date,
    )
    if not grouped.empty:
        highest = grouped.iloc[0]
        lowest = grouped.iloc[-1]
        revenue_difference = int(highest["revenue_cents"] - lowest["revenue_cents"])
        lowest_revenue = int(lowest["revenue_cents"])
        result["category_comparison"] = {
            "highest_category": highest["category"],
            "highest_revenue_cents": int(highest["revenue_cents"]),
            "lowest_category": lowest["category"],
            "lowest_revenue_cents": lowest_revenue,
            "revenue_difference_cents": revenue_difference,
            "difference_percent_of_lowest": (
                revenue_difference / lowest_revenue * 100
                if lowest_revenue
                else None
            ),
        }
    return result


def _period_key(values: pd.Series, granularity: str) -> pd.Series:
    """Convert dates into stable calendar day, Monday-week, or month keys."""
    if granularity not in VALID_GRANULARITIES:
        raise ValueError(
            f"granularity must be one of {sorted(VALID_GRANULARITIES)}."
        )
    dates = pd.to_datetime(values)
    if granularity == "day":
        return dates.dt.strftime("%Y-%m-%d")
    if granularity == "week":
        return dates.dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")
    return dates.dt.to_period("M").astype(str)


def _metric_values(sales: pd.DataFrame, metric: str) -> tuple[str, pd.Series]:
    """Resolve an approved trend metric to a label and numeric column."""
    if metric not in VALID_METRICS:
        raise ValueError(f"metric must be one of {sorted(VALID_METRICS)}.")
    if metric == "revenue":
        return "revenue_cents", sales["revenue_cents"]
    if metric == "orders":
        return "order_count", sales["order_id"]
    return "units", sales["quantity"]


def revenue_by_period(
    store: JsonDataStore,
    start: date | str,
    end: date | str,
    granularity: str = "month",
) -> dict[str, Any]:
    """Aggregate completed-order revenue by a calendar time period."""
    sales, start_date, end_date = _sales_rows(store, start, end)
    sales["period"] = _period_key(sales["order_date"], granularity)
    grouped = (
        sales.groupby("period", as_index=False)
        .agg(revenue_cents=("revenue_cents", "sum"), units=("quantity", "sum"))
        .sort_values("period")
    )
    return _result(
        "revenue_by_period",
        grouped.to_dict(orient="records"),
        start_date,
        end_date,
        {"granularity": granularity},
    )


def _aggregate_metric(sales: pd.DataFrame, metric: str) -> float:
    """Aggregate one of the supported metrics over the selected sales rows."""
    _, values = _metric_values(sales, metric)
    if metric == "orders":
        return float(sales["order_id"].nunique())
    return float(values.sum())


def period_change(
    store: JsonDataStore,
    metric: str,
    current_start: date | str,
    current_end: date | str,
    previous_start: date | str,
    previous_end: date | str,
) -> dict[str, Any]:
    """Compare one approved metric across two explicitly supplied periods."""
    if metric not in VALID_METRICS:
        raise ValueError(f"metric must be one of {sorted(VALID_METRICS)}.")
    current, current_start_date, current_end_date = _sales_rows(
        store, current_start, current_end
    )
    previous, previous_start_date, previous_end_date = _sales_rows(
        store, previous_start, previous_end
    )
    current_value = _aggregate_metric(current, metric)
    previous_value = _aggregate_metric(previous, metric)
    absolute_change = current_value - previous_value
    percent_change = (
        None
        if previous_value == 0
        else (absolute_change / previous_value) * 100
    )
    return {
        "analysis": "period_change",
        "data": [
            {
                "metric": metric,
                "current_value": int(current_value),
                "previous_value": int(previous_value),
                "absolute_change": int(absolute_change),
                "percent_change": percent_change,
            }
        ],
        "period": {
            "current": {
                "start": current_start_date.isoformat(),
                "end": current_end_date.isoformat(),
            },
            "previous": {
                "start": previous_start_date.isoformat(),
                "end": previous_end_date.isoformat(),
            },
        },
        "filters": {"metric": metric},
        "assumptions": [
            "Only completed orders are included.",
            "A zero previous value has no defined percentage change.",
            "Revenue is returned in integer cents.",
        ],
    }


def top_customers(
    store: JsonDataStore,
    start: date | str,
    end: date | str,
    top_n: int = 10,
) -> dict[str, Any]:
    """Rank customers by completed-order revenue over an inclusive period."""
    _validate_positive_integer("top_n", top_n)
    sales, start_date, end_date = _sales_rows(store, start, end)
    grouped = (
        sales.groupby(
            ["customer_id", "customer_name", "region", "segment"],
            as_index=False,
        )
        .agg(
            revenue_cents=("revenue_cents", "sum"),
            order_count=("order_id", "nunique"),
        )
        .sort_values(["revenue_cents", "customer_id"], ascending=[False, True])
        .head(top_n)
    )
    return _result(
        "top_customers",
        grouped.to_dict(orient="records"),
        start_date,
        end_date,
        {"top_n": top_n},
    )


def _series_for_metric(
    store: JsonDataStore,
    metric: str,
    start: date | str,
    end: date | str,
    granularity: str,
) -> tuple[pd.DataFrame, date, date]:
    """Build a sorted series for a validated metric and time granularity."""
    sales, start_date, end_date = _sales_rows(store, start, end)
    sales["period"] = _period_key(sales["order_date"], granularity)
    if metric == "orders":
        series = sales.groupby("period")["order_id"].nunique().rename("value")
    else:
        value_column = "revenue_cents" if metric == "revenue" else "quantity"
        series = sales.groupby("period")[value_column].sum().rename("value")
    return series.reset_index().sort_values("period"), start_date, end_date


def trend(
    store: JsonDataStore,
    metric: str,
    start: date | str,
    end: date | str,
    granularity: str = "month",
) -> dict[str, Any]:
    """Estimate linear slope and direction across period metric values."""
    if metric not in VALID_METRICS:
        raise ValueError(f"metric must be one of {sorted(VALID_METRICS)}.")
    series, start_date, end_date = _series_for_metric(
        store, metric, start, end, granularity
    )
    values = series["value"].astype(float).to_numpy()
    slope = float(np.polyfit(np.arange(len(values)), values, 1)[0]) if len(values) > 1 else 0.0
    direction = "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat"
    return _result(
        "trend",
        [
            {
                "metric": metric,
                "granularity": granularity,
                "slope_per_period": slope,
                "direction": direction,
                "period_values": series.to_dict(orient="records"),
            }
        ],
        start_date,
        end_date,
        {"metric": metric, "granularity": granularity},
        [
            "Slope is the least-squares linear fit across observed periods.",
            "Only completed orders are included.",
            "Revenue, when selected, is measured in integer cents.",
        ],
    )


def outliers(
    store: JsonDataStore,
    metric: str,
    start: date | str,
    end: date | str,
    granularity: str = "month",
) -> dict[str, Any]:
    """Flag period values more than two population standard deviations away."""
    if metric not in VALID_METRICS:
        raise ValueError(f"metric must be one of {sorted(VALID_METRICS)}.")
    series, start_date, end_date = _series_for_metric(
        store, metric, start, end, granularity
    )
    values = series["value"].astype(float)
    mean = float(values.mean()) if not values.empty else 0.0
    deviation = float(values.std(ddof=0)) if not values.empty else 0.0
    cutoff = 2 * deviation
    result_rows = series.assign(
        deviation_from_mean=values - mean,
        is_outlier=(values - mean).abs() > cutoff if deviation else False,
    )
    return _result(
        "outliers",
        result_rows.to_dict(orient="records"),
        start_date,
        end_date,
        {"metric": metric, "granularity": granularity},
        [
            "An outlier is a period more than two population standard "
            "deviations from the selected range's mean.",
            "Only completed orders are included.",
        ],
    )


ANALYSIS_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "revenue_by_product": revenue_by_product,
    "revenue_by_category": revenue_by_category,
    "revenue_by_period": revenue_by_period,
    "period_change": period_change,
    "top_customers": top_customers,
    "trend": trend,
    "outliers": outliers,
}


def run_analysis(
    store: JsonDataStore,
    analysis_name: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Invoke an allowlisted analysis with validated parameter names."""
    if analysis_name not in ANALYSIS_FUNCTIONS:
        raise ValueError(f"Unknown analysis '{analysis_name}'.")
    function = ANALYSIS_FUNCTIONS[analysis_name]
    accepted_parameters = set(function.__annotations__) - {"return", "store"}
    unknown_parameters = parameters.keys() - accepted_parameters
    if unknown_parameters:
        raise ValueError(
            f"Unknown parameter(s) for '{analysis_name}': "
            f"{sorted(unknown_parameters)}."
        )
    return function(store=store, **parameters)
