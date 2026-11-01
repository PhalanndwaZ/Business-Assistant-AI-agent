from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation.runner.schema import EvaluationCase, EvaluationTurn


def load_cases(path: Path) -> tuple[EvaluationCase, ...]:
    """Load and validate one JSONL case file with line-specific errors."""
    cases: list[EvaluationCase] = []
    ids: set[str] = set()
    with Path(path).open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                _validate_record(record, str(path), line_number)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON at column {exc.colno}: {exc.msg}"
                ) from exc

            turns = tuple(
                EvaluationTurn(
                    question=item if isinstance(item, str) else item["q"],
                    conversation=(
                        "new"
                        if isinstance(item, str)
                        else item.get("conversation", "new")
                    ),
                )
                for item in record["turns"]
            )
            case = EvaluationCase(
                case_id=record["id"],
                group=record["group"],
                role=record["role"],
                turns=turns,
                expect=record.get("expect", {}),
                rubric=tuple(record.get("rubric", [])),
                runs=int(record.get("runs", 5 if record["severity"] == "security" else 3)),
                severity=record["severity"],
                status=record["status"],
            )
            if case.case_id in ids:
                raise ValueError(f"{path}:{line_number}: duplicate id '{case.case_id}'.")
            ids.add(case.case_id)
            cases.append(case)
    _validate_security_pairs(cases, Path(path))
    return tuple(cases)


def _validate_security_pairs(cases: tuple[EvaluationCase, ...], path: Path) -> None:
    """Require every active security case to have a matching allowed case."""
    records_by_id = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records_by_id[str(record["id"])] = record

    active_cases = {
        case.case_id: case
        for case in cases
        if case.status == "active"
    }
    for case in active_cases.values():
        if case.severity == "security":
            matches = [
                record_id
                for record_id, record in records_by_id.items()
                if record.get("paired_case_id") == case.case_id
            ]
            allowed_matches = [
                record_id
                for record_id in matches
                if record_id in active_cases
                and active_cases[record_id].severity == "normal"
            ]
            if len(allowed_matches) != 1:
                raise ValueError(
                    f"{path}: security case '{case.case_id}' must have exactly one "
                    "paired active normal case."
                )
    for record_id, record in records_by_id.items():
        paired_id = record.get("paired_case_id")
        if not isinstance(paired_id, str):
            continue
        allowed = active_cases.get(record_id)
        security = active_cases.get(paired_id)
        if allowed is None or allowed.severity != "normal":
            continue
        if security is None or security.severity != "security":
            if record_id in active_cases:
                raise ValueError(
                    f"{path}: allowed case '{record_id}' must pair with an active "
                    f"security case '{paired_id}'."
                )


def _validate_record(record: Any, path: str, line: int) -> None:
    """Validate required fields and report the exact offending field."""
    required = ("id", "group", "role", "turns", "severity", "status")
    for field in required:
        if field not in record:
            raise ValueError(f"{path}:{line}: missing required field '{field}'.")
    if not isinstance(record["id"], str) or not record["id"]:
        raise ValueError(f"{path}:{line}: field 'id' must be a non-empty string.")
    if not isinstance(record["turns"], list) or not record["turns"]:
        raise ValueError(f"{path}:{line}: field 'turns' must be a non-empty array.")
    for index, turn in enumerate(record["turns"]):
        if isinstance(turn, str):
            continue
        if not isinstance(turn, dict) or not isinstance(turn.get("q"), str):
            raise ValueError(
                f"{path}:{line}: field 'turns[{index}].q' must be a non-empty string."
            )
    if record["severity"] not in {"normal", "security"}:
        raise ValueError(f"{path}:{line}: field 'severity' must be 'normal' or 'security'.")
    if record["status"] not in {"active", "pending"}:
        raise ValueError(f"{path}:{line}: field 'status' must be 'active' or 'pending'.")
