"""Tests for provider classification and LLM fallback behavior."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
import pytest
from groq import APIConnectionError as GroqAPIConnectionError
from groq import APIStatusError as GroqAPIStatusError
from langchain_core.messages import AIMessage
from openai import APIConnectionError as OpenAIAPIConnectionError
from openai import APIStatusError as OpenAIAPIStatusError

from app.llm_fallback import (
    AsyncChatModel,
    FallbackChatModel,
    ProviderUnavailableError,
    classify_provider_error,
)


class FakeChatModel:
    """Provide deterministic responses and record model invocations."""

    def __init__(self, results: list[AIMessage | Exception]) -> None:
        """Store model outcomes for successive invocations."""
        self.results = results
        self.calls = 0
        self.last_messages: list[Any] | None = None
        self.bound_tools: list[list[dict[str, Any]]] = []

    def bind_tools(self, tools: list[dict[str, Any]]) -> FakeChatModel:
        """Record the schemas bound to this provider and return this model."""
        self.bound_tools.append(tools)
        return self

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        """Return the next configured result or raise its configured error."""
        self.calls += 1
        self.last_messages = messages
        result = self.results[min(self.calls - 1, len(self.results) - 1)]
        if isinstance(result, Exception):
            raise result
        return result


class SlowChatModel:
    """Simulate a provider that exceeds the configured call budget."""

    def __init__(self) -> None:
        """Initialize the invocation counter."""
        self.calls = 0
        self.bound_tools: list[dict[str, Any]] = []
        self.last_messages: list[Any] | None = None

    def bind_tools(self, tools: list[dict[str, Any]]) -> SlowChatModel:
        """Return this model because tool schemas are irrelevant to the timeout."""
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        """Wait longer than the configured call budget before responding."""
        self.calls += 1
        self.last_messages = messages
        await asyncio.sleep(0.1)
        return AIMessage(content="late primary answer")


def _status_error(
    status_code: int,
    error_type: type[OpenAIAPIStatusError] | type[GroqAPIStatusError] = (
        OpenAIAPIStatusError
    ),
) -> OpenAIAPIStatusError | GroqAPIStatusError:
    """Build a provider status error without making an HTTP request."""
    request = httpx.Request("POST", "https://provider.example/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return error_type(
        "test provider response containing a fake secret",
        response=response,
        body={"error": {"message": "fake-secret"}},
    )


def _wrapper(
    primary: AsyncChatModel | None,
    fallback: AsyncChatModel | None,
    *,
    max_retries: int = 0,
    call_timeout_seconds: float = 1,
) -> FallbackChatModel:
    """Build a wrapper with short deterministic retry settings."""
    return FallbackChatModel(
        primary,
        fallback,
        primary_model="mercury-3",
        fallback_model="llama-3.3-70b-versatile",
        max_retries=max_retries,
        backoff_base_seconds=0.01,
        backoff_max_seconds=0.02,
        call_timeout_seconds=call_timeout_seconds,
    )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_status_error(401), "configuration"),
        (_status_error(402), "configuration"),
        (_status_error(404), "configuration"),
        (_status_error(429), "retryable"),
        (_status_error(500), "retryable"),
        (_status_error(502), "retryable"),
        (_status_error(503), "retryable"),
        (_status_error(504), "retryable"),
        (_status_error(400), None),
        (
            OpenAIAPIConnectionError(
                request=httpx.Request("POST", "https://provider.example")
            ),
            "retryable",
        ),
        (
            GroqAPIConnectionError(
                request=httpx.Request("POST", "https://provider.example")
            ),
            "retryable",
        ),
        (ValueError("invalid request"), None),
    ],
)
def test_classify_provider_error(
    error: Exception,
    expected: str | None,
) -> None:
    """Classify documented provider status and connection failures."""
    assert classify_provider_error(error) == expected


@pytest.mark.parametrize("status_code", [401, 402, 404])
def test_configuration_errors_log_once_and_fall_back(
    status_code: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Credential, billing, and model errors log once before Groq fallback."""
    primary = FakeChatModel([_status_error(status_code)])
    fallback = FakeChatModel([AIMessage(content="fallback answer")])
    caplog.set_level(logging.ERROR, logger="app.llm_fallback")

    response = asyncio.run(_wrapper(primary, fallback).ainvoke([]))

    assert response.content == "fallback answer"
    assert response.response_metadata["llm_provider"] == "groq"
    assert response.response_metadata["llm_model"] == "llama-3.3-70b-versatile"
    assert primary.calls == 1
    assert fallback.calls == 1
    assert caplog.text.count("configuration or billing failure") == 1
    assert "fake-secret" not in caplog.text


