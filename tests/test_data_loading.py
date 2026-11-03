"""Tests for deterministic data generation and validation."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
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
    complete_datasets = dict(datasets)
    if "employees" not in complete_datasets:
        employee_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "sample_data"
            / "employees.json"
        )
        complete_datasets["employees"] = json.loads(
            employee_path.read_text(encoding="utf-8")
        )
    for name, records in complete_datasets.items():
        (directory / f"{name}.json").write_text(
            json.dumps(records), encoding="utf-8"
        )


def test_generate_records_is_reproducible() -> None:
    """The seeded generator returns the same records on every run."""
    assert generate_records() == generate_records()


def test_role_demo_fixtures_match_sample_data() -> None:
    """Role-specific demo JSON stays aligned with source data and safe fields."""
    data_dir = Path(__file__).resolve().parents[1] / "data" / "sample_data"
    manager = json.loads((data_dir / "manager.json").read_text(encoding="utf-8"))
    admin = json.loads((data_dir / "admin.json").read_text(encoding="utf-8"))
    employees = json.loads((data_dir / "employees.json").read_text(encoding="utf-8"))
    orders = json.loads((data_dir / "orders.json").read_text(encoding="utf-8"))
    order_items = json.loads(
        (data_dir / "order_items.json").read_text(encoding="utf-8")
    )
    policy_users = json.loads(
        (data_dir.parent / "policy" / "users.json").read_text(encoding="utf-8")
    )

    orders_by_id = {order["order_id"]: order for order in orders}
    revenue_by_month: defaultdict[str, int] = defaultdict(int)
    completed_orders_by_month: Counter[str] = Counter()
    for item in order_items:
        order = orders_by_id[item["order_id"]]
        if order["status"] == "completed":
            revenue_by_month[order["order_date"][:7]] += (
                item["quantity"] * item["unit_price_cents"]
            )
    completed_orders_by_month.update(
        order["order_date"][:7]
        for order in orders
        if order["status"] == "completed"
    )
    headcount_by_department = Counter(
        employee["department"] for employee in employees
    )
    for period in manager["sales_performance"]:
        assert period["revenue_cents"] == revenue_by_month[period["month"]]
        assert (
            period["completed_orders"]
            == completed_orders_by_month[period["month"]]
        )
    for department in manager["headcount_by_department"]:
        assert (
            department["headcount"]
            == headcount_by_department[department["department"]]
        )
    overview = manager["department_overview"]
    assert {row["department"] for row in overview} == set(
        headcount_by_department
    )
    assert all(
        not any(
            field in row
            for field in ("employee_id", "name", "salary_cents", "work_email")
        )
        for row in overview
    )
    sales_summary = next(row for row in overview if row["department"] == "Sales")
    assert sales_summary["value_percent"] == round(
        100
        * manager["sales_performance"][1]["revenue_cents"]
        / manager["sales_performance"][1]["target_revenue_cents"],
        1,
    )

    demo_accounts = {
        (user["user_id"], user["username"], user["role"])
        for user in policy_users
    }
    fixture_accounts = {
        (user["user_id"], user["username"], user["role"])
        for user in admin["users"]
    }
    assert fixture_accounts == demo_accounts
    assert admin["registration"]["available_roles"] == [
        "sales",
        "hr",
        "manager",
        "admin",
    ]
    assert admin["registration"]["minimum_password_length"] == 12
    assert all(
        "password_hash" not in account and "password" not in account
        for account in admin["users"]
    )


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
