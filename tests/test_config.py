"""Tests for required application settings and validation."""

from __future__ import annotations

from datetime import date

import pytest

import app.config
from app.config import ConfigurationError, load_settings


def test_load_settings_requires_both_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configuration fails clearly when neither LLM key is configured."""
    monkeypatch.setattr(app.config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("INCEPTION_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    with pytest.raises(
        ConfigurationError,
        match="MISTRAL_API_KEY, INCEPTION_API_KEY or GROQ_API_KEY",
    ):
        load_settings()


def test_load_settings_resolves_defaults_and_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid environment values are parsed into stable settings."""
    monkeypatch.setattr(app.config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("INCEPTION_API_KEY", "test-inception-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")
    monkeypatch.delenv("AS_OF_DATE", raising=False)
    monkeypatch.delenv("MIN_SIMILARITY", raising=False)

    settings = load_settings()

    assert settings.as_of_date == date(2025, 1, 15)
    assert settings.min_similarity == 0.84
    assert settings.top_k == 4
    assert settings.groq_max_tokens == 1024
    assert settings.max_history_turns == 10
    assert settings.inception_base_url == "https://api.inceptionlabs.ai/v1"
    assert settings.inception_model == "mercury-3"
    assert settings.inception_max_retries == 2
    assert settings.inception_backoff_base_seconds == 1
    assert settings.inception_backoff_max_seconds == 8
    assert settings.llm_call_timeout_seconds == 20
    assert settings.conversation_db_path.name == "conversations.sqlite3"
    assert settings.data_dir.is_absolute()


def test_load_settings_allows_groq_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Groq remains available when the primary Inception key is absent."""
    monkeypatch.setattr(app.config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.delenv("INCEPTION_API_KEY", raising=False)
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")

    settings = load_settings()

    assert settings.groq_api_key == "test-groq-key"
    assert settings.inception_api_key == ""


def test_load_settings_allows_inception_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inception is sufficient when Groq is not configured."""
    monkeypatch.setattr(app.config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("INCEPTION_API_KEY", "test-inception-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")

    settings = load_settings()

    assert settings.groq_api_key == ""
    assert settings.inception_api_key == "test-inception-key"


def test_rag_settings_do_not_require_the_unused_groq_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The isolated document-search server only needs its Mistral credential."""
    monkeypatch.setattr(app.config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("INCEPTION_API_KEY", raising=False)
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")

    settings = load_settings(require_groq_api_key=False)

    assert settings.groq_api_key == ""
    assert settings.mistral_api_key == "test-mistral-key"


def test_load_settings_rejects_invalid_similarity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Similarity thresholds outside the cosine range are rejected."""
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")
    monkeypatch.setenv("MIN_SIMILARITY", "1.5")

    with pytest.raises(ConfigurationError, match="between 0 and 1"):
        load_settings()


def test_load_settings_rejects_invalid_groq_token_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model output cap must be a positive integer."""
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")
    monkeypatch.setenv("GROQ_MAX_TOKENS", "0")

    with pytest.raises(ConfigurationError, match="GROQ_MAX_TOKENS"):
        load_settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("INCEPTION_MAX_RETRIES", "-1"),
        ("INCEPTION_BACKOFF_BASE_SECONDS", "0"),
        ("INCEPTION_BACKOFF_MAX_SECONDS", "0.5"),
        ("LLM_CALL_TIMEOUT_SECONDS", "0"),
    ],
)
def test_load_settings_rejects_invalid_inception_retry_options(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    """Retry limits and call timeouts must be positive and internally valid."""
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError):
        load_settings()


def test_load_settings_rejects_invalid_history_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conversation memory must retain at least one turn."""
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")
    monkeypatch.setenv("MAX_HISTORY_TURNS", "0")

    with pytest.raises(ConfigurationError, match="MAX_HISTORY_TURNS"):
        load_settings()
