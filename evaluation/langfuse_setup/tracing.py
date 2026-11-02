from __future__ import annotations

import inspect
import os
from typing import Any, Protocol

from app.tracing.mask import fail_closed_mask, hash_user_id


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


def build_langgraph_callback_handler(
    *,
    role: str | None = None,
    case_id: str | None = None,
    group: str | None = None,
    run_number: int | None = None,
    user_id: str | None = None,
    conversation_id: str | None = None,
    provider: str | None = None,
    fallback_happened: bool | None = None,
    moderation_status: str | None = None,
) -> Any | None:
    """Build the Langfuse LangGraph callback when tracing is active."""
    if not tracing_enabled():
        return None
    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        return None

    tags: dict[str, str] = {"role": role or "unknown"}
    if case_id:
        tags["case_id"] = case_id
    if group:
        tags["group"] = group
    if provider:
        tags["provider"] = provider
    if run_number is not None:
        tags["run_number"] = str(run_number)
    if user_id:
        tags["user_id_hash"] = hash_user_id(user_id)
    if conversation_id:
        tags["conversation_id"] = str(conversation_id)

    metadata: dict[str, Any] = {}
    if provider:
        metadata["provider"] = provider
    if fallback_happened is not None:
        metadata["fallback_happened"] = bool(fallback_happened)
    if moderation_status:
        metadata["moderation_status"] = moderation_status
    if conversation_id:
        metadata["conversation_id"] = str(conversation_id)

    try:
        parameters = inspect.signature(CallbackHandler).parameters
        kwargs: dict[str, Any] = {}
        if "tags" in parameters:
            kwargs["tags"] = tags
        if "metadata" in parameters:
            kwargs["metadata"] = metadata
        if "user_id" in parameters and user_id:
            kwargs["user_id"] = user_id
        if "case_id" in parameters and case_id:
            kwargs["case_id"] = case_id
        if "conversation_id" in parameters and conversation_id:
            kwargs["conversation_id"] = str(conversation_id)
        if "session_id" in parameters and conversation_id:
            kwargs["session_id"] = str(conversation_id)
        if kwargs:
            return CallbackHandler(**kwargs)
    except (TypeError, ValueError):
        pass
    return CallbackHandler()


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
    user_id: str | None = None,
    group: str | None = None,
    run_number: int | None = None,
    conversation_id: str | None = None,
    provider: str | None = None,
    fallback_happened: bool | None = None,
    moderation_status: str | None = None,
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
            provider_record = {
                key: str(response[key])
                for key in ("provider", "model")
                if isinstance(response.get(key), str)
            }
            if provider_record:
                providers.append(provider_record)

    provider_name = provider or (
        providers[-1].get("provider") if providers else None
    )
    fallback = fallback_happened
    if fallback is None:
        fallback = len(providers) > 1

    tags: dict[str, str] = {
        "role": role,
        "case_id": case_id or "live",
    }
    if group:
        tags["group"] = group
    if provider_name:
        tags["provider"] = provider_name
    if run_number is not None:
        tags["run_number"] = str(run_number)
    if user_id:
        tags["user_id_hash"] = hash_user_id(user_id)
    if conversation_id:
        tags["conversation_id"] = str(conversation_id)

    metadata: dict[str, Any] = {}
    if conversation_id:
        metadata["conversation_id"] = str(conversation_id)
    if provider_name:
        metadata["provider"] = provider_name
    if fallback is not None:
        metadata["fallback_happened"] = bool(fallback)
    if moderation_status:
        metadata["moderation_status"] = moderation_status

    return {
        "tags": tags,
        "metadata": metadata,
        "steps": steps,
        "tools": [
            step["tool_name"]
            for step in steps
            if isinstance(step.get("tool_name"), str)
        ],
        "providers": providers,
        "answer_present": bool(state.get("final_answer")),
    }
