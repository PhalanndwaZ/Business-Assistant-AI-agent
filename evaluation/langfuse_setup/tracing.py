from __future__ import annotations

import os
from typing import Any, Protocol

from app.tracing.mask import fail_closed_mask


class TraceClient(Protocol):
    def trace(self, **kwargs: Any) -> Any: ...
    def flush(self) -> Any: ...


def tracing_enabled() -> bool:
    return os.getenv("TRACING_ENABLED", "false").casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def create_langfuse_client() -> TraceClient | None:
    if not tracing_enabled():
        return None
    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        raise RuntimeError("Langfuse tracing requires public and secret keys.")
    try:
        from langfuse import Langfuse
    except ImportError as exc:
        raise RuntimeError("Langfuse is not installed.") from exc
    return Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
    )


def send_trace(payload: dict[str, Any], *, name: str = "business-ai-evaluation") -> None:
    if not tracing_enabled():
        return
    client = create_langfuse_client()
    if client is None:
        return
    safe_payload = fail_closed_mask(payload)
    client.trace(name=name, input=safe_payload)
    client.flush()


def build_workflow_trace(
    state: dict[str, Any],
    *,
    role: str,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Create a privacy-safe workflow trace without document or personal data."""
    steps: list[dict[str, Any]] = []
    for event in state.get("workflow_trace", []):
        if not isinstance(event, dict):
            continue
        safe_event = {
            key: event[key]
            for key in ("event", "tool_name", "success", "provider", "model", "node")
            if key in event
        }
        if "event" not in safe_event:
            continue
        steps.append(safe_event)

    providers: list[dict[str, str]] = []
    for response in state.get("llm_responses", []):
        if isinstance(response, dict):
            provider = {
                key: str(response[key])
                for key in ("provider", "model")
                if isinstance(response.get(key), str)
            }
            if provider:
                providers.append(provider)

    return {
        "tags": {
            "role": role,
            "case_id": case_id or "live",
        },
        "steps": steps,
        "tools": [
            step["tool_name"]
            for step in steps
            if isinstance(step.get("tool_name"), str)
        ],
        "providers": providers,
        "answer_present": bool(state.get("final_answer")),
    }
