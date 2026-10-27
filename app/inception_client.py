"""Construction helpers for the Inception Labs chat model."""

from pydantic import SecretStr
from langchain_openai import ChatOpenAI

from app.config import ConfigurationError, Settings


def build_inception_client(settings: Settings) -> ChatOpenAI:
    """Create a LangChain chat client pointed at Inception's API."""
    if not settings.inception_api_key:
        raise ConfigurationError(
            "INCEPTION_API_KEY is required to create the Inception client."
        )
    return ChatOpenAI(
        model=settings.inception_model,
        api_key=SecretStr(settings.inception_api_key),
        base_url=settings.inception_base_url,
        temperature=0,
        max_retries=0,
        timeout=settings.llm_call_timeout_seconds,
        max_completion_tokens=settings.groq_max_tokens,
    )
