"""Tests for configuring the primary/fallback chat model."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

import app.llm_factory
from app.config import ConfigurationError, Settings
from app.llm_fallback import FallbackChatModel


class FakeModel:
    """Provide the minimal chat interface required by the fallback wrapper."""

    def __init__(self) -> None:
        """Initialize captured model inputs."""
        self.bound_tools: list[dict[str, Any]] = []
        self.messages: list[Any] = []
        self.calls = 0

    def bind_tools(self, tools: list[dict[str, Any]]) -> FakeModel:
        """Accept tool schemas and return this model as the bound client."""
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        """Return a deterministic response for the chat model interface."""
        self.messages = messages
        self.calls += 1
        return AIMessage(content="test response")


def _settings(
    *,
    inception_api_key: str = "test-inception-key",
    groq_api_key: str = "test-groq-key",
) -> Settings:
    """Build valid settings for provider factory tests."""
    return Settings(
        groq_api_key=groq_api_key,
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


def test_build_chat_model_uses_both_configured_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The factory configures Inception as primary and Groq as fallback."""
    inception_model = FakeModel()
    groq_model = FakeModel()
    groq_options: dict[str, Any] = {}

    monkeypatch.setattr(
        app.llm_factory,
        "build_inception_client",
        lambda settings: (
            inception_model
            if settings.inception_api_key
            else pytest.fail("Inception key should be configured.")
        ),
    )

    class FakeChatGroq:
        """Capture the Groq constructor options in place of a live client."""

        def __new__(cls, **options: Any) -> FakeModel:
            """Record options and return the configured fake Groq model."""
            groq_options.update(options)
            return groq_model

    monkeypatch.setattr(app.llm_factory, "ChatGroq", FakeChatGroq)

    model = app.llm_factory.build_chat_model(_settings())

    assert isinstance(model, FallbackChatModel)
    tools = [{"type": "function", "function": {"name": "query_business_data"}}]
    bound_model = model.bind_tools(tools)
    response = asyncio.run(bound_model.ainvoke([]))
    assert response.content == "test response"
    assert inception_model.bound_tools == tools
    assert groq_model.bound_tools == tools
    assert inception_model.calls == 1
    assert groq_model.calls == 0
    assert groq_options["model"] == "llama-3.3-70b-versatile"
    assert groq_options["max_retries"] == 0


def test_build_chat_model_supports_groq_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The factory omits Inception and uses Groq when that key is absent."""
    groq_model = FakeModel()
    monkeypatch.setattr(
        app.llm_factory,
        "build_inception_client",
        lambda settings: (
            pytest.fail("Inception should not be constructed.")
            if not settings.inception_api_key
            else FakeModel()
        ),
    )

    def fake_groq(**options: Any) -> FakeModel:
        """Return Groq fake when its fallback settings are constructed."""
        assert options["model"] == "llama-3.3-70b-versatile"
        return groq_model

    monkeypatch.setattr(app.llm_factory, "ChatGroq", fake_groq)

    model = app.llm_factory.build_chat_model(
        _settings(inception_api_key="")
    )

    response = asyncio.run(model.ainvoke([]))

    assert response.content == "test response"
    assert groq_model.calls == 1


def test_build_chat_model_supports_inception_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The factory omits Groq when its fallback key is absent."""
    inception_model = FakeModel()
    monkeypatch.setattr(
        app.llm_factory,
        "build_inception_client",
        lambda settings: (
            inception_model
            if settings.inception_api_key
            else pytest.fail("Inception key should be configured.")
        ),
    )

    def unexpected_groq(**options: Any) -> FakeModel:
        """Fail if the factory creates an unconfigured Groq fallback."""
        assert options
        pytest.fail("Groq should not be constructed.")

    monkeypatch.setattr(app.llm_factory, "ChatGroq", unexpected_groq)
    model = app.llm_factory.build_chat_model(_settings(groq_api_key=""))

    response = asyncio.run(model.ainvoke([]))

    assert response.content == "test response"
    assert inception_model.calls == 1


def test_build_chat_model_rejects_missing_provider_keys() -> None:
    """The factory fails clearly if no LLM provider has a configured key."""
    with pytest.raises(ConfigurationError, match="INCEPTION_API_KEY or GROQ_API_KEY"):
        app.llm_factory.build_chat_model(
            _settings(inception_api_key="", groq_api_key="")
        )
