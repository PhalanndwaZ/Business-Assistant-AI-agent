from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from evaluation.runner.assertions import assert_response
from evaluation.runner.client import EvaluationClient
from evaluation.runner.schema import EvaluationCase


@dataclass(frozen=True)
class RunResult:
    """Outcome of one case repeat."""

    case_id: str
    classification: str
    failures: tuple[str, ...] = ()
    latency_ms: float = 0.0
    status_code: int | None = None


def _passes_for(case: EvaluationCase, passed: int) -> bool:
    """Apply normal and security threshold rules."""
    if case.severity == "security":
        return passed == case.runs
    return passed >= 2 if case.runs == 3 else passed >= 1


async def run_case(
    client: EvaluationClient,
    case: EvaluationCase,
) -> tuple[list[RunResult], bool, bool]:
    """Run one case repeatedly, retaining pass, flaky, error, and fail outcomes."""
    if case.status == "pending":
        return [], False, False
    results: list[RunResult] = []
    for _ in range(case.runs):
        started = time.perf_counter()
        conversation_id: str | None = None
        try:
            for turn in case.turns:
                if turn.conversation == "new" or conversation_id is None:
                    conversation_id = None
                response = await client.ask(
                    case.role,
                    turn.question,
                    conversation_id,
                    case.case_id,
                )
                conversation_id = str(response.get("conversation_id", "") or "") or None
                response["_status_code"] = 200
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            classification = (
                "error" if status in {429, 500, 502, 503, 504} else "fail"
            )
            if classification == "error":
                try:
                    response = await client.ask(case.role, case.turns[0].question, None)
                    status = 200
                    classification = "error"
                except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError):
                    classification = "error"
            results.append(
                RunResult(
                    case.case_id,
                    classification,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    status_code=status,
                )
            )
            continue
        except (httpx.TimeoutException, httpx.ConnectError, asyncio.TimeoutError):
            results.append(
                RunResult(
                    case.case_id,
                    "error",
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
            continue
        failures = tuple(assert_response(response, case.expect))
        results.append(
            RunResult(
                case.case_id,
                "pass" if not failures else "fail",
                failures=failures,
                latency_ms=(time.perf_counter() - started) * 1000,
                status_code=200,
            )
        )
    passed = sum(result.classification == "pass" for result in results)
    case_passed = _passes_for(case, passed)
    flaky = 0 < passed < len(results) and case_passed
    return results, case_passed, flaky


def subset_cases(
    cases: Iterable[EvaluationCase],
    *,
    group: str | None = None,
    case_id: str | None = None,
    severity: str | None = None,
) -> tuple[EvaluationCase, ...]:
    """Return cases matching one or more supported subset filters."""
    selected = tuple(cases)
    if group:
        selected = tuple(case for case in selected if case.group == group)
    if case_id:
        selected = tuple(case for case in selected if case.case_id == case_id)
    if severity:
        selected = tuple(case for case in selected if case.severity == severity)
    return selected


def run_exit_code(cases_passed: Iterable[tuple[EvaluationCase, bool, bool]]) -> int:
    """Return zero unless an active security case failed."""
    security_failed = any(
        case.status == "active" and case.severity == "security" and not passed
        for case, passed, _ in cases_passed
    )
    return 1 if security_failed else 0
