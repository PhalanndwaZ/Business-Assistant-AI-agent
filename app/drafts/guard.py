from __future__ import annotations

import re
from typing import Any

from app.feature_config import load_feature_config


def validate_digit_guard(text: str, allowed: set[str] | None = None) -> bool:
    """Reject digits unless they occur in placeholders or configured terms."""
    allowed_terms = set(load_feature_config("draft_purposes.json").keys())
    if allowed:
        allowed_terms.update(allowed)
    allowed_terms.update(load_feature_config("drafts.json").get("allowed_digit_placeholders", []))
    without_placeholders = re.sub(r"\{\{F\d+\}\}", "", text)
    for allowed_term in allowed_terms:
        if re.search(r"\d", allowed_term, re.IGNORECASE):
            without_placeholders = re.sub(
                re.escape(allowed_term),
                "",
                without_placeholders,
                flags=re.IGNORECASE,
            )
    digits = [match.group() for match in re.finditer(r"\d+", without_placeholders)]
    for token in digits:
        if token.casefold() not in allowed_terms:
            return False
    return True


def check_draft_content(text: str, facts: list[dict[str, Any]], role: str | None = None) -> list[str]:
    """Return configured content-policy warnings found in a draft."""
    lowered = text.casefold()
    warnings: list[str] = []
    config = load_feature_config("drafts.json")
    for phrase in config.get("forbidden_promises", []):
        if phrase.casefold() in lowered and not re.search(r"\{\{F\d+\}\}", text):
            warnings.append(f"Forbidden promise language: {phrase}.")
    for phrase in config.get("forbidden_pressure", []):
        if phrase.casefold() in lowered:
            warnings.append(f"Pressure language: {phrase}.")
    allowed_values = {str(fact["value"]).casefold() for fact in facts}
    for match in re.findall(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b", text):
        if match.casefold() not in allowed_values and not validate_digit_guard(text):
            warnings.append("Draft contains an unsupported number.")
    return warnings


def fill_placeholders(text: str, facts: list[dict[str, Any]]) -> str:
    """Replace only fact placeholders and remove duplicates of the status line."""
    lookup = {fact["id"]: str(fact["value"]) for fact in facts}
    return re.sub(r"\{\{(F\d+)\}\}", lambda match: lookup.get(match.group(1), match.group(0)), text)
