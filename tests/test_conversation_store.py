"""Tests for persistent recent-turn storage."""

from __future__ import annotations

from uuid import UUID, uuid4

from app.conversation_store import ConversationStore
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
