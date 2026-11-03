"""Load demo accounts and authenticate passwords without exposing hashes."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from pwdlib.exceptions import UnknownHashError

from app.auth.passwords import PASSWORD_HASHER, hash_password, verify_password
from app.config import PROJECT_ROOT

DEFAULT_USERS_PATH = PROJECT_ROOT / "data" / "policy" / "users.json"
VALID_ROLES = frozenset({"sales", "hr", "manager", "admin"})
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("not-a-real-demo-password")
USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{2,63}")
USER_STORE_LOCK = Lock()


class UserStoreError(ValueError):
    """Raised when the demo-user data cannot be loaded or validated."""


class UserAlreadyExistsError(UserStoreError):
    """Raised when a new account reuses an existing username."""


@dataclass(frozen=True)
class UserAccount:
    """Expose authenticated identity fields without the stored password hash."""

    user_id: str
    username: str
    name: str
    role: str
    password_hash: str


def _resolve_users_path(path: Path | None) -> Path:
    """Use the configured default path unless a caller supplies a test path."""
    return path if path is not None else DEFAULT_USERS_PATH


def load_users(path: Path | None = None) -> dict[str, UserAccount]:
    """Load and validate demo users from the configured JSON file."""
    path = _resolve_users_path(path)
    try:
        records: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UserStoreError(f"Could not load demo users from {path}: {exc}") from exc
    if not isinstance(records, list) or not records:
        raise UserStoreError("Demo users must be a non-empty JSON array.")

    users: dict[str, UserAccount] = {}
    user_ids: set[str] = set()
    required_fields = {"user_id", "username", "name", "role", "password_hash"}
    for row_number, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) != required_fields:
            raise UserStoreError(
                f"Demo user row {row_number} must contain exactly "
                f"{sorted(required_fields)}."
            )
        user_id = record["user_id"]
        username = record["username"]
        name = record["name"]
        role = record["role"]
        password_hash = record["password_hash"]
        if (
            not isinstance(user_id, str)
            or not user_id
            or user_id in user_ids
            or not isinstance(username, str)
            or not username
            or username in users
            or not isinstance(name, str)
            or not name
            or not isinstance(role, str)
            or role not in VALID_ROLES
            or not isinstance(password_hash, str)
            or not password_hash.startswith("$argon2id$")
        ):
            raise UserStoreError(f"Demo user row {row_number} is invalid.")
        user_ids.add(user_id)
        users[username] = UserAccount(
            user_id=user_id,
            username=username,
            name=name,
            role=role,
            password_hash=password_hash,
        )
    return users


def get_user_by_id(
    user_id: str,
    path: Path | None = None,
) -> UserAccount | None:
    """Return the account with a stable user ID, if it still exists."""
    return next(
        (user for user in load_users(path).values() if user.user_id == user_id),
        None,
    )


def create_user(
    *,
    username: str,
    name: str,
    role: str,
    password: str,
    path: Path | None = None,
) -> UserAccount:
    """Create one validated account and atomically persist its password hash."""
    resolved_path = _resolve_users_path(path)
    normalized_username = username.strip().lower()
    normalized_name = name.strip()
    if not USERNAME_PATTERN.fullmatch(normalized_username):
        raise ValueError(
            "Username must be 3-64 characters using letters, numbers, '.', "
            "'_' or '-'."
        )
    if not normalized_name or len(normalized_name) > 120:
        raise ValueError("Name must contain 1-120 non-whitespace characters.")
    if role not in VALID_ROLES:
        raise ValueError("Role must be one of the configured roles.")
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")

    account = UserAccount(
        user_id=f"user-{uuid4().hex}",
        username=normalized_username,
        name=normalized_name,
        role=role,
        password_hash=hash_password(password),
    )
    with USER_STORE_LOCK:
        users = load_users(resolved_path)
        if normalized_username.casefold() in {
            existing_username.casefold() for existing_username in users
        }:
            raise UserAlreadyExistsError("That username is already registered.")
        records = [
            {
                "user_id": user.user_id,
                "username": user.username,
                "name": user.name,
                "role": user.role,
                "password_hash": user.password_hash,
            }
            for user in users.values()
        ]
        records.append(
            {
                "user_id": account.user_id,
                "username": account.username,
                "name": account.name,
                "role": account.role,
                "password_hash": account.password_hash,
            }
        )
        temporary_path: str | None = None
        try:
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=resolved_path.parent,
                prefix=f".{resolved_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                json.dump(records, temporary_file, indent=2, ensure_ascii=False)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, resolved_path)
        except OSError as exc:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
            raise UserStoreError(
                f"Could not persist new demo user to {resolved_path}: {exc}"
            ) from exc
    return account


def authenticate_user(
    username: str,
    password: str,
    path: Path | None = None,
) -> UserAccount | None:
    """Authenticate a username and password with a same-cost unknown-user check."""
    users = load_users(path)
    user = users.get(username)
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    try:
        matches = verify_password(password, password_hash)
    except UnknownHashError as exc:
        raise UserStoreError("A demo user has an unsupported password hash.") from exc
    return user if user is not None and matches else None
