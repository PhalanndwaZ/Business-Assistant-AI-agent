from __future__ import annotations

import re
from typing import Any

from app.services.evidence_check import check_numeric_evidence
from app.state import ToolResult

NUMBER_PATTERN = re.compile(
    r"(?<![\w.,])[−‑+-]?\d+(?:,\d{3})*(?:\.\d+)?%?"
)


def response_tool_results(response: dict[str, Any]) -> list[ToolResult]:
    """Convert public `/ask` figures into successful tool-result records."""
    results: list[ToolResult] = []
    for figure in response.get("figures", []):
        if not isinstance(figure, dict):
            continue
        tool_name = "run_analysis"
        if "dataset" in figure:
            tool_name = "query_business_data"
        results.append(
            {
                "tool_name": tool_name,
                "arguments": {},
                "result": figure,
                "success": True,
            }
        )
    return results


def check_answer_evidence(
    response: dict[str, Any],
    allowed_numbers: tuple[str, ...] = (),
) -> list[str]:
    """Run the existing evidence checker and report unsupported numeric claims."""
    answer = str(response.get("answer", ""))
    tool_results = response_tool_results(response)
    valid, issues = check_numeric_evidence(answer, tool_results)
    if valid:
        return []

    allowed = set(allowed_numbers)
    return [
        issue
        for issue in issues
        if not any(
            token in allowed
            for token in NUMBER_PATTERN.findall(issue)
        )
    ]


def extra_numbers(answer: str, allowed_numbers: tuple[str, ...] = ()) -> list[str]:
    """List answer numbers that are not present in the configured allowance."""
    allowed = set(allowed_numbers)
    return [number for number in NUMBER_PATTERN.findall(answer) if number not in allowed]


def reconcile_app_evidence(
    response: dict[str, Any],
    runner_issues: list[str],
) -> list[str]:
    """Report disagreement between runner evidence and app evidence caveats."""
    app_reported = any(
        str(caveat).startswith("Evidence check:")
        for caveat in response.get("caveats", [])
    )
    runner_reported = bool(runner_issues)
    if app_reported != runner_reported:
        return [
            "evidence disagreement: "
            f"app_reported={app_reported}, runner_reported={runner_reported}"
        ]
    return []
