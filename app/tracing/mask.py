from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT

MASKING_CONFIG = PROJECT_ROOT / "data" / "config" / "masking.json"
EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_PATTERN = re.compile(
    r"(?i)(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?){2}\d{4}"
)
CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
HEADER_PATTERN = re.compile(
    r"(?i)\b(?:authorization|api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+"
)
PERSONAL_FIELD_PATTERN = re.compile(
    r"(?i)\b(?:customer(?:\s+(?:name|contact))?|customer|email|phone|salary|payroll|compensation)\s*[:=]\s*[^,;\n]+"
)


class MaskingError(RuntimeError):
    pass


def hash_user_id(user_id: str) -> str:
    """Return a stable hash for user IDs before they leave trace metadata."""
    digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()
    return f"u_{digest[:12]}"


def mask_sensitive(value: Any, config_path: Path = MASKING_CONFIG) -> Any:
    """Mask configured sensitive fields, returning placeholders on failure."""
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        blocked = {str(field).casefold() for field in config.get("blocked_fields", [])}
        placeholder = str(config.get("placeholder", "[REDACTED]"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MaskingError("Tracing mask configuration is unavailable") from exc
    return _mask(value, blocked, placeholder)


def _matches_blocked_key(key: str, blocked: set[str]) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
    return normalized in blocked or any(field in normalized for field in blocked)


def _is_luhn_valid(number: str) -> bool:
    digits = re.sub(r"\D", "", number)
    if len(digits) not in {13, 14, 15, 16, 17, 18, 19}:
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        value = int(digit)
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _mask_string(value: str, blocked: set[str], placeholder: str) -> str:
    masked = value
    masked = HEADER_PATTERN.sub(lambda _: placeholder, masked)
    masked = EMAIL_PATTERN.sub(placeholder, masked)
    masked = PHONE_PATTERN.sub(placeholder, masked)

    def replace_card(match: re.Match[str]) -> str:
        content = match.group(0)
        if _is_luhn_valid(content):
            return placeholder
        return content

    masked = CARD_PATTERN.sub(replace_card, masked)
    masked = PERSONAL_FIELD_PATTERN.sub(lambda _: placeholder, masked)
    return masked


def _mask(value: Any, blocked: set[str], placeholder: str) -> Any:
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            if _matches_blocked_key(key, blocked):
                masked[str(key)] = placeholder
            else:
                masked[str(key)] = _mask(item, blocked, placeholder)
        return masked
    if isinstance(value, (list, tuple)):
        return [_mask(item, blocked, placeholder) for item in value]
    if isinstance(value, str):
        return _mask_string(value, blocked, placeholder)
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
