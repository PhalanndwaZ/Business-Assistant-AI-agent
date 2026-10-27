"""Offline checks for the live Phase 5 CLI acceptance script."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts import phase5_cli_smoke


def test_smoke_script_builds_five_structured_question_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The acceptance script covers five different structured-data intents."""
    monkeypatch.setattr(phase5_cli_smoke, "load_dotenv", lambda *_args: None)
    monkeypatch.setattr(phase5_cli_smoke, "get_store", lambda: object())
    monkeypatch.setattr(
        phase5_cli_smoke,
        "query_business_data",
        lambda *_args, **_kwargs: {"total_matches": 60},
    )
    analyses = {
        "revenue_by_category": {
            "data": [{"category": "Furniture", "revenue_cents": 1000}]
        },
        "revenue_by_product": {
            "data": [{"product_name": "Standing Desk", "revenue_cents": 500}]
        },
        "top_customers": {
            "data": [{"customer_name": "Customer 037", "revenue_cents": 250}]
        },
        "period_change": {
            "data": [
                {
                    "current_value": 100,
                    "previous_value": 200,
                    "percent_change": -50.0,
                }
            ]
        },
    }
    monkeypatch.setattr(
        phase5_cli_smoke,
        "run_analysis",
        lambda _store, analysis_name, _parameters: analyses[analysis_name],
    )

    cases = phase5_cli_smoke._build_cases()

    assert len(cases) == 5
    assert [case.source for case in cases] == [
        "query_business_data",
        "run_analysis",
        "run_analysis",
        "run_analysis",
        "run_analysis",
    ]
    assert [case.expected_numbers for case in cases] == [
        (60.0,),
        (1000.0,),
        (500.0,),
        (250.0,),
        (100.0, 200.0, -50.0),
    ]


def test_answer_check_accepts_grounded_values_and_cited_source() -> None:
    """The smoke check accepts dollar formatting and additional source names."""
    case = phase5_cli_smoke.SmokeCase(
        question="Revenue?",
        source="run_analysis",
        expected_text=("Furniture",),
        expected_numbers=(5000.0,),
        money_number_indices=(0,),
    )

    errors = phase5_cli_smoke._check_answer(
        "Furniture revenue was $50.00.\n\nSources: "
        "get_data_schema, run_analysis.",
        case,
    )

    assert errors == []


def test_answer_check_normalizes_nonbreaking_spaces_in_expected_text() -> None:
    """Unicode spacing in model output does not fail a grounded text check."""
    case = phase5_cli_smoke.SmokeCase(
        question="Which customer?",
        source="run_analysis",
        expected_text=("Customer 037",),
        expected_numbers=(),
    )

    errors = phase5_cli_smoke._check_answer(
        "The top customer was Customer\u202f037.\n\nSources: run_analysis.",
        case,
    )

    assert errors == []


def test_customer_count_does_not_accept_fractional_number_as_cents() -> None:
    """Cents-to-dollars conversion applies only to currency expectations."""
    assert not phase5_cli_smoke._expected_number_is_present(
        60.0,
        [0.6],
    )


def test_answer_number_parser_preserves_unicode_negative_percentages() -> None:
    """A Unicode minus remains negative in the acceptance check."""
    assert phase5_cli_smoke._answer_numbers("Change: \u201160.81\u202f%") == [
        -60.81
    ]


def test_answer_check_requires_distinct_numeric_occurrences() -> None:
    """One printed total cannot satisfy both expected comparison-period totals."""
    case = phase5_cli_smoke.SmokeCase(
        question="Compare periods.",
        source="run_analysis",
        expected_text=("revenue",),
        expected_numbers=(100.0, 100.0, 0.0),
        money_number_indices=(0, 1),
    )

    errors = phase5_cli_smoke._check_answer(
        "Revenue was $1.00 and changed 0%.\n\nSources: run_analysis.",
        case,
    )

    assert errors == ["Missing expected numeric value: 100."]


def test_answer_check_rejects_missing_number_or_source() -> None:
    """Unsubstantiated figures and absent source attribution fail the check."""
    case = phase5_cli_smoke.SmokeCase(
        question="Revenue?",
        source="run_analysis",
        expected_text=("Furniture",),
        expected_numbers=(5000.0,),
    )

    errors = phase5_cli_smoke._check_answer(
        "Furniture revenue was $25.00.",
        case,
    )

    assert len(errors) == 2
    assert any("numeric value" in error for error in errors)
    assert any("source attribution" in error for error in errors)


def test_run_case_enables_and_parses_cli_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live case captures structured graph events from the CLI process."""
    events = [{"event": "tool_call", "tool_name": "run_analysis"}]
    stderr = phase5_cli_smoke.TRACE_PREFIX + json.dumps(events)

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert environment["PHASE5_TRACE"] == "1"
        return SimpleNamespace(returncode=0, stdout="answer", stderr=stderr)

    monkeypatch.setattr(phase5_cli_smoke.subprocess, "run", fake_run)
    case = phase5_cli_smoke.SmokeCase(
        question="Revenue?",
        source="run_analysis",
        expected_text=(),
        expected_numbers=(),
    )

    return_code, answer, _, trace = phase5_cli_smoke._run_case(case)

    assert return_code == 0
    assert answer == "answer"
    assert trace == events
