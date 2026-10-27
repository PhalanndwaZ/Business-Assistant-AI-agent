"""Adapt LangChain chat models to the application's async model protocol."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage


class ChatModelAdapter:
    """Narrow LangChain model types to the graph's AI-message interface."""

    def __init__(self, model: Any) -> None:
        """Store a provider model or its tool-bound runnable."""
        self._model = model

    def bind_tools(self, tools: list[dict[str, Any]]) -> ChatModelAdapter:
        """Bind tool schemas and return an adapted runnable."""
        return ChatModelAdapter(self._model.bind_tools(tools))

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        """Invoke the wrapped model and require an AIMessage response."""
        response = await self._model.ainvoke(messages)
        if not isinstance(response, AIMessage):
            raise TypeError("The configured chat model returned a non-AI message.")
        return response
