"""Validate report numbers against the producing MCP tool results."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from app.reporting.formatting import format_value
from app.reporting.models import ReportObject
from app.services.evidence_check import check_numeric_evidence
from app.state import ToolResult

YEAR_PATTERN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
ISO_DATE_PATTERN = re.compile(
    r"(?<!\d)(?:19|20)\d{2}[-/\u2010-\u2015]\d{1,2}"
    r"(?:[-/\u2010-\u2015]\d{1,2})?(?!\d)"
)


def validate_report_evidence(
    report: ReportObject,
    tool_results_by_ref: Mapping[str, ToolResult],
) -> list[str]:
    """Return evidence issues for every numeric claim in a report object."""
    issues: list[str] = []
    successful_results = [
        result for result in tool_results_by_ref.values() if result["success"]
    ]

    def check_section(
        section: str,
        content: str,
        source_refs: Sequence[str] | None = None,
    ) -> None:
        """Check one report section against its cited or all successful results."""
        selected_results = successful_results
        if source_refs is not None:
            selected_results = []
            for source_ref in source_refs:
                source_result = tool_results_by_ref.get(source_ref)
                if source_result is None:
                    issues.append(
                        f"{section} references unknown tool call {source_ref!r}."
                    )
                elif not source_result["success"]:
                    issues.append(
                        f"{section} references unsuccessful tool call "
                        f"{source_ref!r}."
                    )
                else:
                    selected_results.append(source_result)

        normalized_content = _without_report_dates(content)
        valid, evidence_issues = check_numeric_evidence(
            normalized_content,
            selected_results,
        )
        if not valid:
            issues.extend(f"{section}: {issue}" for issue in evidence_issues)

    for index, figure in enumerate(report.key_figures, start=1):
        if figure.format == "text":
            value = str(figure.value)
        else:
            value = format_value(figure.value, figure.format)
        check_section(
            f"key_figures[{index - 1}] {figure.label!r}",
            value,
            [figure.source_ref],
        )

    for index, paragraph in enumerate(report.summary, start=1):
        check_section(f"summary[{index}]", paragraph)

    if report.chart is not None:
        chart_content = " ".join(
            [
                report.chart.title,
                *report.chart.x,
                *(
                    f"Revenue {format_value(value, report.chart.value_format)}"
                    for value in report.chart.y
                ),
            ]
        )
        check_section(
            "chart",
            chart_content,
            [report.chart.source_ref],
        )

    for table_index, table in enumerate(report.tables):
        for row_index, row in enumerate(table.rows):
            row_parts: list[str] = []
            for column_index, (value, value_format) in enumerate(
                zip(row, table.formats, strict=True)
            ):
                if column_index == 0 and table.columns[column_index].strip() == "#":
                    continue
                if value_format == "text":
                    row_parts.append(str(value))
                else:
                    row_parts.append(
                        f"{table.columns[column_index]} "
                        f"{format_value(value, value_format)}"
                    )
            check_section(
                f"tables[{table_index}].rows[{row_index}]",
                " ".join(row_parts),
                [table.source_ref],
            )

    for index, finding in enumerate(report.findings):
        check_section(
            f"findings[{index}]",
            " ".join(
                (
                    finding.finding,
                    finding.evidence,
                    finding.action,
                    finding.caveat,
                )
            ),
            finding.source_refs,
        )

    for index, note in enumerate(report.notes, start=1):
        check_section(f"notes[{index}]", note)

    return issues


def _without_report_dates(content: str) -> str:
    """Remove year-month dates, full dates, and years before numeric checks."""
    without_iso_dates = ISO_DATE_PATTERN.sub(" ", content)
    return YEAR_PATTERN.sub(" ", without_iso_dates)
