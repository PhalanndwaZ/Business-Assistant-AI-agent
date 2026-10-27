"""Render editable-report revenue trend charts as PNG images."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from app.reporting.formatting import format_value
from app.reporting.models import ReportChart

LIGHT_BLUE = "#9BBCE0"
DARK_BLUE = "#1F3A5F"
GREY = "#666666"


def render_revenue_chart(chart: ReportChart, output_path: Path) -> Path:
    """Render a labeled revenue bar chart to a PNG at the requested path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    colors = [LIGHT_BLUE] * len(chart.y)
    if chart.highlight_last:
        colors[-1] = DARK_BLUE

    figure, axis = plt.subplots(figsize=(9, 3.6), constrained_layout=True)
    bars = axis.bar(chart.x, chart.y, color=colors, width=0.62)
    axis.set_title(chart.title, color=DARK_BLUE, loc="left", pad=16)
    axis.yaxis.set_visible(False)
    axis.grid(False)
    axis.tick_params(axis="x", colors=GREY, length=0, pad=8)
    axis.set_ylim(bottom=min(0, min(chart.y) * 0.92))
    for spine_name in ("top", "right", "left"):
        axis.spines[spine_name].set_visible(False)
    axis.spines["bottom"].set_color("#D0D7E2")

    for bar, value in zip(bars, chart.y, strict=True):
        axis.annotate(
            format_value(value, chart.value_format),
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
            color=GREY,
            clip_on=False,
        )

    figure.savefig(output_path, format="png", dpi=180, facecolor="white")
    plt.close(figure)
    return output_path
