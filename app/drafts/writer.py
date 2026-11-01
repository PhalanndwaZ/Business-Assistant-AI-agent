from __future__ import annotations

import re
from typing import Any

from app.drafts.facts import build_facts
from app.drafts.guard import check_draft_content, fill_placeholders, validate_digit_guard
from app.drafts.purposes import get_purpose


def render_template(purpose: str, facts: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """Render a purpose template using facts only."""
    settings = get_purpose(purpose)
    template = str(settings["template"])
    fact_by_key = {fact["key"]: fact["id"] for fact in facts if "key" in fact}
    placeholders = re.findall(r"\{\{([^{}]+)\}\}", template)
    rendered = template
    warnings: list[str] = []
    for placeholder in placeholders:
        fact_id = fact_by_key.get(placeholder)
        if fact_id:
            rendered = rendered.replace(f"{{{{{placeholder}}}}}", f"{{{{{fact_id}}}}}")
        else:
            rendered = rendered.replace(f"{{{{{placeholder}}}}}", placeholder.replace("_", " "))
            warnings.append(f"Fact {placeholder} was unavailable.")
    return rendered, warnings


def render_fallback(purpose: str, facts: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """Render the configured template and fall back safely if placeholder data is absent."""
    placeholder_text, warnings = render_template(purpose, facts)
    final_text = fill_placeholders(placeholder_text, facts)
    return final_text, warnings


def create_draft(
    purpose: str,
    tool_results: list[dict[str, Any]],
    *,
    model_text: str | None = None,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Create a draft, retrying a safe template when model text violates guards."""
    facts = build_facts(tool_results)
    fallback_template, warnings = render_template(purpose, facts)
    candidate = model_text or fallback_template
    if validate_digit_guard(candidate):
        content_warnings = check_draft_content(candidate, facts)
        if not content_warnings:
            return fill_placeholders(candidate, facts), facts, warnings
    final_text, fallback_warnings = render_fallback(purpose, facts)
    warnings.extend(fallback_warnings)
    warnings.append("Model output was rejected; the safe template was used.")
    return final_text, facts, warnings
