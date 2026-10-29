"""Tests for demo-password hashing, signed tokens, and rate limiting."""

from __future__ import annotations

from datetime import timedelta

import jwt
import pytest

from app.auth.passwords import hash_password, verify_password
from app.auth.rate_limit import RateLimiter
from app.auth.tokens import (
    AuthenticationConfigurationError,
    create_access_token,
    decode_access_token,
    load_signing_secret,
)


def test_argon2_password_hash_verifies_without_revealing_password() -> None:
    """Argon2 hashes verify the right password and reject a wrong one."""
    password = "test-only-password"
    password_hash = hash_password(password)

    assert password_hash.startswith("$argon2id$")
    assert verify_password(password, password_hash)
    assert not verify_password("different-password", password_hash)


def test_tokens_are_signed_and_expire() -> None:
    """Tokens reject altered signatures and expired claims."""
    secret = "test-signing-secret-that-is-at-least-32-bytes"
    token = create_access_token("sales.demo", secret)
    assert decode_access_token(token, secret) == "sales.demo"

    altered_token = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(altered_token, secret)

    expired_token = create_access_token(
        "sales.demo",
        secret,
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired_token, secret)


def test_signing_secret_must_be_strong(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing or short JWT secrets fail closed."""
    monkeypatch.setenv("JWT_SECRET_KEY", "too-short")

    with pytest.raises(AuthenticationConfigurationError):
        load_signing_secret()


def test_rate_limiter_counts_by_identity() -> None:
    """The request window is isolated by identity and returns retry timing."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)

    assert limiter.retry_after("sales.demo") is None
    assert limiter.retry_after("sales.demo") is None
    assert limiter.retry_after("sales.demo") is not None
    assert limiter.retry_after("hr.demo") is None


def test_rate_limiter_rejects_invalid_configuration() -> None:
    """Rate-limit settings cannot disable request caps accidentally."""
    with pytest.raises(ValueError, match="must be positive"):
        RateLimiter(max_requests=0)
