"""Offline tests for the MongoDB ingestion entry point."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Sequence

from app.config import EMBEDDING_DIMENSIONS, Settings
from scripts import ingest_mongodb


class FakeStore:
    """Capture ingestion operations without connecting to MongoDB."""

    def __init__(self, _uri: str, _database_name: str) -> None:
        self.documents: dict[str, tuple[dict[str, str], str, list[dict[str, Any]]]] = {}
        self.policies: dict[str, dict[str, Any]] = {}
        self.retained_ids: set[str] = set()
        self.closed = False

    def ping(self) -> None:
        return None

    def ensure_indexes(self) -> None:
        return None

    def replace_document(
        self,
        metadata: dict[str, str],
        content: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        self.documents[metadata["document_id"]] = (metadata, content, chunks)

    def retain_documents(self, document_ids: set[str]) -> None:
        self.retained_ids = document_ids

    def replace_policy(self, policy_id: str, rules: dict[str, Any]) -> None:
        self.policies[policy_id] = rules

    def close(self) -> None:
        self.closed = True


class FakeEmbedder:
    """Return well-shaped deterministic vectors without an API call."""

    def __init__(self, _api_key: str, _model: str) -> None:
        return None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * EMBEDDING_DIMENSIONS for _ in texts]


def test_ingestion_stores_manifest_documents_chunks_and_runtime_policies(
    monkeypatch: Any,
) -> None:
    settings = Settings(
        groq_api_key="unused",
        mistral_api_key="unused",
        groq_model="unused",
        mistral_embedding_model="mistral-embed",
        as_of_date=date(2025, 1, 15),
        min_similarity=0.84,
        top_k=4,
        max_rows=100,
        max_steps=8,
        max_retries=2,
        data_dir=Path("tests/fixtures/business_data").resolve(),
        documents_dir=Path("data/documents").resolve(),
        vector_store_path=Path("data/vector_store/chunks.json"),
        mongodb_enabled=True,
    )
    captured: dict[str, FakeStore] = {}

    def create_store(uri: str, database_name: str) -> FakeStore:
        store = FakeStore(uri, database_name)
        captured["store"] = store
        return store

    monkeypatch.setattr(
        ingest_mongodb,
        "load_settings",
        lambda **_kwargs: settings,
    )
    monkeypatch.setattr(ingest_mongodb, "MongoStore", create_store)
    monkeypatch.setattr(ingest_mongodb, "MistralEmbedder", FakeEmbedder)

    document_count, chunk_count = ingest_mongodb.ingest()
    store = captured["store"]

    assert document_count == 10
    assert chunk_count == sum(
        len(document[2]) for document in store.documents.values()
    )
    assert store.retained_ids == set(store.documents)
    assert {"access_control", "moderation_rules"} == set(store.policies)
    assert all(
        chunk["embedding_model"] == "mistral-embed"
        for _, _, chunks in store.documents.values()
        for chunk in chunks
    )
    assert all(
        "synthetic" in content.casefold()
        for _, content, _ in store.documents.values()
    )
    assert store.closed
