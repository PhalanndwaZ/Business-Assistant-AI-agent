"""Mistral embedding client with bounded batches and retry handling."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence

from mistralai import Mistral
from mistralai.models.sdkerror import SDKError

from app.config import EMBEDDING_DIMENSIONS

LOGGER = logging.getLogger(__name__)
MAX_BATCH_SIZE = 32
MAX_ATTEMPTS = 4
INITIAL_BACKOFF_SECONDS = 1.0


class MistralEmbedder:
    """Embed text using a single configured Mistral model."""

    def __init__(self, api_key: str, model: str) -> None:
        """Create the Mistral SDK client for the configured model."""
        self.model = model
        self._client = Mistral(api_key=api_key)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed text in bounded batches and validate vector dimensions."""
        vectors: list[list[float]] = []
        for offset in range(0, len(texts), MAX_BATCH_SIZE):
            batch = list(texts[offset : offset + MAX_BATCH_SIZE])
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Call the embedding API with exponential backoff for transient errors."""
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self._client.embeddings.create(
                    model=self.model,
                    inputs=texts,
                )
                vectors = [list(item.embedding) for item in response.data]
                if len(vectors) != len(texts):
                    raise RuntimeError(
                        "Mistral returned a different number of embeddings "
                        "than requested."
                    )
                if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
                    raise RuntimeError(
                        "Mistral embedding dimension does not match the "
                        f"configured {EMBEDDING_DIMENSIONS} dimensions."
                    )
                return vectors
            except SDKError as exc:
                status_code = getattr(exc, "status_code", None)
                if status_code != 429 and (
                    status_code is None or status_code < 500
                ):
                    raise RuntimeError(
                        f"Mistral embedding request failed: {exc}"
                    ) from exc
                if attempt == MAX_ATTEMPTS - 1:
                    raise RuntimeError(
                        "Mistral embedding service remained unavailable "
                        f"after {MAX_ATTEMPTS} attempts: {exc}"
                    ) from exc
                delay = INITIAL_BACKOFF_SECONDS * (2**attempt)
                LOGGER.warning(
                    "Transient embedding failure status=%s; retrying in %.1fs",
                    status_code,
                    delay,
                )
                time.sleep(delay)
        raise RuntimeError("Mistral embedding request exhausted retries.")
