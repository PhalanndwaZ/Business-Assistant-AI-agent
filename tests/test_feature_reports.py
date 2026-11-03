"""Tests for Step 5 feature report conversion."""

from pathlib import Path

from docx import Document

from app.reporting.builder import build_report_document
from app.reporting.feature_reports import (
    customer_segments_report,
    product_portfolio_report,
)
from app.reporting.charts import render_revenue_chart
from app.reporting.validate import validate_report_evidence
from app.state import ToolResult


def test_feature_analysis_results_convert_to_report_objects() -> None:
    """Segment and portfolio analyses produce the existing report-model shape."""
    portfolio = {
        "as_of": "2024-12-31",
        "window": {"start": "2024-01-01", "end": "2024-12-31"},
        "portfolio": {"revenue_cents": 300, "top_3_share": 0.8, "hhi": 0.2, "product_count": 3},
        "items": [
            {"product_id": "P001", "revenue_cents": 200, "share": 0.67, "class": "A"},
            {"product_id": "P002", "revenue_cents": 100, "share": 0.33, "class": "B"},
        ],
        "observations": ["Configured concentration observation."],
        "caveats": [],
    }
    segments = {
        "as_of": "2025-01-15",
        "window": {"start": "2024-01-16", "end": "2025-01-15"},
        "customers_counted": 60,
        "segments": [
            {
                "name": "At risk",
                "customers": 5,
                "revenue_cents": 100,
                "suggested_next_step": "Contact the account.",
            }
        ],
        "caveats": [],
    }

    assert len(product_portfolio_report(portfolio, "call-portfolio").key_figures) >= 3
    assert len(customer_segments_report(segments, "call-segments").tables) == 1


def test_customer_segment_report_uses_supported_revenue_and_rand_format() -> None:
    """Segment report claims validate against exact source values and use Rand."""
    result = {
        "as_of": "2025-01-15",
        "window": {"start": "2024-01-16", "end": "2025-01-15"},
        "customers_counted": 60,
        "segments": [
            {
                "name": "Best customers",
                "customers": 17,
                "revenue_cents": 38_437_200,
                "suggested_next_step": "Recognize repeat purchases.",
            },
            {
                "name": "At risk",
                "customers": 8,
                "revenue_cents": 500_000,
                "suggested_next_step": "Review the accounts.",
            },
            {
                "name": "Lost",
                "customers": 5,
                "revenue_cents": 200_000,
                "suggested_next_step": "Review inactive accounts.",
            },
        ],
        "revenue_at_stake_cents": 700_000,
        "caveats": ["Segments describe patterns, not predictions."],
    }
    source_result: ToolResult = {
        "tool_name": "run_analysis",
        "arguments": {"analysis_name": "customer_segments"},
        "result": result,
        "success": True,
    }

    report = customer_segments_report(result, "segments-call")

    assert report.key_figures[1].label == "Best customers revenue"
    assert "R5,000" in report.findings[0].finding
    assert "R7,000" in report.findings[1].evidence
    assert validate_report_evidence(
        report,
        {"segments-call": source_result},
    ) == []


def test_feature_portfolio_report_opens_as_word_document(tmp_path: Path) -> None:
    """A feature report can be rendered by the existing Word builder."""
    result = {
        "as_of": "2024-12-31",
        "window": {"start": "2024-01-01", "end": "2024-12-31"},
        "portfolio": {"revenue_cents": 300, "top_3_share": 1.0, "hhi": 0.5, "product_count": 2},
        "items": [
            {"product_id": "P001", "revenue_cents": 200, "share": 0.67, "class": "A"},
            {"product_id": "P002", "revenue_cents": 100, "share": 0.33, "class": "B"},
        ],
        "observations": ["P001 leads reported product revenue."],
        "caveats": [],
    }
    report = product_portfolio_report(result, "call-portfolio")
    chart_path = render_revenue_chart(report.chart, tmp_path / "portfolio-chart.png")
    output_path = build_report_document(report, tmp_path / "portfolio.docx", chart_path=chart_path)

    assert output_path.is_file()
    assert Document(output_path).paragraphs
