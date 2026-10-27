"""Tests for cosine ranking, thresholding, and metadata filters."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest

from app.config import DEFAULT_MIN_SIMILARITY, EMBEDDING_DIMENSIONS
from app.rag.retriever import DocumentRetriever
from app.rag.vector_store import JsonVectorStore


class FixedEmbedder:
    """Return fixed vectors for deterministic retrieval tests."""

    def __init__(self, vector: list[float]) -> None:
        """Retain the vector returned for every query."""
        self.vector = vector

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one copied vector per input query."""
        return [self.vector.copy() for _ in texts]


def _chunk(
    document_id: str,
    document_type: str,
    vector: list[float],
) -> dict[str, object]:
    """Construct one minimal valid stored chunk."""
    return {
        "document_id": document_id,
        "document_name": f"{document_id}.md",
        "document_type": document_type,
        "document_date": "2024-12-01",
        "chunk_id": f"{document_id}-chunk-0001",
        "text": f"Passage from {document_id}.",
        "embedding": vector,
    }


def _retriever(
    tmp_path: Path,
    chunks: list[dict[str, object]],
    query_vector: list[float],
    threshold: float,
) -> DocumentRetriever:
    """Persist test chunks and construct a retriever with a fixed embedder."""
    store_path = tmp_path / "chunks.json"
    JsonVectorStore(store_path).save(
        {
            "embedding_model": "mistral-embed",
            "embedding_dimensions": EMBEDDING_DIMENSIONS,
            "chunks": chunks,
        }
    )
    return DocumentRetriever(
        store_path,
        "mistral-embed",
        FixedEmbedder(query_vector),
        threshold,
        4,
    )


def test_search_ranks_cosine_matches_and_applies_filters(tmp_path: Path) -> None:
    """Retrieval ranks by cosine score and restricts document type."""
    query = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    diagonal = [0.0, 1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 2)
    retriever = _retriever(
        tmp_path,
        [
            _chunk("exact", "policy", query),
            _chunk("orthogonal", "report", diagonal),
        ],
        query,
        0.5,
    )

    result = retriever.search("returns", document_type="policy")

    assert len(result["results"]) == 1
    assert result["results"][0]["document_name"] == "exact.md"
    assert result["results"][0]["similarity"] == 1.0


def test_search_returns_explicit_no_results_below_threshold(
    tmp_path: Path,
) -> None:
    """A low-scoring passage does not leak through the relevance threshold."""
    query = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    unrelated = [0.0, 1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 2)
    retriever = _retriever(
        tmp_path,
        [_chunk("unrelated", "policy", unrelated)],
        query,
        0.5,
    )

    result = retriever.search("unknown content")

    assert result == {"results": [], "message": "No relevant passages found."}


def test_search_applies_calibrated_similarity_threshold(
    tmp_path: Path,
) -> None:
    """A passage just below the tuned cutoff is excluded, while a match remains."""
    query = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    below_threshold = [0.83, (1 - 0.83**2) ** 0.5] + [
        0.0
    ] * (EMBEDDING_DIMENSIONS - 2)
    retriever = _retriever(
        tmp_path,
        [
            _chunk("match", "report", query),
            _chunk("below-threshold", "report", below_threshold),
        ],
        query,
        DEFAULT_MIN_SIMILARITY,
    )

    result = retriever.search("relevant report")

    assert [item["document_name"] for item in result["results"]] == ["match.md"]
    assert result["results"][0]["similarity"] == 1.0


def test_search_filters_by_document_date(tmp_path: Path) -> None:
    """An optional date filter excludes passages outside the requested date."""
    query = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    november_chunk = _chunk("november", "report", query)
    november_chunk["document_date"] = "2024-11-30"
    december_chunk = _chunk("december", "report", query)
    december_chunk["document_date"] = "2024-12-31"
    retriever = _retriever(
        tmp_path,
        [november_chunk, december_chunk],
        query,
        0.5,
    )

    result = retriever.search("monthly report", document_date="2024-11-30")

    assert [item["document_name"] for item in result["results"]] == [
        "november.md"
    ]


def test_search_rejects_invalid_k(tmp_path: Path) -> None:
    """The per-request result count must be a positive integer."""
    query = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    retriever = _retriever(
        tmp_path,
        [_chunk("exact", "policy", query)],
        query,
        0.5,
    )

    with pytest.raises(ValueError, match="positive integer"):
        retriever.search("returns", k=1.5)  # type: ignore[arg-type]


def test_retriever_refuses_embedding_model_mismatch(tmp_path: Path) -> None:
    """The query embedder must match the stored vector model."""
    store_path = tmp_path / "chunks.json"
    JsonVectorStore(store_path).save(
        {
            "embedding_model": "other-model",
            "embedding_dimensions": EMBEDDING_DIMENSIONS,
            "chunks": [],
        }
    )

    with pytest.raises(ValueError, match="does not match configuration"):
        DocumentRetriever(
            store_path,
            "mistral-embed",
            FixedEmbedder([0.0] * EMBEDDING_DIMENSIONS),
            0.5,
            4,
        )
