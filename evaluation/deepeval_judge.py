"""DeepEval GEval metrics backed by the configured primary/fallback model."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from deepeval.models import DeepEvalBaseLLM
from langchain_core.messages import HumanMessage

from app.config import Settings
from app.llm_factory import build_chat_model
from app.llm_fallback import FallbackChatModel

LOGGER = logging.getLogger(__name__)


class FallbackDeepEvalModel(DeepEvalBaseLLM):
    """Adapt the Inception-first chat wrapper to DeepEval's model interface."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: FallbackChatModel | None = None
        super().__init__(model=self.get_model_name())

    def load_model(self) -> FallbackChatModel:
        """Build the same provider wrapper used by the analyst graph."""
        self._client = build_chat_model(self.settings)
        return self._client

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate synchronously when no event loop is already running."""
        if self._client is None:
            self.load_model()
        _ = kwargs
        client = self._client
        if client is None:
            raise RuntimeError("DeepEval chat model could not be initialized.")
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            response = asyncio.run(
                client.ainvoke([HumanMessage(content=prompt)])
            )
        else:
            raise RuntimeError(
                "Use asynchronous DeepEval metrics while an event loop is running."
            )
        self._log_response_provider(response)
        return str(response.content)

    async def a_generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate asynchronously through the provider fallback wrapper."""
        if self._client is None:
            self.load_model()
        _ = kwargs
        client = self._client
        if client is None:
            raise RuntimeError("DeepEval chat model could not be initialized.")
        response = await client.ainvoke([HumanMessage(content=prompt)])
        self._log_response_provider(response)
        return str(response.content)

    def get_model_name(self) -> str:
        """Name configured providers without exposing credentials."""
        if self.settings.inception_api_key and self.settings.groq_api_key:
            return (
                f"{self.settings.inception_model} "
                f"(Groq fallback: {self.settings.groq_model})"
            )
        if self.settings.inception_api_key:
            return self.settings.inception_model
        return self.settings.groq_model

    @staticmethod
    def _log_response_provider(response: Any) -> None:
        """Log provider metadata for each DeepEval model response."""
        metadata = getattr(response, "response_metadata", {})
        provider = metadata.get("llm_provider")
        model = metadata.get("llm_model")
        if isinstance(provider, str) and isinstance(model, str):
            LOGGER.info(
                "DeepEval LLM response provider=%s model=%s",
                provider,
                model,
            )


async def score_rag_case(
    settings: Settings,
    *,
    question: str,
    answer: str,
    expected_output: str,
    retrieval_context: list[str],
) -> dict[str, dict[str, Any]]:
    """Measure DeepEval faithfulness, relevance, precision, and recall."""
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, SingleTurnParams

    model = FallbackDeepEvalModel(settings)
    test_case = LLMTestCase(
        input=question,
        actual_output=answer,
        expected_output=expected_output,
        retrieval_context=retrieval_context,
    )
    definitions = (
        (
            "faithfulness",
            "Every factual claim in the answer is supported by the supplied retrieved context.",
            [
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.RETRIEVAL_CONTEXT,
            ],
        ),
        (
            "answer_relevancy",
            "The answer directly and completely addresses the user's question without unrelated content.",
            [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        ),
        (
            "context_precision",
            "The retrieved context is relevant to the expected answer; irrelevant passages reduce the score.",
            [SingleTurnParams.EXPECTED_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        ),
        (
            "context_recall",
            "The retrieved context contains the information needed to support the expected answer.",
            [SingleTurnParams.EXPECTED_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        ),
    )
    scores: dict[str, dict[str, Any]] = {}
    for name, criteria, parameters in definitions:
        metric = GEval(
            name=name,
            criteria=criteria,
            evaluation_params=parameters,
            model=model,
            async_mode=True,
        )
        await metric.a_measure(test_case)
        scores[name] = {
            "score": metric.score,
            "reason": metric.reason,
            "success": metric.success,
        }
    return scores
