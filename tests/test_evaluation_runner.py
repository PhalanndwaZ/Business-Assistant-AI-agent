"""Tests for the Step 3 API evaluation runner."""

from __future__ import annotations

import json

import httpx
import pytest

from evaluation.runner.assertions import assert_response
from evaluation.runner.report import (
    build_run_snapshot,
    compare_runs,
    render_report,
    save_run_snapshot,
)
from evaluation.runner.client import EvaluationClient
from evaluation.runner.loader import load_cases
from evaluation.runner.runner import RunResult, run_case
from evaluation.runner.schema import EvaluationCase, EvaluationTurn
from evaluation.runner.numbers import (
    check_answer_evidence,
    extra_numbers,
    reconcile_app_evidence,
)
from evaluation.runner.assertions import assert_response


def test_loader_reports_file_line_and_field_for_malformed_case(tmp_path) -> None:
    """Malformed cases identify their source and missing field."""
    case_file = tmp_path / "cases.jsonl"
    case_file.write_text(
        '{"id":"bad","group":"core","role":"manager","turns":[]}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"cases\.jsonl:1: missing required field 'severity'"):
        load_cases(case_file)


def test_wrong_expectation_reports_expected_and_actual() -> None:
    """Structured assertions distinguish expected and observed values."""
    failures = assert_response(
        {"answer": "The November revenue was 10 cents."},
        {"contains": ["December revenue"]},
    )

    assert failures == [
        "contains 'December revenue': expected present, "
        "actual 'The November revenue was 10 cents.'."
    ]


def test_answer_evidence_rejects_invented_number() -> None:
    """An unsupported numeric claim fails the independent evidence check."""
    failures = check_answer_evidence(
        {
            "answer": "Revenue was 999 cents.",
            "figures": [{"analysis": "revenue_by_product", "data": [{"revenue_cents": 100}]}],
        }
    )

    assert failures
    assert "999" in failures[0]


def test_answer_evidence_accepts_configured_derived_number() -> None:
    """A configured derived number is allowed without weakening tool checks."""
    assert check_answer_evidence(
        {
            "answer": "The answer uses the top 3.",
            "figures": [{"analysis": "revenue_by_product", "data": []}],
        },
        ("3",),
    ) == []
    assert extra_numbers("The answer uses the top 3.", ("3",)) == []


def test_quote_must_exactly_match_a_retrieved_document_chunk() -> None:
    """Document quote assertions reuse the application evidence checker."""
    failures = assert_response(
        {
            "answer": (
                "The report states supplier delays affected availability "
                "[management_report.md], “supplier delays affected availability”."
            ),
            "sources": ["management_report.md"],
            "evidence_chunks": [{
                "document_name": "management_report.md",
                "text": (
                    "Management noted that supplier delays affected availability "
                    "of popular products."
                ),
            }],
            "figures": [],
        },
        {"quote_in_source": True},
    )

    assert not [failure for failure in failures if failure.startswith("quote_in_source:")]


def test_invented_document_quote_is_rejected() -> None:
    failures = assert_response(
        {
            "answer": (
                "The report says inventory was depleted [management_report.md], "
                "“inventory was depleted”."
            ),
            "sources": ["management_report.md"],
            "evidence_chunks": [{
                "document_name": "management_report.md",
                "text": "Management noted that supplier delays affected availability.",
            }],
            "figures": [],
        },
        {"quote_in_source": True},
    )

    assert any("exact quoted passage" in failure for failure in failures)


def test_app_and_runner_evidence_disagreement_is_reported() -> None:
    response = {
        "answer": "Revenue was 999 cents.",
        "figures": [],
        "caveats": [],
    }

    assert reconcile_app_evidence(response, ["unsupported 999"]) == [
        "evidence disagreement: app_reported=False, runner_reported=True"
    ]


def test_report_compares_passes_and_regressions(tmp_path) -> None:
    case = _case({"contains": ["OK"]})
    previous = build_run_snapshot(
        (case,),
        ((case, [RunResult(case.case_id, "pass")], True, False),),
        "previous",
    )
    current = build_run_snapshot(
        (case,),
        ((case, [RunResult(case.case_id, "fail", ("regression",))], False, False),),
        "current",
    )

    comparison = compare_runs(previous, current)

    assert comparison["newly_failing"] == ["test-001"]
    assert comparison["pass_rate_change"] == -100.0


def test_report_snapshot_is_persisted_and_rendered(tmp_path) -> None:
    case = _case({"contains": ["OK"]})
    snapshot = build_run_snapshot(
        (case,),
        ((case, [RunResult(case.case_id, "pass")], True, False),),
        "run-1",
    )
    snapshot_path = tmp_path / "latest.json"
    save_run_snapshot(snapshot_path, snapshot, tmp_path / "history.jsonl")

    assert snapshot_path.read_text(encoding="utf-8").startswith("{")
    assert "Change since last run" in render_report(snapshot)


def _case(expect: dict) -> EvaluationCase:
    return EvaluationCase(
        case_id="test-001",
        group="core",
        role="manager",
        turns=(EvaluationTurn("Known-good question"),),
        expect=expect,
        runs=3,
    )


@pytest.mark.asyncio
async def test_known_good_case_passes() -> None:
    """A successful API response satisfies a contains assertion."""
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "token"})
        assert request.headers["Authorization"] == "Bearer token"
        assert request.headers["X-Evaluation-Case-ID"] == "test-001"
        return httpx.Response(200, json={"answer": "December passed.", "conversation_id": "conv-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = EvaluationClient("http://test", {"manager": "password"}, transport)
        results, passed, flaky = await run_case(client, _case({"contains": ["December"]}))

    assert passed
    assert not flaky
    assert all(result.classification == "pass" for result in results)


@pytest.mark.asyncio
async def test_429_is_error_and_retry_succeeds() -> None:
    """A retried 429 is classified as an error unless the retry succeeds."""
    ask_attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal ask_attempts
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "token"})
        ask_attempts += 1
        if ask_attempts == 1:
            return httpx.Response(429, json={"detail": "rate limited"})
        return httpx.Response(200, json={"answer": "OK", "conversation_id": "conv-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = EvaluationClient("http://test", {"manager": "password"}, transport)
        results, passed, flaky = await run_case(client, _case({"contains": ["OK"]}))

    assert passed
    assert ask_attempts == 4
    assert results[0].classification == "error"


@pytest.mark.asyncio
async def test_mixed_runs_flag_flaky_case() -> None:
    """A case that passes and fails across repeats is reported as flaky."""
    ask_attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal ask_attempts
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "token"})
        ask_attempts += 1
        answer = "expected value" if ask_attempts != 2 else "wrong value"
        return httpx.Response(200, json={"answer": answer, "conversation_id": "conv-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = EvaluationClient("http://test", {"manager": "password"}, transport)
        results, passed, flaky = await run_case(
            client,
            _case({"contains": ["expected"]}),
        )

    assert passed
    assert flaky
    assert [result.classification for result in results] == ["pass", "fail", "pass"]
