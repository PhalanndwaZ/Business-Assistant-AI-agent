from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from app.feature_config import load_feature_config


class DraftStore:
    """Persist conversation drafts with user ownership."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                draft_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                purpose TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                facts_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                edited INTEGER NOT NULL DEFAULT 0
            )
            """
        )

    def _row(self, row: sqlite3.Row) -> dict[str, object]:
        return {
            "draft_id": row["draft_id"],
            "conversation_id": row["conversation_id"],
            "purpose": row["purpose"],
            "subject": row["subject"],
            "body": row["body"],
            "facts_used": json.loads(row["facts_json"]),
            "warnings": json.loads(row["warnings_json"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "edited": bool(row["edited"]),
        }

    def create(
        self,
        *,
        conversation_id: str,
        user_id: str,
        role: str,
        purpose: str,
        subject: str,
        body: str,
        facts: list[dict[str, object]],
        warnings: list[str],
    ) -> dict[str, object]:
        config = load_feature_config("drafts.json")
        now = datetime.now(timezone.utc)
        draft_id = "d_" + uuid4().hex
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            self._ensure_schema(connection)
            hourly = connection.execute(
                """
                SELECT COUNT(*) FROM drafts
                WHERE conversation_id = ? AND user_id = ? AND created_at >= ?
                """,
                (conversation_id, user_id, datetime.fromtimestamp(now.timestamp() - 3600, timezone.utc).isoformat()),
            ).fetchone()[0]
            if hourly >= int(config["drafts_per_conversation_per_hour"]):
                raise ValueError("Draft conversation hourly limit reached.")
            daily = connection.execute(
                """
                SELECT COUNT(*) FROM drafts
                WHERE user_id = ? AND substr(created_at, 1, 10) = ?
                """,
                (user_id, now.date().isoformat()),
            ).fetchone()[0]
            if daily >= int(config["drafts_per_user_per_day"]):
                raise ValueError("Draft daily limit reached.")
            connection.execute(
                """
                INSERT INTO drafts (
                    draft_id, conversation_id, user_id, role, purpose, subject, body,
                    facts_json, warnings_json, status, created_at, edited
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, 0)
                """,
                (
                    draft_id, conversation_id, user_id, role, purpose, subject, body,
                    json.dumps(facts), json.dumps(warnings), now.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)
            ).fetchone()
        return self._row(row)

    def list(self, conversation_id: str, user_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT * FROM drafts WHERE conversation_id = ? AND user_id = ?
                ORDER BY created_at DESC
                """,
                (conversation_id, user_id),
            ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, draft_id: str, user_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            self._ensure_schema(connection)
            row = connection.execute(
                "SELECT * FROM drafts WHERE draft_id = ? AND user_id = ?",
                (draft_id, user_id),
            ).fetchone()
        return self._row(row) if row else None

    def update(
        self,
        draft_id: str,
        user_id: str,
        *,
        subject: str | None = None,
        body: str | None = None,
        status: str | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, object] | None:
        if status not in {None, "draft", "approved", "discarded"}:
            raise ValueError("Invalid draft status.")
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            self._ensure_schema(connection)
            current = connection.execute(
                "SELECT * FROM drafts WHERE draft_id = ? AND user_id = ?",
                (draft_id, user_id),
            ).fetchone()
            if current is None:
                return None
            warnings = (
                json.loads(current["warnings_json"])
                if warnings is None
                else warnings
            )
            next_subject = current["subject"] if subject is None else subject
            next_body = current["body"] if body is None else body
            next_status = current["status"] if status is None else status
            connection.execute(
                """
                UPDATE drafts SET subject = ?, body = ?, status = ?, edited = 1,
                                 warnings_json = ?
                WHERE draft_id = ? AND user_id = ?
                """,
                (
                    next_subject, next_body, next_status, json.dumps(warnings),
                    draft_id, user_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM drafts WHERE draft_id = ? AND user_id = ?",
                (draft_id, user_id),
            ).fetchone()
        return self._row(row)
