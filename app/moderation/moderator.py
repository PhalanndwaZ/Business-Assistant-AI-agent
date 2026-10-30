"""Deterministic moderation checks backed by editable JSON rules."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.config import PROJECT_ROOT
from app.data_access.employee_loader import load_employee_records
from app.policy.policy import AccessPolicy
from app.rag.vector_store import JsonVectorStore

MODERATION_RULES_PATH = (
    PROJECT_ROOT / "data" / "policy" / "moderation_rules.json"
)
SYSTEM_PROMPT_PATH = PROJECT_ROOT / "app" / "prompts" / "system_prompt.md"
EMPLOYEE_ID_PATTERN = re.compile(r"\bE\d{3,}\b", re.IGNORECASE)


class ModerationError(RuntimeError):
    """Raised when moderation rules cannot be loaded or safely applied."""


@dataclass(frozen=True)
class ModerationDecision:
    """A rule match requiring a refusal before the model runs."""

    category: str
    response: str


@dataclass(frozen=True)
class OutputModerationResult:
    """Safe response disposition and non-sensitive reason codes."""

    status: Literal["ok", "redacted"]
    notice: str | None
    reason_codes: tuple[str, ...] = ()


def _load_rules(path: Path) -> dict[str, Any]:
    """Load moderation configuration and reject malformed rules fail-closed."""
    try:
        rules: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModerationError(
            f"Could not load moderation rules from {path}: {exc}"
        ) from exc
    if not isinstance(rules, dict):
        raise ModerationError("Moderation rules must be a JSON object.")
    input_rules = rules.get("input")
    retrieved_rules = rules.get("retrieved_text")
    if not isinstance(input_rules, dict) or not isinstance(retrieved_rules, dict):
        raise ModerationError("Moderation rules are missing required sections.")
    checks = input_rules.get("checks")
    role_checks = input_rules.get("role_checks")
    if not isinstance(checks, list) or not isinstance(role_checks, dict):
        raise ModerationError("Input moderation rules have invalid structure.")
    for role, role_rule in role_checks.items():
        if not isinstance(role, str) or not isinstance(role_rule, dict):
            raise ModerationError("Role moderation rules have invalid structure.")
        _validate_check(role_rule)
    for check in checks:
        if not isinstance(check, dict):
            raise ModerationError("Input moderation check must be an object.")
        _validate_check(check)
    _validate_check(retrieved_rules)
    if retrieved_rules["action"] != "drop":
        raise ModerationError("Retrieved-text rules must use the drop action.")
    return rules


def _validate_check(check: dict[str, Any]) -> None:
    """Ensure every configured check is safe to compile and execute."""
    patterns = check.get("patterns")
    if (
        not isinstance(check.get("category"), str)
        or check.get("action") not in {"refuse", "drop"}
        or not isinstance(patterns, list)
        or not patterns
        or not all(isinstance(pattern, str) and pattern for pattern in patterns)
    ):
        raise ModerationError("A moderation check has invalid fields.")
    response = check.get("response")
    if response is not None and (not isinstance(response, str) or not response):
        raise ModerationError("A moderation response must be non-empty text.")
    try:
        for pattern in patterns:
            re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ModerationError("A moderation rule contains an invalid pattern.") from exc


def check_input(
    question: str,
    role: str,
    path: Path = MODERATION_RULES_PATH,
) -> ModerationDecision | None:
    """Refuse known unsafe or out-of-role requests before any model call."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be non-empty text.")
    if not isinstance(role, str) or not role:
        raise ModerationError("A verified user role is required for moderation.")
    rules = _load_rules(path)
    input_rules = rules["input"]
    checks = list(input_rules["checks"])
    role_checks = input_rules["role_checks"]
    if role not in role_checks:
        raise ModerationError(f"No input moderation rules exist for role {role!r}.")
    checks.append(role_checks[role])
    for check in checks:
        if any(
            re.search(pattern, question, re.IGNORECASE)
            for pattern in check["patterns"]
        ):
            response = check.get("response")
            if not isinstance(response, str) or not response:
                raise ModerationError(
                    f"Moderation check {check['category']} has no response."
                )
            return ModerationDecision(
                category=check["category"],
                response=response,
            )
    return None


