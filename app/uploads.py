"""Ingest and isolate user-uploaded documents."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile
import numpy as np

from docx import Document
from pypdf import PdfReader

from app.config import EMBEDDING_DIMENSIONS, PROJECT_ROOT
from app.feature_config import load_feature_config
from app.rag.embeddings import MistralEmbedder
from app.rag.ingest import _split_text


class UploadError(ValueError):
    """Reject an upload with a safe, user-facing reason."""


class UploadStore:
    """Store upload metadata and embedded chunks in the conversation database."""

    def __init__(self, database_path: Path) -> None:
        """Open upload metadata storage at the configured SQLite path."""
        self.database_path = database_path
        self.upload_root = PROJECT_ROOT / "data" / "uploads"

    def _connect(self) -> sqlite3.Connection:
        """Create upload tables and return an isolated connection."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS uploaded_documents (
                document_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                extension TEXT NOT NULL,
                pages INTEGER NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS uploaded_chunks (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                text TEXT NOT NULL,
                page_number INTEGER,
                embedding_json TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES uploaded_documents(document_id) ON DELETE CASCADE
            )
            """
        )
        return connection

    def own_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Return whether a conversation exists and belongs to the user."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
        return row is not None

    def count_conversation(self, conversation_id: str, user_id: str) -> int:
        """Count uploads in a conversation owned by one user."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) FROM uploaded_documents
                WHERE conversation_id = ? AND user_id = ?
                """,
                (conversation_id, user_id),
            ).fetchone()
        return int(row[0])

    def count_today(self, user_id: str) -> int:
        """Count uploads created by a user in the last 24 hours."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) FROM uploaded_documents
                WHERE user_id = ? AND created_at >= ?
                """,
                (user_id, cutoff),
            ).fetchone()
        return int(row[0])

    def add(
        self,
        *,
        document_id: str,
        conversation_id: str,
        user_id: str,
        name: str,
        extension: str,
        pages: int,
        chunks: list[dict[str, object]],
    ) -> dict[str, object]:
        """Persist one document and its embedded chunks atomically."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=int(load_feature_config("uploads.json")["retention_days"]))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO uploaded_documents (
                    document_id, conversation_id, user_id, name, extension,
                    pages, chunk_count, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id, conversation_id, user_id, name, extension,
                    pages, len(chunks), now.isoformat(), expires.isoformat(),
                ),
            )
            for chunk in chunks:
                connection.execute(
                    """
                    INSERT INTO uploaded_chunks (
                        chunk_id, document_id, conversation_id, user_id,
                        text, page_number, embedding_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk["chunk_id"], document_id, conversation_id, user_id,
                        chunk["text"], chunk.get("page_number"),
                        json.dumps(chunk["embedding"]),
                    ),
                )
        return {
            "document_id": document_id,
            "name": name,
            "pages": pages,
            "chunks": len(chunks),
            "status": "ready",
            "conversation_id": conversation_id,
        }

    def list(self, conversation_id: str, user_id: str) -> list[dict[str, object]]:
        """List documents owned by the user in one conversation."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT document_id, name, extension, pages, chunk_count, created_at
                FROM uploaded_documents
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY created_at ASC
                """,
                (conversation_id, user_id),
            ).fetchall()
        return [
            {
                "document_id": row[0],
                "name": row[1],
                "extension": row[2],
                "pages": row[3],
                "chunks": row[4],
                "status": "ready",
                "created_at": row[5],
            }
            for row in rows
        ]

    def owns_documents(
        self,
        conversation_id: str,
        document_ids: list[str],
        user_id: str,
    ) -> bool:
        """Return whether every requested document belongs to this conversation."""
        if not document_ids:
            return True
        placeholders = ", ".join("?" for _ in document_ids)
        parameters = [conversation_id, user_id, *document_ids]
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(DISTINCT document_id)
                FROM uploaded_documents
                WHERE conversation_id = ? AND user_id = ?
                  AND document_id IN ({placeholders})
                """,
                parameters,
            ).fetchone()
        return len(set(document_ids)) == int(row[0])

    def delete(self, conversation_id: str, document_id: str, user_id: str) -> bool:
        """Delete one document and all of its chunks for its owner."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT document_id FROM uploaded_documents
                WHERE conversation_id = ? AND document_id = ? AND user_id = ?
                """,
                (conversation_id, document_id, user_id),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                "DELETE FROM uploaded_chunks WHERE document_id = ?",
                (document_id,),
            )
            connection.execute(
                "DELETE FROM uploaded_documents WHERE document_id = ?",
                (document_id,),
            )
        directory = self.upload_root / user_id / conversation_id / document_id
        if directory.exists():
            for child in directory.iterdir():
                if child.is_file():
                    child.unlink()
            directory.rmdir()
        return True

    def search(
        self,
        *,
        conversation_id: str,
        user_id: str,
        query_vector: list[float],
        document_ids: list[str] | None,
        min_similarity: float,
        top_k: int,
        embedder_model: str,
    ) -> list[dict[str, object]]:
        """Rank only owned uploaded chunks and return citation metadata."""
        del embedder_model
        placeholders = ""
        parameters: list[object] = [conversation_id, user_id]
        if document_ids:
            placeholders = " AND chunks.document_id IN ({})".format(
                ",".join("?" for _ in document_ids)
            )
            parameters.extend(document_ids)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunks.chunk_id, chunks.document_id, documents.name,
                       documents.extension, chunks.text, chunks.page_number,
                       chunks.embedding_json
                FROM uploaded_chunks AS chunks
                JOIN uploaded_documents AS documents
                  ON documents.document_id = chunks.document_id
                WHERE chunks.conversation_id = ?
                  AND chunks.user_id = ?
                  """ + placeholders,
                parameters,
            ).fetchall()
        query = np.asarray(query_vector, dtype=float)
        query_norm = np.linalg.norm(query)
        ranked: list[tuple[float, tuple[object, ...]]] = []
        for row in rows:
            vector = np.asarray(json.loads(str(row[6])), dtype=float)
            denominator = np.linalg.norm(vector) * query_norm
            similarity = (
                float(vector @ query / denominator)
                if denominator
                else 0.0
            )
            if np.isfinite(similarity) and similarity >= min_similarity:
                ranked.append((similarity, row))
        ranked.sort(key=lambda item: (-item[0], str(item[1][0])))
        return [
            {
                "origin": "uploaded",
                "document_name": str(row[2]),
                "document_type": str(row[3]),
                "document_date": None,
                "chunk_id": str(row[0]),
                "text": str(row[4]),
                "page_number": row[5],
                "similarity": round(score, 4),
            }
            for score, row in ranked[:top_k]
        ]


def _luhn_valid(value: str) -> bool:
    """Apply the Luhn checksum to a digit-only candidate."""
    digits = re.sub(r"\D", "", value)
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        number = int(digit)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def scan_sensitive_text(text: str) -> str | None:
    """Return the sensitive-data category found, without returning its value."""
    candidates = re.findall(r"\b(?:\d[ -]?){12,18}\d\b", text)
    if any(_luhn_valid(candidate) for candidate in candidates):
        return "card number"
    if re.search(r"(?<!\d)\d{13}(?!\d)", text):
        return "national ID number"
    if re.search(r"(?i)\b(?:api[_ -]?key|password|secret|token)\b\s*[:=]\s*\S+", text):
        return "secret"
    return None


def validate_upload_content(filename: str, data: bytes) -> str:
    """Validate file content and return its normalized extension."""
    config = load_feature_config("uploads.json")
    suffix = Path(filename).suffix.lower().lstrip(".")
    allowed = set(config["allowed_extensions"])
    if suffix not in allowed:
        raise UploadError("Unsupported file type.")
    if len(data) > int(config["max_file_bytes"]):
        raise UploadError("File exceeds the 10 MB size limit.")
    if suffix == "pdf":
        if not data.startswith(b"%PDF-"):
            raise UploadError("File content is not a valid PDF.")
        return suffix
    if suffix == "docx":
        try:
            with ZipFile(__import__("io").BytesIO(data)) as archive:
                required = {"[Content_Types].xml", "word/document.xml"}
                if not required.issubset(set(archive.namelist())):
                    raise UploadError("File content is not a valid DOCX.")
        except BadZipFile as exc:
            raise UploadError("File content is not a valid DOCX.") from exc
        return suffix
    if suffix in {"txt", "md"}:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UploadError("Text file is not valid UTF-8.") from exc
        return suffix
    raise UploadError("Unsupported file type.")


class UploadService:
    """Extract, scan, chunk, embed, and persist conversation uploads."""

    def __init__(
        self,
        store: UploadStore,
        embedder: MistralEmbedder,
    ) -> None:
        """Retain upload storage and the configured embedder."""
        self.store = store
        self.embedder = embedder

    def _extract(self, extension: str, data: bytes) -> tuple[list[tuple[str, int | None]], str]:
        """Extract text with page metadata for supported file types."""
        if extension == "pdf":
            try:
                reader = PdfReader(__import__("io").BytesIO(data))
                pages = [(page.extract_text() or "", number) for number, page in enumerate(reader.pages, 1)]
            except Exception as exc:
                raise UploadError("Could not extract text from PDF.") from exc
        elif extension == "docx":
            try:
                document = Document(__import__("io").BytesIO(data))
                text = "\n".join(paragraph.text for paragraph in document.paragraphs)
                pages = [(text, 1)]
            except Exception as exc:
                raise UploadError("Could not extract text from DOCX.") from exc
        else:
            pages = [(data.decode("utf-8"), None)]
        text = "\n".join(page_text for page_text, _ in pages)
        if not text.strip():
            raise UploadError("The file contains no extractable text.")
        return pages, text

    def ingest(
        self,
        *,
        filename: str,
        data: bytes,
        conversation_id: str,
        user_id: str,
    ) -> dict[str, object]:
        """Run the complete upload ingest pipeline and return safe metadata."""
        extension = validate_upload_content(filename, data)
        config = load_feature_config("uploads.json")
        if not self.store.own_conversation(conversation_id, user_id):
            raise UploadError("Conversation not found.")
        if self.store.count_conversation(conversation_id, user_id) >= int(config["max_files_per_conversation"]):
            raise UploadError("Conversation has reached its five-file limit.")
        if self.store.count_today(user_id) >= int(config["uploads_per_user_per_day"]):
            raise UploadError("Daily upload limit reached.")
        pages, combined_text = self._extract(extension, data)
        sensitive = scan_sensitive_text(combined_text)
        if sensitive:
            raise UploadError(f"File refused because it contains a {sensitive}.")

        document_id = uuid4().hex
        chunks: list[dict[str, object]] = []
        position = 0
        for page_text, page_number in pages:
            for chunk_text in _split_text(page_text):
                position += 1
                chunks.append({
                    "chunk_id": f"{document_id}-chunk-{position:04d}",
                    "text": chunk_text,
                    "page_number": page_number,
                })
        if not chunks:
            raise UploadError("The file contains no extractable text.")
        if len(chunks) > int(config["max_chunks_per_file"]):
            raise UploadError("File exceeds the maximum chunk limit.")

        vectors = self.embedder.embed([str(chunk["text"]) for chunk in chunks])
        if len(vectors) != len(chunks) or any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
            raise UploadError("Document embedding failed.")
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk["embedding"] = vector

        directory = self.store.upload_root / user_id / conversation_id / document_id
        directory.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).name).strip(".") or "document"
        stored_path = directory / safe_name
        stored_path.write_bytes(data)
        try:
            return self.store.add(
                document_id=document_id,
                conversation_id=conversation_id,
                user_id=user_id,
                name=safe_name,
                extension=extension,
                pages=len(pages),
                chunks=chunks,
            )
        except Exception:
            stored_path.unlink(missing_ok=True)
            directory.rmdir()
            raise
