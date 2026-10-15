"""SQLite cache for LLM replies, keyed by a hash of (model, prompt).

Why this design:
- The same ticket text must never be paid for twice (free quota is small) and the demo
  must work with Wi-Fi off: every reply we ever got is replayed from this file.
- The key is a SHA-256 of the *masked* prompt, so the cache never stores raw PII.
- One table, plain SQL. `sqlite3` is in the Python standard library.

Example:
    >>> key = make_cache_key("gemini-3.1-flash-lite", "system", "user")
    >>> len(key)
    64
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def make_cache_key(model: str, system: str, user: str) -> str:
    """Stable 64-character key. A separator byte stops 'ab'+'c' colliding with 'a'+'bc'."""
    joined = "\x1f".join([model, system, user])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


class LLMCache:
    """Stores reply text by key. Thread-safe enough for our single-process server."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_cache (
                key        TEXT PRIMARY KEY,
                task       TEXT NOT NULL,
                provider   TEXT NOT NULL,
                model      TEXT NOT NULL,
                response   TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, key: str) -> str | None:
        row = self._conn.execute("SELECT response FROM llm_cache WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, task: str, provider: str, model: str, response: str) -> None:
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._conn.execute(
            "INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?, ?, ?, ?)",
            (key, task, provider, model, response, created),
        )
        self._conn.commit()

    def count(self, task: str | None = None) -> int:
        if task is None:
            row = self._conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) FROM llm_cache WHERE task = ?", (task,)).fetchone()
        return int(row[0])

    def close(self) -> None:
        self._conn.close()
