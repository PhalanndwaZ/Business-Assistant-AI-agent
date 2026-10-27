"""MCP tools for read-only business data queries and Pandas analyses."""

from __future__ import annotations

import logging
import json
import os
import re
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from app.analysis.analyses import run_analysis as dispatch_analysis
from app.data_access.json_loader import JsonDataStore
from app.data_access.schema import (
    AVAILABLE_ANALYSES,
    ANALYSIS_PARAMETERS,
    BUSINESS_GLOSSARY,
    DATASETS,
    RELATIONSHIPS,
)
from app.config import PROJECT_ROOT
from app.reporting.builder import build_report_document
from app.reporting.charts import render_revenue_chart
from app.reporting.models import ReportObject
from app.reporting.validate import validate_report_evidence
from app.state import ToolResult

LOGGER = logging.getLogger(__name__)
MAX_QUERY_LIMIT = 100
VALID_OPERATORS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"})
REPORTS_DIR = PROJECT_ROOT / "reports"
server = FastMCP("business-data")
_store: JsonDataStore | None = None


def get_store() -> JsonDataStore:
    """Return the process-wide, once-loaded JSON data store."""
    global _store
    if _store is None:
        data_dir = Path(os.getenv("DATA_DIR", "data/sample_data"))
        if not data_dir.is_absolute():
            data_dir = PROJECT_ROOT / data_dir
        _store = JsonDataStore(data_dir.resolve())
    return _store


def _get_data_schema() -> dict[str, Any]:
    """Describe allowed data, glossary, analyses, and the configured anchor date."""
    return {
        "datasets": {
            name: {
                "fields": {
                    field_name: field_type.__name__
                    for field_name, field_type in schema.fields.items()
                },
                "primary_key": schema.primary_key,
            }
            for name, schema in DATASETS.items()
        },
        "relationships": [
            {"from": source, "to": target} for source, target in RELATIONSHIPS
        ],
        "glossary": BUSINESS_GLOSSARY,
        "available_analyses": list(AVAILABLE_ANALYSES),
        "analysis_parameters": ANALYSIS_PARAMETERS,
        "as_of_date": os.getenv("AS_OF_DATE", date(2025, 1, 15).isoformat()),
    }


def _apply_filter(
    frame: pd.DataFrame,
    field: str,
    operator: str,
    value: Any,
) -> pd.DataFrame:
    """Apply one validated filter expression to an in-memory dataset."""
    if operator not in VALID_OPERATORS:
        raise ValueError(f"Unsupported filter operator '{operator}'.")
    if operator in {"eq", "ne"}:
        mask = frame[field].eq(value) if operator == "eq" else frame[field].ne(value)
    elif operator == "gt":
        mask = frame[field] > value
    elif operator == "gte":
        mask = frame[field] >= value
    elif operator == "lt":
        mask = frame[field] < value
    elif operator == "lte":
        mask = frame[field] <= value
    elif operator == "in":
        if not isinstance(value, list):
            raise ValueError("The 'in' filter requires a list value.")
        mask = frame[field].isin(value)
    else:
        if not isinstance(value, str):
            raise ValueError("The 'contains' filter requires a string value.")
        mask = frame[field].astype("string").str.contains(
            value, case=False, regex=False, na=False
        )
    return frame.loc[mask]


