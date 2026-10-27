"""Generate deterministic synthetic business datasets for local development."""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "sample_data"
RANDOM_SEED = 42017
YEAR = 2024

PRODUCT_CATALOG = (
    ("P001", "Laptop Stand", "Accessories", 4599),
    ("P002", "Wireless Mouse", "Accessories", 2599),
    ("P003", "Mechanical Keyboard", "Accessories", 8999),
    ("P004", "USB-C Hub", "Electronics", 6499),
    ("P005", "Noise-Cancelling Headphones", "Electronics", 18999),
    ("P006", "Webcam", "Electronics", 9999),
    ("P007", "Notebook Set", "Office Supplies", 1299),
    ("P008", "Desk Lamp", "Office Supplies", 5299),
    ("P009", "Ergonomic Chair", "Furniture", 32999),
    ("P010", "Standing Desk", "Furniture", 57999),
)


def _write_json(path: Path, records: list[dict[str, Any]]) -> None:
    """Write records as stable, readable UTF-8 JSON."""
    path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _month_dates(year: int, month: int) -> tuple[date, date]:
    """Return the inclusive first and last dates for a calendar month."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def generate_records(seed: int = RANDOM_SEED) -> dict[str, list[dict[str, Any]]]:
    """Build all four related business datasets using a fixed random seed."""
    rng = random.Random(seed)
    customers = [
        {
            "customer_id": f"C{customer_number:04d}",
            "name": f"Customer {customer_number:03d}",
            "region": rng.choice(("North", "South", "East", "West")),
            "segment": rng.choice(("Small Business", "Mid-Market", "Enterprise")),
        }
        for customer_number in range(1, 61)
    ]
    products = [
        {
            "product_id": product_id,
            "name": name,
            "category": category,
        }
        for product_id, name, category, _ in PRODUCT_CATALOG
    ]
    customer_ids = [customer["customer_id"] for customer in customers]
    product_prices = {
        product_id: price for product_id, _, _, price in PRODUCT_CATALOG
    }
    orders: list[dict[str, Any]] = []
    order_items: list[dict[str, Any]] = []
    order_number = 1

    for month in range(1, 13):
        start, end = _month_dates(YEAR, month)
        days_in_month = (end - start).days + 1
        order_count = rng.randint(48, 62) if month != 12 else rng.randint(21, 27)
        for _ in range(order_count):
            order_id = f"O{order_number:05d}"
            order_number += 1
            order_date = start + timedelta(days=rng.randrange(days_in_month))
            status = rng.choices(
                ("completed", "returned", "cancelled"),
                weights=(86, 7, 7),
                k=1,
            )[0]
            orders.append(
                {
                    "order_id": order_id,
                    "customer_id": rng.choice(customer_ids),
                    "order_date": order_date.isoformat(),
                    "status": status,
                }
            )
            chosen_products = rng.sample(PRODUCT_CATALOG, rng.randint(1, 3))
            for product_id, _, _, _ in chosen_products:
                order_items.append(
                    {
                        "order_id": order_id,
                        "product_id": product_id,
                        "quantity": rng.randint(1, 4),
                        "unit_price_cents": product_prices[product_id],
                    }
                )

    return {
        "customers": customers,
        "products": products,
        "orders": orders,
        "order_items": order_items,
    }


def main() -> None:
    """Generate the sample JSON datasets in the project data directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    datasets = generate_records()
    for dataset_name, records in datasets.items():
        _write_json(OUTPUT_DIR / f"{dataset_name}.json", records)
    print(
        "Generated reproducible sample datasets in "
        f"{OUTPUT_DIR.relative_to(PROJECT_ROOT)}."
    )


if __name__ == "__main__":
    main()
