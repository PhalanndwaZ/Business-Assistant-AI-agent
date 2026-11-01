"""Calculate deterministic RFM customer segments."""

from __future__ import annotations

from datetime import date, timedelta
from os import getenv
from typing import Any

import pandas as pd

from app.analysis.analyses import _iso_date, _validate_range
from app.analysis.rules import eligible_orders
from app.feature_config import load_feature_config


def _quintile_score(values: pd.Series, *, ascending: bool) -> pd.Series:
    """Assign stable 1-to-5 scores, using first-row ranks for ties."""
    ranked = values.rank(method="first", ascending=ascending)
    if len(ranked) < 5:
        return pd.Series(3, index=values.index, dtype=int)
    try:
        scores = pd.qcut(ranked, 5, labels=[1, 2, 3, 4, 5])
    except ValueError:
        return pd.Series(3, index=values.index, dtype=int)
    return scores.astype(int)


def customer_segments(
    store: Any,
    start: date | str | None = None,
    end: date | str | None = None,
) -> dict[str, Any]:
    """Group customers by recency, frequency, and monetary value."""
    config = load_feature_config("segments.json")
    configured_end = _iso_date(end or getenv("AS_OF_DATE", "2025-01-15"))
    if start is None:
        configured_start = configured_end - timedelta(days=365) + timedelta(days=1)
    else:
        configured_start = _iso_date(start)
    window_start, window_end = _validate_range(configured_start, configured_end)

    orders = store.get_frame("orders")
    completed = eligible_orders(orders)
    counted = completed.loc[
        completed["order_date"].between(
            pd.Timestamp(window_start),
            pd.Timestamp(window_end),
        )
    ]
    items = store.get_frame("order_items")
    customers = store.get_frame("customers")

    customer_counts = counted.groupby("customer_id").size()
    if len(customer_counts) < int(config["min_customers"]):
        return {
            "status": "insufficient_data",
            "as_of": window_end.isoformat(),
            "window": {
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
                "months": 12,
            },
            "method": "rfm",
            "customers_counted": int(len(customer_counts)),
            "segments": [],
            "revenue_at_stake_cents": 0,
            "caveats": [
                f"At least {config['min_customers']} customers with orders are required for RFM scoring."
            ],
        }

    sales = counted.merge(items, on="order_id", how="inner")
    sales["revenue_cents"] = sales["quantity"] * sales["unit_price_cents"]
    monetary = sales.groupby("customer_id")["revenue_cents"].sum()
    order_counts = counted.groupby("customer_id")["order_id"].nunique()
    last_order = counted.groupby("customer_id")["order_date"].max()
    last_order_date = pd.to_datetime(last_order)
    as_of_timestamp = pd.Timestamp(window_end)
    recency = (as_of_timestamp - last_order_date).dt.days
    customer_ids = customer_counts.index

    rfm = pd.DataFrame(
        {
            "customer_id": customer_ids,
            "frequency": order_counts.reindex(customer_ids).fillna(0).astype(int).values,
            "monetary": monetary.reindex(customer_ids).fillna(0).astype(int).values,
            "recency": recency.reindex(customer_ids).fillna(0).astype(int).values,
        }
    ).set_index("customer_id")
    rfm["r_score"] = _quintile_score(rfm["recency"], ascending=True).map(
        lambda value: 6 - int(value)
    )
    rfm["f_score"] = _quintile_score(rfm["frequency"], ascending=True)
    rfm["m_score"] = _quintile_score(rfm["monetary"], ascending=True)

    first_orders = completed.groupby("customer_id")["order_date"].min().to_dict()
    segment_by_customer: dict[str, str] = {}
    for customer_id, row in rfm.iterrows():
        first_date = pd.Timestamp(first_orders[customer_id])
        segment = "Occasional"
        if (as_of_timestamp - first_date).days <= int(config["new_days"]):
            segment = "New"
        elif (
            int(row["r_score"]) >= 4
            and int(row["f_score"]) >= 4
            and int(row["m_score"]) >= 4
        ):
            segment = "Best customers"
        elif int(row["r_score"]) >= 3 and int(row["f_score"]) >= 3:
            segment = "Loyal"
        elif int(row["r_score"]) <= 2 and int(row["f_score"]) >= 3:
            segment = "At risk"
        elif int(row["r_score"]) == 1 and int(row["f_score"]) <= 2:
            segment = "Lost"
        segment_by_customer[str(customer_id)] = segment

    rfm["segment"] = pd.Series(segment_by_customer)
    names = customers.set_index("customer_id")["name"].to_dict()
    segment_details = {item["name"]: item for item in config["segments"]}
    segments = []
    total_customers = len(rfm)
    total_revenue = int(rfm["monetary"].sum())
    for segment_name in [item["name"] for item in config["segments"]]:
        group = rfm.loc[rfm["segment"] == segment_name]
        group_revenue = int(group["monetary"].sum())
        customer_count = len(group)
        top = (
            group.sort_values(["monetary", "recency"], ascending=[False, True])
            .head(int(config["top_customers"]))
            .index.tolist()
        )
        detail = segment_details[segment_name]
        segments.append(
            {
                "name": segment_name,
                "meaning": detail["meaning"],
                "customers": customer_count,
                "share_of_customers": round(customer_count / total_customers, 6),
                "revenue_cents": group_revenue,
                "share_of_revenue": (
                    round(group_revenue / total_revenue, 6)
                    if total_revenue else 0.0
                ),
                "avg_order_value_cents": (
                    round(group_revenue / int(group["frequency"].sum()))
                    if customer_count and int(group["frequency"].sum()) else 0
                ),
                "avg_days_since_last_order": (
                    round(float(group["recency"].mean())) if customer_count else 0
                ),
                "avg_orders": (
                    round(float(group["frequency"].mean()), 2) if customer_count else 0.0
                ),
                "suggested_next_step": detail["suggested_next_step"],
                "owner_role": detail["owner_role"],
                "top_customers": [
                    {
                        "customer_id": customer_id,
                        "name": names.get(customer_id, ""),
                        "revenue_cents": int(group.loc[customer_id, "monetary"]),
                        "days_since_last_order": int(group.loc[customer_id, "recency"]),
                    }
                    for customer_id in top
                ],
            }
        )
    revenue_at_stake = sum(
        item["revenue_cents"]
        for item in segments
        if item["name"] in {"At risk", "Lost"}
    )
    return {
        "status": "ok",
        "as_of": window_end.isoformat(),
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "months": 12,
        },
        "method": "rfm",
        "customers_counted": total_customers,
        "segments": segments,
        "revenue_at_stake_cents": int(revenue_at_stake),
        "caveats": ["Segments describe patterns, not predictions."],
    }
