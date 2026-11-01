"""Tests for Step 5 feature report conversion."""

from pathlib import Path

from docx import Document

from app.reporting.builder import build_report_document
from app.reporting.feature_reports import (
    customer_segments_report,
    product_portfolio_report,
)
from app.reporting.charts import render_revenue_chart


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
