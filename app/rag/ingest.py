"""Load local documents, split their text, and store embedded chunks."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from app.config import load_settings
from app.rag.embeddings import MistralEmbedder
from app.rag.vector_store import JsonVectorStore

LOGGER = logging.getLogger(__name__)
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
SUPPORTED_EXTENSIONS = frozenset({".pdf", ".txt", ".md"})


def _read_manifest(documents_dir: Path) -> list[dict[str, str]]:
    """Load and validate the document manifest and its local file references."""
    manifest_path = documents_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load document manifest: {exc}") from exc
    if not isinstance(manifest, list):
        raise ValueError("Document manifest must be a JSON array.")
    document_ids: set[str] = set()
    for entry in manifest:
        required = {"document_id", "file", "document_type", "document_date"}
        if not isinstance(entry, dict) or set(entry) != required:
            raise ValueError(
                "Each manifest entry must contain document_id, file, "
                "document_type, and document_date."
            )
        if not all(isinstance(entry[key], str) for key in required):
            raise ValueError("All document manifest values must be strings.")
        if not entry["document_id"] or entry["document_id"] in document_ids:
            raise ValueError("Document IDs must be non-empty and unique.")
        document_ids.add(entry["document_id"])
        try:
            date.fromisoformat(entry["document_date"])
        except ValueError as exc:
            raise ValueError(
                f"Invalid document date for {entry['document_id']!r}."
            ) from exc
        document_path = (documents_dir / entry["file"]).resolve()
        if not document_path.is_relative_to(documents_dir.resolve()):
            raise ValueError("Document manifest file path escapes its directory.")
        if document_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported document format: {document_path.suffix}."
            )
        if not document_path.is_file():
            raise ValueError(f"Document file does not exist: {document_path}.")
    return manifest


def _extract_text(path: Path) -> list[tuple[str, int | None]]:
    """Extract document text while retaining PDF page numbers when available."""
    if path.suffix.lower() == ".pdf":
        try:
            return [
                (page.extract_text() or "", page_number)
                for page_number, page in enumerate(PdfReader(path).pages, start=1)
            ]
        except OSError as exc:
            raise ValueError(f"Could not read PDF document {path}: {exc}") from exc
    try:
        return [(path.read_text(encoding="utf-8"), None)]
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Could not read text document {path}: {exc}") from exc


def _split_text(text: str) -> list[str]:
    """Split text into overlapping character chunks without empty chunks."""
    normalized = " ".join(text.split())
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + CHUNK_SIZE, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def _document_chunks(
    entry: dict[str, str],
    documents_dir: Path,
) -> list[dict[str, Any]]:
    """Create stable chunk records with manifest-sourced document metadata."""
    path = (documents_dir / entry["file"]).resolve()
    chunks: list[dict[str, Any]] = []
    position = 0
    for page_text, page_number in _extract_text(path):
        for text in _split_text(page_text):
            position += 1
            chunks.append(
                {
                    "document_id": entry["document_id"],
                    "document_name": path.name,
                    "document_type": entry["document_type"],
                    "document_date": entry["document_date"],
                    "chunk_id": f"{entry['document_id']}-chunk-{position:04d}",
                    "text": text,
                    "page_number": page_number,
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    return chunks


def ingest_documents() -> int:
    """Embed manifest-listed documents and replace their previous chunks."""
    settings = load_settings()
    manifest = _read_manifest(settings.documents_dir)
    embedder = MistralEmbedder(
        settings.mistral_api_key,
        settings.mistral_embedding_model,
    )
    store = JsonVectorStore(settings.vector_store_path)
    total_chunks = 0
    for entry in manifest:
        chunks = _document_chunks(entry, settings.documents_dir)
        vectors = embedder.embed([chunk["text"] for chunk in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk["embedding"] = vector
        store.replace_document_chunks(
            entry["document_id"],
            chunks,
            settings.mistral_embedding_model,
        )
        total_chunks += len(chunks)
        LOGGER.info("Ingested document=%s chunks=%d", entry["document_id"], len(chunks))
    store.retain_documents(
        {entry["document_id"] for entry in manifest},
        settings.mistral_embedding_model,
    )
    return total_chunks


def main() -> None:
    """Run document ingestion and report the total number of embedded chunks."""
    logging.basicConfig(level=logging.INFO)
    total_chunks = ingest_documents()
    print(f"Ingested {total_chunks} document chunks.")


if __name__ == "__main__":
    main()
