"""FastAPI application exposing the analyst workflow over HTTP."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from groq import APIError
from langchain_core.messages import AIMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field, SecretStr, field_validator
from mcp.shared.exceptions import McpError

from app.config import ConfigurationError, Settings, load_settings
from app.conversation_store import ConversationStore
from app.graph import answer_question
from app.mcp_client import AnalystMCPClient

LOGGER = logging.getLogger(__name__)


def _chat_model_options(settings: Settings) -> dict[str, Any]:
    """Configure reasoning output explicitly for Groq's GPT-OSS models."""
    options: dict[str, Any] = {
        "model": settings.groq_model,
        "api_key": SecretStr(settings.groq_api_key),
        "temperature": 0,
        "max_retries": 0,
        "max_tokens": settings.groq_max_tokens,
    }
    if settings.groq_model.startswith("openai/gpt-oss-"):
        options["reasoning_format"] = "parsed"
    return options


class _ChatModelAdapter:
    """Adapt the chat model's broad LangChain types to the graph protocol."""

    def __init__(self, model: Any) -> None:
        self._model = model

    def bind_tools(self, tools: list[dict[str, Any]]) -> _ChatModelAdapter:
        return _ChatModelAdapter(self._model.bind_tools(tools))

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        response = await self._model.ainvoke(messages)
        if not isinstance(response, AIMessage):
            raise TypeError("The configured chat model returned a non-AI message.")
        return response


class AskRequest(BaseModel):
    """Validated request body for the question-answering endpoint."""

    question: str = Field(min_length=1)
    conversation_id: UUID | None = None

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        """Reject whitespace-only questions and normalize surrounding space."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must not be blank.")
        return normalized


class AskResponse(BaseModel):
    """Stable HTTP response containing the answer and supporting evidence."""

    answer: str
    conversation_id: str
    figures: list[dict[str, Any]]
    sources: list[str]
    caveats: list[str]


def _response_fields(
    state: Mapping[str, Any],
    conversation_id: str = "",
) -> AskResponse:
    """Extract tool-backed figures, sources, and caveats from graph state."""
    figures: list[dict[str, Any]] = []
    sources: list[str] = []
    caveats: list[str] = []
    document_sources: set[str] = set()

    for tool_result in state.get("tool_results", []):
        if not tool_result.get("success"):
            continue
        tool_name = tool_result.get("tool_name")
        result = tool_result.get("result")
        if not isinstance(result, dict):
            continue

        if tool_name == "run_analysis":
            analysis_name = result.get("analysis")
            if isinstance(analysis_name, str):
                sources.append(f"run_analysis:{analysis_name}")
            figures.append(
                {
                    "analysis": analysis_name,
                    "period": result.get("period"),
                    "data": result.get("data", []),
                }
            )
            assumptions = result.get("assumptions", [])
            if isinstance(assumptions, list):
                caveats.extend(
                    item for item in assumptions if isinstance(item, str)
                )
        elif tool_name == "query_business_data":
            dataset = result.get("dataset")
            if isinstance(dataset, str):
                sources.append(f"query_business_data:{dataset}")
            figures.append(
                {
                    "dataset": dataset,
                    "total_matches": result.get("total_matches"),
                    "rows": result.get("rows", []),
                }
            )
        elif tool_name == "search_documents":
            sources.append("search_documents")

    for chunk in state.get("retrieved_chunks", []):
        if isinstance(chunk, dict):
            document_name = chunk.get("document_name")
            if isinstance(document_name, str):
                document_sources.add(document_name)
    sources.extend(sorted(document_sources))
    if document_sources:
        caveats.append(
            "Document-derived statements are limited to retrieved passages "
            "and may be incomplete or outdated."
        )
        caveats.append(
            "Reported explanations are not proof that a factor caused a "
            "measured business change."
        )

    for error in state.get("evidence_errors", []):
        if isinstance(error, str):
            caveats.append(f"Evidence check: {error}")
    for error in state.get("errors", []):
        if isinstance(error, str):
            caveats.append(error)

    return AskResponse(
        answer=str(state.get("final_answer", "")),
        conversation_id=conversation_id,
        figures=figures,
        sources=list(dict.fromkeys(sources)),
        caveats=list(dict.fromkeys(caveats)),
    )


async def _run_question(
    question: str,
    conversation_id: UUID | None = None,
) -> AskResponse:
    """Run one question through the same model, MCP tools, and graph as the CLI."""
    settings: Settings = load_settings()
    store = ConversationStore(settings.conversation_db_path)
    active_conversation_id = conversation_id or uuid4()
    if conversation_id is None:
        history: list[tuple[str, str]] = []
        prior_tool_results = []
        prior_retrieved_chunks = []
    else:
        stored_history = store.load_recent_turns(
            active_conversation_id,
            settings.max_history_turns,
        )
        history = stored_history or []
        prior_tool_results, prior_retrieved_chunks = store.load_recent_evidence(
            active_conversation_id,
            settings.max_history_turns,
        )

    model = ChatGroq(**_chat_model_options(settings))
    async with AnalystMCPClient(settings) as mcp_client:
        tools = await mcp_client.list_tools()
        state = await answer_question(
            question,
            _ChatModelAdapter(model),
            tools,
            mcp_client,
            settings.max_steps,
            settings.max_retries,
            history=history,
            prior_tool_results=prior_tool_results,
            prior_retrieved_chunks=prior_retrieved_chunks,
        )
    response = _response_fields(state, str(active_conversation_id))
    store.append_turn(
        active_conversation_id,
        question.strip(),
        response.answer,
        tool_results=[
            result
            for result in state.get("tool_results", [])[len(prior_tool_results) :]
            if result.get("success")
        ],
        retrieved_chunks=state.get("retrieved_chunks", [])[len(prior_retrieved_chunks) :],
    )
    return response


def create_app() -> FastAPI:
    """Create the HTTP app without requiring secrets during module import."""
    application = FastAPI(
        title="Business Analyst AI",
        description="Question-answering API over approved synthetic business data.",
        version="1.0.0",
    )

    @application.post("/ask", response_model=AskResponse)
    async def ask(request: AskRequest) -> AskResponse:
        """Answer a question with evidence-backed figures, sources, and caveats."""
        try:
            return await _run_question(
                request.question,
                request.conversation_id,
            )
        except sqlite3.Error as exc:
            LOGGER.exception("Conversation storage failure: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Conversation memory is temporarily unavailable.",
            ) from exc
        except ConfigurationError as exc:
            LOGGER.error("API configuration failure: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="The question-answering service is not configured.",
            ) from exc
        except APIError as exc:
            LOGGER.warning("Model API request failed: %s", exc)
            raise HTTPException(
                status_code=502,
                detail="The answer model is temporarily unavailable.",
            ) from exc
        except (McpError, OSError, RuntimeError, TimeoutError) as exc:
            LOGGER.error(
                "Question workflow failed type=%s: %s",
                type(exc).__name__,
                exc,
            )
            raise HTTPException(
                status_code=503,
                detail="The question could not be completed because a required service failed.",
            ) from exc

    return application


app = create_app()
