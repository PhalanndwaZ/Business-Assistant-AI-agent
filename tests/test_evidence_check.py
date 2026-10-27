"""Tests for semantic number grounding in structured answers."""

from __future__ import annotations

from app.services.evidence_check import check_numeric_evidence
from app.state import ToolResult


def _result(
    data: dict[str, int | float],
    tool_name: str = "run_analysis",
) -> list[ToolResult]:
    """Create one successful tool result for evidence-check tests."""
    return [
        {
            "tool_name": tool_name,
            "arguments": {},
            "result": data,
            "success": True,
        }
    ]


def test_revenue_cents_can_be_formatted_as_dollars() -> None:
    """Integer cents support the exact dollar-formatted equivalent."""
    is_valid, issues = check_numeric_evidence(
        "Revenue was $50.00.",
        _result({"revenue_cents": 5000}),
    )

    assert is_valid is True
    assert issues == []


def test_order_count_cannot_support_revenue_in_cents() -> None:
    """A matching count value cannot be misrepresented as a money amount."""
    is_valid, issues = check_numeric_evidence(
        "Revenue was 50 cents.",
        _result({"order_count": 50, "revenue_cents": 5000}),
    )

    assert is_valid is False
    assert "50" in issues[0]


def test_unit_price_cannot_support_total_revenue_claim() -> None:
    """A matching unit price is not evidence for an aggregate revenue claim."""
    is_valid, issues = check_numeric_evidence(
        "Revenue was $50.00.",
        _result({"unit_price_cents": 5000}),
    )

    assert is_valid is False
    assert "50.00" in issues[0]


def test_revenue_cannot_support_cost_claim() -> None:
    """Revenue evidence cannot be relabeled as a cost figure."""
    is_valid, issues = check_numeric_evidence(
        "Cost was $50.00.",
        _result({"revenue_cents": 5000}),
    )

    assert is_valid is False
    assert "50.00" in issues[0]


def test_metric_context_is_scoped_to_each_number() -> None:
    """A nearby revenue claim cannot lend evidence to a separate cost claim."""
    is_valid, issues = check_numeric_evidence(
        "Revenue was $50.00, while cost was $50.00.",
        _result({"revenue_cents": 5000}),
    )

    assert is_valid is False
    assert len(issues) == 1


def test_count_cannot_support_percentage_claim() -> None:
    """A percentage claim requires evidence from a percentage field."""
    is_valid, issues = check_numeric_evidence(
        "Revenue changed by 5%.",
        _result({"order_count": 5, "percent_change": 12.5}),
    )

    assert is_valid is False
    assert "5%" in issues[0]


def test_numeric_failure_lists_compared_tool_evidence() -> None:
    """An evidence failure names both the unsupported claim and candidates."""
    is_valid, issues = check_numeric_evidence(
        "Revenue was 50 cents.",
        _result({"order_count": 50, "revenue_cents": 5000}),
    )

    assert is_valid is False
    assert "Number '50'" in issues[0]
    assert "Compared against:" in issues[0]
    assert "50 (count/count)" in issues[0]


def test_non_numeric_response_does_not_require_business_numeric_evidence() -> None:
    """Document-only and cannot-answer drafts may contain no numeric claims."""
    is_valid, issues = check_numeric_evidence(
        "I cannot answer from the available sources.",
        [],
    )

    assert is_valid is True
    assert issues == []


def test_document_text_supports_a_number_with_its_local_unit() -> None:
    """Passage text can ground a number when its nearby wording gives a unit."""
    is_valid, issues = check_numeric_evidence(
        "The policy says customers have 14 calendar days to report damage.",
        _result(
            {
                "results": [
                    {
                        "document_name": "returns_policy.md",
                        "text": (
                            "Customers should report damaged products within "
                            "14 calendar days of delivery."
                        ),
                    }
                ]
            },
            tool_name="search_documents",
        ),
    )

    assert is_valid is True
    assert issues == []


def test_total_matches_supports_dataset_count_claim() -> None:
    """Exact match counts from record queries ground dataset-size answers."""
    is_valid, issues = check_numeric_evidence(
        "There are 6 customers in the database.",
        _result(
            {"total_matches": 6, "returned_rows": 4},
            tool_name="query_business_data",
        ),
    )

    assert is_valid is True
    assert issues == []


def test_reported_year_is_supported_by_analysis_period() -> None:
    """A four-digit year claim matches the date range in the analysis output."""
    result: list[ToolResult] = [
        {
            "tool_name": "run_analysis",
            "arguments": {},
            "result": {
                "period": {"start": "2024-01-01", "end": "2024-12-31"},
                "data": [{"revenue_cents": 24532474}],
            },
            "success": True,
        }
    ]

    is_valid, issues = check_numeric_evidence(
        "Furniture generated the most revenue in 2024, at $245,324.74 "
        "(period ending Dec 31).",
        result,
    )

    assert is_valid is True
    assert issues == []


