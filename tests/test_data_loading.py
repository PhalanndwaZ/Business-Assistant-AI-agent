"""Tests for deterministic data generation and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.data_access.json_loader import DataValidationError, JsonDataStore
from scripts.generate_data import generate_records


def _write_datasets(
    directory: Path,
    datasets: dict[str, list[dict[str, Any]]],
) -> None:
    """Write test datasets to a temporary directory."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, records in datasets.items():
        (directory / f"{name}.json").write_text(
            json.dumps(records), encoding="utf-8"
        )


def test_generate_records_is_reproducible() -> None:
    """The seeded generator returns the same records on every run."""
    assert generate_records() == generate_records()


def test_generated_data_has_a_december_sales_dip(tmp_path: Path) -> None:
    """The synthetic order volume is deliberately lower in December."""
    _write_datasets(tmp_path, generate_records())
    store = JsonDataStore(tmp_path)
    orders = store.get_frame("orders")
    monthly_counts = orders.groupby(orders["order_date"].dt.month).size()

    assert monthly_counts.loc[12] < monthly_counts.loc[11]


def test_loader_rejects_missing_fields(tmp_path: Path) -> None:
    """Required fields cannot be omitted from business records."""
    datasets = generate_records()
    datasets["customers"][0].pop("customer_id")
    _write_datasets(tmp_path, datasets)

    with pytest.raises(DataValidationError, match="missing fields"):
        JsonDataStore(tmp_path)


def test_loader_rejects_invalid_dates(tmp_path: Path) -> None:
    """Order dates must parse as ISO 8601 calendar dates."""
    datasets = generate_records()
    datasets["orders"][0]["order_date"] = "not-a-date"
    _write_datasets(tmp_path, datasets)

    with pytest.raises(DataValidationError, match="invalid ISO date"):
        JsonDataStore(tmp_path)


def test_loader_rejects_broken_references(tmp_path: Path) -> None:
    """Foreign keys must refer to rows in the corresponding allowlisted file."""
    datasets = generate_records()
    datasets["orders"][0]["customer_id"] = "UNKNOWN"
    _write_datasets(tmp_path, datasets)

    with pytest.raises(DataValidationError, match="unknown references"):
        JsonDataStore(tmp_path)


def test_loader_rejects_unapproved_dataset(tmp_path: Path) -> None:
    """The data store cannot access dataset names outside its allowlist."""
    _write_datasets(tmp_path, generate_records())
    store = JsonDataStore(tmp_path)

    with pytest.raises(ValueError, match="Unknown dataset"):
        store.get_frame("secrets")
