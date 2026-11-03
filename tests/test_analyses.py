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
from app.analysis.product_portfolio import product_portfolio
from app.analysis.customer_segments import customer_segments
from app.analysis.risk_assessment import assess_decline_risk
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


def test_product_portfolio_item_revenue_and_shares_sum(store: JsonDataStore) -> None:
    """Portfolio rows preserve the window revenue exactly."""
    result = product_portfolio(store, "2024-01-01", "2024-12-31")

    item_revenue = sum(item["revenue_cents"] for item in result["items"])
    assert item_revenue == result["portfolio"]["revenue_cents"]
    assert abs(sum(item["share"] for item in result["items"]) - 1.0) <= 0.001


def test_customer_segments_totals_and_small_sample(store: JsonDataStore) -> None:
    """Segment memberships and revenue preserve exact totals."""
    result = customer_segments(store, "2024-01-01", "2024-12-31")

    assert sum(segment["customers"] for segment in result["segments"]) == result["customers_counted"]


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


def test_product_portfolio_matches_independent_totals(store: JsonDataStore) -> None:
    """Portfolio revenue, shares, and concentration match raw Pandas totals."""
    orders = store.get_frame("orders")
    items = store.get_frame("order_items")
    products = store.get_frame("products")
    completed = orders.loc[
        orders["status"].eq("completed")
        & orders["order_date"].between("2024-01-01", "2024-12-31")
    ]
    expected = (
        items.merge(completed, on="order_id")
        .assign(revenue=lambda frame: frame["quantity"] * frame["unit_price_cents"])
        .merge(products, on="product_id")
        .groupby("product_id", as_index=False)["revenue"]
        .sum()
    )

    result = product_portfolio(store, "2024-01-01", "2024-12-31")

    assert sum(item["revenue_cents"] for item in result["items"]) == int(
        expected["revenue"].sum()
    )
    assert abs(sum(item["share"] for item in result["items"]) - 1.0) <= 0.001
    assert result["portfolio"]["hhi"] == pytest.approx(
        sum(item["share"] ** 2 for item in result["items"]),
        abs=1e-6,
    )


def test_portfolio_empty_window_and_repeatability(store: JsonDataStore) -> None:
    """Empty windows are deterministic and valid calls do not mutate results."""
    empty = product_portfolio(store, "2023-01-01", "2023-01-31")
    first = product_portfolio(store, "2024-01-01", "2024-12-31")
    second = product_portfolio(store, "2024-01-01", "2024-12-31")

    assert empty["items"] == []
    assert empty["portfolio"]["revenue_cents"] == 0
    assert first == second


def test_customer_segment_totals_and_repeatability(store: JsonDataStore) -> None:
    """Independent segment invariants hold and calls are stable."""
    first = customer_segments(store, "2024-01-01", "2024-12-31")
    second = customer_segments(store, "2024-01-01", "2024-12-31")
    orders = store.get_frame("orders")
    items = store.get_frame("order_items")
    completed_ids = orders.loc[
        orders["status"].eq("completed")
        & orders["order_date"].between("2024-01-01", "2024-12-31"),
        "order_id",
    ]
    window_revenue = int(
        (
            items.loc[items["order_id"].isin(completed_ids), "quantity"]
            * items.loc[items["order_id"].isin(completed_ids), "unit_price_cents"]
        ).sum()
    )

    assert first == second
    assert sum(row["customers"] for row in first["segments"]) == first["customers_counted"]
    assert sum(row["revenue_cents"] for row in first["segments"]) == window_revenue


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Supplier delays reduced availability.", ["Supplier delays", "Availability"]),
        ("Revenue was flat with no reported factor.", []),
    ],
)
def test_decline_risk_reports_factors_without_inferred_cause(
    text: str,
    expected: list[str],
) -> None:
    """Decline-risk evidence is limited to factors named in documents."""
    result = assess_decline_risk([{"text": text, "origin": "uploaded"}])

    if expected:
        assert all(
            factor.startswith(expected_factor)
            for factor, expected_factor in zip(
                result["reported_factors"],
                expected,
            )
        )
        assert all("(reported in your document)" in factor for factor in result["reported_factors"])
    else:
        assert result["reported_factors"] == []
