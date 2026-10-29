"""Primary/fallback chat model wrapper for Inception Labs and Groq."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Literal, Protocol

from groq import APIConnectionError as GroqAPIConnectionError
from groq import APIStatusError as GroqAPIStatusError
from langchain_core.messages import AIMessage
from openai import APIConnectionError as OpenAIAPIConnectionError
from openai import APIStatusError as OpenAIAPIStatusError

LOGGER = logging.getLogger(__name__)
ProviderErrorKind = Literal["retryable", "configuration"]
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
CONFIGURATION_STATUS_CODES = frozenset({401, 402, 404})
SAFE_PROVIDER_ERROR = "The answer model is temporarily unavailable."


class AsyncChatModel(Protocol):
    """Minimal interface required from either provider chat model."""

    def bind_tools(self, tools: list[dict[str, Any]]) -> AsyncChatModel: ...

    async def ainvoke(self, messages: list[Any]) -> AIMessage: ...


class ProviderUnavailableError(RuntimeError):
    """Safe error raised when neither configured LLM provider can answer."""


def _retry_after_seconds(error: Exception) -> float | None:
    """Read a bounded Retry-After delay from a provider response, if present."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    retry_after = headers.get("retry-after")
    if not isinstance(retry_after, str):
        return None
    try:
        delay = float(retry_after)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(retry_after)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
    if delay < 0:
        return 0.0
    return min(delay, 120.0)


def classify_provider_error(
    error: Exception,
) -> ProviderErrorKind | None:
    """Classify provider failures as retryable, configuration, or non-fallback."""
    if isinstance(
        error,
        (
            OpenAIAPIConnectionError,
            GroqAPIConnectionError,
            TimeoutError,
            ConnectionError,
            OSError,
        ),
    ):
        return "retryable"
    if isinstance(error, (OpenAIAPIStatusError, GroqAPIStatusError)):
        if error.status_code in CONFIGURATION_STATUS_CODES:
            return "configuration"
        if error.status_code in RETRYABLE_STATUS_CODES:
            return "retryable"
    return None


class FallbackChatModel:
    """Call Inception first and use Groq when an eligible failure occurs."""

    def __init__(
        self,
        primary: AsyncChatModel | None,
        fallback: AsyncChatModel | None,
        *,
        primary_model: str,
        fallback_model: str,
        max_retries: int,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
        call_timeout_seconds: float,
    ) -> None:
        """Store provider clients and bounded primary retry settings."""
        self._primary = primary
        self._fallback = fallback
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._max_retries = max_retries
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_max_seconds = backoff_max_seconds
        self._call_timeout_seconds = call_timeout_seconds

    def bind_tools(self, tools: list[dict[str, Any]]) -> FallbackChatModel:
        """Bind identical tool schemas to both configured provider models."""
        return FallbackChatModel(
            self._primary.bind_tools(tools) if self._primary is not None else None,
            self._fallback.bind_tools(tools) if self._fallback is not None else None,
            primary_model=self._primary_model,
            fallback_model=self._fallback_model,
            max_retries=self._max_retries,
            backoff_base_seconds=self._backoff_base_seconds,
            backoff_max_seconds=self._backoff_max_seconds,
            call_timeout_seconds=self._call_timeout_seconds,
        )

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        """Invoke Inception and fall back to Groq for classified failures."""
        if self._primary is None:
            response = await self._invoke_fallback(messages)
            return self._tag_response(response, "groq", self._fallback_model)

        try:
            response = await asyncio.wait_for(
                self._invoke_primary_with_retries(messages),
                timeout=self._call_timeout_seconds,
            )
        except Exception as exc:
            error_kind = classify_provider_error(exc)
            if error_kind is None:
                raise
            self._log_provider_failure("inception", exc, error_kind)
            if self._fallback is None:
                raise ProviderUnavailableError(SAFE_PROVIDER_ERROR) from None
            LOGGER.warning(
                "Primary LLM provider unavailable; trying fallback provider=groq"
            )
            response = await self._invoke_fallback(messages)
            return self._tag_response(response, "groq", self._fallback_model)

        return self._tag_response(
            response,
            "inception",
            self._primary_model,
        )

    async def _invoke_primary_with_retries(
        self,
        messages: list[Any],
    ) -> AIMessage:
        """Retry transient primary failures with capped exponential jitter."""
        if self._primary is None:
            raise RuntimeError("The primary LLM provider is not configured.")
        for attempt in range(self._max_retries + 1):
            try:
                return await self._primary.ainvoke(messages)
            except Exception as exc:
                if (
                    classify_provider_error(exc) != "retryable"
                    or attempt >= self._max_retries
                ):
                    raise
                delay_cap = min(
                    self._backoff_max_seconds,
                    self._backoff_base_seconds * (2**attempt),
                )
                delay_seconds = random.uniform(0.0, delay_cap)
                LOGGER.warning(
                    "Transient primary LLM failure provider=inception "
                    "error_type=%s; retrying in %.2fs",
                    type(exc).__name__,
                    delay_seconds,
                )
                await asyncio.sleep(delay_seconds)
        raise RuntimeError("Primary LLM retry loop exited unexpectedly.")

    async def _invoke_fallback(self, messages: list[Any]) -> AIMessage:
        """Retry transient Groq failures before raising a safe error."""
        if self._fallback is None:
            raise ProviderUnavailableError(SAFE_PROVIDER_ERROR) from None
        for attempt in range(self._max_retries + 1):
            try:
                return await asyncio.wait_for(
                    self._fallback.ainvoke(messages),
                    timeout=self._call_timeout_seconds,
                )
            except Exception as exc:
                error_kind = classify_provider_error(exc)
                if error_kind is None:
                    raise
                if error_kind == "retryable" and attempt < self._max_retries:
                    delay_seconds = max(
                        8.0 * (2**attempt),
                        _retry_after_seconds(exc) or 0.0,
                    )
                    LOGGER.warning(
                        "Transient fallback LLM failure provider=groq "
                        "error_type=%s; retrying in %.2fs",
                        type(exc).__name__,
                        delay_seconds,
                    )
                    await asyncio.sleep(delay_seconds)
                    continue
                self._log_provider_failure("groq", exc, error_kind)
                raise ProviderUnavailableError(SAFE_PROVIDER_ERROR) from None
        raise RuntimeError("Fallback LLM retry loop exited unexpectedly.")

    @staticmethod
    def _tag_response(
        response: AIMessage,
        provider: str,
        model: str,
    ) -> AIMessage:
        """Attach the answering provider and model to response metadata."""
        return response.model_copy(
            update={
                "response_metadata": {
                    **response.response_metadata,
                    "llm_provider": provider,
                    "llm_model": model,
                }
            }
        )

    @staticmethod
    def _log_provider_failure(
        provider: str,
        error: Exception,
        error_kind: ProviderErrorKind,
    ) -> None:
        """Log failure classification without including secrets or response text."""
        status_code = getattr(error, "status_code", None)
        if error_kind == "configuration":
            LOGGER.error(
                "LLM provider configuration or billing failure provider=%s "
                "status=%s error_type=%s",
                provider,
                status_code,
                type(error).__name__,
            )
            return
        LOGGER.warning(
            "LLM provider request failed provider=%s status=%s error_type=%s",
            provider,
            status_code,
            type(error).__name__,
        )
