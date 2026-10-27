"""SQLite persistence for short conversation histories keyed by UUID."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

from app.state import ToolResult


class ConversationStore:
    """Store completed user/assistant turns in a local SQLite database."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def load_recent_turns(
        self,
        conversation_id: UUID,
        max_turns: int,
    ) -> list[tuple[str, str]] | None:
        """Return recent conversation messages in order, or None if unknown."""
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (str(conversation_id),),
            ).fetchone()
            if exists is None:
                return None
            rows = connection.execute(
                """
                SELECT role, content
                FROM (
                    SELECT id, role, content
                    FROM conversation_messages
                    WHERE conversation_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
                """,
                (str(conversation_id), max_turns * 2),
            ).fetchall()
        return [(str(role), str(content)) for role, content in rows]

    def load_recent_evidence(
        self,
        conversation_id: UUID,
        max_turns: int,
    ) -> tuple[list[ToolResult], list[dict[str, object]]]:
        """Load tool results and retrieved passages from the recent turns."""
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT evidence.tool_results_json, evidence.retrieved_chunks_json
                FROM conversation_turn_evidence AS evidence
                JOIN conversation_messages AS messages
                  ON messages.id = evidence.assistant_message_id
                WHERE evidence.conversation_id = ?
                  AND messages.role = 'assistant'
                ORDER BY messages.id DESC
                LIMIT ?
                """,
                (str(conversation_id), max_turns),
            ).fetchall()

        tool_results: list[ToolResult] = []
        retrieved_chunks: list[dict[str, object]] = []
        for tool_results_json, chunks_json in reversed(rows):
            stored_results = json.loads(tool_results_json)
            stored_chunks = json.loads(chunks_json)
            tool_results.extend(stored_results)
            retrieved_chunks.extend(stored_chunks)
        return tool_results, retrieved_chunks

    def append_turn(
        self,
        conversation_id: UUID,
        question: str,
        answer: str,
        tool_results: list[ToolResult] | None = None,
        retrieved_chunks: list[dict[str, object]] | None = None,
    ) -> None:
        """Persist a completed answer together with the evidence behind it."""
        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO conversations (id) VALUES (?)",
                (str(conversation_id),),
            )
            connection.execute(
                """
                INSERT INTO conversation_messages (conversation_id, role, content)
                VALUES (?, ?, ?)
                """,
                (str(conversation_id), "user", question),
            )
            cursor = connection.execute(
                """
                INSERT INTO conversation_messages (conversation_id, role, content)
                VALUES (?, ?, ?)
                """,
                (str(conversation_id), "assistant", answer),
            )
            assistant_message_id = cursor.lastrowid
            connection.execute(
                """
                INSERT INTO conversation_turn_evidence (
                    conversation_id,
                    assistant_message_id,
                    tool_results_json,
                    retrieved_chunks_json
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(conversation_id),
                    assistant_message_id,
                    json.dumps(tool_results or [], ensure_ascii=False, default=str),
                    json.dumps(
                        retrieved_chunks or [],
                        ensure_ascii=False,
                        default=str,
                    ),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_turn_evidence (
                conversation_id TEXT NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
                assistant_message_id INTEGER PRIMARY KEY
                    REFERENCES conversation_messages(id) ON DELETE CASCADE,
                tool_results_json TEXT NOT NULL,
                retrieved_chunks_json TEXT NOT NULL
            )
            """
        )
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Commit or roll back a database operation and always close it."""
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()
