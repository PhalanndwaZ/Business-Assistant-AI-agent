"""SQLite audit events that exclude raw questions and sensitive content."""

from __future__ import annotations

import hashlib
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLog:
    """Persist access, moderation, and workflow decisions in SQLite."""

    def __init__(self, database_path: Path) -> None:
        """Create the audit table and retain its database path."""
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_id TEXT,
                    role TEXT,
                    conversation_id TEXT,
                    event_type TEXT NOT NULL,
                    target TEXT,
                    decision TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    duration_ms REAL,
                    question_hash TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
                ON audit_log(timestamp DESC)
                """
            )

    def record(
        self,
        *,
        user_id: str | None,
        role: str | None,
        conversation_id: str | None,
        event_type: str,
        target: str | None,
        decision: str,
        reason_code: str,
        duration_ms: float | None = None,
        question: str | None = None,
    ) -> None:
        """Write one event and hash the question instead of storing its text."""
        if not event_type or not decision or not reason_code:
            raise ValueError("Audit event type, decision, and reason are required.")
        if duration_ms is not None and (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, (int, float))
            or not math.isfinite(duration_ms)
            or duration_ms < 0
        ):
            raise ValueError("Audit duration must be a non-negative number.")
        question_hash = (
            hashlib.sha256(question.encode("utf-8")).hexdigest()
            if question is not None
            else None
        )
        timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO audit_log (
                    timestamp,
                    user_id,
                    role,
                    conversation_id,
                    event_type,
                    target,
                    decision,
                    reason_code,
                    duration_ms,
                    question_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    user_id,
                    role,
                    conversation_id,
                    event_type,
                    target,
                    decision,
                    reason_code,
                    duration_ms,
                    question_hash,
                ),
            )

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the newest audit events without any raw question content."""
        if isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("Audit limit must be between 1 and 500.")
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT id, timestamp, user_id, role, conversation_id, event_type,
                       target, decision, reason_code, duration_ms, question_hash
                FROM audit_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