def filter_retrieved_chunks(
    chunks: list[dict[str, Any]],
    path: Path = MODERATION_RULES_PATH,
) -> tuple[list[dict[str, Any]], int]:
    """Remove retrieved chunks with instructions aimed at the assistant."""
    if not isinstance(chunks, list):
        raise ModerationError("Retrieved document results must be a list.")
    check = _load_rules(path)["retrieved_text"]
    patterns = check["patterns"]
    safe_chunks: list[dict[str, Any]] = []
    dropped_count = 0
    for chunk in chunks:
        if not isinstance(chunk, dict) or not isinstance(chunk.get("text"), str):
            raise ModerationError("Retrieved document data has an invalid shape.")
        if any(
            re.search(pattern, chunk["text"], re.IGNORECASE)
            for pattern in patterns
        ):
            dropped_count += 1
        else:
            safe_chunks.append(chunk)
    return safe_chunks, dropped_count


def moderate_output(
    content: str,
    role: str,
    data_dir: Path,
    vector_store_path: Path,
    *,
    answer_text: str | None = None,
    path: Path = MODERATION_RULES_PATH,
) -> OutputModerationResult:
    """Detect sensitive values, prompt fragments, and forbidden document quotes."""
    rules = _load_rules(path)
    output_rules = rules.get("output")
    if not isinstance(output_rules, dict):
        raise ModerationError("Output moderation rules are missing.")
    checks = output_rules.get("checks")
    notice = output_rules.get("notice")
    prompt_min_words = output_rules.get("system_prompt_min_words")
    quote_min_chars = output_rules.get("restricted_quote_min_chars")
    if (
        not isinstance(checks, list)
        or not checks
        or not isinstance(notice, str)
        or not notice
        or isinstance(prompt_min_words, bool)
        or not isinstance(prompt_min_words, int)
        or prompt_min_words < 6
        or isinstance(quote_min_chars, bool)
        or not isinstance(quote_min_chars, int)
        or quote_min_chars < 10
    ):
        raise ModerationError("Output moderation rules have invalid structure.")
    for check in checks:
        if not isinstance(check, dict):
            raise ModerationError("Output moderation check must be an object.")
        patterns = check.get("patterns")
        if (
            check.get("category") != "M5"
            or check.get("action") != "redact"
            or not isinstance(patterns, list)
            or not patterns
            or not all(isinstance(pattern, str) and pattern for pattern in patterns)
        ):
            raise ModerationError("An output moderation check has invalid fields.")
        try:
            for pattern in patterns:
                re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise ModerationError(
                "An output moderation rule contains an invalid pattern."
            ) from exc

    try:
        policy = AccessPolicy()
        for check in checks:
            for pattern in check["patterns"]:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    if _is_permitted_employee_contact(
                        match.group(),
                        role,
                        policy,
                        data_dir,
                    ):
                        continue
                    return _redacted_output(notice, "M5")

        prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        if _contains_prompt_fragment(content, prompt, prompt_min_words):
            return _redacted_output(notice, "M5")

        if (
            not policy.can_access_field(role, "employees", "employee_id")
            and EMPLOYEE_ID_PATTERN.search(content)
        ):
            return _redacted_output(notice, "M5")

        if not policy.can_access_field(role, "employees", "salary_cents"):
            if re.search(
                r"\b(?:salary|salaries|compensation|employee pay)\b.{0,30}"
                r"\$?\s?\d[\d,]*(?:\.\d{1,2})?\s?[kKmM]?\b",
                content,
                re.IGNORECASE,
            ):
                return _redacted_output(notice, "M5")
            employees = load_employee_records(data_dir)
            if _contains_restricted_salary(content, employees):
                return _redacted_output(notice, "M5")

        quotes = _quoted_passages(
            content if answer_text is None else answer_text,
            quote_min_chars,
        )
        if quotes:
            chunks = JsonVectorStore(vector_store_path).load()["chunks"]
            for chunk in chunks:
                if not isinstance(chunk, dict):
                    raise ModerationError(
                        "A document chunk has an invalid moderation shape."
                    )
                department = chunk.get("department")
                classification = chunk.get("classification")
                text = chunk.get("text")
                if (
                    not isinstance(department, str)
                    or not isinstance(classification, str)
                    or not isinstance(text, str)
                ):
                    raise ModerationError(
                        "A document chunk is missing access metadata."
                    )
                if policy.can_access_document(role, department, classification):
                    continue
                normalized_document = _normalize_text(text)
                if any(
                    _normalize_text(quote) in normalized_document
                    for quote in quotes
                ):
                    return _redacted_output(notice, "M6")
    except ModerationError:
        raise
    except (OSError, ValueError) as exc:
        raise ModerationError("Output moderation could not verify the response.") from exc

    return OutputModerationResult(status="ok", notice=None)


