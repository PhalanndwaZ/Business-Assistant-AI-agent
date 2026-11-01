from __future__ import annotations

from collections.abc import Mapping
from typing import Any

LABELS = {
    "customer_name": "Customer name",
    "customer_id": "Customer ID",
    "days_since_last_order": "Days since last order",
    "revenue_12m": "Revenue in the last 12 months",
    "revenue_cents": "Revenue",
    "product_name": "Product name",
    "product_id": "Product ID",
    "summary": "Summary",
}


def build_facts(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten permitted scalar facts from referenced tool results."""
    facts: list[dict[str, Any]] = []
    for result in tool_results:
        payload = result.get("result", {}) if isinstance(result.get("result"), dict) else {}
        candidates: list[tuple[str, Any, str]] = []

        def visit(value: Any, path: str = "") -> None:
            if isinstance(value, Mapping):
                for key, child in value.items():
                    child_path = f"{path}.{key}" if path else str(key)
                    if isinstance(child, (str, int, float)) and not isinstance(child, bool):
                        candidates.append((str(key), child, str(result.get("call_id", ""))))
                    elif isinstance(child, (Mapping, list)):
                        visit(child, child_path)
            elif isinstance(value, list):
                for index, child in enumerate(value[:3]):
                    if isinstance(child, (Mapping, list)):
                        visit(child, f"{path}.{index}" if path else str(index))

        visit(payload)
        for key, value, result_id in candidates:
            if key in {"analysis", "status", "period"}:
                continue
            facts.append({
                "id": f"F{len(facts) + 1}",
                "label": LABELS.get(key, key.replace("_", " ").title()),
                "value": str(value),
                "key": key,
                "result_id": result_id,
            })
    return facts
