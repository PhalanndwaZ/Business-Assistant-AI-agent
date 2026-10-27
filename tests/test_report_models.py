"""Tests for the Step 1 report-object contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.reporting.models import ReportObject


def _sample_report() -> dict[str, object]:
    """Return a compact report object based on the supplied sample report."""
    return {
        "title": "Monthly Sales Report",
        "period_label": "November 2024",
        "as_of_date": "2024-11-30",
        "key_figures": [
            {
                "label": "Revenue, Nov 2024",
                "value": 18420000,
                "format": "money",
                "source_ref": "call_2",
            },
            {
                "label": "Change vs October",
                "value": -12.0,
                "format": "percent",
                "source_ref": "call_3",
            },
            {
                "label": "Top product",
                "value": "Oak Dining Table",
                "format": "text",
                "source_ref": "call_4",
            },
        ],
        "summary": [
            "November revenue was R184,200, down 12.0% from October.",
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
                "rows": [[1, "Oak Dining Table", 3140000, 17.0]],
                "source_ref": "call_4",
            }
        ],
        "findings": [
            {
                "finding": "Revenue fell 12.0% in November.",
                "evidence": "October R209,318 to November R184,200, down R25,118.",
                "action": "Check stock and delivery records for November.",
                "caveat": "The report mentions supply delays but does not prove cause.",
                "source_refs": ["call_3"],
            },
            {
                "finding": "Five products make up 66.3% of November revenue.",
                "evidence": "Top five total R122,100 of R184,200.",
                "action": "Confirm stock levels for the five products.",
                "caveat": "Completed orders only; one month of data.",
                "source_refs": ["call_4"],
            },
        ],
        "notes": ["Revenue is quantity multiplied by unit price on completed orders."],
    }


def test_sample_report_object_loads() -> None:
    """The supplied sample-report structure passes model validation."""
    report = ReportObject.model_validate(_sample_report())

    assert report.title == "Monthly Sales Report"
    assert report.as_of_date.isoformat() == "2024-11-30"
    assert report.key_figures[0].value == 18420000
    assert report.chart is not None
    assert len(report.findings) == 2


def test_missing_finding_caveat_is_rejected() -> None:
    """Every finding must include its caveat."""
    report_data = _sample_report()
    findings = report_data["findings"]
    assert isinstance(findings, list)
    del findings[0]["caveat"]

    with pytest.raises(ValidationError, match="caveat"):
        ReportObject.model_validate(report_data)


def test_too_many_findings_are_rejected() -> None:
    """The report is limited to five findings."""
    report_data = _sample_report()
    findings = report_data["findings"]
    assert isinstance(findings, list)
    findings.extend([findings[0], findings[0], findings[0], findings[0]])

    with pytest.raises(ValidationError, match="at most 5"):
        ReportObject.model_validate(report_data)


def test_unknown_key_figure_format_is_rejected() -> None:
    """Formats outside the report specification are rejected."""
    report_data = _sample_report()
    figures = report_data["key_figures"]
    assert isinstance(figures, list)
    figures[0]["format"] = "currency"

    with pytest.raises(ValidationError, match="Input should be"):
        ReportObject.model_validate(report_data)
