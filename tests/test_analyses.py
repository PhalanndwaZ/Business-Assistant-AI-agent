"""Tests for deterministic analysis results and edge cases."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.analysis.analyses import (
    outliers,
    period_change,
    revenue_by_category,
    revenue_by_period,
    revenue_by_product,
    run_analysis,
    top_customers,
    trend,
)
from app.data_access.json_loader import JsonDataStore
from scripts.generate_data import generate_records


@pytest.fixture
def store(tmp_path: Path) -> JsonDataStore:
    """Load freshly generated records for an isolated analysis test."""
    from tests.test_data_loading import _write_datasets

    _write_datasets(tmp_path, generate_records())
    return JsonDataStore(tmp_path)


def test_revenue_by_product_matches_independent_calculation(
    store: JsonDataStore,
) -> None:
    """Product revenue agrees with a separate Pandas calculation."""
    orders = store.get_frame("orders")
    items = store.get_frame("order_items")
    products = store.get_frame("products")
    selected_orders = orders.loc[
        orders["status"].eq("completed")
        & orders["order_date"].between("2024-11-01", "2024-11-30")
    ]
    expected = (
        items.merge(selected_orders, on="order_id")
        .assign(revenue=lambda frame: frame["quantity"] * frame["unit_price_cents"])
        .merge(products, on="product_id")
        .groupby("product_id")["revenue"]
        .sum()
        .sort_values(ascending=False)
    )

    result = revenue_by_product(store, "2024-11-01", "2024-11-30", top_n=1)

    assert result["data"][0]["product_id"] == expected.index[0]
    assert result["data"][0]["revenue_cents"] == expected.iloc[0]
    assert result["period"] == {"start": "2024-11-01", "end": "2024-11-30"}


def test_revenue_by_category_returns_integer_cents(store: JsonDataStore) -> None:
    """Category totals are represented as integer cents."""
    result = revenue_by_category(store, "2024-01-01", "2024-12-31")

    assert result["data"]
    assert all(isinstance(row["revenue_cents"], int) for row in result["data"])
    comparison = result["category_comparison"]
    assert comparison["highest_category"] == result["data"][0]["category"]
    assert comparison["lowest_category"] == result["data"][-1]["category"]
    assert comparison["revenue_difference_cents"] == (
        result["data"][0]["revenue_cents"]
        - result["data"][-1]["revenue_cents"]
    )
    assert comparison["difference_percent_of_lowest"] == pytest.approx(
        comparison["revenue_difference_cents"]
        / comparison["lowest_revenue_cents"]
        * 100
    )


def test_revenue_by_period_supports_month_granularity(
    store: JsonDataStore,
) -> None:
    """Monthly aggregation emits sorted month keys."""
    result = revenue_by_period(store, "2024-01-01", "2024-12-31", "month")

    periods = [row["period"] for row in result["data"]]
    assert periods == sorted(periods)
    assert periods[0] == "2024-01"
    assert periods[-1] == "2024-12"


def test_period_change_handles_zero_previous_value(store: JsonDataStore) -> None:
    """Percentage change is undefined rather than crashing at a zero baseline."""
    result = period_change(
        store,
        "revenue",
        "2024-11-01",
        "2024-11-30",
        "2023-11-01",
        "2023-11-30",
    )

    assert result["data"][0]["previous_value"] == 0
    assert result["data"][0]["percent_change"] is None


def test_empty_period_returns_an_empty_result(store: JsonDataStore) -> None:
    """A valid date range without sales returns an empty data list."""
    result = revenue_by_product(store, "2023-01-01", "2023-01-31")

    assert result["data"] == []


def test_top_customers_has_limit_and_revenue(store: JsonDataStore) -> None:
    """Customer ranking obeys top_n and includes calculated revenue."""
    result = top_customers(store, "2024-01-01", "2024-12-31", top_n=3)

    assert len(result["data"]) == 3
    assert all("revenue_cents" in customer for customer in result["data"])


def test_trend_and_outliers_include_metric_assumptions(
    store: JsonDataStore,
) -> None:
    """Trend and outlier outputs identify their methods and selected metric."""
    trend_result = trend(
        store, "revenue", "2024-01-01", "2024-12-31", "month"
    )
    outlier_result = outliers(
        store, "revenue", "2024-01-01", "2024-12-31", "month"
    )

    assert trend_result["data"][0]["direction"] in {
        "increasing",
        "decreasing",
        "flat",
    }
    assert "population standard" in outlier_result["assumptions"][0]


def test_run_analysis_rejects_unknown_parameters(
    store: JsonDataStore,
) -> None:
    """Analysis dispatch rejects parameters that are not part of its interface."""
    with pytest.raises(ValueError, match="Unknown parameter"):
        run_analysis(
            store,
            "revenue_by_product",
            {"start": "2024-01-01", "end": "2024-12-31", "path": "x"},
        )
