"""HTTP API contract tests for the Phase 11 FastAPI endpoint."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from pydantic import SecretStr

import main
from app.config import ConfigurationError, Settings
from app.llm_factory import groq_client_options
from app.llm_fallback import ProviderUnavailableError
from app.state import AnalystState


def test_gpt_oss_uses_parsed_reasoning_format() -> None:
    """GPT-OSS tool calls use Groq's structured reasoning response format."""
    settings = Settings(
        groq_api_key="test",
        mistral_api_key="test",
        groq_model="openai/gpt-oss-120b",
        mistral_embedding_model="test-embedding",
        as_of_date=date(2025, 1, 15),
        min_similarity=0.84,
        top_k=4,
        max_rows=100,
        max_steps=8,
        max_retries=2,
        data_dir=Path("data/sample_data"),
        documents_dir=Path("data/documents"),
        vector_store_path=Path("data/vector_store/chunks.json"),
    )

    assert groq_client_options(settings) == {
        "model": "openai/gpt-oss-120b",
        "api_key": SecretStr("test"),
        "temperature": 0,
        "max_retries": 0,
        "timeout": 20,
        "max_tokens": 1024,
        "reasoning_format": "parsed",
    }


def test_run_question_uses_the_same_graph_answer_as_the_cli(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """The HTTP service delegates to answer_question and returns its answer."""
    settings = Settings(
        groq_api_key="test",
        mistral_api_key="test",
        groq_model="test-model",
        mistral_embedding_model="test-embedding",
        as_of_date=date(2025, 1, 15),
        min_similarity=0.84,
        top_k=4,
        max_rows=100,
        max_steps=8,
        max_retries=2,
        data_dir=Path("data/sample_data"),
        documents_dir=Path("data/documents"),
        vector_store_path=Path("data/vector_store/chunks.json"),
        conversation_db_path=tmp_path / "conversations.sqlite3",
    )
    observed: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, actual_settings: Settings) -> None:
            observed["settings"] = actual_settings

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
            observed["client_closed"] = True
            observed["client_exit"] = (exc_type, exc, traceback)
            return None

        async def list_tools(self) -> list[object]:
            return []

    async def fake_answer_question(
        question: str,
        _model: Any,
        _tools: list[object],
        _client: Any,
        max_steps: int,
        max_retries: int,
        history: list[tuple[str, str]],
        prior_tool_results: list[dict[str, Any]],
        prior_retrieved_chunks: list[dict[str, object]],
    ) -> AnalystState:
        assert observed["settings"] is settings
        assert _model is fake_model
        assert _tools == []
        assert isinstance(_client, FakeClient)
        observed.update(
            question=question,
            max_steps=max_steps,
            max_retries=max_retries,
            history=history,
            prior_tool_results=prior_tool_results,
            prior_retrieved_chunks=prior_retrieved_chunks,
        )
        return {
            "final_answer": "The CLI-compatible graph answer.",
            "tool_results": [],
            "retrieved_chunks": [],
            "evidence_errors": [],
            "errors": [],
        }

    fake_model = object()

    def fake_build_chat_model(actual_settings: Settings) -> object:
        """Return a sentinel model and record the settings passed by the API."""
        observed["settings"] = actual_settings
        observed["model_built"] = True
        return fake_model

    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "build_chat_model", fake_build_chat_model)
    monkeypatch.setattr(
        main, "AnalystMCPClient", lambda actual_settings: FakeClient(actual_settings)
    )
    monkeypatch.setattr(main, "answer_question", fake_answer_question)

    response = asyncio.run(main._run_question("What changed?"))

    assert observed == {
        "question": "What changed?",
        "settings": settings,
        "max_steps": 8,
        "max_retries": 2,
        "history": [],
        "prior_tool_results": [],
        "prior_retrieved_chunks": [],
        "model_built": True,
        "client_closed": True,
        "client_exit": (None, None, None),
    }
    assert response.answer == "The CLI-compatible graph answer."
    assert isinstance(UUID(response.conversation_id), UUID)


