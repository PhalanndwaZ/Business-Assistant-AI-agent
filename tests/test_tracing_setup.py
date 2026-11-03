from __future__ import annotations

from pathlib import Path

import pytest

from app.tracing.mask import MaskingError, fail_closed_mask, mask_sensitive
from evaluation.langfuse_setup.tracing import (
    build_langgraph_callback_handler,
    build_workflow_trace,
    send_trace,
    tracing_enabled,
)


def test_mask_sensitive_redacts_structured_private_fields() -> None:
    masked = mask_sensitive({
        "customer_name": "Alice",
        "answer": "Revenue increased",
        "uploaded_text": "confidential memo",
        "salary": 250000,
    })

    assert masked == {
        "customer_name": "[REDACTED]",
        "answer": "Revenue increased",
        "uploaded_text": "[REDACTED]",
        "salary": "[REDACTED]",
    }


def test_mask_failure_is_fail_closed() -> None:
    def broken_mask(_: object) -> object:
        raise RuntimeError("mask unavailable")

    assert fail_closed_mask({"answer": "private"}, broken_mask) == "[REDACTED]"


def test_tracing_disabled_sends_nothing(monkeypatch) -> None:
    monkeypatch.setenv("TRACING_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")

    send_trace({"answer": "unchanged"})

    assert not tracing_enabled()


def test_missing_mask_config_is_explicit(monkeypatch, tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(MaskingError, match="configuration is unavailable"):
        mask_sensitive({"answer": "test"}, missing)


def test_workflow_trace_contains_metadata_without_sensitive_payloads() -> None:
    trace = build_workflow_trace(
        {
            "workflow_trace": [
                {"event": "tool_call", "tool_name": "search_documents", "success": True},
                {"event": "tool_call", "tool_name": "run_analysis", "arguments": {"salary": 100000}},
            ],
            "llm_responses": [{"provider": "inception", "model": "mercury-3"}],
            "final_answer": "Safe summary",
        },
        role="sales",
        case_id="SEG-001",
        user_id="user-123",
    )
    serialized = repr(trace)
    assert trace["tags"]["role"] == "sales"
    assert trace["tags"]["case_id"] == "SEG-001"
    assert trace["tags"]["user_id_hash"] != "user-123"
    assert trace["tools"] == ["search_documents", "run_analysis"]
    assert "100000" not in serialized


def test_workflow_trace_includes_run_metadata_for_step_8() -> None:
    trace = build_workflow_trace(
        {
            "workflow_trace": [{"event": "tool_call", "tool_name": "search_documents"}],
            "llm_responses": [{"provider": "inception", "model": "mercury-3"}, {"provider": "groq", "model": "llama-3.1"}],
            "final_answer": "Safe summary",
        },
        role="sales",
        case_id="SEG-001",
        user_id="user-123",
        group="segments",
        run_number=2,
        conversation_id="conv-42",
        provider="groq",
        fallback_happened=True,
        moderation_status="passed",
    )

    assert trace["tags"]["role"] == "sales"
    assert trace["tags"]["group"] == "segments"
    assert trace["tags"]["provider"] == "groq"
    assert trace["tags"]["run_number"] == "2"
    assert trace["tags"]["conversation_id"] == "conv-42"
    assert trace["metadata"]["fallback_happened"] is True
    assert trace["metadata"]["moderation_status"] == "passed"


def test_langgraph_callback_handler_is_safe_when_tracing_disabled(monkeypatch) -> None:
    monkeypatch.setenv("TRACING_ENABLED", "false")
    callback = build_langgraph_callback_handler(
        role="sales",
        case_id="SEG-001",
        group="segments",
    )
    assert callback is None


def test_mask_sensitive_replaces_card_number_customer_and_salary_from_trace_payload() -> None:
    payload = {
        "message": "Customer: Alice Smith; card: 4111 1111 1111 1111; salary: 250000",
        "user": {"user_id": "user-42", "email": "alice@example.com"},
    }

    masked = mask_sensitive(payload)
    serialized = repr(masked)

    assert "Alice" not in serialized
    assert "4111" not in serialized
    assert "250000" not in serialized
    assert "alice@example.com" not in serialized
    assert "[REDACTED]" in serialized
