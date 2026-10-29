"""Load and validate synthetic employee records without exposing them to tools."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any


class EmployeeDataValidationError(ValueError):
    """Raised when the employee dataset violates its declared schema."""


EMPLOYEE_FIELDS = {
    "employee_id": str,
    "department": str,
    "job_title": str,
    "hire_date": date,
    "manager_id": str | None,
    "salary_cents": int,
    "performance_rating": int,
    "work_email": str,
    "phone": str,
}
SYNTHETIC_PHONE_PATTERN = re.compile(r"\+1-202-555-01\d{2}")


def load_employee_records(data_dir: Path) -> list[dict[str, Any]]:
    """Read employee records and validate fields, dates, and manager links."""
    data_path = data_dir / "employees.json"
    try:
        records = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmployeeDataValidationError(
            f"Could not read employee dataset from {data_path}: {exc}"
        ) from exc
    if not isinstance(records, list) or not records:
        raise EmployeeDataValidationError(
            "Employee dataset must contain a non-empty JSON array."
        )

    employee_ids: set[str] = set()
    for row_number, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) != set(EMPLOYEE_FIELDS):
            raise EmployeeDataValidationError(
                f"Employee row {row_number} must contain exactly "
                f"{sorted(EMPLOYEE_FIELDS)}."
            )
        for field_name, expected_type in EMPLOYEE_FIELDS.items():
            value = record[field_name]
            if expected_type is date:
                if not isinstance(value, str):
                    raise EmployeeDataValidationError(
                        f"Employee row {row_number} field '{field_name}' "
                        "must be an ISO date."
                    )
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise EmployeeDataValidationError(
                        f"Employee row {row_number} field '{field_name}' "
                        f"has invalid ISO date {value!r}."
                    ) from exc
            elif field_name == "manager_id":
                if value is not None and not isinstance(value, str):
                    raise EmployeeDataValidationError(
                        f"Employee row {row_number} field '{field_name}' "
                        "must be a string or null."
                    )
            elif not isinstance(value, expected_type) or (
                expected_type is int and isinstance(value, bool)
            ):
                raise EmployeeDataValidationError(
                    f"Employee row {row_number} field '{field_name}' "
                    f"must be {expected_type.__name__}."
                )
        if not record["employee_id"] or record["employee_id"] in employee_ids:
            raise EmployeeDataValidationError(
                "Employee IDs must be non-empty and unique."
            )
        if not record["department"] or not record["job_title"]:
            raise EmployeeDataValidationError(
                f"Employee {record['employee_id']!r} must have a department "
                "and job title."
            )
        if record["salary_cents"] < 0:
            raise EmployeeDataValidationError(
                f"Employee {record['employee_id']!r} has a negative salary."
            )
        if not 1 <= record["performance_rating"] <= 5:
            raise EmployeeDataValidationError(
                f"Employee {record['employee_id']!r} has an invalid "
                "performance rating."
            )
        if not record["work_email"].endswith(".invalid") or "@" not in record[
            "work_email"
        ]:
            raise EmployeeDataValidationError(
                f"Employee {record['employee_id']!r} must use a reserved "
                "synthetic email address."
            )
        if not SYNTHETIC_PHONE_PATTERN.fullmatch(record["phone"]):
            raise EmployeeDataValidationError(
                f"Employee {record['employee_id']!r} must use a reserved "
                "synthetic phone number."
            )
        employee_ids.add(record["employee_id"])

    for record in records:
        manager_id = record["manager_id"]
        if manager_id is not None and (
            manager_id not in employee_ids or manager_id == record["employee_id"]
        ):
            raise EmployeeDataValidationError(
                f"Employee {record['employee_id']!r} has an invalid manager."
            )
    return records
