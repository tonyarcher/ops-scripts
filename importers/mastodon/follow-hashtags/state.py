#!/usr/bin/env python3
"""SQLite progress store for the follow-hashtags importer.

Same schema as the former TypeScript version. Uses stdlib sqlite3.

Run:  python importers/mastodon/follow-hashtags/follow_hashtags.py --help
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tags (
  name TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  updated_at TEXT NOT NULL
);
"""


@dataclass
class TagRow:
    name: str
    status: str
    attempts: int
    last_error: str | None
    updated_at: str


@dataclass
class StatusCounts:
    pending: int = 0
    done: int = 0
    already: int = 0
    error: int = 0
    invalid: int = 0


class ProgressStore:
    """Tracks per-tag status so re-runs skip finished work."""

    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            parent = Path(db_path).parent
            if str(parent) and str(parent) != ".":
                parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path)
        self._db.execute(SCHEMA)
        self._db.commit()

    def get(self, name: str) -> TagRow | None:
        """Return the row for name, or None."""
        cur = self._db.execute(
            "SELECT name, status, attempts, last_error, updated_at FROM tags WHERE name = ?",
            (name,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return TagRow(
            name=row[0],
            status=row[1],
            attempts=row[2],
            last_error=row[3],
            updated_at=row[4],
        )

    def upsert(self, name: str, status: str, error: str | None = None) -> None:
        """Insert or update a tag row, bumping attempts."""
        now = datetime.now(UTC).isoformat()
        self._db.execute(
            """
            INSERT INTO tags (name, status, attempts, last_error, updated_at)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
              status = excluded.status,
              attempts = tags.attempts + 1,
              last_error = excluded.last_error,
              updated_at = excluded.updated_at
            """,
            (name, status, error, now),
        )
        self._db.commit()

    def summary(self) -> StatusCounts:
        """Count rows by status."""
        counts = StatusCounts()
        cur = self._db.execute("SELECT status, COUNT(*) FROM tags GROUP BY status")
        for status, count in cur.fetchall():
            if hasattr(counts, status):
                setattr(counts, status, count)
        return counts

    def close(self) -> None:
        """Close the database connection."""
        self._db.close()


def open_progress_store(db_path: str) -> ProgressStore:
    """Open a progress store at db_path (or :memory: for tests)."""
    return ProgressStore(db_path)
