"""Typed state exchanged by the LangGraph question-answering workflow."""

from __future__ import annotations

import operator
from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ToolResult(TypedDict):
    """Record one MCP call, its validated arguments, and its result."""

    call_id: NotRequired[str]
    tool_name: str
    arguments: dict[str, Any]
    result: Any
    success: bool


class AnalystState(TypedDict, total=False):
    """State passed through agent, tools, evidence, and finalization nodes."""

    question: str
    messages: Annotated[list[BaseMessage], add_messages]
    tool_results: Annotated[list[ToolResult], operator.add]
    retrieved_chunks: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    workflow_trace: Annotated[list[dict[str, Any]], operator.add]
    llm_responses: Annotated[list[dict[str, str]], operator.add]
    step_count: int
    retry_count: int
    draft_answer: str
    final_answer: str
    evidence_ok: bool
    evidence_errors: list[str]
    clarification_question: str
    step_limit_reached: bool
