"""Tests for the editable Word report builder."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Mm

from app.reporting.builder import build_report_document
from app.reporting.charts import render_revenue_chart
from app.reporting.models import ReportObject


def _render_chart(report: ReportObject, output_path: Path) -> Path:
    """Render a chart after asserting the report fixture includes one."""
    assert report.chart is not None
    return render_revenue_chart(report.chart, output_path)


@pytest.fixture
def report() -> ReportObject:
    """Provide a small validated report based on the supplied sales sample."""
    return ReportObject.model_validate(
        {
            "title": "Monthly Sales Report",
            "period_label": "November 2024",
            "as_of_date": date(2024, 11, 30),
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
                "November revenue was R184,200, down 12.0% from October."
            ],
            "chart": {
                "title": "Monthly revenue, Jun to Nov 2024",
                "x": ["Oct", "Nov"],
                "y": [20931800, 18420000],
                "value_format": "money",
                "highlight_last": True,
                "source_ref": "call_2",
            },
            "tables": [
                {
                    "title": "Top products in November",
                    "columns": ["#", "Product", "Revenue", "Share"],
                    "formats": ["integer", "text", "money", "percent"],
                    "rows": [
                        [1, "Oak Dining Table", 3140000, 17.0],
                        [2, "Lounge Chair", 2870000, 15.6],
                    ],
                    "source_ref": "call_4",
                }
            ],
            "findings": [
                {
                    "finding": "Revenue fell 12.0% in November.",
                    "evidence": "October R209,318 to November R184,200.",
                    "action": "Check stock and delivery records.",
                    "caveat": "One month of data does not prove cause.",
                    "source_refs": ["call_3"],
                },
                {
                    "finding": "Five products make up 66.3% of revenue.",
                    "evidence": "The top five total R122,100 of R184,200.",
                    "action": "Confirm stock levels for those products.",
                    "caveat": "Completed orders only.",
                    "source_refs": ["call_4"],
                },
            ],
            "notes": ["Revenue uses completed orders only."],
        }
    )


def test_builder_creates_editable_report_with_required_structure(
    tmp_path: Path,
    report: ReportObject,
) -> None:
    """The DOCX contains the required section order, values, and editable tables."""
    chart_path = _render_chart(report, tmp_path / "chart.png")
    output_path = build_report_document(
        report,
        tmp_path / "monthly-sales.docx",
        chart_path=chart_path,
        source_labels={"call_2": "Revenue analysis"},
    )

    document = Document(str(output_path))
    headings = [
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.style is not None and paragraph.style.name == "Heading 1"
    ]
    assert document.paragraphs[0].text == "Monthly Sales Report"
    assert headings == [
        "Summary",
        "Revenue trend",
        "Top products in November",
        "Findings and recommended actions",
        "Sources and notes",
    ]
    assert len(document.tables) == 3
    assert "R184,200" in document.tables[0].cell(0, 0).text
    assert "-12.0%" in document.tables[0].cell(0, 1).text
    assert "R31,400" in document.tables[1].cell(1, 2).text
    assert document.tables[1].cell(1, 0).paragraphs[0].alignment == (
        WD_ALIGN_PARAGRAPH.RIGHT
    )
    assert document.tables[2].cell(1, 0).text == (
        "Revenue fell 12.0% in November."
    )
    assert document.tables[2].cell(1, 1).text == (
        "October R209,318 to November R184,200."
    )

    findings_heading = next(
        paragraph
        for paragraph in document.paragraphs
        if paragraph.text == "Findings and recommended actions"
    )
    assert findings_heading.paragraph_format.page_break_before
    assert len(document.inline_shapes) == 1
    assert document.inline_shapes[0]._inline.docPr.get("descr") == (
        "Monthly revenue, Jun to Nov 2024"
    )
    assert any(
        paragraph.style is not None
        and paragraph.style.name == "List Bullet"
        and paragraph.text == "Revenue analysis"
        for paragraph in document.paragraphs
    )


def test_builder_applies_page_layout_table_formatting_and_page_fields(
    tmp_path: Path,
    report: ReportObject,
) -> None:
    """The DOCX uses A4, fixed-width tables, cell shading, and page fields."""
    chart_path = _render_chart(report, tmp_path / "chart.png")
    output_path = build_report_document(
        report,
        tmp_path / "monthly-sales.docx",
        chart_path=chart_path,
    )
    document = Document(str(output_path))

    section = document.sections[0]
    assert section.page_width is not None
    assert section.page_height is not None
    assert abs(section.page_width - Mm(210)) <= 635
    assert abs(section.page_height - Mm(297)) <= 635
    assert section.left_margin == Inches(1)
    assert section.right_margin == Inches(1)

    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for table in document.tables:
        assert not table.autofit
        assert all(cell.width is not None for row in table.rows for cell in row.cells)
        grid_widths = [
            int(grid_column.get(f"{ns}w"))
            for grid_column in table._tbl.tblGrid.gridCol_lst
        ]
        assert all(width > 0 for width in grid_widths)
        table_width = table._tbl.tblPr.find(f"{ns}tblW")
        assert table_width is not None
        assert int(table_width.get(f"{ns}w")) == sum(grid_widths)

    header_properties = document.tables[1].cell(0, 0)._tc.get_or_add_tcPr()
    tile_properties = document.tables[0].cell(0, 0)._tc.get_or_add_tcPr()
    header_shading = header_properties.find(f"{ns}shd")
    tile_shading = tile_properties.find(f"{ns}shd")
    assert header_shading is not None
    assert tile_shading is not None
    assert header_shading.get(f"{ns}fill") == "1F3A5F"
    assert tile_shading.get(f"{ns}fill") == "EEF2F7"
    header_repeat = document.tables[2].rows[0]._tr.get_or_add_trPr().find(
        f"{ns}tblHeader"
    )
    assert header_repeat is not None
    findings_rows = document.tables[2].rows[1:]
    assert all(
        row._tr.get_or_add_trPr().find(
            f"{ns}cantSplit"
        )
        is not None
        for row in findings_rows
    )

    footer_xml = document.sections[0].footer._element.xml
    assert "PAGE" in footer_xml
    assert "NUMPAGES" in footer_xml
    assert "Sample report. All figures are illustrative." in footer_xml


def test_builder_requires_chart_image_when_report_has_chart(
    tmp_path: Path,
    report: ReportObject,
) -> None:
    """A chart-bearing report cannot silently omit its chart."""
    with pytest.raises(ValueError, match="chart image path is required"):
        build_report_document(report, tmp_path / "monthly-sales.docx")
    assert not (tmp_path / "monthly-sales.docx").exists()
