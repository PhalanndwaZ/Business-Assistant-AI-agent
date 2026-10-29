"""Tests for role-based policy decisions and filtering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.policy.filters import filter_fields, group_size_allowed
from app.policy.policy import AccessPolicy, PolicyError


POLICY_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "policy"
    / "access_policy.json"
)


@pytest.fixture
def policy() -> AccessPolicy:
    """Load the project access policy for decision tests."""
    return AccessPolicy(POLICY_PATH)


@pytest.mark.parametrize(
    ("role", "dataset", "expected"),
    [
        ("sales", "orders", True),
        ("hr", "orders", False),
        ("manager", "orders", True),
        ("sales", "employees", False),
        ("hr", "employees", True),
        ("manager", "employees", True),
        ("admin", "orders", False),
    ],
)
def test_dataset_access_matrix(
    policy: AccessPolicy,
    role: str,
    dataset: str,
    expected: bool,
) -> None:
    """Dataset access matches the approved department-role matrix."""
    assert policy.can_access_dataset(role, dataset) is expected


def test_tool_analysis_and_role_access(policy: AccessPolicy) -> None:
    """Tool and analysis permissions remain role-specific."""
    assert policy.can_use_tool("sales", "run_analysis")
    assert not policy.can_use_tool("hr", "run_analysis")
    assert policy.can_run_analysis("manager", "decline_risk")
    assert not policy.can_run_analysis("hr", "decline_risk")
    assert policy.can_run_analysis("hr", "headcount")
    assert not policy.can_use_tool("unknown", "query_business_data")


def test_unclassified_fields_are_denied_even_for_wildcard_allowlists(
    policy: AccessPolicy,
) -> None:
    """Wildcard field lists never make an unclassified field visible."""
    assert not policy.can_access_field("sales", "orders", "new_column")
    assert "new_column" not in filter_fields(
        policy,
        "sales",
        "orders",
        ["order_id", "new_column"],
    )


def test_manager_employee_access_is_aggregate_and_hides_restricted_fields(
    policy: AccessPolicy,
) -> None:
    """Manager employee access exposes only aggregate dimensions."""
    assert policy.dataset_mode("manager", "employees") == "aggregate_only"
    assert filter_fields(
        policy,
        "manager",
        "employees",
        ["employee_id", "department", "hire_date", "salary_cents"],
    ) == ["department", "hire_date"]
    assert policy.can_access_field("hr", "employees", "salary_cents")
    assert not policy.can_access_field("manager", "employees", "salary_cents")


def test_documents_are_filtered_by_department_and_classification(
    policy: AccessPolicy,
) -> None:
    """HR notes stay hidden from sales and managers; general policy is readable."""
    assert policy.can_access_document("sales", "general", "internal")
    assert policy.can_access_document("hr", "hr", "restricted")
    assert not policy.can_access_document("sales", "hr", "restricted")
    assert not policy.can_access_document("manager", "hr", "restricted")
    assert not policy.can_access_document("manager", "hr", "internal")


def test_aggregate_group_minimum_is_enforced(policy: AccessPolicy) -> None:
    """Manager aggregate groups must meet the configured five-person minimum."""
    assert not group_size_allowed(policy, "manager", "employees", 4)
    assert group_size_allowed(policy, "manager", "employees", 5)
    assert group_size_allowed(policy, "hr", "employees", 1)
    assert not group_size_allowed(policy, "sales", "employees", 100)
    with pytest.raises(ValueError, match="non-negative integer"):
        group_size_allowed(policy, "manager", "employees", -1)


def test_invalid_policy_fails_closed(tmp_path: Path) -> None:
    """Malformed policy data raises an error instead of granting access."""
    path = tmp_path / "policy.json"
    path.write_text('{"roles": {}}', encoding="utf-8")

    with pytest.raises(PolicyError, match="missing required sections"):
        AccessPolicy(path)


def test_invalid_field_classification_fails_closed(tmp_path: Path) -> None:
    """Malformed classification values cannot bypass policy validation."""
    data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    data["field_classifications"]["orders"]["status"] = []
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(PolicyError, match="invalid classification"):
        AccessPolicy(path)
