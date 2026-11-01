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


def _customer_segment_truth(
    sales: pd.DataFrame,
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    start: str,
    end: str,
) -> dict[str, Any]:
    """Calculate independent RFM segment totals from raw approved data."""
    completed = orders.loc[
        orders["status"].eq("completed")
        & orders["order_date"].between(start, end)
    ].copy()
    customers_by_order = completed["customer_id"].unique().tolist()
    if len(customers_by_order) < 5:
        return {
            "customers_counted": len(customers_by_order),
            "revenue_cents": int(
                sales.loc[
                    sales["order_id"].isin(completed["order_id"]),
                    "revenue_cents",
                ].sum()
            ),
            "segments": {},
        }

    period_sales = sales.loc[sales["order_id"].isin(completed["order_id"])]
    monetary = period_sales.groupby("customer_id", sort=False)["revenue_cents"].sum()
    frequency = completed.groupby("customer_id")["order_id"].nunique()
    recency = (
        pd.Timestamp(end) - completed.groupby("customer_id")["order_date"].max()
    ).dt.days
    rfm = pd.concat(
        {"frequency": frequency, "monetary": monetary, "recency": recency},
        axis=1,
    )

    def score(values: pd.Series, ascending: bool) -> pd.Series:
        if len(values) < 5:
            return pd.Series(3, index=values.index, dtype=int)
        ranks = values.rank(method="first", ascending=ascending)
        return pd.qcut(ranks, 5, labels=[1, 2, 3, 4, 5]).astype(int)

    rfm["r_score"] = 6 - score(rfm["recency"], ascending=True)
    rfm["f_score"] = score(rfm["frequency"], ascending=True)
    rfm["m_score"] = score(rfm["monetary"], ascending=True)
    segment_names = {
        "Champions": lambda row: row["r_score"] >= 4
        and row["f_score"] >= 4
        and row["m_score"] >= 4,
        "Loyal": lambda row: row["r_score"] >= 3 and row["f_score"] >= 3,
        "At Risk": lambda row: row["r_score"] <= 2 and row["f_score"] >= 3,
        "Lost": lambda row: row["r_score"] == 1 and row["f_score"] <= 2,
    }
    assigned: list[str] = []
    for _, row in rfm.iterrows():
        segment = "Occasional"
        for name, predicate in segment_names.items():
            if predicate(row):
                segment = "At risk" if name == "At Risk" else name
                break
        assigned.append(segment)
    rfm["segment"] = assigned
    segment_counts = rfm.groupby("segment").size().to_dict()
    segment_revenue = rfm.join(monetary.rename("segment_revenue")).groupby("segment")[
        "segment_revenue"
    ].sum().to_dict()
    return {
        "customers_counted": len(rfm),
        "revenue_cents": int(monetary.sum()),
        "segments": {
            str(name): {
                "customers": int(segment_counts.get(name, 0)),
                "revenue_cents": int(segment_revenue.get(name, 0)),
            }
            for name in ["Champions", "Loyal", "At risk", "Lost", "Occasional"]
        },
    }


def _product_portfolio_truth(
    sales: pd.DataFrame,
    start: str,
    end: str,
) -> dict[str, Any]:
    """Calculate independent product revenue, shares and concentration."""
    selected = _date_slice(sales, start, end)
    rows = (
        selected.groupby(
            ["product_id", "product_name", "category"], as_index=False
        )
        .agg(
            revenue_cents=("revenue_cents", "sum"),
            units=("quantity", "sum"),
        )
        .sort_values(["revenue_cents", "product_id"], ascending=[False, True])
        .reset_index(drop=True)
    )
    total_revenue = int(rows["revenue_cents"].sum()) if not rows.empty else 0
    if not rows.empty:
        rows["share"] = rows["revenue_cents"] / total_revenue
    return {
        "revenue_cents": total_revenue,
        "product_count": len(rows),
        "hhi": float((rows["share"] ** 2).sum()) if not rows.empty else 0.0,
        "items": rows.to_dict(orient="records"),
    }


def compute_expected_answers(
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Calculate exact expected results for every structured benchmark case."""
    source_dir = data_dir or PROJECT_ROOT / "data" / "sample_data"
    sales = _completed_sales(source_dir)
    orders = _read_dataset(source_dir, "orders")
    orders["order_date"] = pd.to_datetime(orders["order_date"])
    customers = _read_dataset(source_dir, "customers")
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
        elif case.analysis_name == "customer_segments":
            expected[case.case_id] = _customer_segment_truth(
                sales,
                orders,
                customers,
                parameters.get("start", "2024-01-01"),
                parameters.get("end", "2024-12-31"),
            )
        elif case.analysis_name == "product_portfolio":
            expected[case.case_id] = _product_portfolio_truth(
                sales,
                parameters.get("start", "2024-01-01"),
                parameters.get("end", "2024-12-31"),
            )
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
