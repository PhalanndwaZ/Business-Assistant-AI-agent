"""Load demo accounts and authenticate passwords without exposing hashes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pwdlib.exceptions import UnknownHashError

from app.auth.passwords import PASSWORD_HASHER, verify_password
from app.config import PROJECT_ROOT

DEFAULT_USERS_PATH = PROJECT_ROOT / "data" / "policy" / "users.json"
VALID_ROLES = frozenset({"sales", "hr", "manager", "admin"})
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("not-a-real-demo-password")


class UserStoreError(ValueError):
    """Raised when the demo-user data cannot be loaded or validated."""


@dataclass(frozen=True)
class UserAccount:
    """Expose authenticated identity fields without the stored password hash."""

    user_id: str
    username: str
    name: str
    role: str
    password_hash: str


def load_users(path: Path = DEFAULT_USERS_PATH) -> dict[str, UserAccount]:
    """Load and validate demo users from the configured JSON file."""
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


def get_user_by_id(user_id: str, path: Path = DEFAULT_USERS_PATH) -> UserAccount | None:
    """Return the account with a stable user ID, if it still exists."""
    return next(
        (user for user in load_users(path).values() if user.user_id == user_id),
        None,
    )


def authenticate_user(
    username: str,
    password: str,
    path: Path = DEFAULT_USERS_PATH,
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
