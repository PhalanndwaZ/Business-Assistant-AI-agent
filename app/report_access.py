"""Persistent ownership records for generated report downloads."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ReportOwner:
    """Owner metadata retained for one generated report."""

    user_id: str
    role: str


class ReportAccessStore:
    """Persist report ownership so downloads can enforce per-user access."""

    def __init__(self, database_path: Path) -> None:
        """Create the ownership table and retain its database path."""
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS report_access (
                    filename TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    owner_role TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def register_report(self, filename: str, user_id: str, role: str) -> None:
        """Record the authenticated owner of a newly generated report."""
        if not filename or not user_id or not role:
            raise ValueError("Report filename, owner, and role are required.")
        created_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO report_access (
                    filename,
                    owner_user_id,
                    owner_role,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (filename, user_id, role, created_at),
            )

    def get_owner(self, filename: str) -> ReportOwner | None:
        """Return the report owner, or None when no ownership record exists."""
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT owner_user_id, owner_role
                FROM report_access
                WHERE filename = ?
                """,
                (filename,),
            ).fetchone()
        if row is None:
            return None
        return ReportOwner(user_id=row[0], role=row[1])
