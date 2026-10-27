"""Tests for the Step 4 report evidence validator."""

from __future__ import annotations

from typing import Any

from app.reporting.models import ReportObject
from app.reporting.validate import validate_report_evidence
from app.state import ToolResult


def _report() -> ReportObject:
    """Create a Rand-formatted report grounded in synthetic tool-call results."""
    return ReportObject.model_validate(
        {
            "title": "Monthly Sales Report",
            "period_label": "November 2024",
            "as_of_date": "2024-11-30",
            "key_figures": [
                {
                    "label": "Revenue, Nov 2024",
                    "value": 18420000,
                    "format": "money",
                    "source_ref": "call_1",
                },
                {
                    "label": "Change vs October",
                    "value": -12.0,
                    "format": "percent",
                    "source_ref": "call_2",
                },
                {
                    "label": "Top product",
                    "value": "Oak Dining Table",
                    "format": "text",
                    "source_ref": "call_3",
                },
            ],
            "summary": [
                "Revenue for November 2024 was R184,200, down 12.0% from October."
            ],
            "chart": {
                "title": "Monthly revenue, Jun to Nov 2024",
                "x": ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov"],
                "y": [19850000, 20310000, 20780000, 21140000, 20931800, 18420000],
                "value_format": "money",
                "highlight_last": True,
                "source_ref": "call_1",
            },
            "tables": [
                {
                    "title": "Top products in November",
                    "columns": ["#", "Product", "Revenue", "Share"],
                    "formats": ["integer", "text", "money", "percent"],
                    "rows": [
                        [1, "Oak Dining Table", 3140000, 17.0],
                    ],
                    "source_ref": "call_3",
                }
            ],
            "findings": [
                {
                    "finding": "Revenue fell 12.0% in November.",
                    "evidence": "October R209,318 to November R184,200, down R25,118.",
                    "action": "Check stock and delivery records.",
                    "caveat": "The report mentions supply delays but does not prove cause.",
                    "source_refs": ["call_2", "call_4"],
                },
                {
                    "finding": "Five products make up 66.3% of November revenue.",
                    "evidence": "Top five total R122,100 of R184,200.",
                    "action": "Confirm stock levels for the five products.",
                    "caveat": "Completed orders only; one month of data.",
                    "source_refs": ["call_3"],
                },
            ],
            "notes": [
                "Revenue means quantity multiplied by unit price on completed orders."
            ],
        }
    )


def _tool_result(
    tool_name: str,
    result: dict[str, Any],
    *,
    success: bool = True,
) -> ToolResult:
    """Create a tool-result fixture for one report source reference."""
    return {
        "tool_name": tool_name,
        "arguments": {},
        "result": result,
        "success": success,
    }


def _sources() -> dict[str, ToolResult]:
    """Return report analysis and document evidence keyed by source reference."""
    return {
        "call_1": _tool_result(
            "run_analysis",
            {
                "analysis": "revenue_by_period",
                "data": [
                    {"period": "2024-06", "revenue_cents": 19850000},
                    {"period": "2024-07", "revenue_cents": 20310000},
                    {"period": "2024-08", "revenue_cents": 20780000},
                    {"period": "2024-09", "revenue_cents": 21140000},
                    {"period": "2024-10", "revenue_cents": 20931800},
                    {"period": "2024-11", "revenue_cents": 18420000},
                ],
            },
        ),
        "call_2": _tool_result(
            "run_analysis",
            {
                "analysis": "period_change",
                "data": [
                    {
                        "metric": "revenue",
                        "previous_value": 20931800,
                        "current_value": 18420000,
                        "absolute_change": -2511800,
                        "percent_change": -12.0,
                    }
                ],
            },
        ),
        "call_3": _tool_result(
            "run_analysis",
            {
                "analysis": "revenue_by_product",
                "data": [
                    {
                        "product_name": "Oak Dining Table",
                        "revenue_cents": 3140000,
                        "share_percent": 17.0,
                        "top_product_count": 5,
                        "top_five_share_percent": 66.3,
                        "top_five_revenue_cents": 12210000,
                    }
                ],
                "totals": {"revenue_cents": 18420000},
            },
        ),
        "call_4": _tool_result(
            "search_documents",
            {
                "results": [
                    {
                        "document_name": "management_report_2024-11.md",
                        "text": "The management report mentions supply delays.",
                    }
                ]
            },
        ),
    }


def test_valid_report_numbers_match_cited_tool_results() -> None:
    """The sample-style report passes with values and sources from tool output."""
    assert validate_report_evidence(_report(), _sources()) == []


def test_altered_key_figure_is_rejected_and_names_the_claim() -> None:
    """A changed figure cannot pass merely because similar evidence exists."""
    report = _report()
    report.key_figures[0].value = 19900000

    issues = validate_report_evidence(report, _sources())

    assert len(issues) == 1
    assert "key_figures[0]" in issues[0]
    assert "199,000" in issues[0]
    assert "Compared against:" in issues[0]


def test_unknown_source_reference_is_rejected() -> None:
    """A report cannot cite a source call absent from the supplied state."""
    report = _report()
    report.key_figures[0].source_ref = "missing_call"

    issues = validate_report_evidence(report, _sources())

    assert any("unknown tool call 'missing_call'" in issue for issue in issues)


def test_failed_source_reference_is_rejected() -> None:
    """An unsuccessful MCP call cannot be used as report evidence."""
    report = _report()
    sources = _sources()
    failed_source = sources["call_1"]
    failed_source["success"] = False

    issues = validate_report_evidence(report, sources)

    assert any("unsuccessful tool call 'call_1'" in issue for issue in issues)


def test_report_years_and_table_row_numbers_are_ignored() -> None:
    """Report labels and display row indices are not treated as data claims."""
    report = _report()
    report.tables[0].rows[0][0] = 99

    assert validate_report_evidence(report, _sources()) == []