def _query_business_data(
    dataset: str,
    fields: list[str],
    filters: list[dict[str, Any]] | None = None,
    date_range: dict[str, str] | None = None,
    sort: dict[str, str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Filter an allowlisted dataset and return a capped result with count."""
    started_at = time.monotonic()
    if dataset not in DATASETS:
        raise ValueError(f"Unknown dataset '{dataset}'.")
    if isinstance(limit, bool) or not 1 <= limit <= MAX_QUERY_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_QUERY_LIMIT}.")
    allowed_fields = set(DATASETS[dataset].fields)
    if not fields or set(fields) - allowed_fields:
        invalid_fields = sorted(set(fields) - allowed_fields)
        raise ValueError(
            f"fields must contain approved fields; invalid fields: {invalid_fields}."
        )
    frame = get_store().get_frame(dataset)

    if date_range is not None:
        if dataset not in {"orders", "order_items"}:
            raise ValueError(
                "date_range is supported only for orders and order_items."
            )
        if set(date_range) != {"start", "end"}:
            raise ValueError("date_range must contain exactly start and end.")
        try:
            start_date = pd.Timestamp(date.fromisoformat(date_range["start"]))
            end_date = pd.Timestamp(date.fromisoformat(date_range["end"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("date_range values must be ISO 8601 dates.") from exc
        if start_date > end_date:
            raise ValueError("date_range start must be on or before end.")
        if dataset == "orders":
            frame = frame.loc[frame["order_date"].between(start_date, end_date)]
        else:
            order_dates = get_store().get_frame("orders")[["order_id", "order_date"]]
            selected_ids = order_dates.loc[
                order_dates["order_date"].between(start_date, end_date), "order_id"
            ]
            frame = frame.loc[frame["order_id"].isin(selected_ids)]

    for filter_item in filters or []:
        if set(filter_item) != {"field", "operator", "value"}:
            raise ValueError("Each filter requires field, operator, and value.")
        field = filter_item["field"]
        if field not in allowed_fields:
            raise ValueError(f"Unknown field '{field}' for dataset '{dataset}'.")
        frame = _apply_filter(
            frame,
            field,
            filter_item["operator"],
            filter_item["value"],
        )

    if sort is not None:
        if set(sort) != {"field", "direction"}:
            raise ValueError("sort requires field and direction.")
        sort_field = sort["field"]
        direction = sort["direction"]
        if sort_field not in allowed_fields:
            raise ValueError(
                f"Unknown sort field '{sort_field}' for dataset '{dataset}'."
            )
        if direction not in {"asc", "desc"}:
            raise ValueError("sort direction must be 'asc' or 'desc'.")
        frame = frame.sort_values(sort_field, ascending=direction == "asc")

    total_matches = len(frame)
    selected_rows = frame.loc[:, fields].head(limit)
    rows = json.loads(selected_rows.to_json(orient="records", date_format="iso"))
    elapsed_ms = round((time.monotonic() - started_at) * 1000, 2)
    LOGGER.info(
        "tool=query_business_data duration_ms=%.2f dataset=%s rows=%d",
        elapsed_ms,
        dataset,
        min(total_matches, limit),
    )
    return {
        "dataset": dataset,
        "fields": fields,
        "total_matches": total_matches,
        "returned_rows": len(rows),
        "rows": rows,
    }


def _run_analysis(
    analysis_name: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Run one allowlisted deterministic analysis with its validated inputs."""
    started_at = time.monotonic()
    result = dispatch_analysis(get_store(), analysis_name, parameters)
    LOGGER.info(
        "tool=run_analysis duration_ms=%.2f analysis=%s result_rows=%d period=%s",
        (time.monotonic() - started_at) * 1000,
        analysis_name,
        len(result["data"]),
        result.get("period"),
    )
    return result


def _generate_report(
    report_data: dict[str, Any],
    tool_results_by_ref: dict[str, ToolResult] | None = None,
) -> dict[str, Any]:
    """Validate evidence and create a safely named editable Word report."""
    try:
        report = ReportObject.model_validate(report_data)
    except (ValidationError, TypeError, ValueError) as exc:
        return {"error": f"Invalid report object: {exc}"}

    if tool_results_by_ref is None:
        return {
            "error": (
                "Report evidence is unavailable. Run the required analyses first "
                "and cite their tool call IDs in source_ref."
            )
        }

    evidence_issues = validate_report_evidence(report, tool_results_by_ref)
    if evidence_issues:
        return {
            "error": "Report evidence validation failed:\n"
            + "\n".join(f"- {issue}" for issue in evidence_issues)
        }

    filename = _report_filename(report)
    output_path = REPORTS_DIR / filename
    source_labels = _report_source_labels(tool_results_by_ref)
    try:
        if report.chart is None:
            build_report_document(
                report,
                output_path,
                source_labels=source_labels,
                footer_note="Figures are based on cited analysis results",
            )
        else:
            with tempfile.TemporaryDirectory(prefix="business-report-") as temp_dir:
                chart_path = render_revenue_chart(
                    report.chart,
                    Path(temp_dir) / "revenue-chart.png",
                )
                build_report_document(
                    report,
                    output_path,
                    chart_path=chart_path,
                    source_labels=source_labels,
                    footer_note="Figures are based on cited analysis results",
                )
    except (OSError, RuntimeError, ValueError) as exc:
        output_path.unlink(missing_ok=True)
        LOGGER.exception("Report generation failed filename=%s", filename)
        return {"error": f"Report generation failed: {exc}"}

    return {"path": str(output_path), "warnings": []}


def _report_filename(report: ReportObject) -> str:
    """Generate a collision-resistant DOCX name from safe title and period slugs."""
    title = _safe_filename_part(report.title)
    period = _safe_filename_part(report.period_label)
    return (
        f"{title}-{period}-{uuid4().hex}.docx"
        if title and period
        else f"sales-report-{uuid4().hex}.docx"
    )


def _safe_filename_part(value: str) -> str:
    """Reduce untrusted report text to lowercase ASCII filename characters."""
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:50].strip("-")


def _report_source_labels(
    tool_results_by_ref: dict[str, ToolResult],
) -> dict[str, str]:
    """Describe report sources by analysis name without inventing provenance."""
    labels: dict[str, str] = {}
    for call_id, tool_result in tool_results_by_ref.items():
        result = tool_result.get("result")
        if tool_result.get("tool_name") == "run_analysis" and isinstance(result, dict):
            analysis_name = result.get("analysis")
            if isinstance(analysis_name, str) and analysis_name:
                labels[call_id] = analysis_name.replace("_", " ").title()
                continue
        if tool_result.get("tool_name") == "search_documents":
            labels[call_id] = "Document search"
        else:
            labels[call_id] = tool_result.get("tool_name", "Tool result")
    return labels


@server.tool()
def get_data_schema() -> dict[str, Any]:
    """Return approved datasets, their fields, glossary, analyses, and as-of date."""
    return _get_data_schema()


@server.tool()
def query_business_data(
    dataset: str,
    fields: list[str],
    filters: list[dict[str, Any]] | None = None,
    date_range: dict[str, str] | None = None,
    sort: dict[str, str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return capped rows and exact total_matches for the dataset and filters."""
    return _query_business_data(dataset, fields, filters, date_range, sort, limit)


@server.tool()
def run_analysis(
    analysis_name: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Run one named Pandas analysis with validated arguments."""
    return _run_analysis(analysis_name, parameters)


@server.tool()
def generate_report(
    report: dict[str, Any],
    tool_results_by_ref: dict[str, ToolResult] | None = None,
) -> dict[str, Any]:
    """Create a DOCX only when its figures validate against cited tool results."""
    return _generate_report(report, tool_results_by_ref)


def main() -> None:
    """Run the business-data MCP server over local stdio transport."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    get_store()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
