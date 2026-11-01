"""Tests for isolated Step 7 uploaded-document retrieval."""

from pathlib import Path

from app.conversation_store import ConversationStore
from app.uploads import UploadStore


class FixedEmbedder:
    """Produce deterministic vectors for retrieval tests."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one unit vector for each text."""
        return [[1.0, 0.0] for _ in texts]


def test_uploaded_search_is_isolated_to_owner_conversation(tmp_path: Path) -> None:
    """A user's chunks cannot be returned from another conversation or user."""
    database = tmp_path / "conversations.sqlite3"
    conversations = ConversationStore(database)
    conversations.claim_conversation("11111111-1111-1111-1111-111111111111", "user-a", "sales")
    conversations.claim_conversation("22222222-2222-2222-2222-222222222222", "user-b", "sales")
    store = UploadStore(database)
    vector = [1.0, 0.0]
    store.add(
        document_id="doc-a",
        conversation_id="11111111-1111-1111-1111-111111111111",
        user_id="user-a",
        name="strategy.pdf",
        extension="pdf",
        pages=1,
        chunks=[{
            "chunk_id": "doc-a-chunk-0001",
            "text": "Quarterly target is ten million rand.",
            "page_number": 1,
            "embedding": vector,
        }],
    )

    own_results = store.search(
        conversation_id="11111111-1111-1111-1111-111111111111",
        user_id="user-a",
        query_vector=vector,
        document_ids=None,
        min_similarity=0.0,
        top_k=4,
        embedder_model="test",
    )
    foreign_results = store.search(
        conversation_id="22222222-2222-2222-2222-222222222222",
        user_id="user-b",
        query_vector=vector,
        document_ids=None,
        min_similarity=0.0,
        top_k=4,
        embedder_model="test",
    )

    assert own_results[0]["origin"] == "uploaded"
    assert own_results[0]["page_number"] == 1
    assert foreign_results == []
