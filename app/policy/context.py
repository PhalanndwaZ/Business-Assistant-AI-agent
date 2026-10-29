"""Resolve the trusted caller identity carried outside MCP tool arguments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context

from app.auth.users import UserStoreError, get_user_by_id

ACCESS_DENIED_MESSAGE = "That data isn't available for your account."


class PolicyAccessDenied(PermissionError):
    """Raised when an identity, tool, or protected data is not permitted."""

    def __init__(self) -> None:
        """Use one generic message for forbidden and unknown data."""
        super().__init__(ACCESS_DENIED_MESSAGE)


@dataclass(frozen=True)
class MCPUserContext:
    """Minimal verified identity sent through MCP request metadata."""

    user_id: str
    role: str


def resolve_mcp_user(context: Context | Any) -> MCPUserContext:
    """Validate metadata against the current demo-user record."""
    try:
        metadata = context.request_context.meta
        extra = metadata.model_extra if metadata is not None else None
        identity = extra.get("user_context") if isinstance(extra, dict) else None
        user_id = identity.get("user_id") if isinstance(identity, dict) else None
        role = identity.get("role") if isinstance(identity, dict) else None
        if not isinstance(user_id, str) or not isinstance(role, str):
            raise PolicyAccessDenied()
        user = get_user_by_id(user_id)
    except (AttributeError, TypeError, UserStoreError) as exc:
        raise PolicyAccessDenied() from exc
    if user is None or user.role != role:
        raise PolicyAccessDenied()
    return MCPUserContext(user_id=user.user_id, role=user.role)
