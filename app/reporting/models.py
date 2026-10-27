"""Validated data models for editable monthly sales reports."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

ReportFormat = Literal["money", "percent", "integer", "text"]
NumericFormat = Literal["money", "percent", "integer"]
ReportValue = StrictInt | StrictFloat | StrictStr
ReportNumber = StrictInt | StrictFloat
NonEmptyText = Annotated[StrictStr, Field(min_length=1)]


class ReportModel(BaseModel):
    """Forbid fields not explicitly defined by the report specification."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class KeyFigure(ReportModel):
    """One raw value, display format, label, and producing tool call."""

    label: NonEmptyText
    value: ReportValue
    format: ReportFormat
    source_ref: NonEmptyText

    @model_validator(mode="after")
    def validate_value_matches_format(self) -> KeyFigure:
        """Require text values for text format and numbers for numeric formats."""
        if self.format == "text" and not isinstance(self.value, str):
            raise ValueError("text figures must have a string value.")
        if self.format != "text" and isinstance(self.value, str):
            raise ValueError(f"{self.format} figures must have a numeric value.")
        if self.format == "integer" and isinstance(self.value, float):
            if not self.value.is_integer():
                raise ValueError("integer figures must use whole-number values.")
        return self


class ReportChart(ReportModel):
    """Revenue chart values kept raw until rendering."""

    title: NonEmptyText
    x: list[NonEmptyText] = Field(min_length=1)
    y: list[ReportNumber] = Field(min_length=1)
    value_format: NumericFormat
    highlight_last: bool
    source_ref: NonEmptyText

    @model_validator(mode="after")
    def validate_series_lengths(self) -> ReportChart:
        """Require one raw value for each chart label."""
        if len(self.x) != len(self.y):
            raise ValueError("chart x and y must contain the same number of items.")
        return self


class ReportTable(ReportModel):
    """A titled table with one format per column and rectangular rows."""

    title: NonEmptyText
    columns: list[NonEmptyText] = Field(min_length=1)
    formats: list[ReportFormat] = Field(min_length=1)
    rows: list[list[ReportValue]]
    source_ref: NonEmptyText

    @model_validator(mode="after")
    def validate_table_shape(self) -> ReportTable:
        """Require column formats and every row to match the column count."""
        if len(self.columns) != len(self.formats):
            raise ValueError("table formats must match the number of columns.")
        for row_number, row in enumerate(self.rows, start=1):
            if len(row) != len(self.columns):
                raise ValueError(
                    f"table row {row_number} must match the number of columns."
                )
            for value, value_format in zip(row, self.formats, strict=True):
                if value_format == "text" and not isinstance(value, str):
                    raise ValueError("text table cells must have string values.")
                if value_format != "text" and isinstance(value, str):
                    raise ValueError(
                        f"{value_format} table cells must have numeric values."
                    )
                if value_format == "integer" and isinstance(value, float):
                    if not value.is_integer():
                        raise ValueError(
                            "integer table cells must use whole-number values."
                        )
        return self


class Finding(ReportModel):
    """A finding with supporting evidence, action, caveat, and source calls."""

    finding: NonEmptyText
    evidence: NonEmptyText
    action: NonEmptyText
    caveat: NonEmptyText
    source_refs: list[NonEmptyText] = Field(min_length=1)


class ReportObject(ReportModel):
    """Complete report content, validated before evidence checks or rendering."""

    title: NonEmptyText
    period_label: NonEmptyText
    as_of_date: date
    key_figures: list[KeyFigure] = Field(min_length=3, max_length=5)
    summary: list[NonEmptyText] = Field(min_length=1, max_length=2)
    chart: ReportChart | None = None
    tables: list[ReportTable] = Field(default_factory=list, max_length=2)
    findings: list[Finding] = Field(min_length=2, max_length=5)
    notes: list[NonEmptyText] = Field(default_factory=list)
