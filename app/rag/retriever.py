"""In-memory cosine-similarity retrieval with a configured relevance threshold."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from app.config import EMBEDDING_DIMENSIONS
from app.policy.policy import AccessPolicy
from app.rag.embeddings import MistralEmbedder
from app.rag.vector_store import JsonVectorStore


class DocumentRetriever:
    """Load document vectors once and rank relevant passages for each query."""

    def __init__(
        self,
        store_path: Path,
        embedding_model: str,
        embedder: MistralEmbedder,
        min_similarity: float,
        top_k: int,
    ) -> None:
        """Load vectors and refuse model, dimension, or limit mismatches."""
        if not 0.0 <= min_similarity <= 1.0:
            raise ValueError("min_similarity must be between 0 and 1.")
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")
        stored = JsonVectorStore(store_path).load()
        if stored["embedding_model"] != embedding_model:
            raise ValueError(
                "Vector store embedding model does not match configuration: "
                f"{stored['embedding_model']} vs {embedding_model}."
            )
        if stored["embedding_dimensions"] != EMBEDDING_DIMENSIONS:
            raise ValueError("Vector store embedding dimensions do not match.")
        self._chunks: list[dict[str, Any]] = stored["chunks"]
        self._matrix = (
            np.asarray([chunk["embedding"] for chunk in self._chunks], dtype=float)
            if self._chunks
            else np.empty((0, EMBEDDING_DIMENSIONS), dtype=float)
        )
        self._embedder = embedder
        self._min_similarity = min_similarity
        self._top_k = top_k

    def search(
        self,
        query: str,
        document_type: str | None = None,
        document_date: str | None = None,
        k: int | None = None,
        *,
        access_policy: AccessPolicy | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        """Return the top relevant passages after metadata and threshold filters."""
        if not query.strip():
            raise ValueError("query cannot be empty.")
        if (access_policy is None) != (role is None):
            raise ValueError("access_policy and role must be supplied together.")
        result_count = self._top_k if k is None else k
        if (
            isinstance(result_count, bool)
            or not isinstance(result_count, int)
            or result_count < 1
        ):
            raise ValueError("k must be a positive integer.")
        cutoff_date = None
        if document_date is not None:
            try:
                cutoff_date = date.fromisoformat(document_date)
            except ValueError as exc:
                raise ValueError(
                    "document_date must be an ISO 8601 calendar date."
                ) from exc
        candidates = [
            index
            for index, chunk in enumerate(self._chunks)
            if (document_type is None or chunk["document_type"] == document_type)
            and (
                cutoff_date is None
                or date.fromisoformat(chunk["document_date"]) == cutoff_date
            )
            and (
                access_policy is None
                or access_policy.can_access_document(
                    role or "",
                    chunk.get("department"),
                    chunk.get("classification"),
                )
            )
        ]
        if not candidates:
            return self._no_results()
        query_vector = np.asarray(self._embedder.embed([query])[0], dtype=float)
        if (
            query_vector.shape != (EMBEDDING_DIMENSIONS,)
            or not np.isfinite(query_vector).all()
        ):
            raise ValueError(
                "Query embedding must have the configured dimension and contain "
                "only finite values."
            )
        candidate_matrix = self._matrix[candidates]
        denominators = np.linalg.norm(candidate_matrix, axis=1) * np.linalg.norm(
            query_vector
        )
        similarities = np.divide(
            candidate_matrix @ query_vector,
            denominators,
            out=np.zeros(len(candidates), dtype=float),
            where=denominators != 0,
        )
        ranked = sorted(
            zip(candidates, similarities.tolist(), strict=True),
            key=lambda item: item[1],
            reverse=True,
        )
        results = []
        for chunk_index, score in ranked:
            if not np.isfinite(score) or score < self._min_similarity:
                continue
            chunk = self._chunks[chunk_index]
            results.append(
                {
                    "document_name": chunk["document_name"],
                    "document_type": chunk["document_type"],
                    "document_date": chunk["document_date"],
                    "chunk_id": chunk["chunk_id"],
                    "text": chunk["text"],
                    "page_number": chunk.get("page_number"),
                    "similarity": round(float(score), 4),
                }
            )
            if len(results) == result_count:
                break
        return (
            {"results": results, "message": None}
            if results
            else self._no_results()
        )

    @staticmethod
    def _no_results() -> dict[str, Any]:
        """Return the explicit no-relevant-passages result shape."""
        return {"results": [], "message": "No relevant passages found."}
