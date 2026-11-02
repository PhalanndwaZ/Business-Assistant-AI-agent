from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from langchain_core.messages import HumanMessage

from app.config import Settings, load_settings
from app.llm_factory import build_chat_model
from evaluation.langfuse_setup.tracing import create_langfuse_client, tracing_enabled

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class JudgeVerdict:
    """One yes/no rubric verdict with a short reason and tagging metadata."""

    item: str
    passed: bool
    reason: str
    model: str = "judge"
    tagged: str = "judge"


def _coerce_bool(value: Any) -> bool:
    """Normalize common yes/no strings to a boolean verdict."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        cleaned = value.strip().casefold()
        if cleaned in {"true", "yes", "y", "pass", "passed", "1"}:
            return True
        if cleaned in {"false", "no", "n", "fail", "failed", "0"}:
            return False
    return False


def _extract_json(payload: str) -> dict[str, Any]:
    """Extract a JSON object from a model response, falling back to heuristic parsing."""
    text = payload.strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    lowered = payload.casefold()
    if "yes" in lowered and "no" not in lowered:
        return {"passed": True, "reason": payload.strip()[:200]}
    if "no" in lowered and "yes" not in lowered:
        return {"passed": False, "reason": payload.strip()[:200]}
    return {"passed": False, "reason": "Judge could not parse the verdict."}


async def _judge_one(
    *,
    question: str,
    answer: str,
    tool_results: Any,
    item: str,
    model: Any,
) -> JudgeVerdict:
    """Ask the model for a single yes/no verdict and a one-line rationale."""
    prompt = (
        "Evaluate the answer using the rubric question only. "
        "Do not judge numbers or access rules. Return JSON with keys: "
        "passed and reason. 'passed' must be true or false. 'reason' must be "
        "one short sentence.\n\n"
        f"Question: {question}\n\n"
        f"Answer: {answer}\n\n"
        f"Tool results: {json.dumps(tool_results, ensure_ascii=False, default=str)}\n\n"
        f"Rubric item: {item}"
    )
    response = await model.ainvoke([HumanMessage(content=prompt)])
    parsed = _extract_json(str(response.content))
    return JudgeVerdict(
        item=item,
        passed=_coerce_bool(parsed.get("passed", False)),
        reason=str(parsed.get("reason", "No reason provided."))[:200],
        model=getattr(response, "response_metadata", {}).get("llm_model", "judge"),
        tagged="judge",
    )


async def judge_answer(
    question: str,
    answer: str,
    *,
    tool_results: Any = None,
    rubric_items: Sequence[str] | None = None,
    settings: Settings | None = None,
    model: Any | None = None,
) -> list[JudgeVerdict]:
    """Return yes/no wording verdicts for each rubric item, without affecting code assertions."""
    items = list(rubric_items or [])
    if not items:
        return []
    config = settings or load_settings(require_groq_api_key=False)
    judge_model = model or build_chat_model(config)
    verdicts: list[JudgeVerdict] = []
    for item in items:
        verdicts.append(await _judge_one(
            question=question,
            answer=answer,
            tool_results=tool_results,
            item=item,
            model=judge_model,
        ))
    return verdicts


def score_judge_results(
    verdicts: Sequence[JudgeVerdict],
    *,
    trace_id: str | None = None,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    """Record rubric verdicts in Langfuse as explicit judge scores when tracing is enabled."""
    if not verdicts or not tracing_enabled():
        return []
    client = create_langfuse_client()
    if client is None:
        return []
    scored: list[dict[str, Any]] = []
    for verdict in verdicts:
        payload = {
            "name": f"judge:{verdict.item}",
            "value": 1.0 if verdict.passed else 0.0,
            "data_type": "NUMERIC",
            "comment": verdict.reason,
            "metadata": {
                "tag": verdict.tagged,
                "question": verdict.item,
                "judged_by": verdict.model,
                "status": "pass" if verdict.passed else "fail",
            },
        }
        if trace_id:
            payload["trace_id"] = trace_id
        if session_id:
            payload["session_id"] = session_id
        client.create_score(**payload)
        scored.append(payload)
    return scored