def _is_permitted_employee_contact(
    value: str,
    role: str,
    policy: AccessPolicy,
    data_dir: Path,
) -> bool:
    """Allow a contact value only when it belongs to an accessible employee."""
    field = "work_email" if "@" in value else "phone"
    if not policy.can_access_field(role, "employees", field):
        return False
    employees = load_employee_records(data_dir)
    if field == "work_email":
        normalized_value = value.casefold()
        return any(
            employee["work_email"].casefold() == normalized_value
            for employee in employees
        )

    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return any(
        re.sub(r"\D", "", employee["phone"]).removeprefix("1") == digits
        for employee in employees
    )


def _redacted_output(
    notice: str,
    reason_code: str,
) -> OutputModerationResult:
    """Return one generic notice without exposing which content matched."""
    return OutputModerationResult(
        status="redacted",
        notice=notice,
        reason_codes=(reason_code,),
    )


def _contains_prompt_fragment(
    content: str,
    prompt: str,
    minimum_words: int,
) -> bool:
    """Detect exact contiguous prompt fragments without matching short phrases."""
    content_words = re.findall(r"\b[\w'-]+\b", content.casefold())
    prompt_words = re.findall(r"\b[\w'-]+\b", prompt.casefold())
    if len(prompt_words) < minimum_words:
        raise ModerationError("The system prompt is too short to validate.")
    content_windows = {
        tuple(content_words[index : index + minimum_words])
        for index in range(len(content_words) - minimum_words + 1)
    }
    return any(
        tuple(prompt_words[index : index + minimum_words]) in content_windows
        for index in range(len(prompt_words) - minimum_words + 1)
    )


def _contains_restricted_salary(
    content: str,
    employees: list[dict[str, Any]],
) -> bool:
    """Find exact cents or dollar values for roles without salary permission."""
    for employee in employees:
        cents = employee["salary_cents"]
        dollars = cents / 100
        variants = {
            str(cents),
            f"{cents:,}",
            f"{dollars:.2f}",
            f"{dollars:,.2f}",
        }
        if cents % 100 == 0:
            variants.update({str(cents // 100), f"{cents // 100:,}"})
        for value in variants:
            pattern = rf"(?<![\w.])\$?{re.escape(value)}(?![\w.])"
            if re.search(pattern, content):
                return True
    return False


def _quoted_passages(content: str, minimum_chars: int) -> list[str]:
    """Extract substantive double-quoted and typographically quoted passages."""
    return [
        quote
        for quote in re.findall(
            r'["“]([^"“”\r\n]{10,})["”]',
            content,
        )
        if len(quote.strip()) >= minimum_chars
    ]


def _normalize_text(text: str) -> str:
    """Normalize whitespace and punctuation for exact quote containment checks."""
    return " ".join(re.findall(r"\w+", text.casefold()))
