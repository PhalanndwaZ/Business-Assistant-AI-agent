"""Tests for incremental JSON-to-Neon migration behavior."""

import pytest

from app.data_access.schema import DATASETS
from scripts.migrate_data_to_neon import (
    _build_upsert_query,
    _quote_identifier,
    _validate_records,
)


def test_upsert_updates_existing_rows_and_adds_new_rows() -> None:
    """Conflict handling refreshes source fields rather than skipping records."""
    query = _build_upsert_query(
        "orders",
        ["order_id", "customer_id", "order_date", "status"],
        ["order_id"],
    )

    assert 'INSERT INTO "orders"' in query
    assert 'ON CONFLICT ("order_id") DO UPDATE SET' in query
    assert '"status" = EXCLUDED."status"' in query


def test_order_item_upsert_uses_composite_database_primary_key() -> None:
    """Order-item lines conflict on both key columns, not just order ID."""
    query = _build_upsert_query(
        "order_items",
        ["order_id", "product_id", "quantity", "unit_price_cents"],
        ["order_id", "product_id"],
    )

    assert 'ON CONFLICT ("order_id", "product_id") DO UPDATE SET' in query


def test_migration_identifiers_are_quoted_and_validated() -> None:
    """Untrusted identifier strings cannot be interpolated into SQL."""
    assert _quote_identifier("order_items") == '"order_items"'
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        _quote_identifier("orders; DROP TABLE customers")


def test_source_rows_are_checked_against_database_composite_key() -> None:
    """Distinct products on the same order remain distinct source records."""
    fields = list(DATASETS["order_items"].fields)
    record = {
        "order_id": "ORD-001",
        "product_id": "PROD-001",
        "quantity": 2,
        "unit_price_cents": 1250,
    }

    columns = _validate_records(
        "order_items",
        [record],
        fields,
        ["order_id", "product_id"],
    )

    assert columns == fields


def test_migration_rejects_duplicate_composite_keys() -> None:
    """Repeated order/product pairs are rejected before reaching Neon."""
    fields = list(DATASETS["order_items"].fields)
    record = {
        "order_id": "ORD-001",
        "product_id": "PROD-001",
        "quantity": 2,
        "unit_price_cents": 1250,
    }

    with pytest.raises(ValueError, match="duplicate primary key"):
        _validate_records(
            "order_items",
            [record, record.copy()],
            fields,
            ["order_id", "product_id"],
        )