def test_iso_period_dates_do_not_become_count_claims() -> None:
    """Numeric date components in an answer match date evidence, not metrics."""
    result: list[ToolResult] = [
        {
            "tool_name": "run_analysis",
            "arguments": {},
            "result": {
                "period": {"start": "2024-01-01", "end": "2024-12-31"},
                "data": [{"revenue_cents": 24532474}],
            },
            "success": True,
        }
    ]

    is_valid, issues = check_numeric_evidence(
        "Revenue was $245,324.74 for 2024-01-01 through 2024-12-31.",
        result,
    )

    assert is_valid is True
    assert issues == []


def test_date_followed_by_comma_is_not_parsed_as_count() -> None:
    """A comma after an ISO date must remain punctuation, not part of a number."""
    result: list[ToolResult] = [
        {
            "tool_name": "run_analysis",
            "arguments": {
                "analysis_name": "revenue_by_product",
                "parameters": {
                    "start": "2024-11-01",
                    "end": "2024-11-30",
                    "top_n": 1,
                },
            },
            "result": {
                "data": [
                    {
                        "product_id": "P010",
                        "product_name": "Standing Desk",
                        "revenue_cents": 1971966,
                        "units": 34,
                    }
                ],
                "period": {"start": "2024-11-01", "end": "2024-11-30"},
            },
            "success": True,
        }
    ]

    is_valid, issues = check_numeric_evidence(
        "Revenue was 1,971,966 cents for 2024\u201111\u201130, "
        "which includes completed orders.",
        result,
    )

    assert is_valid is True
    assert issues == []


def test_period_revenue_and_percent_change_keep_their_own_metrics() -> None:
    """Nearby percentage wording does not relabel table totals as percentages."""
    result: list[ToolResult] = [
        {
            "tool_name": "run_analysis",
            "arguments": {
                "analysis_name": "period_change",
                "parameters": {"metric": "revenue"},
            },
            "result": {
                "data": [
                    {
                        "metric": "revenue",
                        "current_value": 1574792,
                        "previous_value": 4017949,
                        "percent_change": -60.80607294915888,
                    }
                ],
                "period": {
                    "current": {
                        "start": "2024-12-01",
                        "end": "2024-12-31",
                    },
                    "previous": {
                        "start": "2024-11-01",
                        "end": "2024-11-30",
                    },
                },
            },
            "success": True,
        }
    ]

    is_valid, issues = check_numeric_evidence(
        "**Completed-order revenue (cents)**\n\n"
        "| Period | Revenue |\n"
        "| November 2024 | 4,017,949 |\n"
        "| December 2024 | 1,574,792 |\n\n"
        "**Percentage change (December vs. November)**\n"
        "-60.80607294915888\u202f%",
        result,
    )

    assert is_valid is True
    assert issues == []


def test_revenue_cents_field_reference_and_conversion_constant_are_valid() -> None:
    """Explicit revenue_cents references and divide-by-100 are not extra claims."""
    result: list[ToolResult] = [
        {
            "tool_name": "run_analysis",
            "arguments": {},
            "result": {
                "data": [
                    {
                        "metric": "revenue",
                        "current_value": 1345428,
                    }
                ]
            },
            "success": True,
        }
    ]

    is_valid, issues = check_numeric_evidence(
        "The analysis returns revenue_cents = 1,345,428 for the leading "
        "customer. Converting cents to dollars (divide by 100) gives "
        "$13,454.28.",
        result,
    )

    assert is_valid is True
    assert issues == []


def test_unicode_minus_and_escaped_percent_match_percentage_evidence() -> None:
    """Unicode minus signs and LaTeX-escaped percent signs preserve the claim."""
    result: list[ToolResult] = [
        {
            "tool_name": "run_analysis",
            "arguments": {},
            "result": {"percent_change": -60.80607294915888},
            "success": True,
        }
    ]

    is_valid, issues = check_numeric_evidence(
        "Percentage change was \\(-60.81\\%\\) or "
        "\u201160.80607294915888\u202f%.",
        result,
    )

    assert is_valid is True
    assert issues == []


def test_unicode_hyphens_in_dates_match_analysis_period() -> None:
    """Common Unicode hyphen variants preserve year-month-day evidence."""
    result: list[ToolResult] = [
        {
            "tool_name": "run_analysis",
            "arguments": {},
            "result": {
                "period": {"start": "2024-01-01", "end": "2024-12-31"},
                "data": [{"revenue_cents": 24532474}],
            },
            "success": True,
        }
    ]

    is_valid, issues = check_numeric_evidence(
        "Revenue was 24532474 cents for 2024\u201101\u201101 through "
        "2024\u201112\u201131.",
        result,
    )

    assert is_valid is True
    assert issues == []


