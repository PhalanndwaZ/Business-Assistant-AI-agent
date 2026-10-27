"""JSON persistence for document chunks and their embedding vectors."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from app.config import EMBEDDING_DIMENSIONS


class VectorStoreError(ValueError):
    """Raised when the vector store is missing or contains invalid data."""


class JsonVectorStore:
    """Read and write a single JSON file containing embedded document chunks."""

    def __init__(self, path: Path) -> None:
        """Retain the configured JSON chunk-store path."""
        self.path = path

    def load(self) -> dict[str, Any]:
        """Load and validate the JSON chunk store from disk."""
        try:
            store = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise VectorStoreError(
                f"Vector store does not exist at {self.path}; ingest documents first."
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise VectorStoreError(
                f"Could not read vector store at {self.path}: {exc}"
            ) from exc
        if not isinstance(store, dict) or not isinstance(store.get("chunks"), list):
            raise VectorStoreError("Vector store must contain a chunks array.")
        if not isinstance(store.get("embedding_model"), str):
            raise VectorStoreError("Vector store is missing its embedding model.")
        if store.get("embedding_dimensions") != EMBEDDING_DIMENSIONS:
            raise VectorStoreError(
                "Vector store embedding dimensions do not match the configured "
                f"{EMBEDDING_DIMENSIONS} dimensions."
            )
        for chunk in store["chunks"]:
            if not isinstance(chunk, dict):
                raise VectorStoreError("Every chunk must be a JSON object.")
            vector = chunk.get("embedding")
            if (
                not isinstance(vector, list)
                or len(vector) != EMBEDDING_DIMENSIONS
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    for value in vector
                )
            ):
                raise VectorStoreError(
                    f"Chunk {chunk.get('chunk_id', '<unknown>')} has an invalid "
                    "embedding vector."
                )
        return store

    def save(self, store: dict[str, Any]) -> None:
        """Write a complete JSON store atomically to avoid partial files."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        try:
            temporary_path.write_text(
                json.dumps(store, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, self.path)
        except OSError as exc:
            raise VectorStoreError(
                f"Could not write vector store at {self.path}: {exc}"
            ) from exc

    def replace_document_chunks(
        self,
        document_id: str,
        new_chunks: list[dict[str, Any]],
        embedding_model: str,
    ) -> None:
        """Replace one document's chunks while preserving other documents."""
        if self.path.exists():
            store = self.load()
            if store["embedding_model"] != embedding_model:
                raise VectorStoreError(
                    "Cannot mix embedding models in one vector store: "
                    f"{store['embedding_model']} vs {embedding_model}."
                )
        else:
            store = {
                "embedding_model": embedding_model,
                "embedding_dimensions": EMBEDDING_DIMENSIONS,
                "chunks": [],
            }
        retained = [
            chunk for chunk in store["chunks"] if chunk["document_id"] != document_id
        ]
        store["chunks"] = retained + new_chunks
        self.save(store)

    def retain_documents(
        self,
        document_ids: set[str],
        embedding_model: str,
    ) -> None:
        """Remove chunks for documents no longer present in the manifest."""
        if self.path.exists():
            store = self.load()
            if store["embedding_model"] != embedding_model:
                raise VectorStoreError(
                    "Cannot reconcile a vector store with a different "
                    f"embedding model: {store['embedding_model']} vs "
                    f"{embedding_model}."
                )
        else:
            store = {
                "embedding_model": embedding_model,
                "embedding_dimensions": EMBEDDING_DIMENSIONS,
                "chunks": [],
            }
        store["chunks"] = [
            chunk
            for chunk in store["chunks"]
            if chunk["document_id"] in document_ids
        ]
        self.save(store)
