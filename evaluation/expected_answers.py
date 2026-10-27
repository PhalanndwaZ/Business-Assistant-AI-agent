"""Independent Pandas ground truth for the question-level benchmark."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.config import PROJECT_ROOT
from evaluation.questions import COMBINED, QUESTIONS, STRUCTURED_DATA


def _read_dataset(data_dir: Path, name: str) -> pd.DataFrame:
    """Read a raw approved JSON dataset without using production analyses."""
    return pd.read_json(data_dir / f"{name}.json", convert_dates=False)


def _completed_sales(data_dir: Path) -> pd.DataFrame:
    """Build completed-order line items independently from the analysis layer."""
    orders = _read_dataset(data_dir, "orders")
    orders["order_date"] = pd.to_datetime(orders["order_date"])
    completed = orders.loc[orders["status"].eq("completed")]
    items = _read_dataset(data_dir, "order_items")
    products = _read_dataset(data_dir, "products").rename(
        columns={"name": "product_name"}
    )
    customers = _read_dataset(data_dir, "customers").rename(
        columns={"name": "customer_name"}
    )
    sales = (
        items.merge(completed, on="order_id", how="inner")
        .merge(products, on="product_id", how="left")
        .merge(customers, on="customer_id", how="left")
    )
    sales["revenue_cents"] = sales["quantity"] * sales["unit_price_cents"]
    return sales


def _date_slice(
    sales: pd.DataFrame, start: str, end: str
) -> pd.DataFrame:
    return sales.loc[sales["order_date"].between(start, end)]


def _period_change(
    sales: pd.DataFrame,
    metric: str,
    current_start: str,
    current_end: str,
    previous_start: str,
    previous_end: str,
) -> dict[str, Any]:
    current = _date_slice(sales, current_start, current_end)
    previous = _date_slice(sales, previous_start, previous_end)
    if metric == "orders":
        current_value = int(current["order_id"].nunique())
        previous_value = int(previous["order_id"].nunique())
    elif metric == "units":
        current_value = int(current["quantity"].sum())
        previous_value = int(previous["quantity"].sum())
    else:
        current_value = int(current["revenue_cents"].sum())
        previous_value = int(previous["revenue_cents"].sum())
    change = current_value - previous_value
    percentage = (change / previous_value * 100) if previous_value else None
    return {
        "metric": metric,
        "current_value": current_value,
        "previous_value": previous_value,
        "absolute_change": change,
        "percent_change": percentage,
    }


def compute_expected_answers(
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Calculate exact expected results for every structured benchmark case."""
    source_dir = data_dir or PROJECT_ROOT / "data" / "sample_data"
    sales = _completed_sales(source_dir)
    expected: dict[str, Any] = {}

    for case in QUESTIONS:
        if case.group not in {STRUCTURED_DATA, COMBINED}:
            continue
        parameters = case.parameters or {}
        if case.analysis_name == "revenue_by_product":
            selected = _date_slice(
                sales, parameters["start"], parameters["end"]
            )
            rows = (
                selected.groupby(
                    ["product_id", "product_name", "category"], as_index=False
                )
                .agg(
                    revenue_cents=("revenue_cents", "sum"),
                    units=("quantity", "sum"),
                )
                .sort_values(
                    ["revenue_cents", "product_id"],
                    ascending=[False, True],
                )
                .head(parameters["top_n"])
            )
            expected[case.case_id] = rows.to_dict(orient="records")
        elif case.analysis_name == "revenue_by_category":
            selected = _date_slice(
                sales, parameters["start"], parameters["end"]
            )
            rows = (
                selected.groupby("category", as_index=False)
                .agg(
                    revenue_cents=("revenue_cents", "sum"),
                    units=("quantity", "sum"),
                )
                .sort_values(
                    ["revenue_cents", "category"],
                    ascending=[False, True],
                )
            )
            expected[case.case_id] = rows.to_dict(orient="records")
        elif case.analysis_name in {"revenue_by_period", "trend"}:
            selected = _date_slice(
                sales, parameters["start"], parameters["end"]
            ).copy()
            selected["period"] = selected["order_date"].dt.to_period("M").astype(str)
            if case.analysis_name == "revenue_by_period":
                rows = (
                    selected.groupby("period", as_index=False)
                    .agg(
                        revenue_cents=("revenue_cents", "sum"),
                        units=("quantity", "sum"),
                    )
                    .sort_values("period")
                )
                expected[case.case_id] = rows.to_dict(orient="records")
            else:
                periods = (
                    selected.groupby("period")["quantity"]
                    .sum()
                    .rename("value")
                    .reset_index()
                    .sort_values("period")
                )
                values = periods["value"].astype(float).to_numpy()
                slope = (
                    float(np.polyfit(np.arange(len(values)), values, 1)[0])
                    if len(values) > 1
                    else 0.0
                )
                direction = (
                    "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat"
                )
                expected[case.case_id] = {
                    "metric": "units",
                    "granularity": "month",
                    "direction": direction,
                    "period_values": periods.to_dict(orient="records"),
                }
        elif case.analysis_name == "period_change":
            expected[case.case_id] = _period_change(
                sales,
                parameters["metric"],
                parameters["current_start"],
                parameters["current_end"],
                parameters["previous_start"],
                parameters["previous_end"],
            )
        elif case.analysis_name == "top_customers":
            selected = _date_slice(
                sales, parameters["start"], parameters["end"]
            )
            rows = (
                selected.groupby(
                    ["customer_id", "customer_name"], as_index=False
                )
                .agg(
                    revenue_cents=("revenue_cents", "sum"),
                    order_count=("order_id", "nunique"),
                )
                .sort_values(
                    ["revenue_cents", "customer_id"],
                    ascending=[False, True],
                )
                .head(parameters["top_n"])
            )
            expected[case.case_id] = rows.to_dict(orient="records")
        elif case.dataset == "customers":
            expected[case.case_id] = {"total_matches": len(_read_dataset(source_dir, "customers"))}
        elif case.dataset == "orders":
            orders = _read_dataset(source_dir, "orders")
            orders["order_date"] = pd.to_datetime(orders["order_date"])
            date_range = parameters["date_range"]
            selected = orders.loc[
                orders["order_date"].between(
                    date_range["start"], date_range["end"]
                )
            ]
            selected = selected.loc[selected["status"].eq("completed")]
            expected[case.case_id] = {"total_matches": len(selected)}
        elif case.dataset == "products":
            products = _read_dataset(source_dir, "products")
            selected = products.loc[
                products["category"].eq("Electronics")
            ]
            expected[case.case_id] = {
                "total_matches": len(selected),
                "rows": selected[["name", "category"]].to_dict(orient="records"),
            }

    return expected
