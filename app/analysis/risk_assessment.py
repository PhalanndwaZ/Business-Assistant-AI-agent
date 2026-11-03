from __future__ import annotations

import re
from typing import Any, Iterable

FACTOR_TERMS = (
    "supplier delay",
    "supplier delays",
    "promotion",
    "pricing",
    "price",
    "stock",
    "availability",
    "weather",
    "competition",
    "competitor",
    "demand",
    "staff",
    "transport",
)

FACTOR_LABELS = {
    "supplier delay": "Supplier delays",
    "supplier delays": "Supplier delays",
    "promotion": "Promotion",
    "pricing": "Pricing",
    "price": "Price",
    "stock": "Stock",
    "availability": "Availability",
    "weather": "Weather",
    "competition": "Competition",
    "competitor": "Competitor",
    "demand": "Demand",
    "staff": "Staff",
    "transport": "Transport",
}


def reported_factors(chunks: Iterable[dict[str, Any]]) -> list[str]:
    """Extract document-named factors without inferring cause."""
    factors: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        text = str(chunk.get("text", ""))
        lowered = text.casefold()
        for term in FACTOR_TERMS:
            if term in lowered:
                label = FACTOR_LABELS[term]
                if label.casefold() not in seen:
                    seen.add(label.casefold())
                    factors.append(label)
    return factors


def assess_decline_risk(chunks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Classify document evidence while preserving data-analyst handoff."""
    chunks = list(chunks)
    factors = reported_factors(chunks)
    labelled_factors = [
        label_reported_factor(chunk, factor)
        for chunk in chunks
        for factor in factors
        if factor.casefold().replace(" ", "") in str(chunk.get("text", "")).casefold().replace(" ", "")
    ]
    labelled_factors = list(dict.fromkeys(labelled_factors))
    if labelled_factors:
        factors = labelled_factors
    if factors:
        return {
            "explanation_status": "reported_factors",
            "reported_factors": factors,
            "reported_factor_labels": factors,
            "next_step": "Review the reported factors and playbook actions.",
        }
    return {
        "explanation_status": "none",
        "reported_factors": [],
        "reported_factor_labels": [],
        "next_step": "Consult a data analyst.",
    }


def label_reported_factor(chunk: dict[str, Any], factor: str) -> str:
    """Label upload factors as user-reported context."""
    if chunk.get("origin") == "uploaded":
        return f"{factor} (reported in your document)"
    return factor