def test_run_question_returns_current_turn_figures_not_historical_evidence(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """Keep prior evidence for follow-ups without echoing it in the API response."""
    settings = Settings(
        groq_api_key="test",
        mistral_api_key="test",
        groq_model="test-model",
        mistral_embedding_model="test-embedding",
        as_of_date=date(2025, 1, 15),
        min_similarity=0.84,
        top_k=4,
        max_rows=100,
        max_steps=8,
        max_retries=2,
        data_dir=Path("data/sample_data"),
        documents_dir=Path("data/documents"),
        vector_store_path=Path("data/vector_store/chunks.json"),
        conversation_db_path=tmp_path / "conversations.sqlite3",
    )
    conversation_id = UUID("00000000-0000-0000-0000-000000000004")
    historical_result = {
        "call_id": "historical-analysis",
        "tool_name": "run_analysis",
        "arguments": {},
        "result": {
            "analysis": "revenue_by_product",
            "data": [{"product_name": "Standing Desk", "revenue_cents": 16645713}],
        },
        "success": True,
    }
    historical_chunk = {"document_name": "old_report.md", "text": "old evidence"}
    store = main.ConversationStore(settings.conversation_db_path)
    store.append_turn(
        conversation_id,
        "Which product led?",
        "Standing Desk led.",
        [historical_result],
        [historical_chunk],
    )
    observed: dict[str, Any] = {}

    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
            return None

        async def list_tools(self) -> list[object]:
            return []

    current_result = {
        "call_id": "current-query",
        "tool_name": "query_business_data",
        "arguments": {},
        "result": {
            "dataset": "orders",
            "total_matches": 514,
            "rows": [],
        },
        "success": True,
    }

    async def fake_answer_question(
        _question: str,
        _model: Any,
        _tools: list[object],
        _client: Any,
        _max_steps: int,
        _max_retries: int,
        history: list[tuple[str, str]],
        prior_tool_results: list[dict[str, Any]],
        prior_retrieved_chunks: list[dict[str, object]],
    ) -> AnalystState:
        observed["history"] = history
        observed["prior_tool_results"] = prior_tool_results
        observed["prior_retrieved_chunks"] = prior_retrieved_chunks
        return {
            "final_answer": "There are 514 completed orders.",
            "tool_results": [*prior_tool_results, current_result],
            "retrieved_chunks": prior_retrieved_chunks,
            "evidence_errors": [],
            "errors": [],
        }

    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "build_chat_model", lambda _settings: object())
    monkeypatch.setattr(main, "AnalystMCPClient", lambda _settings: FakeClient())
    monkeypatch.setattr(main, "answer_question", fake_answer_question)

    response = asyncio.run(
        main._run_question("How many orders have been completed?", conversation_id)
    )

    assert observed["prior_tool_results"] == [historical_result]
    assert observed["prior_retrieved_chunks"] == [historical_chunk]
    assert response.answer == "There are 514 completed orders."
    assert response.figures == [
        {"dataset": "orders", "total_matches": 514, "rows": []}
    ]
    assert response.sources == ["query_business_data:orders"]
    assert "revenue_by_product" not in str(response.model_dump())
    assert "old_report.md" not in str(response.model_dump())


def test_ask_returns_same_answer_and_supporting_workflow_data(
    monkeypatch: Any,
) -> None:
    """The API returns the graph answer with figures, sources, and caveats."""
    async def fake_run_question(
        question: str,
        conversation_id: UUID | None = None,
    ) -> main.AskResponse:
        assert question == "What changed?"
        return main._response_fields(
            {
                "final_answer": "Revenue decreased in December.",
                "tool_results": [
                    {
                        "tool_name": "run_analysis",
                        "success": True,
                        "result": {
                            "analysis": "period_change",
                            "period": {
                                "current": {"start": "2024-12-01"},
                                "previous": {"start": "2024-11-01"},
                            },
                            "data": [{"current_value": 100, "previous_value": 200}],
                            "assumptions": ["Only completed orders are included."],
                        },
                    },
                    {
                        "tool_name": "search_documents",
                        "success": True,
                        "result": {"results": []},
                    },
                ],
                "retrieved_chunks": [
                    {"document_name": "management_report_2024-12.md"}
                ],
                "evidence_errors": [],
                "errors": [],
            },
            str(conversation_id or UUID("00000000-0000-0000-0000-000000000001")),
        )

    monkeypatch.setattr(main, "_run_question", fake_run_question)

    response = TestClient(main.create_app()).post(
        "/ask", json={"question": "  What changed?  "}
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Revenue decreased in December.",
        "conversation_id": "00000000-0000-0000-0000-000000000001",
        "figures": [
            {
                "analysis": "period_change",
                "period": {
                    "current": {"start": "2024-12-01"},
                    "previous": {"start": "2024-11-01"},
                },
                "data": [{"current_value": 100, "previous_value": 200}],
            }
        ],
        "sources": ["run_analysis:period_change", "search_documents", "management_report_2024-12.md"],
        "caveats": [
            "Only completed orders are included.",
            "Document-derived statements are limited to retrieved passages and may be incomplete or outdated.",
            "Reported explanations are not proof that a factor caused a measured business change.",
        ],
    }


