from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT

MASKING_CONFIG = PROJECT_ROOT / "data" / "config" / "masking.json"


class MaskingError(RuntimeError):
    pass


def mask_sensitive(value: Any, config_path: Path = MASKING_CONFIG) -> Any:
    """Mask configured sensitive fields, returning placeholders on failure."""
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        blocked = {str(field).casefold() for field in config["blocked_fields"]}
        placeholder = str(config.get("placeholder", "[REDACTED]"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MaskingError("Tracing mask configuration is unavailable") from exc
    return _mask(value, blocked, placeholder)


def _mask(value: Any, blocked: set[str], placeholder: str) -> Any:
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if normalized in blocked or any(
                field in normalized for field in blocked
            ):
                masked[str(key)] = placeholder
            else:
                masked[str(key)] = _mask(item, blocked, placeholder)
        return masked
    if isinstance(value, (list, tuple)):
        return [_mask(item, blocked, placeholder) for item in value]
    if isinstance(value, str):
        # Credentials and bearer values can occur outside structured fields.
        return re.sub(
            r"(?i)\b(?:bearer\s+)?(?:password|secret|token)\s*[:=]\s*\S+",
            lambda _: placeholder,
            value,
        )
    return value


def fail_closed_mask(
    value: Any,
    masker: Callable[[Any], Any] = mask_sensitive,
) -> Any:
    """Never allow an exception to produce raw trace payloads."""
    try:
        return masker(value)
    except Exception:
        return "[REDACTED]"
