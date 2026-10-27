"""Tests for validated business-data query and analysis tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.data_access.json_loader import JsonDataStore
from app.mcp_servers import business_data_server
from scripts.generate_data import generate_records
from tests.test_data_loading import _write_datasets


@pytest.fixture
def data_tool_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JsonDataStore:
    """Provide an isolated, once-loaded test store to the MCP tool functions."""
    _write_datasets(tmp_path, generate_records())
    store = JsonDataStore(tmp_path)
    monkeypatch.setattr(business_data_server, "get_store", lambda: store)
    return store


def test_schema_exposes_allowlisted_datasets_and_analyses() -> None:
    """The schema tool describes the approved names and shared glossary."""
    schema = business_data_server.get_data_schema()

    assert set(schema["datasets"]) == {
        "customers",
        "products",
        "orders",
        "order_items",
    }
    assert "revenue_by_product" in schema["available_analyses"]
    assert schema["analysis_parameters"]["top_customers"] == {
        "required": ["start", "end"],
        "optional": {"top_n": "positive integer, default 10"},
    }
    assert "completed orders" in schema["glossary"]["sales"]


def test_query_business_data_caps_rows_and_returns_total(
    data_tool_store: JsonDataStore,
) -> None:
    """Queries return only requested columns with a separate total count."""
    result = business_data_server.query_business_data(
        "orders",
        ["order_id", "status"],
        filters=[{"field": "status", "operator": "eq", "value": "completed"}],
        limit=3,
    )

    assert result["returned_rows"] == 3
    assert result["total_matches"] > result["returned_rows"]
    assert set(result["rows"][0]) == {"order_id", "status"}


def test_customer_query_returns_exact_count_even_when_rows_are_capped(
    data_tool_store: JsonDataStore,
) -> None:
    """Customer counts use total_matches, not the number of returned rows."""
    result = business_data_server.query_business_data(
        "customers",
        ["customer_id"],
        limit=1,
    )

    assert result["returned_rows"] == 1
    assert result["total_matches"] == len(
        data_tool_store.get_frame("customers")
    )


def test_query_business_data_rejects_unknown_fields(
    data_tool_store: JsonDataStore,
) -> None:
    """A request cannot use arbitrary or unapproved field names."""
    with pytest.raises(ValueError, match="invalid fields"):
        business_data_server.query_business_data("orders", ["password"])


def test_query_business_data_rejects_unknown_operators(
    data_tool_store: JsonDataStore,
) -> None:
    """Filter operators are restricted to the declared operator allowlist."""
    with pytest.raises(ValueError, match="Unsupported filter operator"):
        business_data_server.query_business_data(
            "orders",
            ["order_id"],
            filters=[
                {"field": "status", "operator": "regex", "value": ".*"}
            ],
        )


def test_query_business_data_filters_items_by_related_order_date(
    data_tool_store: JsonDataStore,
) -> None:
    """Order-item date filters use the parent order's date."""
    result = business_data_server.query_business_data(
        "order_items",
        ["order_id", "product_id"],
        date_range={"start": "2024-01-01", "end": "2024-01-31"},
        limit=100,
    )
    order_dates = data_tool_store.get_frame("orders").set_index("order_id")

    assert result["rows"]
    assert all(
        order_dates.loc[row["order_id"], "order_date"].month == 1
        for row in result["rows"]
    )
