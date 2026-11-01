"""Calculate deterministic product portfolio concentration and movement."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from app.analysis.analyses import (
    _iso_date,
    _sales_rows,
    _validate_positive_integer,
    _validate_range,
)
from app.feature_config import load_feature_config


def _portfolio_sales(
    store: Any,
    start: date | str,
    end: date | str,
) -> tuple[pd.DataFrame, date, date]:
    """Aggregate completed sales by product for one inclusive period."""
    sales, start_date, end_date = _sales_rows(store, start, end)
    if sales.empty:
        return sales, start_date, end_date
    return (
        sales.groupby(
            ["product_id", "product_name", "category"],
            as_index=False,
        ).agg(
            revenue_cents=("revenue_cents", "sum"),
            units=("quantity", "sum"),
            order_count=("order_id", "nunique"),
        ),
        start_date,
        end_date,
    )


def _assign_classes(items: pd.DataFrame) -> pd.DataFrame:
    """Assign A/B/C classes using the smallest set reaching 80 percent."""
    if items.empty:
        return items.assign(product_class=pd.Series(dtype=str))
    config = load_feature_config("portfolio.json")
    cutoff = float(config["class_a_cumulative_share"])
    ranked = items.sort_values(
        ["revenue_cents", "product_id"],
        ascending=[False, True],
    ).copy()
    ranked["cumulative_share"] = ranked["revenue_cents"].cumsum()
    ranked["cumulative_share"] = ranked["cumulative_share"] / ranked[
        "revenue_cents"
    ].sum()
    cumulative = ranked["cumulative_share"]
    classes = pd.Series("C", index=ranked.index, dtype=str)
    if (cumulative > cutoff).any():
        first_after = cumulative[cumulative > cutoff].index[0]
        a_mask = ranked.index.map(lambda index: ranked.index.get_loc(index) <= ranked.index.get_loc(first_after))
        classes.loc[a_mask] = "A"
    else:
        classes.loc[:] = "A"
    remaining = classes == "C"
    classes.loc[remaining & (cumulative <= min(0.95, cutoff + 0.15))] = "B"
    ranked["product_class"] = classes
    return ranked


def _percent_change(current: int, previous: int) -> float | None:
    """Calculate a percentage change or mark a zero previous base unavailable."""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100.0, 2)


def product_portfolio(
    store: Any,
    start: date | str,
    end: date | str,
    level: str = "product",
    top_n: int = 10,
) -> dict[str, Any]:
    """Build a product portfolio with concentration, movers, and portfolio classes."""
    if level not in {"product", "category"}:
        raise ValueError("level must be 'product' or 'category'.")
    _validate_positive_integer("top_n", top_n)
    start_date, end_date = _validate_range(start, end)
    current, current_start, current_end = _portfolio_sales(store, start_date, end_date)

    group_fields = ["product_id", "product_name", "category"]
    if level == "category":
        current = (
            current.groupby("category", as_index=False)
            .agg(revenue_cents=("revenue_cents", "sum"), units=("units", "sum"))
            .assign(
                product_id=lambda frame: frame["category"],
                product_name=lambda frame: frame["category"],
            )
        )
    current = current.sort_values(
        ["revenue_cents", "product_id"],
        ascending=[False, True],
    ).reset_index(drop=True)
    total_revenue = int(current["revenue_cents"].sum()) if not current.empty else 0
    current["share"] = (
        current["revenue_cents"] / total_revenue if total_revenue else 0.0
    )

    period_days = (end_date - start_date).days + 1
    comparison_end = start_date - timedelta(days=1)
    comparison_start = comparison_end - timedelta(days=period_days - 1)
    previous, previous_start, previous_end = _portfolio_sales(
        store,
        comparison_start,
        comparison_end,
    )
    if level == "category":
        previous = (
            previous.groupby("category", as_index=False)
            .agg(revenue_cents=("revenue_cents", "sum"), units=("units", "sum"))
        )
    previous_by_id = previous.set_index(
        "category" if level == "category" else "product_id"
    )["revenue_cents"].to_dict() if not previous.empty else {}
    previous_units_by_id = previous.set_index(
        "category" if level == "category" else "product_id"
    )["units"].to_dict() if not previous.empty else {}

    catalog = store.get_frame("products")
    if level == "product":
        catalog_ids = set(catalog["product_id"])
        current_ids = set(current["product_id"])
    else:
        catalog_ids = set(catalog["category"])
        current_ids = set(current["category"])
    dormant = sorted(catalog_ids - current_ids)

    if level == "product":
        ranked = _assign_classes(current)
        item_records = []
        for row in ranked.to_dict(orient="records"):
            units = int(row["units"])
            revenue = int(row["revenue_cents"])
            product_id = str(row["product_id"])
            previous_revenue = int(previous_by_id.get(product_id, 0))
            item_records.append(
                {
                    "product_id": product_id,
                    "name": row["product_name"],
                    "category": row["category"],
                    "revenue_cents": revenue,
                    "share": round(float(row["share"]), 6),
                    "units": units,
                    "avg_price_cents": round(revenue / units) if units else 0,
                    "class": row["product_class"],
                    "change_cents": revenue - previous_revenue,
                    "previous_units": int(previous_units_by_id.get(product_id, 0)),
                }
            )
    else:
        item_records = []
        for row in current.to_dict(orient="records"):
            category = str(row["category"])
            previous_revenue = int(previous_by_id.get(category, 0))
            units = int(row["units"])
            revenue = int(row["revenue_cents"])
            item_records.append(
                {
                    "category": category,
                    "revenue_cents": revenue,
                    "share": round(float(row["share"]), 6),
                    "units": units,
                    "avg_price_cents": round(revenue / units) if units else 0,
                    "change_cents": revenue - previous_revenue,
                    "previous_units": int(previous_units_by_id.get(category, 0)),
                }
            )

    config = load_feature_config("portfolio.json")
    min_base_cents = int(config["min_base_cents"])
    movers_source = [
        item for item in item_records
        if item["change_cents"] != 0
    ]
    risers = sorted(
        [item for item in movers_source if item["change_cents"] > 0],
        key=lambda item: (-item["change_cents"], item.get("product_id", item["category"])),
    )[:top_n]
    fallers = sorted(
        [item for item in movers_source if item["change_cents"] < 0],
        key=lambda item: (item["change_cents"], item.get("product_id", item["category"])),
    )[:top_n]

    def mover(item: dict[str, Any]) -> dict[str, Any]:
        """Format one revenue mover without converting cents rank to percentages."""
        previous_revenue = int(
            previous_by_id.get(
                item.get("product_id", item.get("category")),
                0,
            )
        )
        units_change = int(item["units"]) - int(item["previous_units"])
        current_avg_price = int(item["avg_price_cents"])
        previous_units = int(item["previous_units"])
        previous_avg_price = (
            previous_revenue // previous_units if previous_units else 0
        )
        return {
            **{key: item[key] for key in item if key != "share"},
            "change_cents": item["change_cents"],
            "percent_change": (
                _percent_change(item["revenue_cents"], previous_revenue)
                if previous_revenue >= min_base_cents
                else None
            ),
            "units_change": units_change,
            "avg_price_change_cents": current_avg_price - previous_avg_price,
        }

    hhi = sum((float(share) ** 2) for share in current["share"])
    top3_share = float(current.head(3)["revenue_cents"].sum() / total_revenue) if total_revenue else 0.0
    caveats = []
    earliest_order = store.get_frame("orders").loc[
        store.get_frame("orders")["status"] == "completed", "order_date"
    ].min()
    if pd.Timestamp(previous_start) < pd.Timestamp(earliest_order):
        caveats.append("Comparison window starts before the earliest completed order; changes may be partial.")

    observations = []
    configured = config["observations"]
    if top3_share > float(configured[0]["threshold"]):
        observations.append(configured[0]["sentence"])
    if dormant and len(configured) > 3 and configured[3]["condition"] == "any_dormant":
        observations.append(configured[3]["sentence"])

    return {
        "status": "ok",
        "analysis": "product_portfolio",
        "as_of": end_date.isoformat(),
        "window": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": period_days,
        },
        "level": level,
        "portfolio": {
            "revenue_cents": total_revenue,
            "product_count": len(current),
            "hhi": round(hhi, 6),
            "top_3_share": round(top3_share, 6),
        },
        "items": item_records,
        "movers": {
            "risers": [mover(item) for item in risers],
            "fallers": [mover(item) for item in fallers],
            "new": [
                item for item in item_records
                if previous_by_id.get(item.get("product_id", item.get("category")), 0) == 0
                and item["revenue_cents"] > 0
            ],
            "dropped": [
                key for key, revenue in previous_by_id.items()
                if revenue > 0 and key not in set(
                    current["category"] if level == "category" else current["product_id"]
                )
            ],
        },
        "dormant": dormant,
        "observations": observations,
        "caveats": caveats,
    }
