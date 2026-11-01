"""Load and validate feature configuration used by the planned tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT

FEATURE_CONFIG_NAMES = (
    "segments.json",
    "portfolio.json",
    "draft_purposes.json",
    "drafts.json",
    "uploads.json",
)


def load_feature_config(name: str) -> dict[str, Any]:
    """Load one allowlisted feature config and reject malformed JSON."""
    if name not in FEATURE_CONFIG_NAMES:
        raise ValueError(f"Unknown feature configuration: {name}.")
    path = PROJECT_ROOT / "config" / name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load feature configuration {name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Feature configuration {name} must be a JSON object.")
    return data


def validate_feature_configs() -> dict[str, dict[str, Any]]:
    """Load and validate required sections in all Step 1 feature configs."""
    required_names = (
        "segments.json",
        "portfolio.json",
        "draft_purposes.json",
        "uploads.json",
    )
    configs = {name: load_feature_config(name) for name in required_names}
    load_feature_config("drafts.json")
    segments = configs["segments.json"]
    if (
        not isinstance(segments.get("min_customers"), int)
        or segments["min_customers"] < 1
        or not isinstance(segments.get("segments"), list)
        or not isinstance(segments.get("rules"), list)
    ):
        raise ValueError("segments.json has invalid RFM settings.")
    portfolio = configs["portfolio.json"]
    if (
        not isinstance(portfolio.get("top_n"), int)
        or portfolio["top_n"] < 1
        or not isinstance(portfolio.get("observations"), list)
    ):
        raise ValueError("portfolio.json has invalid portfolio settings.")
    purposes = configs["draft_purposes.json"]
    for purpose, settings in purposes.items():
        if (
            not isinstance(purpose, str)
            or not isinstance(settings, dict)
            or not isinstance(settings.get("allowed_roles"), list)
            or not isinstance(settings.get("allowed_result_types"), list)
            or not isinstance(settings.get("required_fields"), list)
            or not isinstance(settings.get("max_words"), int)
            or not isinstance(settings.get("allowed_tones"), list)
            or not isinstance(settings.get("template"), str)
        ):
            raise ValueError("draft_purposes.json has an invalid purpose.")
    uploads = configs["uploads.json"]
    required_positive = (
        "max_file_bytes",
        "max_files_per_conversation",
        "max_chunks_per_file",
        "uploads_per_user_per_day",
        "retention_days",
        "context_max",
    )
    if (
        not isinstance(uploads.get("allowed_extensions"), list)
        or any(
            isinstance(uploads.get(field), bool)
            or not isinstance(uploads.get(field), int)
            or uploads[field] < 1
            for field in required_positive
        )
    ):
        raise ValueError("uploads.json has invalid limits.")
    return configs
