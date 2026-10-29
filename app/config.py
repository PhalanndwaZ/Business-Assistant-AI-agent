"""Application settings loaded from environment variables."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
DEFAULT_AS_OF_DATE = date(2025, 1, 15)
EMBEDDING_DIMENSIONS = 1024
DEFAULT_MIN_SIMILARITY = 0.84
DEFAULT_TOP_K = 4
DEFAULT_MAX_ROWS = 100
DEFAULT_MAX_STEPS = 8
DEFAULT_MAX_RETRIES = 2
DEFAULT_GROQ_MAX_TOKENS = 1024
DEFAULT_MAX_HISTORY_TURNS = 10
DEFAULT_INCEPTION_BASE_URL = "https://api.inceptionlabs.ai/v1"
DEFAULT_INCEPTION_MODEL = "mercury-3"
DEFAULT_INCEPTION_MAX_RETRIES = 2
DEFAULT_INCEPTION_BACKOFF_BASE_SECONDS = 1.0
DEFAULT_INCEPTION_BACKOFF_MAX_SECONDS = 8.0
DEFAULT_LLM_CALL_TIMEOUT_SECONDS = 20.0


class ConfigurationError(ValueError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Validated configuration used by the application."""

    groq_api_key: str
    mistral_api_key: str
    groq_model: str
    mistral_embedding_model: str
    as_of_date: date
    min_similarity: float
    top_k: int
    max_rows: int
    max_steps: int
    max_retries: int
    data_dir: Path
    documents_dir: Path
    vector_store_path: Path
    groq_max_tokens: int = DEFAULT_GROQ_MAX_TOKENS
    conversation_db_path: Path = PROJECT_ROOT / "data" / "conversations.sqlite3"
    max_history_turns: int = DEFAULT_MAX_HISTORY_TURNS
    inception_api_key: str = ""
    inception_base_url: str = DEFAULT_INCEPTION_BASE_URL
    inception_model: str = DEFAULT_INCEPTION_MODEL
    inception_max_retries: int = DEFAULT_INCEPTION_MAX_RETRIES
    inception_backoff_base_seconds: float = (
        DEFAULT_INCEPTION_BACKOFF_BASE_SECONDS
    )
    inception_backoff_max_seconds: float = DEFAULT_INCEPTION_BACKOFF_MAX_SECONDS
    llm_call_timeout_seconds: float = DEFAULT_LLM_CALL_TIMEOUT_SECONDS


def _path_from_environment(name: str, default: str) -> Path:
    """Resolve a configured relative path from the project root."""
    configured_path = Path(os.getenv(name, default))
    if not configured_path.is_absolute():
        configured_path = PROJECT_ROOT / configured_path
    return configured_path.resolve()


