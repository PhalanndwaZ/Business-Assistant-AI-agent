"""Tests for the SQLite audit log and admin-only read endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import main
from app.audit_log import AuditLog
from app.auth.tokens import create_access_token


def test_audit_log_hashes_questions_and_never_stores_raw_text(
    tmp_path: Path,
) -> None:
    audit = AuditLog(tmp_path / "audit.sqlite3")
    question = "What is the confidential salary?"

    audit.record(
        user_id="user-sales-demo",
        role="sales",
        conversation_id="conversation-1",
        event_type="ask",
        target="/ask",
        decision="refused",
        reason_code="M3",
        duration_ms=12.5,
        question=question,
    )

    event = audit.list_recent()[0]
    assert event["question_hash"] is not None
    assert question not in str(event)
    assert event["decision"] == "refused"
    assert event["reason_code"] == "M3"
    assert event["duration_ms"] == 12.5


def test_audit_log_rejects_invalid_limits(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path / "audit.sqlite3")

    with pytest.raises(ValueError, match="between 1 and 500"):
        audit.list_recent(0)


def test_audit_endpoint_is_admin_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audit = AuditLog(tmp_path / "audit.sqlite3")
    audit.record(
        user_id="user-sales-demo",
        role="sales",
        conversation_id=None,
        event_type="login",
        target=None,
        decision="allowed",
        reason_code="authenticated",
    )
    monkeypatch.setattr(main, "_get_audit_log", lambda: audit)
    secret = "audit-endpoint-test-secret-that-is-long-enough"
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    client = TestClient(main.create_app())

    admin_token = create_access_token("user-admin-demo", secret)
    sales_token = create_access_token("user-sales-demo", secret)
    admin_response = client.get(
        "/audit",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    sales_response = client.get(
        "/audit",
        headers={"Authorization": f"Bearer {sales_token}"},
    )

    assert admin_response.status_code == 200
    assert admin_response.json()[0]["reason_code"] == "authenticated"
    assert sales_response.status_code == 403
