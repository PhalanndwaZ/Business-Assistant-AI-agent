"""Tests for MongoDB document, policy, and report persistence."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import mongomock
import pytest

import app.mongodb as mongodb
from app.mongodb import (
    MongoStore,
    MongoStoreError,
    load_access_policy,
    load_moderation_rules,
)
from app.rag.retriever import DocumentRetriever


class FakeGridFSBucket:
    """Provide the GridFS stream API without requiring a MongoDB service."""

    def __init__(self, _database: Any, bucket_name: str) -> None:
        self.files: dict[str, bytes] = {}
        self.bucket_name = bucket_name

    def upload_from_stream(
        self,
        filename: str,
        source: Any,
        metadata: dict[str, Any],
    ) -> None:
        self.files[filename] = source.read()

    def open_download_stream_by_name(
        self,
        filename: str,
        revision: int,
    ) -> io.BytesIO:
        if filename not in self.files:
            from gridfs.errors import NoFile

            raise NoFile(filename)
        return io.BytesIO(self.files[filename])


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> MongoStore:
    """Use an isolated in-memory MongoDB-compatible database."""
    monkeypatch.setattr(mongodb, "MongoClient", mongomock.MongoClient)
    monkeypatch.setattr(mongodb, "GridFSBucket", FakeGridFSBucket)
    instance = MongoStore("mongodb://localhost", "test_database")
    instance.ensure_indexes()
    return instance


def test_document_chunks_are_replaced_and_stale_documents_removed(
    store: MongoStore,
) -> None:
    chunk = {
        "document_id": "policy",
        "chunk_id": "policy-chunk-0001",
        "text": "Updated policy text.",
        "embedding": [0.0] * 1024,
        "embedding_model": "mistral-embed",
        "department": "general",
        "classification": "internal",
    }

    store.replace_document(
        {"document_id": "policy", "document_type": "policy"},
        "Policy source text.",
        [chunk],
    )
    store.replace_document(
        {"document_id": "policy", "document_type": "policy"},
        "Updated source text.",
        [{**chunk, "text": "Updated chunk text."}],
    )

    assert store.documents.count_documents({}) == 1
    assert store.documents.find_one({"document_id": "policy"})["content"] == (
        "Updated source text."
    )
    assert store.list_chunks()[0]["text"] == "Updated chunk text."

    store.retain_documents(set())

    assert store.documents.count_documents({}) == 0
    assert store.list_chunks() == []


def test_policy_documents_are_loaded_by_stable_id(store: MongoStore) -> None:
    store.replace_policy("access_control", {"roles": {"sales": {}}})

    assert store.get_policy("access_control") == {"roles": {"sales": {}}}
    with pytest.raises(MongoStoreError, match="is missing"):
        store.get_policy("moderation_rules")


def test_mongodb_policy_controls_document_search(store: MongoStore) -> None:
    policy_path = Path("data/policy/access_policy.json")
    policy_data = json.loads(policy_path.read_text(encoding="utf-8"))
    store.replace_policy("access_control", policy_data)
    policy = load_access_policy(store)
    visible = {
        "document_id": "visible",
        "document_name": "visible.md",
        "document_type": "policy",
        "document_date": "2024-01-01",
        "department": "general",
        "classification": "internal",
        "chunk_id": "visible-chunk-0001",
        "text": "Visible policy passage.",
        "embedding": [1.0] + [0.0] * 1023,
        "embedding_model": "mistral-embed",
    }
    restricted = {
        **visible,
        "document_id": "restricted",
        "document_name": "restricted.md",
        "department": "hr",
        "classification": "restricted",
        "chunk_id": "restricted-chunk-0001",
    }
    store.replace_document(
        {"document_id": "visible", "document_type": "policy"},
        visible["text"],
        [visible],
    )
    store.replace_document(
        {"document_id": "restricted", "document_type": "policy"},
        restricted["text"],
        [restricted],
    )

    class FixedEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0] + [0.0] * 1023 for _ in texts]

    retriever = DocumentRetriever(
        None,
        "mistral-embed",
        FixedEmbedder(),
        0.5,
        4,
        mongo_store=store,
    )

    result = retriever.search(
        "policy",
        access_policy=policy,
        role="sales",
    )

    assert [item["document_name"] for item in result["results"]] == ["visible.md"]


def test_moderation_rules_are_stored_as_mongo_policy_documents(
    store: MongoStore,
) -> None:
    rules_path = Path("data/policy/moderation_rules.json")
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    store.replace_policy("moderation_rules", rules)

    assert load_moderation_rules(store) == rules


def test_generated_report_is_round_tripped_through_gridfs(
    store: MongoStore,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "report.docx"
    report_path.write_bytes(b"synthetic report contents")

    store.store_report(report_path.name, report_path)
    report = store.open_report(report_path.name)

    assert report is not None
    assert report.read() == b"synthetic report contents"
    report.close()


def test_report_filename_must_be_a_basename(
    store: MongoStore,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "report.docx"
    report_path.write_bytes(b"report")

    with pytest.raises(ValueError, match="basename"):
        store.store_report("../report.docx", report_path)