def test_currency_claim_is_not_misclassified_by_nearby_unit_count() -> None:
    """A nearby unit count must not prevent revenue currency from grounding."""
    result: list[ToolResult] = [
        {
            "tool_name": "run_analysis",
            "arguments": {},
            "result": {
                "data": [{"revenue_cents": 24532474, "units": 526}],
            },
            "success": True,
        }
    ]

    is_valid, issues = check_numeric_evidence(
        "Furniture revenue was $245,324.74 from 526 units.",
        result,
    )

    assert is_valid is True
    assert issues == []


def test_customer_identifier_is_not_interpreted_as_numeric_count() -> None:
    """The numeric suffix in a customer name is grounded as an identifier."""
    result: list[ToolResult] = [
        {
            "tool_name": "run_analysis",
            "arguments": {},
            "result": {
                "data": [{"customer_name": "Customer 037", "revenue_cents": 5000}],
            },
            "success": True,
        }
    ]

    is_valid, issues = check_numeric_evidence(
        "Customer 037 generated $50.00 in revenue.",
        result,
    )

    assert is_valid is True
    assert issues == []


def test_matching_percentage_field_supports_percentage_claim() -> None:
    """Percentage evidence supports a claim with the same percentage."""
    is_valid, issues = check_numeric_evidence(
        "Revenue changed by 12.5%.",
        _result({"percent_change": 12.5}),
    )

    assert is_valid is True
    assert issues == []


def test_period_change_uses_sibling_metric_context() -> None:
    """Generic comparison values inherit the declared metric and its units."""
    result: list[ToolResult] = [
        {
            "tool_name": "run_analysis",
            "arguments": {"metric": "revenue"},
            "result": {
                "analysis": "period_change",
                "period": {
                    "current": {
                        "start": "2024-12-01",
                        "end": "2024-12-31",
                    },
                    "previous": {
                        "start": "2024-11-01",
                        "end": "2024-11-30",
                    },
                },
                "data": [
                    {
                        "metric": "revenue",
                        "current_value": 7500,
                        "previous_value": 6500,
                        "absolute_change": 1000,
                        "percent_change": 15.38,
                    }
                ],
            },
            "success": True,
        }
    ]

    is_valid, issues = check_numeric_evidence(
        "Revenue increased by 1000 cents, or 15.38%.",
        result,
    )

    assert is_valid is True
    assert issues == []


def test_downward_change_magnitudes_match_signed_change_evidence() -> None:
    """Explicit decrease wording supports the magnitude of signed changes."""
    result: list[ToolResult] = [
        {
            "tool_name": "run_analysis",
            "arguments": {"metric": "revenue"},
            "result": {
                "analysis": "period_change",
                "period": {
                    "current": {
                        "start": "2024-12-01",
                        "end": "2024-12-31",
                    },
                    "previous": {
                        "start": "2024-11-01",
                        "end": "2024-11-30",
                    },
                },
                "data": [
                    {
                        "metric": "revenue",
                        "current_value": 1574792,
                        "previous_value": 4017949,
                        "absolute_change": -2443157,
                        "percent_change": -60.80607294915888,
                    }
                ],
            },
            "success": True,
        }
    ]

    is_valid, issues = check_numeric_evidence(
        "Completed\u2011order revenue fell from\u202f$40,179.49\u202fin "
        "November\u202f2024 to\u202f$15,747.92\u202fin December\u202f2024, "
        "a decrease of\u202f$24,431.57 (\u221260.8\u202f%). This reflects "
        "only orders with status \u201ccompleted.\u201d",
        result,
    )

    assert is_valid is True
    assert issues == []


def test_downward_change_magnitude_in_cents_matches_signed_evidence() -> None:
    """An explicitly stated decrease in cents matches a negative change."""
    is_valid, issues = check_numeric_evidence(
        "Revenue had a decrease of 2,443,157 cents.",
        _result(
            {
                "data": [
                    {
                        "metric": "revenue",
                        "absolute_change": -2443157,
                    }
                ]
            }
        ),
    )

    assert is_valid is True
    assert issues == []


def test_positive_change_magnitude_without_decrease_wording_is_rejected() -> None:
    """An unsigned number is not grounded as a change without direction wording."""
    result: list[ToolResult] = [
        {
            "tool_name": "run_analysis",
            "arguments": {"metric": "revenue"},
            "result": {
                "analysis": "period_change",
                "data": [
                    {
                        "metric": "revenue",
                        "absolute_change": -2443157,
                    }
                ],
            },
            "success": True,
        }
    ]

    is_valid, issues = check_numeric_evidence(
        "Revenue changed by $24,431.57.",
        result,
    )

    assert is_valid is False
    assert len(issues) == 1
    assert "24,431.57" in issues[0]
