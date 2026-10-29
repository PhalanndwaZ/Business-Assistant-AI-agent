"""Create and validate short-lived signed bearer tokens."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from jwt.exceptions import InvalidTokenError

from app.config import PROJECT_ROOT

TOKEN_ALGORITHM = "HS256"
TOKEN_ISSUER = "business-analyst-ai"
ACCESS_TOKEN_LIFETIME = timedelta(minutes=30)
MINIMUM_SECRET_LENGTH = 32


class AuthenticationConfigurationError(ValueError):
    """Raised when the signing secret is missing or too weak."""


def load_signing_secret() -> str:
    """Load a sufficiently strong JWT secret from the environment or .env."""
    load_dotenv(PROJECT_ROOT / ".env")
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if len(secret.encode("utf-8")) < MINIMUM_SECRET_LENGTH:
        raise AuthenticationConfigurationError(
            "JWT_SECRET_KEY must contain at least 32 bytes."
        )
    return secret


def create_access_token(
    user_id: str,
    secret: str,
    expires_delta: timedelta = ACCESS_TOKEN_LIFETIME,
) -> str:
    """Sign an expiring token whose subject is the stable user ID."""
    issued_at = datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "iss": TOKEN_ISSUER,
        "iat": issued_at,
        "exp": issued_at + expires_delta,
    }
    return jwt.encode(claims, secret, algorithm=TOKEN_ALGORITHM)


def decode_access_token(token: str, secret: str) -> str:
    """Verify token signature and claims, returning its user-ID subject."""
    claims = jwt.decode(
        token,
        secret,
        algorithms=[TOKEN_ALGORITHM],
        issuer=TOKEN_ISSUER,
        options={"require": ["exp", "iat", "iss", "sub"]},
    )
    username = claims.get("sub")
    if not isinstance(username, str) or not username:
        raise InvalidTokenError("Token subject is invalid.")
    return username
