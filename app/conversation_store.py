"""SQLite persistence for short conversation histories keyed by UUID."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

from app.state import ToolResult


class ConversationOwnershipError(ValueError):
    """Raised when a conversation does not belong to the authenticated user."""


@dataclass(frozen=True)
class ConversationIdentity:
    """Record the owner and role stored when a conversation was created."""

    user_id: str | None
    role: str | None


class ConversationStore:
    """Store completed user/assistant turns in a local SQLite database."""

    def __init__(self, database_path: Path) -> None:
        """Retain the SQLite path used by subsequent store operations."""
        self.database_path = database_path

    def load_recent_turns(
        self,
        conversation_id: UUID,
        max_turns: int,
        *,
        user_id: str | None = None,
    ) -> list[tuple[str, str]] | None:
        """Return recent conversation messages in order, or None if unknown."""
        with self._connection() as connection:
            if user_id is not None:
                self._require_owner(connection, conversation_id, user_id)
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
        *,
        user_id: str | None = None,
    ) -> tuple[list[ToolResult], list[dict[str, object]]]:
        """Load tool results and retrieved passages from the recent turns."""
        with self._connection() as connection:
            if user_id is not None:
                self._require_owner(connection, conversation_id, user_id)
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
        *,
        user_id: str | None = None,
        role: str | None = None,
    ) -> None:
        """Persist a completed answer together with the evidence behind it."""
        if (user_id is None) != (role is None):
            raise ValueError("user_id and role must be supplied together.")
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO conversations (id, user_id, role)
                VALUES (?, ?, ?)
                """,
                (str(conversation_id), user_id, role),
            )
            if user_id is not None:
                self._require_owner(connection, conversation_id, user_id)
            else:
                identity = self._get_conversation_identity(
                    connection,
                    conversation_id,
                )
                if identity is not None and identity.user_id is not None:
                    raise ConversationOwnershipError(
                        "Conversation ownership does not match."
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

    def claim_conversation(
        self,
        conversation_id: UUID,
        user_id: str,
        role: str,
    ) -> ConversationIdentity:
        """Create an owned conversation or verify ownership of an existing ID."""
        if not user_id or not role:
            raise ValueError("user_id and role must not be empty.")
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO conversations (id, user_id, role)
                VALUES (?, ?, ?)
                """,
                (str(conversation_id), user_id, role),
            )
            identity = self._get_conversation_identity(
                connection,
                conversation_id,
            )
            if identity is None:
                raise sqlite3.DatabaseError(
                    "Conversation could not be created or loaded."
                )
            if identity.user_id != user_id:
                raise ConversationOwnershipError(
                    "Conversation ownership does not match."
                )
            return identity

    def get_conversation_identity(
        self,
        conversation_id: UUID,
    ) -> ConversationIdentity | None:
        """Return the persisted owner and role without reading message content."""
        with self._connection() as connection:
            return self._get_conversation_identity(connection, conversation_id)

    @staticmethod
    def _get_conversation_identity(
        connection: sqlite3.Connection,
        conversation_id: UUID,
    ) -> ConversationIdentity | None:
        """Read ownership metadata for one conversation ID."""
        row = connection.execute(
            "SELECT user_id, role FROM conversations WHERE id = ?",
            (str(conversation_id),),
        ).fetchone()
        if row is None:
            return None
        return ConversationIdentity(
            user_id=str(row[0]) if row[0] is not None else None,
            role=str(row[1]) if row[1] is not None else None,
        )

    @classmethod
    def _require_owner(
        cls,
        connection: sqlite3.Connection,
        conversation_id: UUID,
        user_id: str,
    ) -> None:
        """Reject missing, legacy-unowned, or foreign-owned conversations."""
        identity = cls._get_conversation_identity(connection, conversation_id)
        if identity is None or identity.user_id != user_id:
            raise ConversationOwnershipError(
                "Conversation ownership does not match."
            )

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                role TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(conversations)"
            ).fetchall()
        }
        for column in ("user_id", "role"):
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE conversations ADD COLUMN {column} TEXT"
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
