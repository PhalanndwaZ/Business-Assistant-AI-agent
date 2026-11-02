"""Ingest the manifest documents and runtime policies into MongoDB."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import PROJECT_ROOT, load_settings
from app.mongodb import MongoStore
from app.moderation.moderator import validate_moderation_rules
from app.policy.policy import AccessPolicy
from app.rag.embeddings import MistralEmbedder
from app.rag.ingest import _document_chunks, _extract_text, _read_manifest

LOGGER = logging.getLogger(__name__)
POLICIES_DIR = PROJECT_ROOT / "data" / "policy"


def _read_policy(policy_id: str) -> dict[str, Any]:
    """Read one checked-in JSON policy object for MongoDB storage."""
    path = POLICIES_DIR / f"{policy_id}.json"
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load policy file {path}: {exc}") from exc
    if not isinstance(policy, dict):
        raise ValueError(f"Policy file {path} must contain a JSON object.")
    return policy


def ingest() -> tuple[int, int]:
    """Embed current source documents and replace their MongoDB records."""
    settings = load_settings(require_groq_api_key=False)
    manifest = _read_manifest(settings.documents_dir)
    policies = {
        "access_control": _read_policy("access_policy"),
        "moderation_rules": validate_moderation_rules(
            _read_policy("moderation_rules")
        ),
    }
    AccessPolicy.from_data(policies["access_control"])
    embedder = MistralEmbedder(
        settings.mistral_api_key,
        settings.mistral_embedding_model,
    )
    store = MongoStore(settings.mongodb_uri, settings.mongodb_database)
    try:
        store.ping()
        store.ensure_indexes()
        total_chunks = 0
        uploaded_at = datetime.now(timezone.utc).isoformat()
        for entry in manifest:
            path = (settings.documents_dir / entry["file"]).resolve()
            document_text = "\n".join(
                page_text for page_text, _ in _extract_text(path)
            )
            chunks = _document_chunks(entry, settings.documents_dir)
            vectors = embedder.embed([chunk["text"] for chunk in chunks])
            if len(vectors) != len(chunks):
                raise RuntimeError(
                    f"Embedding count did not match chunks for {entry['document_id']}."
                )
            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk["embedding"] = vector
                chunk["embedding_model"] = settings.mistral_embedding_model
            metadata = {
                **entry,
                "source_file": path.name,
                "uploaded_at": uploaded_at,
            }
            store.replace_document(metadata, document_text, chunks)
            total_chunks += len(chunks)
            LOGGER.info(
                "Ingested document=%s chunks=%d",
                entry["document_id"],
                len(chunks),
            )
        store.retain_documents(
            {entry["document_id"] for entry in manifest}
        )
        for policy_id, rules in policies.items():
            store.replace_policy(policy_id, rules)
        return len(manifest), total_chunks
    finally:
        store.close()


def main() -> None:
    """Run MongoDB ingestion and print a concise summary."""
    logging.basicConfig(level=logging.INFO)
    document_count, chunk_count = ingest()
    print(
        f"Ingested {document_count} documents, embedded into "
        f"{chunk_count} chunks, and stored 2 runtime policies in MongoDB."
    )


if __name__ == "__main__":
    main()
