"""Focused tests for the Step 6 upload backend."""

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from docx import Document

from app.conversation_store import ConversationStore
from app.uploads import (
    UploadError,
    UploadService,
    UploadStore,
    scan_sensitive_text,
    validate_upload_content,
)


class FakeEmbedder:
    """Return deterministic vectors in tests without calling Mistral."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Create one fixed-dimension unit vector per supplied text."""
        return [[1.0] + ([0.0] * 1023) for _ in texts]


@pytest.fixture
def upload_service(tmp_path: Path) -> tuple[UploadService, UploadStore, str]:
    """Create an owned conversation and an isolated upload service."""
    database_path = tmp_path / "conversation.sqlite3"
    conversation_store = ConversationStore(database_path)
    conversation_id = uuid4()
    conversation_store.claim_conversation(conversation_id, "user-1", "sales")
    store = UploadStore(database_path)
    store.upload_root = tmp_path / "uploads"
    return UploadService(store, FakeEmbedder()), store, str(conversation_id)


def test_docx_ingest_list_and_delete(upload_service: tuple[UploadService, UploadStore, str]) -> None:
    """A valid DOCX is stored and its chunks disappear when deleted."""
    service, store, conversation_id = upload_service
    source = Document()
    source.add_paragraph("Quarterly targets for the sales team.")
    output = BytesIO()
    source.save(output)

    uploaded = service.ingest(
        filename="targets.docx",
        data=output.getvalue(),
        conversation_id=conversation_id,
        user_id="user-1",
    )
    assert uploaded["status"] == "ready"
    assert uploaded["chunks"] >= 1
    assert len(store.list(conversation_id, "user-1")) == 1
    assert store.delete(conversation_id, str(uploaded["document_id"]), "user-1")
    assert store.list(conversation_id, "user-1") == []


@pytest.mark.parametrize(
    ("filename", "data", "message"),
    [
        ("wrong.pdf", b"not a pdf", "valid PDF"),
        ("wrong.docx", b"not a zip", "valid DOCX"),
        ("large.txt", b"x" * (10 * 1024 * 1024 + 1), "10 MB"),
    ],
)
def test_invalid_upload_content_is_refused(filename: str, data: bytes, message: str) -> None:
    """Wrong content and oversized files receive explicit refusals."""
    with pytest.raises(UploadError, match=message):
        validate_upload_content(filename, data)


def test_sensitive_card_text_is_refused(upload_service: tuple[UploadService, UploadStore, str]) -> None:
    """A Luhn-valid card number is identified only by category."""
    service, _, conversation_id = upload_service
    with pytest.raises(UploadError, match="card number"):
        service.ingest(
            filename="notes.txt",
            data=b"Payment card: 4111 1111 1111 1111",
            conversation_id=conversation_id,
            user_id="user-1",
        )
    assert scan_sensitive_text("Payment card: 4111 1111 1111 1111") == "card number"
