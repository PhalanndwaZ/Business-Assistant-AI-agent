"""Deterministic checks that structured answer figures come from tool results."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from app.state import ToolResult

NUMBER_PATTERN = re.compile(
    r"(?:(?<![\w.])|(?<=[Rr]))[−‑+-]?\d+(?:,\d{3})*(?:\.\d+)?%?"
)
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<!\d)[.!?](?!\d)|\n")
MONEY_CENT_KEYS = frozenset(
    {"revenue_cents", "unit_price_cents", "salary_cents_sum"}
)
METRIC_TERMS = (
    (
        "payroll",
        re.compile(
            r"\b(payroll|earnings?|salar(?:y|ies)|wages?|compensation)\b",
            re.IGNORECASE,
        ),
    ),
    ("revenue", re.compile(r"\b(revenue|sales)\b", re.IGNORECASE)),
    ("price", re.compile(r"\b(price|unit price)\b", re.IGNORECASE)),
    ("cost", re.compile(r"\bcost\b", re.IGNORECASE)),
    ("spend", re.compile(r"\bspend\b", re.IGNORECASE)),
    ("amount", re.compile(r"\bamount\b", re.IGNORECASE)),
    (
        "count",
        re.compile(
            r"\b(orders?|customers?|employees?|products?|categories?|items?|units?|"
            r"quantities|count|records?|days?|weeks?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "date",
        re.compile(
            r"\b(dates?|years?|months?|periods?)\b",
            re.IGNORECASE,
        ),
    ),
)
MONTH_PATTERN = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\b",
    re.IGNORECASE,
)
ISO_DATE_PATTERN = re.compile(
    r"\b(?:19|20)\d{2}[-/\u2010-\u2015]\d{1,2}[-/\u2010-\u2015]\d{1,2}\b"
)
DOCUMENT_CITATION_PATTERN = re.compile(
    r"\[([^\]]+\.(?:md|txt|pdf))\]",
    re.IGNORECASE,
)
DOCUMENT_ATTRIBUTION_PATTERN = re.compile(
    r"\b(?:according to|management "
    r"(?:reported|noted|mentions|states|described)|(?:the|this|a) "
    r"(?:report|document|policy|memo|meeting notes)|"
    r"(?:the )?(?:report|document|policy|memo) "
    r"(?:says|states|reports|mentions|notes|indicates|describes))\b",
    re.IGNORECASE,
)
DOCUMENT_QUOTE_PATTERN = re.compile(r"[“\"]([^”\"]{8,})[”\"]")
CAUSAL_PATTERN = re.compile(
    r"\b(?:caus(?:e[sd]?|ation)|causing|due to|because of|result(?:ed|s|ing) in|"
    r"led to|driven by|drove|responsible for|contribut(?:ed|es|ing) to)\b",
    re.IGNORECASE,
)
CAUSAL_UNCERTAINTY_PATTERN = re.compile(
    r"\b(?:possible|potential|may|might|could|not establish|not prove|not proof|"
    r"does not show|doesn't show|unproven|uncertain|not confirmed)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NumericEvidence:
    """One number with the field context and unit supplied by a tool result."""

    value: float
    category: str
    unit: str
    field_name: str | None = None


def _number_value(token: str) -> float | None:
    """Normalize formatted integers, decimals, and percentages."""
    normalized = token.replace(",", "").removesuffix("%").replace("−", "-")
    normalized = normalized.replace("‑", "-")
    try:
        value = float(normalized)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _field_category(field_path: str) -> str:
    """Classify tool fields so answer figures preserve semantic context."""
    normalized_path = field_path.lower()
    if any(
        key in normalized_path
        for key in ("percent", "percentage", "_pct", "growth_rate")
    ):
        return "percentage"
    if any(
        key in normalized_path
        for key in ("salary", "payroll", "earnings", "wages", "compensation")
    ):
        return "payroll"
    if "revenue" in normalized_path or "sales" in normalized_path:
        return "revenue"
    if any(
        metric in normalized_path
        for metric in ("metric=orders", "metric=units")
    ):
        return "count"
    if "price" in normalized_path:
        return "price"
    if "cost" in normalized_path:
        return "cost"
    if "spend" in normalized_path:
        return "spend"
    if "amount" in normalized_path:
        return "amount"
    if any(
        key in normalized_path
        for key in (
            "order_count",
            "customer_count",
            "total_matches",
            "quantity",
            "units",
            "count",
        )
    ):
        return "count"
    if any(key in normalized_path for key in ("date", "period", "year")):
        return "date"
    return "general"


def _collect_numbers(
    value: Any,
    parent_key: str = "",
) -> list[NumericEvidence]:
    """Recursively collect numeric evidence with its field path and unit."""
    numbers: list[NumericEvidence] = []
    if isinstance(value, bool) or value is None:
        return numbers
    if isinstance(value, (int, float)):
        if math.isfinite(value):
            category = _field_category(parent_key)
            value_field = parent_key.split(".")[-1]
            unit = (
                "cents"
                if value_field in MONEY_CENT_KEYS
                or (
                    "revenue" in value_field
                    and value_field.endswith("_cents")
                )
                or (
                    "metric=revenue" in parent_key.lower()
                    and value_field
                    in {"current_value", "previous_value", "absolute_change"}
                )
                else category
            )
            numbers.append(
                NumericEvidence(float(value), category, unit, value_field)
            )
            if unit == "cents":
                numbers.append(
                    NumericEvidence(
                        float(value) / 100,
                        category,
                        "dollars",
                        value_field,
                    )
                )
        return numbers
    if isinstance(value, str):
        for match in NUMBER_PATTERN.finditer(value):
            number = _number_value(match.group())
            if number is not None:
                category = _field_category(parent_key)
                if category == "general":
                    inferred_category, _ = _claim_category(value, match)
                    if inferred_category is not None:
                        category = inferred_category
                numbers.append(
                    NumericEvidence(
                        number,
                        category,
                        category,
                        parent_key.split(".")[-1] or None,
                    )
                )
        return numbers
    if isinstance(value, dict):
        metric = value.get("metric")
        context_key = (
            f"{parent_key}.metric={metric}" if metric is not None else parent_key
        )
        for key, item in value.items():
            field_path = f"{context_key}.{key}" if context_key else str(key)
            numbers.extend(_collect_numbers(item, field_path))
        return numbers
    if isinstance(value, (list, tuple)):
        for item in value:
            numbers.extend(_collect_numbers(item, parent_key))
    return numbers


def _claim_category(
    draft_answer: str,
    match: re.Match[str],
) -> tuple[str | None, str | None]:
    """Infer a numeric claim's metric or unit from its nearby wording."""
    preceding_text = draft_answer[max(0, match.start() - 40) : match.start()]
    following_text = draft_answer[match.end() : match.end() + 40]
    unit_following_text = re.split(
        r"[.!?;\n]",
        following_text,
        maxsplit=1,
    )[0]
    if re.search(
        r"\b(customer|product|order)\s+(?:id\s*)?#?\s*$",
        preceding_text,
        re.IGNORECASE,
    ):
        return None, None
    if re.search(r"\brevenue_cents\s*=\s*$", preceding_text, re.IGNORECASE):
        return "revenue", "cents"
    if re.search(r"\b(?:top|first|last)\s*$", preceding_text, re.IGNORECASE):
        return "count", None
    date_start = max(0, match.start() - 10)
    date_end = min(len(draft_answer), match.end() + 10)
    for date_match in ISO_DATE_PATTERN.finditer(draft_answer, date_start, date_end):
        if date_match.start() <= match.start() and match.end() <= date_match.end():
            return "date", None
    year = _number_value(match.group())
    if (
        "," not in match.group()
        and match.group().isdigit()
        and year is not None
        and 1900 <= year <= 2100
    ):
        return "date", None
    day_token = match.group().replace(",", "")
    if day_token.isdigit() and 1 <= int(day_token) <= 31:
        context_start = max(0, match.start() - 40)
        month_context = draft_answer[
            context_start : min(len(draft_answer), match.end() + 40)
        ]
        for month_match in MONTH_PATTERN.finditer(month_context):
            month_start = context_start + month_match.start()
            month_end = context_start + month_match.end()
            distance = min(
                abs(month_start - match.end()),
                abs(match.start() - month_end),
            )
            if distance <= 2:
                return "date", None
            month_to_day = draft_answer[month_end : match.start()]
            day_to_month = draft_answer[match.end() : month_start]
            if re.fullmatch(
                r"\s*,?\s*(?:(?:which\s+)?"
                r"(?:has|had|contains|contained)\s+)?",
                month_to_day,
                re.IGNORECASE,
            ) or re.fullmatch(
                r"\s+(?:calendar\s+)?days?\s+(?:in|for|during)\s+",
                day_to_month,
                re.IGNORECASE,
            ):
                return "date", None
    unit = None
    if match.group().endswith("%") or re.match(
        r"\s*(?:\\?%|percent(?:age)?\b)",
        unit_following_text,
        re.IGNORECASE,
    ):
        unit = "percentage"
    elif (
        preceding_text.rstrip().endswith(("$", "R", "r"))
        or re.search(
            r"\b(dollars?|usd)\b",
            unit_following_text,
            re.IGNORECASE,
        )
    ):
        unit = "dollars"
    elif re.search(r"\bcents?\b", unit_following_text, re.IGNORECASE):
        unit = "cents"
    if unit == "percentage":
        return "percentage", unit
    sentence_start = 0
    sentence_end = len(draft_answer)
    for boundary in SENTENCE_BOUNDARY_PATTERN.finditer(draft_answer):
        if boundary.end() <= match.start():
            sentence_start = boundary.end()
        elif boundary.start() >= match.end():
            sentence_end = boundary.start()
            break
    nearest_metric: tuple[int, str] | None = None
    context_start = sentence_start
    context_end = sentence_end
    for category, pattern in METRIC_TERMS:
        if unit in {"cents", "dollars"} and category not in {
            "payroll",
            "revenue",
            "price",
            "cost",
            "spend",
            "amount",
        }:
            continue
        for term_match in pattern.finditer(
            draft_answer,
            context_start,
            context_end,
        ):
            distance = min(
                abs(term_match.start() - match.start()),
                abs(term_match.end() - match.start()),
            )
            if category == "date" and distance > 2:
                continue
            if nearest_metric is None or distance < nearest_metric[0]:
                nearest_metric = (distance, category)
    return (nearest_metric[1] if nearest_metric else None), unit


