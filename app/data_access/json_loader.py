"""Load and validate approved JSON datasets without modifying source files."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from app.data_access.schema import DATASETS


class DataValidationError(ValueError):
    """Raised when a business dataset violates its declared schema."""


class JsonDataStore:
    """Load the fixed set of JSON datasets once and expose read-only views."""

    def __init__(self, data_dir: Path) -> None:
        """Load, validate, and retain all approved datasets."""
        self._data_dir = data_dir
        self._frames = self._load_all()

    def _load_all(self) -> dict[str, pd.DataFrame]:
        """Read all allowlisted dataset files and verify their relationships."""
        frames: dict[str, pd.DataFrame] = {}
        for dataset_name, schema in DATASETS.items():
            file_path = self._data_dir / f"{dataset_name}.json"
            try:
                records = json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise DataValidationError(
                    f"Could not read approved dataset '{dataset_name}' "
                    f"from {file_path}: {exc}"
                ) from exc
            if not isinstance(records, list):
                raise DataValidationError(
                    f"Dataset '{dataset_name}' must contain a JSON array."
                )
            self._validate_records(dataset_name, records, schema.fields)
            frames[dataset_name] = pd.DataFrame.from_records(records)

        self._validate_relationships(frames)
        return frames

    @staticmethod
    def _validate_records(
        dataset_name: str,
        records: list[Any],
        field_types: Any,
    ) -> None:
        """Reject missing, extra, duplicated, or incorrectly typed fields."""
        required_fields = set(field_types)
        seen_keys: set[Any] = set()
        primary_key = DATASETS[dataset_name].primary_key
        for row_number, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                raise DataValidationError(
                    f"Dataset '{dataset_name}' row {row_number} must be an object."
                )
            missing = required_fields - record.keys()
            extra = record.keys() - required_fields
            if missing or extra:
                raise DataValidationError(
                    f"Dataset '{dataset_name}' row {row_number} has "
                    f"missing fields {sorted(missing)} and unknown fields "
                    f"{sorted(extra)}."
                )
            for field_name, expected_type in field_types.items():
                value = record[field_name]
                if expected_type is date:
                    if not isinstance(value, str):
                        raise DataValidationError(
                            f"Dataset '{dataset_name}' row {row_number} "
                            f"field '{field_name}' must be an ISO date."
                        )
                    try:
                        date.fromisoformat(value)
                    except ValueError as exc:
                        raise DataValidationError(
                            f"Dataset '{dataset_name}' row {row_number} "
                            f"field '{field_name}' has invalid ISO date "
                            f"{value!r}."
                        ) from exc
                elif not isinstance(value, expected_type) or (
                    expected_type is int and isinstance(value, bool)
                ):
                    raise DataValidationError(
                        f"Dataset '{dataset_name}' row {row_number} field "
                        f"'{field_name}' must be {expected_type.__name__}."
                    )
            key_value = record[primary_key]
            if key_value in seen_keys and dataset_name != "order_items":
                raise DataValidationError(
                    f"Dataset '{dataset_name}' contains duplicate "
                    f"{primary_key} {key_value!r}."
                )
            seen_keys.add(key_value)

    @staticmethod
    def _validate_relationships(frames: dict[str, pd.DataFrame]) -> None:
        """Reject rows whose foreign keys do not point to approved records."""
        relationships = (
            ("orders", "customer_id", "customers", "customer_id"),
            ("order_items", "order_id", "orders", "order_id"),
            ("order_items", "product_id", "products", "product_id"),
        )
        for source, source_field, target, target_field in relationships:
            source_values = set(frames[source][source_field])
            target_values = set(frames[target][target_field])
            missing_values = source_values - target_values
            if missing_values:
                examples = sorted(missing_values)[:5]
                raise DataValidationError(
                    f"Dataset '{source}.{source_field}' contains unknown "
                    f"references to '{target}.{target_field}': {examples}."
                )

    @property
    def dataset_names(self) -> tuple[str, ...]:
        """Return the approved dataset names."""
        return tuple(DATASETS)

    def get_frame(self, dataset_name: str) -> pd.DataFrame:
        """Return a defensive copy of an allowlisted dataset."""
        if dataset_name not in DATASETS:
            raise ValueError(f"Unknown dataset '{dataset_name}'.")
        result = self._frames[dataset_name].copy(deep=True)
        if dataset_name == "orders":
            result["order_date"] = pd.to_datetime(
                result["order_date"], format="%Y-%m-%d"
            )
        return result
