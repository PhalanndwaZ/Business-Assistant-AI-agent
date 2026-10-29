"""Async MCP stdio client for the local business-data server."""

from __future__ import annotations

import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, Tool

from app.config import PROJECT_ROOT, Settings
from app.policy.context import MCPUserContext
from app.policy.policy import AccessPolicy


class BusinessDataMCPClient:
    """Manage the local business-data server process and tool calls."""

    def __init__(
        self,
        settings: Settings,
        user_context: MCPUserContext,
    ) -> None:
        """Configure the local stdio server with only required environment."""
        self.settings = settings
        self.user_context = user_context
        self._exit_stack = AsyncExitStack()
        self._session: ClientSession | None = None

    async def __aenter__(self) -> BusinessDataMCPClient:
        """Start the stdio server and initialize the MCP session."""
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "WINDIR": os.environ.get("WINDIR", ""),
            "TEMP": os.environ.get("TEMP", ""),
            "TMP": os.environ.get("TMP", ""),
            "DATA_DIR": str(self.settings.data_dir),
            "AS_OF_DATE": self.settings.as_of_date.isoformat(),
            "PYTHONPATH": str(PROJECT_ROOT),
        }
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_servers.business_data_server"],
            env=environment,
            cwd=Path(PROJECT_ROOT),
        )
        try:
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                stdio_client(parameters)
            )
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await self._session.initialize()
        except BaseException:
            await self._exit_stack.aclose()
            self._session = None
            raise
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        """Close the MCP session and its child server process."""
        await self._exit_stack.aclose()
        self._session = None

    async def list_tools(self) -> list[Tool]:
        """Return tool declarations from the connected MCP server."""
        if self._session is None:
            raise RuntimeError("MCP client is not connected.")
        result = await self._session.list_tools()
        return result.tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> CallToolResult:
        """Call a discovered MCP tool and preserve the protocol response."""
        if self._session is None:
            raise RuntimeError("MCP client is not connected.")
        metadata = {
            "user_context": {
                "user_id": self.user_context.user_id,
                "role": self.user_context.role,
            },
        }
        return await self._session.call_tool(
            tool_name,
            arguments,
            meta=metadata,
        )


class DocumentSearchMCPClient(BusinessDataMCPClient):
    """Manage the local document-search server with its embedding settings."""

    async def __aenter__(self) -> DocumentSearchMCPClient:
        """Start and initialize the document-search MCP server."""
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "WINDIR": os.environ.get("WINDIR", ""),
            "TEMP": os.environ.get("TEMP", ""),
            "TMP": os.environ.get("TMP", ""),
            "MISTRAL_API_KEY": self.settings.mistral_api_key,
            "MISTRAL_EMBEDDING_MODEL": self.settings.mistral_embedding_model,
            "VECTOR_STORE_PATH": str(self.settings.vector_store_path),
            "MIN_SIMILARITY": str(self.settings.min_similarity),
            "TOP_K": str(self.settings.top_k),
            "PYTHONPATH": str(PROJECT_ROOT),
        }
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_servers.rag_server"],
            env=environment,
            cwd=Path(PROJECT_ROOT),
        )
        try:
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                stdio_client(parameters)
            )
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await self._session.initialize()
        except BaseException:
            await self._exit_stack.aclose()
            self._session = None
            raise
        return self


class AnalystMCPClient:
    """Expose business-data and document-search MCP tools as one client."""

    def __init__(
        self,
        settings: Settings,
        user_context: MCPUserContext,
    ) -> None:
        """Create both isolated stdio MCP clients."""
        if not user_context.user_id or not user_context.role:
            raise ValueError("MCP user context must include user ID and role.")
        self.user_context = user_context
        self._policy = AccessPolicy()
        self._business_client = BusinessDataMCPClient(settings, user_context)
        self._document_client = DocumentSearchMCPClient(settings, user_context)
        self._tool_clients: dict[str, BusinessDataMCPClient] = {}
        self._stack = AsyncExitStack()
        self._tools: list[Tool] = []
        self._connected = False

    async def __aenter__(self) -> AnalystMCPClient:
        """Start both MCP servers and index their tool declarations."""
        try:
            await self._stack.enter_async_context(self._business_client)
            await self._stack.enter_async_context(self._document_client)
            business_tools = await self._business_client.list_tools()
            document_tools = await self._document_client.list_tools()
            all_tools = business_tools + document_tools
            tool_names = [tool.name for tool in all_tools]
            if len(tool_names) != len(set(tool_names)):
                raise RuntimeError("MCP servers declared duplicate tool names.")
            allowed_tools = [
                tool
                for tool in all_tools
                if self._policy.can_use_tool(self.user_context.role, tool.name)
                and (
                    tool.name != "generate_report"
                    or self._policy.can_generate_report(self.user_context.role)
                )
            ]
            allowed_tool_names = {tool.name for tool in allowed_tools}
            self._tool_clients = {
                tool.name: client
                for client, tools in (
                    (self._business_client, business_tools),
                    (self._document_client, document_tools),
                )
                for tool in tools
                if tool.name in allowed_tool_names
            }
            self._tools = allowed_tools
            self._connected = True
        except BaseException:
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        """Close both MCP server processes."""
        await self._stack.aclose()
        self._tool_clients.clear()
        self._tools = []
        self._connected = False

    async def list_tools(self) -> list[Tool]:
        """Return tool declarations from both connected MCP servers."""
        if not self._connected:
            raise RuntimeError("MCP clients are not connected.")
        return self._tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> CallToolResult:
        """Dispatch a tool call to the server that declared it."""
        client = self._tool_clients.get(tool_name)
        if client is None:
            raise ValueError(f"Unknown MCP tool: {tool_name}.")
        return await client.call_tool(tool_name, arguments)
