"""Deterministic tests for the Phase 10 evaluation question bank."""

from __future__ import annotations

import pytest

from app.analysis.analyses import run_analysis
from app.config import PROJECT_ROOT
from app.data_access.json_loader import JsonDataStore
from evaluation.audit import audit_cases
from evaluation.expected_answers import compute_expected_answers
from evaluation.live import (
    _check_case,
    _has_unqualified_causal_claim,
    _subset_matches,
)
from evaluation.questions import GROUP_COUNTS, QUESTIONS, STRUCTURED_DATA, COMBINED


@pytest.fixture(scope="module")
def case_audits():
    return {item.case.case_id: item for item in audit_cases()}


@pytest.mark.parametrize("case_id", [case.case_id for case in QUESTIONS])
def test_evaluation_case_has_valid_contract(case_id: str, case_audits) -> None:
    """Every benchmark prompt has a valid offline contract and fixture."""
    case = next(item for item in QUESTIONS if item.case_id == case_id)
    audit = case_audits[case_id]

    assert audit.passed, "; ".join(audit.failures)
    assert case.question.strip()
    assert case.group in GROUP_COUNTS


def test_question_bank_has_architecture_phase_ten_group_sizes() -> None:
    """The 30 cases stay within the architecture's specified group counts."""
    counts = {
        group: sum(case.group == group for case in QUESTIONS)
        for group in GROUP_COUNTS
    }

    assert len(QUESTIONS) == 31
    assert counts == GROUP_COUNTS


def test_ground_truth_is_independent_and_contains_all_numeric_cases() -> None:
    """Ground truth covers all structured and combined cases from raw JSON."""
    expected = compute_expected_answers()
    expected_ids = {
        case.case_id
        for case in QUESTIONS
        if case.group in {STRUCTURED_DATA, COMBINED}
        and (case.analysis_name or case.dataset)
    }

    assert expected_ids == expected.keys()
    assert all(value is not None for value in expected.values())


def test_independent_pandas_truth_matches_production_analysis_outputs() -> None:
    """Compare independent expected values with each production analysis result."""
    expected = compute_expected_answers()
    store = JsonDataStore(PROJECT_ROOT / "data" / "sample_data")
    analysis_cases = [case for case in QUESTIONS if case.analysis_name]

    for case in analysis_cases:
        actual = run_analysis(store, case.analysis_name or "", case.parameters or {})
        actual_data = actual["data"]
        if case.analysis_name == "period_change":
            actual_data = actual_data[0]
        elif case.analysis_name == "trend":
            actual_data = actual_data[0]
        assert _subset_matches(actual_data, expected[case.case_id]), case.case_id


def test_independent_ground_truth_matches_december_dip_contract() -> None:
    """Independent Pandas data confirms December has fewer completed orders."""
    expected = compute_expected_answers()
    december = expected["C01"]["current_value"]
    november = expected["C01"]["previous_value"]

    assert december < november


def test_live_grader_checks_period_arguments_result_and_answer() -> None:
    """The live score rejects neither correctly grounded values nor arguments."""
    case = next(item for item in QUESTIONS if item.case_id == "S04")
    expected = compute_expected_answers()["S04"]
    state = {
        "workflow_trace": [
            {
                "event": "tool_call",
                "tool_name": "run_analysis",
                "arguments": {
                    "analysis_name": "period_change",
                    "parameters": case.parameters,
                },
                "parsed_result": {
                    "analysis": "period_change",
                    "data": [expected],
                },
                "success": True,
            }
        ],
        "final_answer": (
            "Completed orders fell from 49 in November to 20 in December, "
            "a decrease of 29 orders or 59.18%."
        ),
        "evidence_ok": True,
        "evidence_errors": [],
        "retrieved_chunks": [],
    }

    assert _check_case(case, state, expected) == []


def test_live_grader_reports_wrong_tool_arguments_and_result() -> None:
    """A correct-looking draft cannot hide an incorrect analysis request."""
    case = next(item for item in QUESTIONS if item.case_id == "S04")
    expected = compute_expected_answers()["S04"]
    state = {
        "workflow_trace": [
            {
                "event": "tool_call",
                "tool_name": "run_analysis",
                "arguments": {
                    "analysis_name": "period_change",
                    "parameters": {
                        **(case.parameters or {}),
                        "current_start": "2024-11-01",
                    },
                },
                "parsed_result": {
                    "analysis": "period_change",
                    "data": [{"current_value": 999}],
                },
                "success": True,
            }
        ],
        "final_answer": "Completed orders were 20 from 49, a decrease of 29 (-59.18%).",
        "evidence_ok": True,
        "evidence_errors": [],
        "retrieved_chunks": [],
    }

    failures = _check_case(case, state, expected)

    assert any("arguments" in failure for failure in failures)
    assert any("ground truth" in failure for failure in failures)


def test_causality_grader_allows_explicit_non_causal_qualification() -> None:
    """A documented factor is not mistaken for an asserted cause if qualified."""
    assert not _has_unqualified_causal_claim(
        "The report does not prove supplier delays caused the change."
    )
    assert _has_unqualified_causal_claim(
        "Supplier delays caused the revenue decline."
    )


def test_live_grader_rejects_unknown_analysis_tool_calls() -> None:
    """The agent must not invoke an invented analysis name."""
    case = next(item for item in QUESTIONS if item.case_id == "I04")
    state = {
        "workflow_trace": [
            {
                "event": "tool_call",
                "tool_name": "run_analysis",
                "arguments": {"analysis_name": "payroll_risk_estimate"},
                "success": True,
            }
        ],
        "final_answer": "I cannot run that unsupported analysis.",
        "evidence_ok": True,
        "evidence_errors": [],
        "retrieved_chunks": [],
    }

    failures = _check_case(case, state, None)

    assert any("disallowed request" in failure for failure in failures)
