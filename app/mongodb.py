"""MongoDB persistence for documents, policies, and generated reports."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv
from gridfs import GridFSBucket
from gridfs.errors import NoFile
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import PyMongoError

from app.config import EMBEDDING_DIMENSIONS, PROJECT_ROOT

if TYPE_CHECKING:
    from app.policy.policy import AccessPolicy


class MongoStoreError(RuntimeError):
    """Raised when MongoDB content is missing or malformed."""


class MongoStore:
    """Persist source documents, embedded chunks, policies, and report files."""

    def __init__(self, uri: str, database_name: str) -> None:
        """Create a pooled MongoDB client for the selected application database."""
        if not uri.strip() or not database_name.strip():
            raise ValueError("MongoDB URI and database name are required.")
        self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self._database = self._client[database_name]
        self.documents = self._database["documents"]
        self.chunks = self._database["document_chunks"]
        self.policies = self._database["policies"]
        self._reports = GridFSBucket(
            self._database,
            bucket_name="generated_reports",
        )

    @classmethod
    def from_environment(cls) -> MongoStore:
        """Create a store from the project .env or process environment."""
        load_dotenv(PROJECT_ROOT / ".env")
        return get_mongo_store(
            os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017"),
            os.getenv("MONGODB_DATABASE", "business_assistant"),
        )

    def ping(self) -> None:
        """Verify connectivity before starting an ingestion operation."""
        self._client.admin.command("ping")

    def ensure_indexes(self) -> None:
        """Create stable identifiers for idempotent document and chunk writes."""
        self.documents.create_index(
            [("document_id", ASCENDING)],
            unique=True,
        )
        self.chunks.create_index(
            [("chunk_id", ASCENDING)],
            unique=True,
        )
        self.chunks.create_index(
            [
                ("department", ASCENDING),
                ("classification", ASCENDING),
                ("document_type", ASCENDING),
                ("document_date", ASCENDING),
            ]
        )

    def replace_document(
        self,
        metadata: dict[str, str],
        content: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        """Replace one source document and reconcile its embedded text chunks."""
        document_id = metadata["document_id"]
        embedding_model = next(
            (
                chunk.get("embedding_model")
                for chunk in chunks
                if isinstance(chunk.get("embedding_model"), str)
            ),
            None,
        )
        self.documents.replace_one(
            {"document_id": document_id},
            {
                **metadata,
                "content": content,
                "embedding_model": embedding_model,
                "embedding_dimensions": EMBEDDING_DIMENSIONS,
            },
            upsert=True,
        )
        if chunks:
            for chunk in chunks:
                self.chunks.replace_one(
                    {"chunk_id": chunk["chunk_id"]},
                    chunk,
                    upsert=True,
                )
            self.chunks.delete_many(
                {
                    "document_id": document_id,
                    "chunk_id": {
                        "$nin": [chunk["chunk_id"] for chunk in chunks]
                    },
                }
            )
        else:
            self.chunks.delete_many({"document_id": document_id})

    def retain_documents(self, document_ids: set[str]) -> None:
        """Remove documents and chunks that are absent from the source manifest."""
        stale = {"document_id": {"$nin": sorted(document_ids)}}
        self.documents.delete_many(stale)
        self.chunks.delete_many(stale)

    def list_chunks(self) -> list[dict[str, Any]]:
        """Return persisted chunks in stable order for in-process cosine ranking."""
        return list(self.chunks.find({}, {"_id": 0}).sort("chunk_id", ASCENDING))

    def replace_policy(self, policy_id: str, rules: dict[str, Any]) -> None:
        """Replace one named application policy document."""
        if not policy_id or not isinstance(rules, dict):
            raise ValueError("Policy ID and an object of policy rules are required.")
        self.policies.replace_one(
            {"_id": policy_id},
            {"_id": policy_id, "rules": rules},
            upsert=True,
        )

    def get_policy(self, policy_id: str) -> dict[str, Any]:
        """Load a policy document or fail explicitly when it was not ingested."""
        record = self.policies.find_one({"_id": policy_id})
        if record is None:
            raise MongoStoreError(
                f"MongoDB policy {policy_id!r} is missing; run the ingestion script."
            )
        rules = record.get("rules")
        if not isinstance(rules, dict):
            raise MongoStoreError(
                f"MongoDB policy {policy_id!r} has an invalid shape."
            )
        return rules

    def store_report(self, filename: str, path: Path) -> None:
        """Upload a generated DOCX report to GridFS under its safe filename."""
        if not filename or Path(filename).name != filename:
            raise ValueError("Report filename must be a basename.")
        with Path(path).open("rb") as source:
            self._reports.upload_from_stream(
                filename,
                source,
                metadata={
                    "content_type": (
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                    "stored_at": datetime.now(timezone.utc),
                },
            )

    def open_report(self, filename: str) -> Any | None:
        """Open the latest GridFS revision of a report, if it exists."""
        try:
            return self._reports.open_download_stream_by_name(
                filename,
                revision=-1,
            )
        except NoFile:
            return None

    def close(self) -> None:
        """Close the underlying MongoDB connection pool."""
        self._client.close()


@lru_cache(maxsize=8)
def get_mongo_store(uri: str, database_name: str) -> MongoStore:
    """Reuse a connection pool for each configured MongoDB database."""
    return MongoStore(uri, database_name)


def load_access_policy(store: MongoStore | None = None) -> AccessPolicy:
    """Load and validate the access-control policy from MongoDB."""
    from app.policy.policy import AccessPolicy, PolicyError

    try:
        policy_data = (store or MongoStore.from_environment()).get_policy(
            "access_control"
        )
        return AccessPolicy.from_data(policy_data)
    except (MongoStoreError, PyMongoError, ValueError) as exc:
        if isinstance(exc, PolicyError):
            raise
        raise PolicyError(f"Could not load access policy from MongoDB: {exc}") from exc


def load_moderation_rules(store: MongoStore | None = None) -> dict[str, Any]:
    """Load moderation rules from MongoDB for runtime safety checks."""
    try:
        return (store or MongoStore.from_environment()).get_policy("moderation_rules")
    except (MongoStoreError, PyMongoError) as exc:
        raise ValueError(
            f"Could not load moderation rules from MongoDB: {exc}"
        ) from exc
