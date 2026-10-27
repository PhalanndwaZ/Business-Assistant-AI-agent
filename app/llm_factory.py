"""Build the configured primary/fallback chat model."""

from __future__ import annotations

from typing import Any

from langchain_groq import ChatGroq
from pydantic import SecretStr

from app.config import ConfigurationError, Settings
from app.llm_adapter import ChatModelAdapter
from app.inception_client import build_inception_client
from app.llm_fallback import FallbackChatModel


def groq_client_options(settings: Settings) -> dict[str, Any]:
    """Return Groq client options, including GPT-OSS reasoning settings."""
    options: dict[str, Any] = {
        "model": settings.groq_model,
        "api_key": SecretStr(settings.groq_api_key),
        "temperature": 0,
        "max_retries": 0,
        "timeout": settings.llm_call_timeout_seconds,
        "max_tokens": settings.groq_max_tokens,
    }
    if settings.groq_model.startswith("openai/gpt-oss-"):
        options["reasoning_format"] = "parsed"
    return options


def build_chat_model(settings: Settings) -> FallbackChatModel:
    """Build the Inception-first chat model with optional Groq fallback."""
    if not settings.inception_api_key and not settings.groq_api_key:
        raise ConfigurationError(
            "INCEPTION_API_KEY or GROQ_API_KEY is required to build the "
            "question-answering model."
        )

    inception_model = (
        ChatModelAdapter(build_inception_client(settings))
        if settings.inception_api_key
        else None
    )
    groq_model = (
        ChatModelAdapter(ChatGroq(**groq_client_options(settings)))
        if settings.groq_api_key
        else None
    )
    return FallbackChatModel(
        inception_model,
        groq_model,
        primary_model=settings.inception_model,
        fallback_model=settings.groq_model,
        max_retries=settings.inception_max_retries,
        backoff_base_seconds=settings.inception_backoff_base_seconds,
        backoff_max_seconds=settings.inception_backoff_max_seconds,
        call_timeout_seconds=settings.llm_call_timeout_seconds,
    )
