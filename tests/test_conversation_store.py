"""Tests for persistent recent-turn storage."""

from __future__ import annotations

import sqlite3
from uuid import UUID, uuid4

import pytest

from app.conversation_store import (
    ConversationOwnershipError,
    ConversationStore,
)
from app.state import ToolResult


def test_conversation_store_persists_and_limits_recent_turns(tmp_path) -> None:
    """Stored conversation history survives store instances and respects cap."""
    database_path = tmp_path / "nested" / "conversations.sqlite3"
    conversation_id = uuid4()

    first_store = ConversationStore(database_path)
    assert first_store.load_recent_turns(conversation_id, 10) is None
    first_store.append_turn(conversation_id, "Question one", "Answer one")
    first_store.append_turn(conversation_id, "Question two", "Answer two")

    reopened_store = ConversationStore(database_path)

    assert reopened_store.load_recent_turns(conversation_id, 1) == [
        ("user", "Question two"),
        ("assistant", "Answer two"),
    ]
    assert reopened_store.load_recent_turns(conversation_id, 2) == [
        ("user", "Question one"),
        ("assistant", "Answer one"),
        ("user", "Question two"),
        ("assistant", "Answer two"),
    ]


def test_conversation_store_keeps_conversations_isolated(tmp_path) -> None:
    """A different ID cannot read another conversation's messages."""
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    first_id = uuid4()
    second_id: UUID = uuid4()
    store.append_turn(first_id, "Private question", "Private answer")

    assert store.load_recent_turns(second_id, 10) is None


def test_conversation_store_persists_recent_tool_evidence(tmp_path) -> None:
    """Tool result IDs and retrieved document chunks survive API restarts."""
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    conversation_id = uuid4()
    tool_results: list[ToolResult] = [
        {
            "call_id": "category-call",
            "tool_name": "run_analysis",
            "arguments": {
                "analysis_name": "revenue_by_category",
                "parameters": {"start": "2024-01-01", "end": "2024-12-31"},
            },
            "result": {
                "analysis": "revenue_by_category",
                "data": [
                    {
                        "category": "Furniture",
                        "revenue_cents": 24532474,
                        "units": 526,
                    }
                ],
            },
            "success": True,
        }
    ]
    chunks = [
        {
            "document_name": "annual_report.md",
            "text": "Synthetic sample passage.",
        }
    ]
    store.append_turn(
        conversation_id,
        "Which category led in 2024?",
        "Furniture led.",
        tool_results,
        chunks,
    )

    loaded_results, loaded_chunks = store.load_recent_evidence(conversation_id, 10)

    assert loaded_results == tool_results
    assert loaded_chunks == chunks


def test_conversation_ownership_blocks_other_users(tmp_path) -> None:
    """Only the account that claimed a conversation can read or append turns."""
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    conversation_id = uuid4()
    store.claim_conversation(conversation_id, "user-sales-demo", "sales")
    store.append_turn(
        conversation_id,
        "Sales question",
        "Sales answer",
        user_id="user-sales-demo",
        role="sales",
    )

    with pytest.raises(ConversationOwnershipError):
        store.claim_conversation(conversation_id, "user-hr-demo", "hr")
    with pytest.raises(ConversationOwnershipError):
        store.load_recent_turns(
            conversation_id,
            10,
            user_id="user-hr-demo",
        )
    with pytest.raises(ConversationOwnershipError):
        store.append_turn(
            conversation_id,
            "Private question",
            "Private answer",
            user_id="user-hr-demo",
            role="hr",
        )


def test_legacy_conversations_migrate_as_unowned_and_cannot_be_claimed(
    tmp_path,
) -> None:
    """Old conversations remain stored but fail closed without an owner."""
    database_path = tmp_path / "conversations.sqlite3"
    conversation_id = uuid4()
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        "INSERT INTO conversations (id) VALUES (?)",
        (str(conversation_id),),
    )
    connection.commit()
    connection.close()

    store = ConversationStore(database_path)
    identity = store.get_conversation_identity(conversation_id)
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(conversations)")
        }

    assert identity is not None
    assert identity.user_id is None
    assert {"user_id", "role"} <= columns
    with pytest.raises(ConversationOwnershipError):
        store.claim_conversation(conversation_id, "user-sales-demo", "sales")
