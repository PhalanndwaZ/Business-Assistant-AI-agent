"""Tests for local document parsing, chunking, and JSON vector storage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rag.ingest import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    _document_chunks,
    _read_manifest,
    _split_text,
    ingest_documents,
)
from app.rag.vector_store import JsonVectorStore, VectorStoreError
from app.config import EMBEDDING_DIMENSIONS


def test_split_text_uses_configured_overlap() -> None:
    """Long text produces bounded chunks with the configured overlap."""
    text = "x" * (CHUNK_SIZE + 20)

    chunks = _split_text(text)

    assert len(chunks) == 2
    assert len(chunks[0]) == CHUNK_SIZE
    assert len(chunks[1]) == CHUNK_OVERLAP + 20
    assert chunks[0][-CHUNK_OVERLAP:] == chunks[1][:CHUNK_OVERLAP]


def test_document_chunks_preserve_manifest_metadata(tmp_path: Path) -> None:
    """Chunk IDs and metadata derive from the document manifest."""
    document = tmp_path / "policy.md"
    document.write_text("Synthetic returns policy.", encoding="utf-8")
    entry = {
        "document_id": "policy",
        "file": "policy.md",
        "document_type": "policy",
        "document_date": "2024-01-01",
    }

    chunks = _document_chunks(entry, tmp_path)

    assert chunks[0]["chunk_id"] == "policy-chunk-0001"
    assert chunks[0]["document_type"] == "policy"
    assert chunks[0]["page_number"] is None


def test_manifest_rejects_paths_outside_documents_directory(
    tmp_path: Path,
) -> None:
    """Manifest file paths cannot escape the configured documents directory."""
    outside_file = tmp_path.parent / "outside.md"
    outside_file.write_text("not in documents", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "document_id": "outside",
                    "file": "../outside.md",
                    "document_type": "test",
                    "document_date": "2024-01-01",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes its directory"):
        _read_manifest(tmp_path)


def test_phase_six_sample_documents_are_synthetic_and_fully_manifested() -> None:
    """The Phase 6 sample set is readable, labelled, dated, and covers required types."""
    documents_dir = Path(__file__).resolve().parents[1] / "data" / "documents"
    manifest = _read_manifest(documents_dir)
    document_types = {entry["document_type"] for entry in manifest}
    contents = {
        entry["document_id"]: (
            documents_dir / entry["file"]
        ).read_text(encoding="utf-8")
        for entry in manifest
    }

    assert {"policy", "management_report", "meeting_notes", "security_test"} <= (
        document_types
    )
    assert sum(
        entry["document_type"] == "management_report" for entry in manifest
    ) >= 2
    assert all("synthetic" in content.casefold() for content in contents.values())

    december_report = next(
        content
        for document_id, content in contents.items()
        if document_id == "management-report-2024-12"
    ).casefold()
    assert "fewer completed orders than november" in december_report
    assert "supplier delays" in december_report

    injection_note = next(
        content
        for document_id, content in contents.items()
        if document_id == "security-test-note"
    ).casefold()
    assert "ignore previous instructions" in injection_note
    assert "untrusted document content" in injection_note


def test_vector_store_replaces_document_chunks_without_duplicates(
    tmp_path: Path,
) -> None:
    """Replacing an ingested document keeps one current chunk per ID."""
    store = JsonVectorStore(tmp_path / "chunks.json")
    base_chunk = {
        "document_id": "policy",
        "document_name": "policy.md",
        "document_type": "policy",
        "document_date": "2024-01-01",
        "chunk_id": "policy-chunk-0001",
        "text": "Policy text.",
        "embedding": [0.0] * EMBEDDING_DIMENSIONS,
    }

    store.replace_document_chunks("policy", [base_chunk], "mistral-embed")
    store.replace_document_chunks(
        "policy",
        [{**base_chunk, "text": "Updated policy text."}],
        "mistral-embed",
    )
    persisted = store.load()

    assert len(persisted["chunks"]) == 1
    assert persisted["chunks"][0]["text"] == "Updated policy text."


def test_vector_store_rejects_mixed_embedding_models(tmp_path: Path) -> None:
    """One vector store cannot mix vectors from different models."""
    store = JsonVectorStore(tmp_path / "chunks.json")
    store.replace_document_chunks("one", [], "model-one")

    with pytest.raises(VectorStoreError, match="Cannot mix embedding models"):
        store.replace_document_chunks("two", [], "model-two")


def test_vector_store_rejects_non_finite_embedding_values(
    tmp_path: Path,
) -> None:
    """NaN and infinite coordinates cannot be persisted as valid vectors."""
    store = JsonVectorStore(tmp_path / "chunks.json")
    chunk = {
        "document_id": "policy",
        "document_name": "policy.md",
        "document_type": "policy",
        "document_date": "2024-01-01",
        "chunk_id": "policy-chunk-0001",
        "text": "Policy text.",
        "embedding": [float("nan")] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
    }
    store.save(
        {
            "embedding_model": "mistral-embed",
            "embedding_dimensions": EMBEDDING_DIMENSIONS,
            "chunks": [chunk],
        }
    )

    with pytest.raises(VectorStoreError, match="invalid embedding vector"):
        store.load()


def test_vector_store_prunes_documents_removed_from_manifest(
    tmp_path: Path,
) -> None:
    """Reconciliation removes stale document chunks but retains listed ones."""
    store = JsonVectorStore(tmp_path / "chunks.json")
    chunks = [
        {
            "document_id": document_id,
            "document_name": f"{document_id}.md",
            "document_type": "policy",
            "document_date": "2024-01-01",
            "chunk_id": f"{document_id}-chunk-0001",
            "text": "Policy text.",
            "embedding": [0.0] * EMBEDDING_DIMENSIONS,
        }
        for document_id in ("current", "removed")
    ]
    store.save(
        {
            "embedding_model": "mistral-embed",
            "embedding_dimensions": EMBEDDING_DIMENSIONS,
            "chunks": chunks,
        }
    )

    store.retain_documents({"current"}, "mistral-embed")

    assert [chunk["document_id"] for chunk in store.load()["chunks"]] == ["current"]


def test_ingestion_embeds_all_manifest_documents_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repeated ingestion stores one metadata-complete embedding per chunk."""
    documents_dir = tmp_path / "documents"
    documents_dir.mkdir()
    (documents_dir / "policy.md").write_text(
        "Synthetic policy text for embedding.", encoding="utf-8"
    )
    (documents_dir / "notes.txt").write_text(
        "Synthetic operations meeting notes.", encoding="utf-8"
    )
    manifest = [
        {
            "document_id": "policy",
            "file": "policy.md",
            "document_type": "policy",
            "document_date": "2024-01-01",
        },
        {
            "document_id": "notes",
            "file": "notes.txt",
            "document_type": "meeting_notes",
            "document_date": "2024-02-01",
        },
    ]
    (documents_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    vector_store_path = tmp_path / "chunks.json"
    settings = type(
        "TestSettings",
        (),
        {
            "documents_dir": documents_dir,
            "mistral_api_key": "test-key",
            "mistral_embedding_model": "test-embed",
            "vector_store_path": vector_store_path,
        },
    )()
    monkeypatch.setattr("app.rag.ingest.load_settings", lambda: settings)

    class FixedEmbedder:
        """Return correctly sized deterministic vectors without network access."""

        def __init__(self, api_key: str, model: str) -> None:
            assert api_key == "test-key"
            assert model == "test-embed"

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [
                [float(index)] * EMBEDDING_DIMENSIONS
                for index, _text in enumerate(texts)
            ]

    monkeypatch.setattr("app.rag.ingest.MistralEmbedder", FixedEmbedder)

    first_count = ingest_documents()
    first_store = JsonVectorStore(vector_store_path).load()
    second_count = ingest_documents()
    second_store = JsonVectorStore(vector_store_path).load()

    assert first_count == second_count == len(manifest)
    assert second_store["embedding_model"] == "test-embed"
    assert second_store["embedding_dimensions"] == EMBEDDING_DIMENSIONS
    assert len(second_store["chunks"]) == len(manifest)
    assert len({chunk["chunk_id"] for chunk in second_store["chunks"]}) == len(
        second_store["chunks"]
    )
    assert {
        (chunk["document_id"], chunk["document_type"], chunk["document_date"])
        for chunk in second_store["chunks"]
    } == {
        ("policy", "policy", "2024-01-01"),
        ("notes", "meeting_notes", "2024-02-01"),
    }
    assert all(
        {
            "document_name",
            "text",
            "embedding",
            "page_number",
            "uploaded_at",
        }
        <= chunk.keys()
        for chunk in second_store["chunks"]
    )
    assert [chunk["chunk_id"] for chunk in first_store["chunks"]] == [
        chunk["chunk_id"] for chunk in second_store["chunks"]
    ]