def test_rate_limit_retries_before_falling_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A primary 429 is retried up to the configured count before Groq runs."""
    primary = FakeChatModel(
        [
            _status_error(429),
            _status_error(429),
            _status_error(429),
        ]
    )
    fallback = FakeChatModel([AIMessage(content="fallback answer")])

    async def no_wait(delay: float) -> None:
        """Skip elapsed time while preserving retry behavior in the test."""
        assert delay >= 0

    monkeypatch.setattr("app.llm_fallback.asyncio.sleep", no_wait)
    monkeypatch.setattr(
        "app.llm_fallback.random.uniform",
        lambda low, high: min(low, high),
    )

    response = asyncio.run(
        _wrapper(primary, fallback, max_retries=2).ainvoke([])
    )

    assert response.content == "fallback answer"
    assert primary.calls == 3
    assert fallback.calls == 1


def test_fallback_rate_limit_retries_with_provider_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Groq fallback 429 responses are retried instead of failing immediately."""
    primary = FakeChatModel(
        [
            OpenAIAPIConnectionError(
                request=httpx.Request("POST", "https://inception.example")
            )
        ]
    )
    fallback = FakeChatModel(
        [
            _status_error(429, GroqAPIStatusError),
            _status_error(429, GroqAPIStatusError),
            AIMessage(content="fallback answer"),
        ]
    )
    delays: list[float] = []

    async def no_wait(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.llm_fallback.asyncio.sleep", no_wait)

    response = asyncio.run(
        _wrapper(primary, fallback, max_retries=2).ainvoke([])
    )

    assert response.content == "fallback answer"
    assert response.response_metadata["llm_provider"] == "groq"
    assert primary.calls == 3
    assert fallback.calls == 3
    assert delays[-2:] == [8.0, 16.0]


def test_fallback_rate_limit_respects_retry_after_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider Retry-After value takes precedence over the default wait."""
    primary = FakeChatModel(
        [
            OpenAIAPIConnectionError(
                request=httpx.Request("POST", "https://inception.example")
            )
        ]
    )
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://groq.example"),
        headers={"Retry-After": "12"},
    )
    limited = GroqAPIStatusError(
        "rate limited",
        response=response,
        body={"error": {"code": "rate_limit_exceeded"}},
    )
    fallback = FakeChatModel([limited, AIMessage(content="fallback answer")])
    delays: list[float] = []

    async def no_wait(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.llm_fallback.asyncio.sleep", no_wait)
    monkeypatch.setattr(
        "app.llm_fallback.random.uniform",
        lambda low, high: 0.0,
    )

    response_message = asyncio.run(
        _wrapper(primary, fallback, max_retries=2).ainvoke([])
    )

    assert response_message.content == "fallback answer"
    assert delays == [0.0, 0.0, 12.0]


def test_bad_request_does_not_fall_back() -> None:
    """An Inception 400 is surfaced without sending the bad request to Groq."""
    bad_request = _status_error(400)
    primary = FakeChatModel([bad_request])
    fallback = FakeChatModel([AIMessage(content="must not be used")])

    with pytest.raises(OpenAIAPIStatusError) as error:
        asyncio.run(_wrapper(primary, fallback).ainvoke([]))

    assert error.value is bad_request
    assert primary.calls == 1
    assert fallback.calls == 0


def test_both_provider_failures_raise_safe_error() -> None:
    """A failed fallback yields a short error with no provider details."""
    primary = FakeChatModel(
        [
            OpenAIAPIConnectionError(
                message="contains fake-secret and C:\\private\\path",
                request=httpx.Request("POST", "https://inception.example"),
            )
        ]
    )
    fallback = FakeChatModel(
        [
            GroqAPIConnectionError(
                message="contains fake-secret and C:\\private\\path",
                request=httpx.Request("POST", "https://groq.example"),
            )
        ]
    )

    with pytest.raises(ProviderUnavailableError) as error:
        asyncio.run(_wrapper(primary, fallback).ainvoke([]))

    assert str(error.value) == "The answer model is temporarily unavailable."
    assert "fake-secret" not in str(error.value)
    assert "private" not in str(error.value)


def test_primary_call_budget_expires_before_fallback() -> None:
    """The primary retry budget is bounded before a fallback call begins."""
    primary = SlowChatModel()
    fallback = FakeChatModel([AIMessage(content="fallback answer")])

    response = asyncio.run(
        _wrapper(
            primary,
            fallback,
            call_timeout_seconds=0.01,
        ).ainvoke([])
    )

    assert response.content == "fallback answer"
    assert primary.calls == 1
    assert fallback.calls == 1


def test_tools_are_bound_to_both_provider_models() -> None:
    """The same schemas are bound to primary and fallback clients."""
    primary = FakeChatModel([AIMessage(content="primary answer")])
    fallback = FakeChatModel([AIMessage(content="fallback answer")])
    tools = [{"type": "function", "function": {"name": "run_analysis"}}]

    model = _wrapper(primary, fallback).bind_tools(tools)

    assert isinstance(model, FallbackChatModel)
    assert primary.bound_tools == [tools]
    assert fallback.bound_tools == [tools]


def test_groq_only_mode_skips_primary() -> None:
    """The fallback provider answers directly when Inception is unconfigured."""
    fallback = FakeChatModel([AIMessage(content="Groq answer")])

    response = asyncio.run(_wrapper(None, fallback).ainvoke([]))

    assert response.content == "Groq answer"
    assert response.response_metadata["llm_provider"] == "groq"
    assert response.response_metadata["llm_model"] == "llama-3.3-70b-versatile"
