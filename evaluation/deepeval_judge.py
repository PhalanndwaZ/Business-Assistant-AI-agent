"""DeepEval GEval metrics backed by the configured Groq chat model."""

from __future__ import annotations

from typing import Any

from deepeval.models import DeepEvalBaseLLM
from langchain_groq import ChatGroq
from pydantic import SecretStr

from app.config import Settings


class GroqDeepEvalModel(DeepEvalBaseLLM):
    """Small DeepEval model adapter using the application's Groq settings."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: ChatGroq | None = None
        super().__init__(model=settings.groq_model)

    def load_model(self) -> ChatGroq:
        self._client = ChatGroq(
            model=self.settings.groq_model,
            api_key=SecretStr(self.settings.groq_api_key),
            temperature=0,
            max_retries=0,
            max_tokens=self.settings.groq_max_tokens,
            reasoning_format=(
                "parsed"
                if self.settings.groq_model.startswith("openai/gpt-oss-")
                else None
            ),
        )
        return self._client

    def generate(self, prompt: str, **kwargs: Any) -> str:
        if self._client is None:
            raise RuntimeError("DeepEval Groq model has not been initialized.")
        _ = kwargs
        response = self._client.invoke(prompt)
        return str(response.content)

    async def a_generate(self, prompt: str, **kwargs: Any) -> str:
        if self._client is None:
            raise RuntimeError("DeepEval Groq model has not been initialized.")
        _ = kwargs
        response = await self._client.ainvoke(prompt)
        return str(response.content)

    def get_model_name(self) -> str:
        return self.settings.groq_model


def score_rag_case(
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

    model = GroqDeepEvalModel(settings)
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
            async_mode=False,
        )
        metric.measure(test_case)
        scores[name] = {
            "score": metric.score,
            "reason": metric.reason,
            "success": metric.success,
        }
    return scores
