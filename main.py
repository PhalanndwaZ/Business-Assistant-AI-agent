"""FastAPI application exposing the analyst workflow over HTTP."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from groq import APIError as GroqAPIError
from openai import APIError as OpenAIAPIError
from pydantic import BaseModel, Field, field_validator
from mcp.shared.exceptions import McpError

from app.config import ConfigurationError, Settings, load_settings
from app.conversation_store import ConversationStore
from app.graph import answer_question
from app.llm_factory import build_chat_model
from app.llm_fallback import ProviderUnavailableError
from app.mcp_client import AnalystMCPClient

LOGGER = logging.getLogger(__name__)


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

    model = build_chat_model(settings)
    async with AnalystMCPClient(settings) as mcp_client:
        tools = await mcp_client.list_tools()
        state = await answer_question(
            question,
            model,
            tools,
            mcp_client,
            settings.max_steps,
            settings.max_retries,
            history=history,
            prior_tool_results=prior_tool_results,
            prior_retrieved_chunks=prior_retrieved_chunks,
        )
    current_turn_state = dict(state)
    current_turn_state["tool_results"] = state.get("tool_results", [])[
        len(prior_tool_results) :
    ]
    current_turn_state["retrieved_chunks"] = state.get("retrieved_chunks", [])[
        len(prior_retrieved_chunks) :
    ]
    response = _response_fields(current_turn_state, str(active_conversation_id))
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
        except ProviderUnavailableError as exc:
            LOGGER.error("Model providers are unavailable.")
            raise HTTPException(
                status_code=502,
                detail=str(exc),
            ) from exc
        except (GroqAPIError, OpenAIAPIError) as exc:
            LOGGER.warning(
                "Model API request failed type=%s status=%s",
                type(exc).__name__,
                getattr(exc, "status_code", None),
            )
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