def check_numeric_evidence(
    draft_answer: str,
    tool_results: list[ToolResult],
) -> tuple[bool, list[str]]:
    """Ensure each numeric claim is present in successful tool output."""
    citation_spans = [
        citation.span()
        for citation in DOCUMENT_CITATION_PATTERN.finditer(draft_answer)
    ]
    numeric_claims = [
        match
        for match in NUMBER_PATTERN.finditer(draft_answer)
        if not any(start <= match.start() < end for start, end in citation_spans)
    ]
    successful_results = [
        tool_result["result"]
        for tool_result in tool_results
        if tool_result["success"]
    ]
    if not successful_results:
        if not numeric_claims:
            return True, []
        return False, ["No successful business-data tool result supports an answer."]

    supported_numbers = _collect_numbers(successful_results)
    compared_values = sorted(
        {
            (evidence.value, evidence.category, evidence.unit)
            for evidence in supported_numbers
        }
    )
    comparison_summary = ", ".join(
        f"{value:g} ({category}/{unit})"
        for value, category, unit in compared_values[:20]
    )
    if len(compared_values) > 20:
        comparison_summary += f", ... and {len(compared_values) - 20} more"
    if not comparison_summary:
        comparison_summary = "no numeric values in successful tool results"

    issues = []
    for match in numeric_claims:
        claimed_number = _number_value(match.group())
        if claimed_number is None:
            continue
        if match.group() == "100":
            preceding_text = draft_answer[max(0, match.start() - 20) : match.start()]
            following_text = draft_answer[match.end() : match.end() + 20]
            is_percent_conversion = re.search(
                r"(?:×|\\times|\*)\s*$",
                preceding_text,
            ) and re.match(r"\s*=\s*[-+]?\d", following_text)
            is_cents_conversion = re.search(
                r"(?:divide(?:d|ing)?\s+by|÷)\s*$",
                preceding_text,
                re.IGNORECASE,
            )
            if is_percent_conversion or is_cents_conversion:
                continue
        claim_category, claim_unit = _claim_category(draft_answer, match)
        has_matching_evidence = any(
            _claim_matches_number(claimed_number, match, draft_answer, evidence)
            and _claim_matches_evidence(
                claim_category,
                claim_unit,
                evidence,
            )
            for evidence in supported_numbers
        )
        if has_matching_evidence:
            continue

        if (
            claim_category == "percentage"
            and claim_unit == "percentage"
            and claimed_number > 0
            and any(
                evidence.category == "percentage"
                and evidence.field_name == "percent_change"
                and evidence.value < 0
                and math.isclose(
                    claimed_number,
                    abs(evidence.value),
                    rel_tol=1e-4,
                    abs_tol=0.005,
                )
                for evidence in supported_numbers
            )
        ):
            issues.append(
                f"Percentage {match.group()!r} matches the magnitude of a "
                "negative percentage change, but omits its direction. State "
                "the signed value or explicitly describe it as a decrease."
            )
            continue

        if not has_matching_evidence:
            issues.append(
                f"Number {match.group()!r} (metric={claim_category!r}, "
                f"unit={claim_unit!r}) does not appear in successful tool "
                f"results. Compared against: {comparison_summary}."
            )
    return not issues, issues


