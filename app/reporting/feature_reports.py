"""Convert segment and portfolio analyses into evidence-backed report objects."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.reporting.models import (
    Finding,
    KeyFigure,
    ReportChart,
    ReportObject,
    ReportTable,
    ReportContextItem,
)

MAX_CONTEXT_QUOTE = 280


def attach_report_context(
    report_data: dict[str, Any],
    chunks: list[dict[str, Any]],
    max_items: int = 3,
) -> dict[str, Any]:
    """Add relevant retrieved passages to report data without creating figures."""
    context: list[dict[str, Any]] = []
    for chunk in chunks[:max_items]:
        text = str(chunk.get("text", "")).strip()
        if not text:
            continue
        origin = chunk.get("origin")
        if origin not in {"company", "uploaded"}:
            continue
        source_label = (
            "your document" if origin == "uploaded" else "company document"
        )
        context.append(
            ReportContextItem(
                quote=text[:MAX_CONTEXT_QUOTE],
                document_name=str(chunk.get("document_name") or chunk.get("source") or "Document"),
                origin=origin,
                page_number=chunk.get("page_number"),
                source_label=source_label,
            ).model_dump()
        )
    if context:
        report_data["context"] = context
    return report_data


def feature_analysis_report(
    analysis_name: str,
    result: dict[str, Any],
    source_ref: str,
) -> ReportObject:
    """Convert a named segment or portfolio analysis to a report object."""
    converters = {
        "product_portfolio": product_portfolio_report,
        "customer_segments": customer_segments_report,
    }
    try:
        converter = converters[analysis_name]
    except KeyError as exc:
        raise ValueError(f"No report converter exists for analysis {analysis_name!r}.") from exc
    return converter(result, source_ref)


def product_portfolio_report(
    result: dict[str, Any],
    source_ref: str,
) -> ReportObject:
    """Build a product portfolio report from one validated analysis result."""
    portfolio = result["portfolio"]
    window = result["window"]
    top_items = result["items"][:10]
    observations = result["observations"] or ["No configured portfolio observation applied."]
    return ReportObject(
        title="Product Portfolio Analysis",
        period_label=f"{window['start']} to {window['end']}",
        as_of_date=date.fromisoformat(result["as_of"]),
        key_figures=[
            KeyFigure(label="Window revenue", value=portfolio["revenue_cents"], format="money", source_ref=source_ref),
            KeyFigure(label="Top 3 share", value=portfolio["top_3_share"] * 100, format="percent", source_ref=source_ref),
            KeyFigure(label="HHI concentration", value=portfolio["hhi"], format="percent", source_ref=source_ref),
        ],
        summary=observations[:2],
        chart=ReportChart(
            title="Revenue by product",
            x=[str(item.get("product_id", item.get("category"))) for item in top_items],
            y=[item["revenue_cents"] for item in top_items],
            value_format="money",
            highlight_last=False,
            source_ref=source_ref,
        ),
        tables=[
            ReportTable(
                title="Product revenue and portfolio class",
                columns=["Product", "Revenue", "Share", "Class"],
                formats=["text", "money", "percent", "text"],
                rows=[
                    [str(item["product_id"]), item["revenue_cents"], round(item["share"] * 100, 2), item["class"]]
                    for item in top_items
                ],
                source_ref=source_ref,
            )
        ],
        findings=[
            Finding(
                finding=observations[0],
                evidence=f"{portfolio['product_count']} products contributed the reported revenue.",
                action="Review the configured movers and dormant products before the next period closes.",
                caveat="Comparison changes may be partial when the available history is short.",
                source_refs=[source_ref],
            ),
            Finding(
                finding=f"Portfolio concentration was {portfolio['hhi']:.4f} by HHI.",
                evidence=f"The top three products supplied {portfolio['top_3_share'] * 100:.1f}% of window revenue.",
                action="Monitor concentration when planning inventory and sales targets.",
                caveat="HHI and share results depend on the products with sales in this window.",
                source_refs=[source_ref],
            ),
        ],
        notes=["Only completed orders are included. Product classes use the configured revenue-share thresholds."],
    )


def customer_segments_report(
    result: dict[str, Any],
    source_ref: str,
) -> ReportObject:
    """Build a customer segment report from one validated analysis result."""
    window = result["window"]
    segments = result["segments"]
    revenue_total = sum(segment["revenue_cents"] for segment in segments)
    at_risk = next(
        (segment for segment in segments if segment["name"] == "At risk"),
        {"customers": 0, "revenue_cents": 0},
    )
    revenue_at_stake = result.get(
        "revenue_at_stake_cents",
        sum(
            segment["revenue_cents"]
            for segment in segments
            if segment["name"] in {"At risk", "Lost"}
        ),
    )
    return ReportObject(
        title="Customer Segments Analysis",
        period_label=f"{window['start']} to {window['end']}",
        as_of_date=date.fromisoformat(result["as_of"]),
        key_figures=[
            KeyFigure(label="Customers counted", value=result["customers_counted"], format="integer", source_ref=source_ref),
            KeyFigure(label="Segment revenue", value=revenue_total, format="money", source_ref=source_ref),
            KeyFigure(label="At-risk revenue", value=at_risk["revenue_cents"], format="money", source_ref=source_ref),
        ],
        summary=[
            f"{at_risk['customers']} customers are classified as At risk.",
            "The segment labels describe buying patterns, not predictions of customer departure.",
        ],
        chart=ReportChart(
            title="Revenue by customer segment",
            x=[segment["name"] for segment in segments],
            y=[segment["revenue_cents"] for segment in segments],
            value_format="money",
            highlight_last=False,
            source_ref=source_ref,
        ),
        tables=[
            ReportTable(
                title="Customer segment summary",
                columns=["Segment", "Customers", "Revenue", "Suggested next step"],
                formats=["text", "integer", "money", "text"],
                rows=[
                    [segment["name"], segment["customers"], segment["revenue_cents"], segment["suggested_next_step"]]
                    for segment in segments
                ],
                source_ref=source_ref,
            )
        ],
        findings=[
            Finding(
                finding=f"At risk customers hold {at_risk['revenue_cents']} cents of window revenue.",
                evidence=f"{at_risk['customers']} customers meet the configured quiet-but-frequent pattern.",
                action=at_risk["suggested_next_step"],
                caveat="A descriptive segment label does not predict whether a customer will leave.",
                source_refs=[source_ref],
            ),
            Finding(
                finding=f"Segments account for {result['customers_counted']} customers.",
                evidence=f"Revenue at stake across at-risk and lost customers is {revenue_at_stake} cents.",
                action=at_risk.get("suggested_next_step", "Review the configured segment actions."),
                caveat="Revenue at stake is descriptive and excludes customers outside those configured segments.",
                source_refs=[source_ref],
            ),
        ],
        notes=result["caveats"] + ["Suggested next steps come from segments.json and are not model-generated recommendations."],
    )
