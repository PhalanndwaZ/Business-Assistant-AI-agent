"""Tests for bounded and retryable Mistral embedding requests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from mistralai.models.sdkerror import SDKError

from app.config import EMBEDDING_DIMENSIONS
from app.rag import embeddings


class FakeEmbeddingEndpoint:
    """Capture requests and return predetermined SDK-shaped responses."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _response(count: int, dimension: int = EMBEDDING_DIMENSIONS) -> Any:
    """Build an SDK-shaped embedding response."""
    return SimpleNamespace(
        data=[
            SimpleNamespace(embedding=[float(index)] * dimension)
            for index in range(count)
        ]
    )


def _rate_limit_error() -> SDKError:
    """Create a representative HTTP 429 error from the Mistral SDK."""
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://api.mistral.ai/v1/embeddings"),
        text="rate limited",
    )
    return SDKError("rate limit", response)


def test_embed_splits_requests_into_bounded_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedding requests never exceed the configured batch size."""
    endpoint = FakeEmbeddingEndpoint(
        [_response(embeddings.MAX_BATCH_SIZE), _response(1)]
    )
    monkeypatch.setattr(
        embeddings,
        "Mistral",
        lambda **_kwargs: SimpleNamespace(
            embeddings=SimpleNamespace(create=endpoint.create)
        ),
    )

    embedder = embeddings.MistralEmbedder("test-key", "test-model")
    vectors = embedder.embed(["text"] * (embeddings.MAX_BATCH_SIZE + 1))

    assert [len(call["inputs"]) for call in endpoint.calls] == [
        embeddings.MAX_BATCH_SIZE,
        1,
    ]
    assert all(call["model"] == "test-model" for call in endpoint.calls)
    assert len(vectors) == embeddings.MAX_BATCH_SIZE + 1
    assert all(len(vector) == EMBEDDING_DIMENSIONS for vector in vectors)


def test_embed_retries_rate_limits_with_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 429 retries use exponential delays and eventually return vectors."""
    endpoint = FakeEmbeddingEndpoint(
        [_rate_limit_error(), _rate_limit_error(), _response(1)]
    )
    delays: list[float] = []
    monkeypatch.setattr(
        embeddings,
        "Mistral",
        lambda **_kwargs: SimpleNamespace(
            embeddings=SimpleNamespace(create=endpoint.create)
        ),
    )
    monkeypatch.setattr(embeddings.time, "sleep", delays.append)

    vectors = embeddings.MistralEmbedder("test-key", "test-model").embed(["text"])

    assert len(vectors) == 1
    assert len(endpoint.calls) == 3
    assert delays == [
        embeddings.INITIAL_BACKOFF_SECONDS,
        embeddings.INITIAL_BACKOFF_SECONDS * 2,
    ]


def test_embed_does_not_retry_client_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Permanent 4xx errors surface immediately instead of retrying."""
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.mistral.ai/v1/embeddings"),
        text="invalid input",
    )
    endpoint = FakeEmbeddingEndpoint([SDKError("bad request", response)])
    delays: list[float] = []
    monkeypatch.setattr(
        embeddings,
        "Mistral",
        lambda **_kwargs: SimpleNamespace(
            embeddings=SimpleNamespace(create=endpoint.create)
        ),
    )
    monkeypatch.setattr(embeddings.time, "sleep", delays.append)

    with pytest.raises(RuntimeError, match="embedding request failed"):
        embeddings.MistralEmbedder("test-key", "test-model").embed(["text"])

    assert len(endpoint.calls) == 1
    assert delays == []


def test_embed_rejects_mismatched_response_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vectors from an incompatible embedding model are rejected."""
    endpoint = FakeEmbeddingEndpoint([_response(1, EMBEDDING_DIMENSIONS - 1)])
    monkeypatch.setattr(
        embeddings,
        "Mistral",
        lambda **_kwargs: SimpleNamespace(
            embeddings=SimpleNamespace(create=endpoint.create)
        ),
    )

    with pytest.raises(RuntimeError, match="dimension does not match"):
        embeddings.MistralEmbedder("test-key", "test-model").embed(["text"])

    assert len(endpoint.calls) == 1
