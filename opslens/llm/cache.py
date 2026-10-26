from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def make_cache_key(model: str, system: str, user: str) -> str:
    joined = "\x1f".join([model, system, user])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


class LLMCache:
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
