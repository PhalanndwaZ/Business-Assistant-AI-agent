"""Tests for the synthetic employee and demo-user data added in Step 1."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.data_access.employee_loader import (
    EmployeeDataValidationError,
    load_employee_records,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_employee_data_loads_and_supports_five_person_groups() -> None:
    """Employee records validate and each department meets the group minimum."""
    data_dir = PROJECT_ROOT / "data" / "sample_data"

    records = load_employee_records(data_dir)

    group_sizes: dict[str, int] = {}
    for record in records:
        group_sizes[record["department"]] = (
            group_sizes.get(record["department"], 0) + 1
        )
    assert len(records) == 15
    assert set(group_sizes.values()) == {5}


def test_employee_loader_rejects_unknown_manager_reference(tmp_path: Path) -> None:
    """Employee manager IDs must refer to an existing different employee."""
    records = load_employee_records(PROJECT_ROOT / "data" / "sample_data")
    records[1]["manager_id"] = "E999"
    (tmp_path / "employees.json").write_text(
        json.dumps(records), encoding="utf-8"
    )

    with pytest.raises(EmployeeDataValidationError, match="invalid manager"):
        load_employee_records(tmp_path)


def test_demo_users_have_hashed_passwords_only() -> None:
    """Each demo role has a PBKDF2 hash and no stored plaintext password."""
    users_path = PROJECT_ROOT / "data" / "policy" / "users.json"
    users = json.loads(users_path.read_text(encoding="utf-8"))

    assert {user["role"] for user in users} == {
        "sales",
        "hr",
        "manager",
        "admin",
    }
    assert len({user["username"] for user in users}) == 4
    assert len({user["user_id"] for user in users}) == 4
    for user in users:
        assert set(user) == {
            "user_id",
            "username",
            "name",
            "role",
            "password_hash",
        }
        assert user["password_hash"].startswith("$argon2id$")
        assert "password" not in user
        assert re.fullmatch(r"[A-Za-z0-9._-]+", user["username"])