def _claim_matches_number(
    claimed_number: float,
    match: re.Match[str],
    draft_answer: str,
    evidence: NumericEvidence,
) -> bool:
    """Match exact values, or explicit downward-change magnitudes."""
    preceding_text = draft_answer[max(0, match.start() - 60) : match.start()]
    is_rand = preceding_text.rstrip().endswith(("R", "r"))
    has_negative_rand_prefix = bool(
        re.search(r"[-−‑]\s*[Rr]\s*$", preceding_text)
    )
    normalized_claim = -claimed_number if has_negative_rand_prefix else claimed_number
    tolerance = 0.5 if is_rand and evidence.unit == "dollars" else 0.005
    if math.isclose(
        normalized_claim,
        evidence.value,
        rel_tol=1e-4,
        abs_tol=tolerance,
    ):
        return True
    if (
        normalized_claim <= 0
        or evidence.value >= 0
        or evidence.field_name not in {"absolute_change", "percent_change"}
    ):
        return False

    preceding_text = preceding_text.rstrip().rstrip("$€£Rr").rstrip()
    describes_decrease = re.search(
        r"(?:\b(?:decreased|declined|dropped|fell|reduced)\s*(?:(?:by|of)\s*)?|"
        r"\b(?:decrease|decline|drop|reduction)\s+(?:of|was|is)\s*|"
        r"\bdown(?:\s+by)?)$",
        preceding_text,
        re.IGNORECASE,
    )
    return bool(
        describes_decrease
        and math.isclose(
            normalized_claim,
            abs(evidence.value),
            rel_tol=1e-4,
            abs_tol=tolerance,
        )
    )


