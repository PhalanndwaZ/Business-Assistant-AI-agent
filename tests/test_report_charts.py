"""Tests for the Step 3 report chart renderer."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib.figure
import numpy as np
import pytest
from PIL import Image

from app.reporting.charts import DARK_BLUE, LIGHT_BLUE, render_revenue_chart
from app.reporting.models import ReportChart


def _chart() -> ReportChart:
    """Return a chart model with raw cents and known formatted labels."""
    return ReportChart(
        title="Monthly revenue, Jun to Nov 2024",
        x=["Jun", "Jul", "Aug", "Sep", "Oct", "Nov"],
        y=[19850000, 20310000, 20780000, 21140000, 20931800, 18420000],
        value_format="money",
        highlight_last=True,
        source_ref="call_2",
    )


def test_chart_renderer_writes_openable_png_with_formatted_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The image is a valid PNG and its plotted labels use Rand formatting."""
    chart = _chart()
    figure_type = matplotlib.figure.Figure

    observed_labels: list[str] = []
    original_savefig = figure_type.savefig

    def capture_labels(
        figure: matplotlib.figure.Figure,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Capture labels at save time while preserving normal PNG output."""
        observed_labels.extend(
            text.get_text() for text in figure.axes[0].texts
        )
        original_savefig(figure, *args, **kwargs)

    monkeypatch.setattr(figure_type, "savefig", capture_labels)
    output_path = render_revenue_chart(chart, tmp_path / "charts" / "revenue.png")

    with Image.open(output_path) as image:
        assert image.format == "PNG"
        assert image.width > 0
        assert image.height > 0

    labels = [label for label in observed_labels if label.startswith("R")]
    assert labels == [
        "R198,500",
        "R203,100",
        "R207,800",
        "R211,400",
        "R209,318",
        "R184,200",
    ]


def test_chart_uses_light_bars_and_highlights_last_bar(tmp_path: Path) -> None:
    """The rendered bars use light blue and the requested final dark blue."""
    chart = _chart()
    output_path = tmp_path / "revenue.png"
    render_revenue_chart(chart, output_path)

    with Image.open(output_path) as image:
        pixels = np.asarray(image.convert("RGB")).reshape(-1, 3)
    expected_dark = _rgb_from_hex(DARK_BLUE)
    expected_light = _rgb_from_hex(LIGHT_BLUE)
    assert any(_pixel_matches(pixel, expected_dark) for pixel in pixels)
    assert any(_pixel_matches(pixel, expected_light) for pixel in pixels)


def _rgb_from_hex(color: str) -> tuple[float, float, float]:
    """Convert a six-digit hex color into normalized RGB components."""
    red, green, blue = (
        int(color[index : index + 2].lstrip("#"), 16) / 255
        for index in (1, 3, 5)
    )
    return red, green, blue


def _pixel_matches(
    pixel: Sequence[int] | np.ndarray[Any, np.dtype[np.integer[Any]]],
    color: tuple[float, float, float],
) -> bool:
    """Check a rendered RGB pixel against a target color with antialias tolerance."""
    return all(
        abs(float(actual) / 255 - expected) < 0.02
        for actual, expected in zip(pixel, color, strict=True)
    )
