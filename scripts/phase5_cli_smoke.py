"""Run five live CLI questions to verify Phase 5 structured-data behaviour."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from math import isclose
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from app.analysis.analyses import run_analysis
from app.config import PROJECT_ROOT as CONFIG_PROJECT_ROOT
from app.mcp_servers.business_data_server import (
    get_store,
    query_business_data,
)

REPORT_PATH = PROJECT_ROOT / "evaluation" / "reports" / "phase5-cli-smoke.md"
NUMBER_PATTERN = re.compile(r"(?<![\w.])[−‑+-]?\d[\d,]*(?:\.\d+)?%?")
REQUEST_INTERVAL_SECONDS = 65
TRACE_PREFIX = "PHASE5_TRACE_JSON="


@dataclass(frozen=True)
class SmokeCase:
    """One CLI question with values that must appear in its grounded answer."""

    question: str
    source: str
    expected_text: tuple[str, ...]
    expected_numbers: tuple[float, ...]
    money_number_indices: tuple[int, ...] = ()


def _build_cases() -> list[SmokeCase]:
    """Build five question checks from the configured sample data."""
    load_dotenv(CONFIG_PROJECT_ROOT / ".env")
    store = get_store()

    customer_count = query_business_data(
        "customers",
        ["customer_id"],
        limit=1,
    )["total_matches"]
    category_result = run_analysis(
        store,
        "revenue_by_category",
        {"start": "2024-01-01", "end": "2024-12-31"},
    )["data"]
    top_category = category_result[0]
    product_result = run_analysis(
        store,
        "revenue_by_product",
        {"start": "2024-11-01", "end": "2024-11-30", "top_n": 1},
    )["data"][0]
    customer_result = run_analysis(
        store,
        "top_customers",
        {"start": "2024-01-01", "end": "2024-12-31", "top_n": 1},
    )["data"][0]
    change_result = run_analysis(
        store,
        "period_change",
        {
            "metric": "revenue",
            "current_start": "2024-12-01",
            "current_end": "2024-12-31",
            "previous_start": "2024-11-01",
            "previous_end": "2024-11-30",
        },
    )["data"][0]

    return [
        SmokeCase(
            question="How many customers are in the database?",
            source="query_business_data",
            expected_text=("customer",),
            expected_numbers=(float(customer_count),),
        ),
        SmokeCase(
            question="Which category generated the most revenue in 2024?",
            source="run_analysis",
            expected_text=(str(top_category["category"]),),
            expected_numbers=(float(top_category["revenue_cents"]),),
            money_number_indices=(0,),
        ),
        SmokeCase(
            question=(
                "Which product had the highest completed-order revenue "
                "in November 2024?"
            ),
            source="run_analysis",
            expected_text=(str(product_result["product_name"]),),
            expected_numbers=(float(product_result["revenue_cents"]),),
            money_number_indices=(0,),
        ),
        SmokeCase(
            question=(
                "Which customer generated the most completed-order revenue "
                "in 2024?"
            ),
            source="run_analysis",
            expected_text=(str(customer_result["customer_name"]),),
            expected_numbers=(float(customer_result["revenue_cents"]),),
            money_number_indices=(0,),
        ),
        SmokeCase(
            question=(
                "Compare completed-order revenue in December and November "
                "2024. Give both totals in cents and the percentage change."
            ),
            source="run_analysis",
            expected_text=("revenue",),
            expected_numbers=(
                float(change_result["current_value"]),
                float(change_result["previous_value"]),
                float(change_result["percent_change"]),
            ),
            money_number_indices=(0, 1),
        ),
    ]


def _answer_numbers(answer: str) -> list[float]:
    """Extract numeric tokens from a CLI answer for smoke-check comparison."""
    numbers = []
    for match in NUMBER_PATTERN.finditer(answer):
        token = (
            match.group()
            .replace(",", "")
            .removesuffix("%")
            .replace("−", "-")
            .replace("‑", "-")
        )
        try:
            numbers.append(float(token))
        except ValueError:
            continue
    return numbers


def _expected_number_is_present(
    expected: float,
    actual_numbers: list[float],
    allow_dollar_format: bool = False,
) -> bool:
    """Accept exact values, two-decimal rounding, or cents formatted as dollars."""
    candidates = {expected, round(expected, 2)}
    if allow_dollar_format and expected.is_integer():
        candidates.add(round(expected / 100, 2))
    return any(
        isclose(actual, candidate, rel_tol=1e-4, abs_tol=0.005)
        for actual in actual_numbers
        for candidate in candidates
    )


def _check_answer(answer: str, case: SmokeCase) -> list[str]:
    """Return missing expected content, numeric evidence, or source attribution."""
    errors = []
    normalized_answer = " ".join(answer.casefold().split())
    for text in case.expected_text:
        normalized_text = " ".join(text.casefold().split())
        if normalized_text not in normalized_answer:
            errors.append(f"Missing expected answer text: {text!r}.")

    available_numbers = _answer_numbers(answer)
    for index, expected in enumerate(case.expected_numbers):
        matching_number = next(
            (
                number_index
                for number_index, actual in enumerate(available_numbers)
                if _expected_number_is_present(
                    expected,
                    [actual],
                    allow_dollar_format=index in case.money_number_indices,
                )
            ),
            None,
        )
        if matching_number is None:
            errors.append(f"Missing expected numeric value: {expected:g}.")
        else:
            available_numbers.pop(matching_number)

    source_match = re.search(r"\bSources:\s*([^\r\n]+)", answer, re.IGNORECASE)
    reported_sources = (
        {
            source.strip().rstrip(".").casefold()
            for source in source_match.group(1).split(",")
        }
        if source_match
        else set()
    )
    if case.source.casefold() not in reported_sources:
        errors.append(f"Missing source attribution: {case.source}.")
    return errors


def _run_case(case: SmokeCase) -> tuple[int, str, str, list[dict[str, Any]]]:
    """Invoke the real CLI in a subprocess for one question."""
    environment = os.environ.copy()
    environment["PHASE5_TRACE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "app.cli", case.question],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return 124, "", "CLI question timed out after 180 seconds.", []
    trace_events = [
        json.loads(line[len(TRACE_PREFIX) :])
        for line in completed.stderr.splitlines()
        if line.startswith(TRACE_PREFIX)
    ]
    trace = trace_events[-1] if trace_events else []
    return (
        completed.returncode,
        completed.stdout.strip(),
        completed.stderr.strip(),
        trace,
    )


def _write_report(
    results: list[tuple[SmokeCase, str, list[str], str, list[dict[str, Any]]]],
) -> None:
    """Write a reviewable report containing each question and CLI response."""
    passed = sum(not errors for _, _, errors, _, _ in results)
    lines = [
        "# Phase 5 CLI smoke test",
        "",
        f"- Passed: {passed} of {len(results)}",
        "- Scope: five live structured-data questions through `app.cli`.",
        "- Expected figures are calculated from the configured local datasets.",
        "",
    ]
    trace_records = []
    for index, (case, answer, errors, stderr, trace) in enumerate(results, start=1):
        trace_record = {
            "question": case.question,
            "tool_calls": [
                event for event in trace if event.get("event") == "tool_call"
            ],
            "drafts": [
                event for event in trace if event.get("event") == "model_response"
            ],
            "evidence_checks": [
                event for event in trace if event.get("event") == "evidence_check"
            ],
            "final_answer": answer,
        }
        trace_records.append(trace_record)
        lines.extend(
            [
                f"## {index}. {'PASS' if not errors else 'FAIL'}",
                "",
                f"Question: {case.question}",
                "",
                "Answer:",
                "",
                "```text",
                answer or "(no answer returned)",
                "```",
                "",
            ]
        )
        if errors:
            lines.extend(["Issues:", *[f"- {error}" for error in errors], ""])
            if stderr:
                lines.extend(
                    [
                        "CLI diagnostics:",
                        "",
                        "```text",
                        stderr,
                        "```",
                        "",
                    ]
                )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    trace_path = REPORT_PATH.with_name("phase5-cli-trace.jsonl")
    trace_path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=True, default=str) + "\n"
            for record in trace_records
        ),
        encoding="utf-8",
    )


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the five-question acceptance check and report its outcome."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        type=int,
        choices=range(1, 6),
        help="Run one question by its 1-based number in the smoke test set.",
    )
    options = parser.parse_args(arguments)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cases = _build_cases()
    if options.case is not None:
        cases = [cases[options.case - 1]]
    results: list[
        tuple[SmokeCase, str, list[str], str, list[dict[str, Any]]]
    ] = []
    for index, case in enumerate(cases, start=1):
        if index > 1:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        return_code, answer, stderr, trace = _run_case(case)
        errors = (
            [
                f"CLI exited with status {return_code}: "
                f"{stderr or 'no error details returned'}"
            ]
            if return_code != 0
            else _check_answer(answer, case)
        )
        results.append((case, answer, errors, stderr, trace))
        print(f"[{'PASS' if not errors else 'FAIL'}] {index}/5: {case.question}")
        if answer:
            print(answer)
        if errors:
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            if stderr:
                print(stderr, file=sys.stderr)
        if return_code != 0:
            break

    _write_report(results)
    print(f"\nReport: {REPORT_PATH}")
    print(f"Trace: {REPORT_PATH.with_name('phase5-cli-trace.jsonl')}")
    return 0 if len(results) == len(cases) and all(
        not errors for _, _, errors, _, _ in results
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
