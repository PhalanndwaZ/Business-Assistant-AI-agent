"""Offline integrity checks for evaluation cases and their reference data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT
from app.data_access.schema import DATASETS
from evaluation.expected_answers import compute_expected_answers
from evaluation.questions import (
    COMBINED,
    GROUP_COUNTS,
    QUESTIONS,
    SAFETY,
    STRUCTURED_DATA,
    UNANSWERABLE,
    EvaluationCase,
)


@dataclass(frozen=True)
class CaseAudit:
    """Offline readiness result for one benchmark case."""

    case: EvaluationCase
    passed: bool
    checks: tuple[str, ...]
    failures: tuple[str, ...]
    expected: Any = None


def audit_cases(
    data_dir: Path | None = None,
    documents_dir: Path | None = None,
) -> list[CaseAudit]:
    """Check the complete case bank, data truth, and cited-source fixtures."""
    dataset_dir = data_dir or PROJECT_ROOT / "data" / "sample_data"
    document_dir = documents_dir or PROJECT_ROOT / "data" / "documents"
    expected_answers = compute_expected_answers(dataset_dir)
    case_ids = [case.case_id for case in QUESTIONS]
    observed_counts: dict[str, int] = {}
    for case in QUESTIONS:
        observed_counts[case.group] = observed_counts.get(case.group, 0) + 1

    results: list[CaseAudit] = []
    for case in QUESTIONS:
        checks: list[str] = []
        failures: list[str] = []
        truth = expected_answers.get(case.case_id)
        if len(case_ids) != len(set(case_ids)):
            failures.append("Question IDs are not unique.")
        if observed_counts != GROUP_COUNTS:
            failures.append(
                f"Question counts {observed_counts} do not match {GROUP_COUNTS}."
            )

        if case.group in {STRUCTURED_DATA, COMBINED} and (
            case.analysis_name or case.dataset
        ):
            if case.case_id not in expected_answers:
                failures.append("No independent Pandas ground truth was computed.")
            else:
                checks.append("Independent Pandas ground truth computed.")

        if case.analysis_name:
            if "run_analysis" not in case.expected_tools:
                failures.append("Analysis case does not require run_analysis.")
            if not case.parameters:
                failures.append("Analysis case has no expected parameters.")
            elif {"start", "end"} - case.parameters.keys() and (
                case.analysis_name != "period_change"
            ):
                failures.append("Date-bounded analysis is missing start/end.")
            else:
                checks.append("Analysis name and required parameters specified.")

        if case.dataset:
            if case.dataset not in DATASETS:
                failures.append(f"Dataset '{case.dataset}' is not approved.")
            if "query_business_data" not in case.expected_tools:
                failures.append("Dataset case does not require query_business_data.")
            if case.case_id in expected_answers:
                checks.append("Dataset result computed from raw JSON with Pandas.")

        for document_name in case.document_names:
            document_path = document_dir / document_name
            if not document_path.is_file():
                failures.append(f"Expected source document is missing: {document_name}.")
                continue
            document_text = document_path.read_text(encoding="utf-8").casefold()
            missing_terms = [
                term
                for term in case.required_terms
                if term.casefold() not in document_text
            ]
            if missing_terms:
                failures.append(
                    f"{document_name} does not contain required terms: "
                    f"{missing_terms}."
                )
            else:
                checks.append(f"Source fixture and terms verified: {document_name}.")
        if case.required_terms and not case.document_names:
            failures.append("Evidence terms have no expected source document.")
        if case.document_names and "search_documents" not in case.expected_tools:
            failures.append("Document case does not require search_documents.")

        if case.group == UNANSWERABLE:
            if case.expected_behavior != "admit_unanswerable":
                failures.append("Unanswerable case lacks an honest-refusal criterion.")
            elif case.case_id == "U01" and (
                not case.document_names
                or "quantified estimate"
                not in (
                    document_dir / case.document_names[0]
                ).read_text(encoding="utf-8").casefold()
            ):
                failures.append(
                    "The unanswerable source does not establish the missing estimate."
                )
            else:
                checks.append("Unanswerable/refusal criterion is explicit.")

        if case.group == SAFETY:
            if not case.expected_behavior.startswith(("deny_", "ignore_")):
                failures.append("Safety case has no denial/injection criterion.")
            elif case.expected_behavior == "deny_unapproved_dataset":
                if "employee_salaries" in DATASETS:
                    failures.append("The safety case dataset is unexpectedly approved.")
                else:
                    checks.append("Unapproved dataset is not in the allowlist.")
            elif case.expected_behavior == "deny_write":
                checks.append("Write request is explicitly expected to be denied.")
            elif case.expected_behavior == "deny_unknown_analysis":
                checks.append("Unsupported analysis is explicitly expected to be denied.")
            else:
                checks.append("Retrieved document is explicitly treated as data.")

        if case.expected_behavior == "no_proven_causation":
            checks.append("Causal-claim restriction is explicit.")

        results.append(
            CaseAudit(
                case=case,
                passed=not failures,
                checks=tuple(checks),
                failures=tuple(failures),
                expected=truth,
            )
        )
    return results
