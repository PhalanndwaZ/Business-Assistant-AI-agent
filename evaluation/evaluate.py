"""Run Phase 10 offline benchmark checks and write a Markdown report."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

from app.config import ConfigurationError, PROJECT_ROOT, load_settings
from groq import APIError
from mcp.shared.exceptions import McpError
from evaluation.audit import CaseAudit, audit_cases
from evaluation.live import run_live_evaluation
from evaluation.questions import GROUP_COUNTS, QUESTIONS

DEFAULT_REPORT = PROJECT_ROOT / "evaluation" / "reports" / "phase10-evaluation.md"


def _format_expected(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _run_pytest() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_evaluation.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _report_text(
    results: list[CaseAudit],
    test_result: subprocess.CompletedProcess[str],
    live_results: list[dict[str, Any]] | None = None,
    live_error: str | None = None,
    live_requested: bool = False,
) -> str:
    grouped: dict[str, list[CaseAudit]] = defaultdict(list)
    for result in results:
        grouped[result.case.group].append(result)

    lines = [
        "# Phase 10 question evaluation",
        "",
        "## Run details",
        "",
        "- Mode: live question-bank agent evaluation."
        if live_results is not None
        else (
            "- Mode: live evaluation requested but not completed."
            if live_requested
            else "- Mode: offline case, source-fixture, and independent-ground-truth validation."
        ),
        "- Agent/model answers: evaluated."
        if live_results is not None
        else (
            "- Agent/model answers: not completed."
            if live_requested
            else "- Agent/model answers: not invoked; this is not a live answer-quality score."
        ),
        "- DeepEval criteria: run for document and combined cases."
        if live_results is not None
        and any(result.get("deepeval") for result in live_results)
        else "- API-dependent DeepEval metrics: not run.",
        f"- Question bank: {len(QUESTIONS)} cases.",
        f"- Pytest: {'passed' if test_result.returncode == 0 else 'failed'}.",
        "",
        (
            "The group rates below measure actual agent/tool/evidence checks."
            if live_results is not None
            else "The group rates below measure benchmark readiness only. Use --live"
            " to score actual model answers and tool calls."
        ),
        "",
        "## Group answer pass rates" if live_results is not None else "## Group readiness",
        "",
        "| Group | Passed / ready | Total | Pass / readiness rate |",
        "|---|---:|---:|---:|",
    ]
    for group, total in GROUP_COUNTS.items():
        if live_results is None:
            passed = sum(item.passed for item in grouped[group])
        else:
            passed = sum(
                bool(item["passed"])
                for item in live_results
                if item["group"] == group
            )
            total = sum(item["group"] == group for item in live_results)
        rate = passed / total * 100 if total else 0.0
        lines.append(f"| {group} | {passed} | {total} | {rate:.1f}% |")

    lines.extend(
        [
            "",
            "## Offline case readiness",
            "",
            "| ID | Group | Status | Checks / failure causes | Independent expected result |",
            "|---|---|---|---|---|",
        ]
    )
    for result in results:
        detail = result.checks + result.failures
        detail_text = "; ".join(detail).replace("|", "\\|") or "No checks recorded."
        status = "READY" if result.passed else "FAIL"
        lines.append(
            f"| {result.case.case_id} | {result.case.group} | {status} | "
            f"{detail_text} | `{_format_expected(result.expected)}` |"
        )
    if live_results is not None:
        lines.extend(
            [
                "",
                "## Live answer results and failure causes",
                "",
                "| ID | Group | Result | Tool calls | Retrieved documents | Failures |",
                "|---|---|---|---|---|---|",
            ]
        )
        for result in live_results:
            failures = result["failures"]
            failure_text = "; ".join(str(item) for item in failures) or "None"
            answer = str(result["answer"]).replace("|", "\\|").replace("\n", " ")
            status = (
                "NOT RUN"
                if not result.get("completed", True)
                else "PASS"
                if result["passed"]
                else "FAIL"
            )
            lines.append(
                f"| {result['case_id']} | {result['group']} | "
                f"{status} | "
                f"`{_format_expected(result['tools'])}` | "
                f"`{_format_expected(result['retrieved_documents'])}` | "
                f"{failure_text} — Answer: {answer} |"
            )
        deepeval_scores = [
            (str(result["case_id"]), result["deepeval"])
            for result in live_results
            if result.get("deepeval")
        ]
        if deepeval_scores:
            lines.extend(
                [
                    "",
                    "## DeepEval signals",
                    "",
                    "| ID | Metric | Score | Success | Reason |",
                    "|---|---|---:|---|---|",
                ]
            )
            for case_id, metric_scores in deepeval_scores:
                for metric_name, metric in metric_scores.items():
                    reason = str(metric.get("reason", "")).replace("|", "\\|")
                    lines.append(
                        f"| {case_id} | {metric_name} | {metric.get('score')} | "
                        f"{metric.get('success')} | {reason} |"
                    )
    if live_error:
        lines.extend(["", "## Live run error", "", f"`{live_error}`"])
    lines.extend(
        [
            "",
            "## Pytest output",
            "",
            "```text",
            (test_result.stdout + test_result.stderr).strip() or "(no output)",
            "```",
            "",
            "## Interpretation",
            "",
            "The independent expected values are computed from the raw approved",
            "JSON files with Pandas and do not call the production analysis",
            "functions. Offline readiness confirms that every question has a",
            "valid contract and its expected reference data is available; it",
            "does not establish that the agent answered correctly.",
            "",
        ]
    )
    return "\n".join(lines)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT,
        help="Markdown report path (default: evaluation/reports/phase10-evaluation.md).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run all benchmark questions against Groq and both MCP servers.",
    )
    parser.add_argument(
        "--deep-eval",
        action="store_true",
        help="Run DeepEval RAG quality metrics; requires --live.",
    )
    parsed = parser.parse_args(arguments)
    if parsed.deep_eval and not parsed.live:
        parser.error("--deep-eval requires --live.")

    results = audit_cases()
    test_result = _run_pytest()
    live_results: list[dict[str, Any]] | None = None
    live_error = None
    if parsed.live:
        try:
            live_results = asyncio.run(
                run_live_evaluation(load_settings(), use_deepeval=parsed.deep_eval)
            )
        except (
            APIError,
            ConfigurationError,
            McpError,
            OSError,
            RuntimeError,
            TimeoutError,
            ValueError,
        ) as exc:
            live_error = f"{type(exc).__name__}: {exc}"

    report_path = parsed.output
    if not report_path.is_absolute():
        report_path = PROJECT_ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _report_text(
            results,
            test_result,
            live_results,
            live_error,
            live_requested=parsed.live,
        ),
        encoding="utf-8",
    )

    ready_count = sum(item.passed for item in results)
    if live_results is None:
        print(f"Phase 10 case readiness: {ready_count}/{len(results)}")
    else:
        passed_live = sum(bool(item["passed"]) for item in live_results)
        print(f"Phase 10 live answers: {passed_live}/{len(live_results)}")
    print(f"Pytest exit code: {test_result.returncode}")
    print(f"Report: {report_path}")
    live_passed = (
        live_error is None
        and live_results is not None
        and all(bool(item["passed"]) for item in live_results)
    )
    return 0 if (
        test_result.returncode == 0
        and ready_count == len(results)
        and (not parsed.live or live_passed)
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