def test_ask_rejects_missing_or_blank_question() -> None:
    """The request contract rejects missing, empty, and whitespace-only input."""
    client = TestClient(main.create_app())

    assert client.post("/ask", json={}).status_code == 422
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={"question": "   "}).status_code == 422
    assert client.post(
        "/ask",
        json={"question": "Revenue?", "conversation_id": "not-a-uuid"},
    ).status_code == 422


def test_ask_returns_and_accepts_server_generated_conversation_id(
    monkeypatch: Any,
) -> None:
    """Clients can pass the returned UUID to continue the same conversation."""
    observed_ids: list[UUID | None] = []

    async def fake_run_question(
        question: str,
        conversation_id: UUID | None = None,
    ) -> main.AskResponse:
        observed_ids.append(conversation_id)
        active_id = conversation_id or UUID(
            "00000000-0000-0000-0000-000000000002"
        )
        return main.AskResponse(
            answer=f"Answer to {question}",
            conversation_id=str(active_id),
            figures=[],
            sources=[],
            caveats=[],
        )

    monkeypatch.setattr(main, "_run_question", fake_run_question)
    client = TestClient(main.create_app())

    first_response = client.post("/ask", json={"question": "First question"})
    generated_id = first_response.json()["conversation_id"]
    second_response = client.post(
        "/ask",
        json={
            "question": "Follow-up question",
            "conversation_id": generated_id,
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert observed_ids == [None, UUID(generated_id)]
    assert second_response.json()["conversation_id"] == generated_id


def test_ask_accepts_client_supplied_id_for_new_conversation(
    monkeypatch: Any,
) -> None:
    """A valid client ID that is not stored yet starts a new conversation."""
    supplied_id = UUID("00000000-0000-0000-0000-000000000003")
    observed_ids: list[UUID | None] = []

    async def create_with_supplied_id(
        question: str,
        conversation_id: UUID | None = None,
    ) -> main.AskResponse:
        observed_ids.append(conversation_id)
        assert question == "Start with my ID"
        return main.AskResponse(
            answer="Started a new conversation.",
            conversation_id=str(conversation_id),
            figures=[],
            sources=[],
            caveats=[],
        )

    monkeypatch.setattr(main, "_run_question", create_with_supplied_id)
    response = TestClient(main.create_app()).post(
        "/ask",
        json={
            "question": "Start with my ID",
            "conversation_id": str(supplied_id),
        },
    )

    assert response.status_code == 200
    assert response.json()["conversation_id"] == str(supplied_id)
    assert observed_ids == [supplied_id]


def test_ask_reports_configuration_failure_without_exposing_details(
    monkeypatch: Any,
) -> None:
    """Configuration failures have an explicit service error response."""
    async def fail_to_run(
        _question: str,
        _conversation_id: UUID | None = None,
    ) -> main.AskResponse:
        assert _question == "Revenue?"
        raise ConfigurationError("Missing GROQ_API_KEY")

    monkeypatch.setattr(main, "_run_question", fail_to_run)

    response = TestClient(main.create_app()).post(
        "/ask", json={"question": "Revenue?"}
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "The question-answering service is not configured."
    }
    assert "GROQ_API_KEY" not in response.text


def test_provider_unavailable_returns_safe_existing_error(
    monkeypatch: Any,
) -> None:
    """Unavailable provider errors return a generic model-service response."""
    async def fail_to_run(
        _question: str,
        _conversation_id: UUID | None = None,
    ) -> main.AskResponse:
        raise ProviderUnavailableError(
            "The answer model is temporarily unavailable."
        )

    monkeypatch.setattr(main, "_run_question", fail_to_run)

    response = TestClient(main.create_app()).post(
        "/ask", json={"question": "Revenue?"}
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The answer model is temporarily unavailable."
    }


def test_api_response_has_no_figures_for_unanswerable_graph_state() -> None:
    """An honest graph fallback remains intact and does not invent figures."""
    state: AnalystState = {
        "final_answer": "I cannot answer from available sources.",
        "tool_results": [],
        "retrieved_chunks": [],
        "evidence_errors": [],
        "errors": [],
    }

    response = main._response_fields(state)

    assert response.answer == "I cannot answer from available sources."
    assert response.figures == []
    assert response.sources == []
    assert response.caveats == []
