"""Shared business calculations and order-status rules."""

from __future__ import annotations

import pandas as pd

REVENUE_STATUSES = frozenset({"completed"})
EXCLUDED_STATUSES = frozenset({"cancelled", "returned"})


def calculate_revenue_cents(items: pd.DataFrame) -> pd.Series:
    """Calculate exact line revenue in integer cents."""
    return items["quantity"] * items["unit_price_cents"]


def eligible_orders(orders: pd.DataFrame) -> pd.DataFrame:
    """Select completed orders eligible for sales and revenue analysis."""
    return orders.loc[orders["status"].isin(REVENUE_STATUSES)].copy()