def check_document_evidence(
    draft_answer: str,
    retrieved_chunks: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Validate document citations, quoted support, and cautious causal claims."""
    documents: dict[str, list[str]] = {}
    for chunk in retrieved_chunks:
        document_name = chunk.get("document_name")
        text = chunk.get("text")
        if isinstance(document_name, str) and isinstance(text, str):
            documents.setdefault(document_name.casefold(), []).append(text)

    issues: list[str] = []
    is_refusal = bool(
        re.search(
            r"\b(?:cannot answer|can't answer|unable to answer|"
            r"no relevant passages|not enough information)\b",
            draft_answer,
            re.IGNORECASE,
        )
    )
    if (
        documents
        and draft_answer.strip()
        and not DOCUMENT_CITATION_PATTERN.search(draft_answer)
        and not is_refusal
    ):
        issues.append(
            "Retrieved document passages are available, but the draft does "
            "not cite a retrieved source."
        )

    sentences = re.split(r"(?<=[.!?])\s+", draft_answer.strip())
    for sentence in sentences:
        citations = [
            citation.casefold()
            for citation in DOCUMENT_CITATION_PATTERN.findall(sentence)
        ]
        is_attributed = bool(DOCUMENT_ATTRIBUTION_PATTERN.search(sentence))
        has_causal_claim = bool(CAUSAL_PATTERN.search(sentence))
        needs_document_evidence = is_attributed or bool(citations) or has_causal_claim

        if not needs_document_evidence:
            continue
        if not documents:
            issues.append(
                "A document-attributed claim has no retrieved document evidence."
            )
            continue

        matching_citations = [name for name in citations if name in documents]
        invalid_citations = [name for name in citations if name not in documents]
        if invalid_citations:
            issues.append(
                "Cited document name(s) do not match retrieved sources: "
                + ", ".join(invalid_citations)
                + "."
            )
        if not citations or not matching_citations:
            issues.append(
                "A document-attributed claim must cite the exact retrieved "
                "document name in square brackets."
            )
            continue

        quotes = [
            " ".join(quote.casefold().split())
            for quote in DOCUMENT_QUOTE_PATTERN.findall(sentence)
        ]
        source_text = " ".join(
            " ".join(text.casefold().split())
            for citation in matching_citations
            for text in documents[citation]
        )
        if not quotes or not all(quote in source_text for quote in quotes):
            issues.append(
                "A document-attributed claim must include an exact quoted "
                "passage from its cited retrieved chunk."
            )

        if has_causal_claim and (
            not DOCUMENT_ATTRIBUTION_PATTERN.search(sentence)
            or not CAUSAL_UNCERTAINTY_PATTERN.search(sentence)
        ):
            issues.append(
                "A causal explanation must be attributed to a retrieved "
                "document and described as possible or not established."
            )

    return not issues, issues


def _claim_matches_evidence(
    claim_category: str | None,
    claim_unit: str | None,
    evidence: NumericEvidence,
) -> bool:
    """Match numeric values only when explicit claim units agree."""
    if claim_unit is not None and evidence.unit != claim_unit:
        return False
    if claim_category is None:
        return True
    if claim_category == "percentage":
        return evidence.category == "percentage"
    return evidence.category == claim_category


def tool_results_as_json(tool_results: list[ToolResult]) -> str:
    """Serialize successful numerical evidence for internal validation prompts."""
    return json.dumps(
        [
            {
                "tool_name": tool_result["tool_name"],
                "arguments": tool_result["arguments"],
                "result": tool_result["result"],
            }
            for tool_result in tool_results
            if tool_result["success"]
        ],
        ensure_ascii=True,
        sort_keys=True,
    )
