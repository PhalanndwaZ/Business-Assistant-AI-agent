"""Approved business datasets, fields, relationships, and glossary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class DatasetSchema:
    """Describe the fields and unique key for an approved dataset."""

    fields: Mapping[str, type]
    primary_key: str


DATASETS: Mapping[str, DatasetSchema] = MappingProxyType(
    {
        "customers": DatasetSchema(
            fields=MappingProxyType(
                {
                    "customer_id": str,
                    "name": str,
                    "region": str,
                    "segment": str,
                }
            ),
            primary_key="customer_id",
        ),
        "products": DatasetSchema(
            fields=MappingProxyType(
                {
                    "product_id": str,
                    "name": str,
                    "category": str,
                }
            ),
            primary_key="product_id",
        ),
        "orders": DatasetSchema(
            fields=MappingProxyType(
                {
                    "order_id": str,
                    "customer_id": str,
                    "order_date": date,
                    "status": str,
                }
            ),
            primary_key="order_id",
        ),
        "order_items": DatasetSchema(
            fields=MappingProxyType(
                {
                    "order_id": str,
                    "product_id": str,
                    "quantity": int,
                    "unit_price_cents": int,
                }
            ),
            primary_key="order_id",
        ),
    }
)

RELATIONSHIPS = (
    ("orders.customer_id", "customers.customer_id"),
    ("order_items.order_id", "orders.order_id"),
    ("order_items.product_id", "products.product_id"),
)

BUSINESS_GLOSSARY = {
    "revenue": "quantity multiplied by unit price in integer cents.",
    "sales": (
        "Revenue from completed orders only; cancelled and returned orders "
        "are excluded."
    ),
    "order_date": "ISO 8601 calendar date on which an order was placed.",
    "as_of_date": "Configured date used to resolve relative date questions.",
}

AVAILABLE_ANALYSES = (
    "revenue_by_product",
    "revenue_by_category",
    "revenue_by_period",
    "period_change",
    "top_customers",
    "trend",
    "outliers",
)

ANALYSIS_PARAMETERS = {
    "revenue_by_product": {
        "required": ["start", "end"],
        "optional": {"top_n": "positive integer, default 10"},
    },
    "revenue_by_category": {
        "required": ["start", "end"],
        "optional": {},
    },
    "revenue_by_period": {
        "required": ["start", "end"],
        "optional": {
            "granularity": "day, week, or month; default month",
        },
    },
    "period_change": {
        "required": [
            "metric",
            "current_start",
            "current_end",
            "previous_start",
            "previous_end",
        ],
        "optional": {},
        "metric_values": ["revenue", "orders", "units"],
    },
    "top_customers": {
        "required": ["start", "end"],
        "optional": {"top_n": "positive integer, default 10"},
    },
    "trend": {
        "required": ["metric", "start", "end"],
        "optional": {
            "granularity": "day, week, or month; default month",
        },
        "metric_values": ["revenue", "orders", "units"],
    },
    "outliers": {
        "required": ["metric", "start", "end"],
        "optional": {
            "granularity": "day, week, or month; default month",
        },
        "metric_values": ["revenue", "orders", "units"],
    },
}
