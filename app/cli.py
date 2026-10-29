"""Command-line interface for single-turn business data questions."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groq import APIError as GroqAPIError
from mcp.shared.exceptions import McpError
from openai import APIError as OpenAIAPIError

from app.config import ConfigurationError, load_settings
from app.auth.users import UserAccount, UserStoreError, authenticate_user
from app.graph import answer_question
from app.llm_factory import build_chat_model
from app.mcp_client import AnalystMCPClient
from app.moderation.moderator import check_input
from app.policy.context import MCPUserContext

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


def _authenticate_cli_user() -> UserAccount:
    """Prompt for demo credentials and return only a verified account."""
    username = input("Demo username: ").strip()
    password = getpass.getpass("Demo password: ")
    user = authenticate_user(username, password)
    if user is None:
        raise PermissionError("Invalid demo username or password.")
    return user


async def _answer(question: str) -> str:
    """Connect the primary/fallback model and MCP server for one question."""
    user = _authenticate_cli_user()
    moderation_decision = check_input(question, user.role)
    if moderation_decision is not None:
        LOGGER.warning(
            "moderation event=input_refusal user_id=%s role=%s reason=%s",
            user.user_id,
            user.role,
            moderation_decision.category,
        )
        return moderation_decision.response
    settings = load_settings()
    model = build_chat_model(settings)
    async with AnalystMCPClient(
        settings,
        MCPUserContext(user.user_id, user.role),
    ) as mcp_client:
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
    except (GroqAPIError, OpenAIAPIError) as exc:
        LOGGER.error(
            "Model API request failed type=%s status=%s",
            type(exc).__name__,
            getattr(exc, "status_code", None),
        )
        return 1
    except (
        ConfigurationError,
        McpError,
        OSError,
        PermissionError,
        RuntimeError,
        UserStoreError,
    ) as exc:
        LOGGER.error("Could not answer question: %s", exc)
        return 1
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
