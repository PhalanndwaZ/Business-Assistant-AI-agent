from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from evaluation.runner.runner import RunResult
from evaluation.runner.schema import EvaluationCase


def build_run_snapshot(
    cases: Iterable[EvaluationCase],
    case_results: Iterable[tuple[EvaluationCase, list[RunResult], bool, bool]],
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build the stable machine-readable summary persisted for comparisons."""
    case_list = tuple(cases)
    rows = list(case_results)
    case_passes = {
        case.case_id: passed
        for case, _, passed, _ in rows
    }
    results = [result for _, repeat_results, _, _ in rows for result in repeat_results]
    return {
        "run_id": run_id or datetime.now(timezone.utc).isoformat(),
        "cases": [
            {
                "case_id": case.case_id,
                "group": case.group,
                "severity": case.severity,
                "passed": case_passes.get(case.case_id, False),
            }
            for case in case_list
        ],
        "repeat_results": [asdict(result) for result in results],
        "overall_passed": sum(case_passes.values()),
        "overall_total": sum(case.status == "active" for case in case_list),
    }


def save_run_snapshot(
    path: Path,
    snapshot: dict[str, Any],
    history_path: Path | None = None,
) -> None:
    """Atomically append one run summary before writing the current snapshot."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_path is not None:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(snapshot, sort_keys=True) + "\n")


def load_previous_snapshot(current_path: Path) -> dict[str, Any] | None:
    if not current_path.is_file():
        return None
    try:
        return json.loads(current_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def compare_runs(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, list[str] | float]:
    """Compare case outcomes and overall pass rates."""
    previous_cases = {
        item["case_id"]: bool(item["passed"])
        for item in (previous or {}).get("cases", [])
    }
    current_cases = {
        item["case_id"]: bool(item["passed"])
        for item in current.get("cases", [])
    }
    newly_failing = sorted(
        case_id
        for case_id in current_cases
        if previous_cases.get(case_id) is True and not current_cases[case_id]
    )
    newly_passing = sorted(
        case_id
        for case_id in current_cases
        if previous_cases.get(case_id) is False and current_cases[case_id]
    )
    previous_rate = (
        _snapshot_pass_rate(previous)
        if previous is not None
        else 0.0
    )
    return {
        "newly_failing": newly_failing,
        "newly_passing": newly_passing,
        "pass_rate_change": round(
            _snapshot_pass_rate(current) - previous_rate,
            1,
        ),
    }


def _snapshot_pass_rate(snapshot: dict[str, Any]) -> float:
    total = int(snapshot.get("overall_total", 0))
    passed = int(snapshot.get("overall_passed", 0))
    return round(passed / total * 100, 1) if total else 0.0


def render_report(
    snapshot: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> str:
    """Render the human-readable evaluation summary and failure comparison."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in snapshot["cases"]:
        grouped[str(case["group"])].append(case)

    lines = [
        "# Evaluation run",
        "",
        f"- Run: {snapshot['run_id']}",
        f"- Verdict: {'PASS' if snapshot['overall_passed'] == snapshot['overall_total'] else 'FAIL'}",
        f"- Overall: {snapshot['overall_passed']}/{snapshot['overall_total']} "
        f"({_snapshot_pass_rate(snapshot):.1f}%)",
        "",
        "| Group | Passed | Total | Rate |",
        "|---|---:|---:|---:|",
    ]
    for group, cases in sorted(grouped.items()):
        passed = sum(bool(case["passed"]) for case in cases)
        total = len(cases)
        lines.append(
            f"| {group} | {passed} | {total} | "
            f"{passed / total * 100:.1f}% |"
        )

    comparison = compare_runs(previous, snapshot)
    lines.extend(["", "## Change since last run", ""])
    newly_failing = comparison["newly_failing"]
    newly_passing = comparison["newly_passing"]
    lines.append(
        "- Newly failing: "
        + (", ".join(newly_failing) if newly_failing else "None")
    )
    lines.append(
        "- Newly passing: "
        + (", ".join(newly_passing) if newly_passing else "None")
    )
    lines.append(f"- Pass rate change: {comparison['pass_rate_change']:+.1f}%")

    failures = [
        result
        for result in snapshot.get("repeat_results", [])
        if result.get("classification") == "fail"
    ]
    lines.extend(["", "## Failures", ""])
    if not failures:
        lines.append("None.")
    else:
        for result in failures:
            details = "; ".join(result.get("failures", [])) or "Case failed."
            lines.append(f"- {result['case_id']}: {details}")
    return "\n".join(lines) + "\n"
