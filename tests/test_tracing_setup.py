from __future__ import annotations

from pathlib import Path

import pytest

from app.tracing.mask import MaskingError, fail_closed_mask, mask_sensitive
from evaluation.langfuse_setup.tracing import build_workflow_trace, send_trace, tracing_enabled


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
    )
    serialized = repr(trace)
    assert trace["tags"] == {"role": "sales", "case_id": "SEG-001"}
    assert trace["tools"] == ["search_documents", "run_analysis"]
    assert "100000" not in serialized