def load_settings(*, require_groq_api_key: bool = True) -> Settings:
    """Load settings and require an LLM key for application workflows."""
    load_dotenv(PROJECT_ROOT / ".env")
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    inception_api_key = os.getenv("INCEPTION_API_KEY", "").strip()
    missing_keys = [
        key_name
        for key_name in ("MISTRAL_API_KEY",)
        if not os.getenv(key_name, "").strip()
    ]
    if require_groq_api_key and not (groq_api_key or inception_api_key):
        missing_keys.append("INCEPTION_API_KEY or GROQ_API_KEY")
    if missing_keys:
        raise ConfigurationError(
            "Missing required environment variable(s): "
            f"{', '.join(missing_keys)}. Copy .env.example to .env and add "
            "your keys."
        )
    if require_groq_api_key and not inception_api_key:
        LOGGER.warning(
            "INCEPTION_API_KEY is not configured; using Groq-only mode."
        )

    try:
        as_of_date = date.fromisoformat(
            os.getenv("AS_OF_DATE", DEFAULT_AS_OF_DATE.isoformat())
        )
        min_similarity = float(
            os.getenv("MIN_SIMILARITY", str(DEFAULT_MIN_SIMILARITY))
        )
        top_k = int(os.getenv("TOP_K", str(DEFAULT_TOP_K)))
        max_rows = int(os.getenv("MAX_ROWS", str(DEFAULT_MAX_ROWS)))
        max_steps = int(os.getenv("MAX_STEPS", str(DEFAULT_MAX_STEPS)))
        max_retries = int(os.getenv("MAX_RETRIES", str(DEFAULT_MAX_RETRIES)))
        inception_max_retries = int(
            os.getenv(
                "INCEPTION_MAX_RETRIES",
                str(DEFAULT_INCEPTION_MAX_RETRIES),
            )
        )
        inception_backoff_base_seconds = float(
            os.getenv(
                "INCEPTION_BACKOFF_BASE_SECONDS",
                str(DEFAULT_INCEPTION_BACKOFF_BASE_SECONDS),
            )
        )
        inception_backoff_max_seconds = float(
            os.getenv(
                "INCEPTION_BACKOFF_MAX_SECONDS",
                str(DEFAULT_INCEPTION_BACKOFF_MAX_SECONDS),
            )
        )
        llm_call_timeout_seconds = float(
            os.getenv(
                "LLM_CALL_TIMEOUT_SECONDS",
                str(DEFAULT_LLM_CALL_TIMEOUT_SECONDS),
            )
        )
        groq_max_tokens = int(
            os.getenv("GROQ_MAX_TOKENS", str(DEFAULT_GROQ_MAX_TOKENS))
        )
        max_history_turns = int(
            os.getenv("MAX_HISTORY_TURNS", str(DEFAULT_MAX_HISTORY_TURNS))
        )
    except ValueError as exc:
        raise ConfigurationError(f"Invalid application setting: {exc}") from exc

    if not 0.0 <= min_similarity <= 1.0:
        raise ConfigurationError("MIN_SIMILARITY must be between 0 and 1.")
    for name, value in (
        ("TOP_K", top_k),
        ("MAX_ROWS", max_rows),
        ("MAX_STEPS", max_steps),
    ):
        if value < 1:
            raise ConfigurationError(f"{name} must be at least 1.")
    if max_retries < 0:
        raise ConfigurationError("MAX_RETRIES cannot be negative.")
    if inception_max_retries < 0:
        raise ConfigurationError("INCEPTION_MAX_RETRIES cannot be negative.")
    for name, value in (
        ("INCEPTION_BACKOFF_BASE_SECONDS", inception_backoff_base_seconds),
        ("INCEPTION_BACKOFF_MAX_SECONDS", inception_backoff_max_seconds),
        ("LLM_CALL_TIMEOUT_SECONDS", llm_call_timeout_seconds),
    ):
        if value <= 0:
            raise ConfigurationError(f"{name} must be greater than 0.")
    if inception_backoff_max_seconds < inception_backoff_base_seconds:
        raise ConfigurationError(
            "INCEPTION_BACKOFF_MAX_SECONDS must be at least "
            "INCEPTION_BACKOFF_BASE_SECONDS."
        )
    if groq_max_tokens < 1:
        raise ConfigurationError("GROQ_MAX_TOKENS must be at least 1.")
    if max_history_turns < 1:
        raise ConfigurationError("MAX_HISTORY_TURNS must be at least 1.")

    return Settings(
        groq_api_key=groq_api_key,
        mistral_api_key=os.environ["MISTRAL_API_KEY"],
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        mistral_embedding_model=os.getenv(
            "MISTRAL_EMBEDDING_MODEL", "mistral-embed"
        ),
        as_of_date=as_of_date,
        min_similarity=min_similarity,
        top_k=top_k,
        max_rows=max_rows,
        max_steps=max_steps,
        max_retries=max_retries,
        data_dir=_path_from_environment("DATA_DIR", "data/sample_data"),
        documents_dir=_path_from_environment("DOCUMENTS_DIR", "data/documents"),
        vector_store_path=_path_from_environment(
            "VECTOR_STORE_PATH", "data/vector_store/chunks.json"
        ),
        groq_max_tokens=groq_max_tokens,
        conversation_db_path=_path_from_environment(
            "CONVERSATION_DB_PATH", "data/conversations.sqlite3"
        ),
        max_history_turns=max_history_turns,
        inception_api_key=inception_api_key,
        inception_base_url=os.getenv(
            "INCEPTION_BASE_URL",
            DEFAULT_INCEPTION_BASE_URL,
        ),
        inception_model=os.getenv(
            "INCEPTION_MODEL",
            DEFAULT_INCEPTION_MODEL,
        ),
        inception_max_retries=inception_max_retries,
        inception_backoff_base_seconds=inception_backoff_base_seconds,
        inception_backoff_max_seconds=inception_backoff_max_seconds,
        llm_call_timeout_seconds=llm_call_timeout_seconds,
    )
