"""Tests for constructing the Inception chat client."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

import app.inception_client
from app.config import ConfigurationError, Settings


def _settings(*, inception_api_key: str = "test-inception-key") -> Settings:
    """Build minimal settings for Inception client construction tests."""
    return Settings(
        groq_api_key="test-groq-key",
        mistral_api_key="test-mistral-key",
        groq_model="llama-3.3-70b-versatile",
        mistral_embedding_model="mistral-embed",
        as_of_date=date(2025, 1, 15),
        min_similarity=0.84,
        top_k=4,
        max_rows=100,
        max_steps=8,
        max_retries=2,
        data_dir=Path("data"),
        documents_dir=Path("documents"),
        vector_store_path=Path("chunks.json"),
        inception_api_key=inception_api_key,
    )


def test_build_inception_client_uses_openai_compatible_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client uses configured Inception credentials, model, and endpoint."""
    captured: dict[str, Any] = {}

    class FakeChatOpenAI:
        """Capture client options instead of making a network request."""

        def __init__(self, **options: Any) -> None:
            """Record the options used to configure the chat client."""
            captured.update(options)

    monkeypatch.setattr(app.inception_client, "ChatOpenAI", FakeChatOpenAI)

    app.inception_client.build_inception_client(_settings())

    assert captured["model"] == "mercury-3"
    assert captured["base_url"] == "https://api.inceptionlabs.ai/v1"
    assert captured["api_key"] == SecretStr("test-inception-key")
    assert captured["max_retries"] == 0
    assert captured["timeout"] == 20
    assert captured["max_completion_tokens"] == 1024


def test_build_inception_client_requires_an_api_key() -> None:
    """Client construction fails clearly when Inception is not configured."""
    with pytest.raises(ConfigurationError, match="INCEPTION_API_KEY"):
        app.inception_client.build_inception_client(
            _settings(inception_api_key="")
        )
