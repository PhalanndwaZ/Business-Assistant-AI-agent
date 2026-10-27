"""Command-line interface for single-turn business data questions."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groq import APIError
from langchain_groq import ChatGroq
from mcp.shared.exceptions import McpError

from app.config import ConfigurationError, load_settings
from app.graph import answer_question
from app.mcp_client import AnalystMCPClient

LOGGER = logging.getLogger(__name__)


def _parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse one standalone natural-language question."""
    parser = argparse.ArgumentParser(
        description="Ask one question about the synthetic business datasets."
    )
    parser.add_argument(
        "question",
        nargs="+",
        help="Question to answer using the approved business-data tools.",
    )
    return parser.parse_args(arguments)


async def _answer(question: str) -> str:
    """Connect the Groq model and MCP server for one question."""
    settings = load_settings()
    model = ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key, # pyright: ignore[reportArgumentType]
        temperature=0,
        max_retries=0,
        max_tokens=settings.groq_max_tokens,
        reasoning_format=(
            "parsed"
            if settings.groq_model.startswith("openai/gpt-oss-")
            else None
        ),
    )
    async with AnalystMCPClient(settings) as mcp_client:
        tools = await mcp_client.list_tools()
        result = await answer_question(
            question,
            model,
            tools,
            mcp_client,
            settings.max_steps,
            settings.max_retries,
        )
    if os.getenv("PHASE5_TRACE") == "1":
        print(
            "PHASE5_TRACE_JSON="
            + json.dumps(
                result.get("workflow_trace", []),
                ensure_ascii=True,
                default=str,
            ),
            file=sys.stderr,
        )
    return result["final_answer"]


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the CLI question and write the final answer to standard output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    parsed = _parse_arguments(arguments)
    question = " ".join(parsed.question)
    try:
        answer = asyncio.run(_answer(question))
    except (APIError, ConfigurationError, McpError, OSError, RuntimeError) as exc:
        LOGGER.error("Could not answer question: %s", exc)
        return 1
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
