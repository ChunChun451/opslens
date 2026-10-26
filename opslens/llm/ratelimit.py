from __future__ import annotations

import sqlite3
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class RateLimiter:
    def __init__(
        self,
        db_path: Path,
        now_fn: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_usage (
                provider TEXT NOT NULL,
                day      TEXT NOT NULL,
                calls    INTEGER NOT NULL,
                PRIMARY KEY (provider, day)
            )
            """
        )
        self._conn.commit()
        self._now = now_fn
        self._sleep = sleep_fn
        self._recent: dict[str, deque[float]] = {}

    def _today(self) -> str:
        return datetime.fromtimestamp(self._now(), tz=timezone.utc).strftime("%Y-%m-%d")

    def calls_today(self, provider: str) -> int:
        row = self._conn.execute(
            "SELECT calls FROM llm_usage WHERE provider = ? AND day = ?", (provider, self._today())
        ).fetchone()
        return int(row[0]) if row else 0

    def has_daily_budget(self, provider: str, requests_per_day: int) -> bool:
        return self.calls_today(provider) < requests_per_day

    def wait_for_slot(self, provider: str, requests_per_minute: int) -> float:
        window = self._recent.setdefault(provider, deque())
        now = self._now()
        while window and now - window[0] >= 60.0:
            window.popleft()
        slept = 0.0
        if len(window) >= requests_per_minute:
            wait = 60.0 - (now - window[0])
            if wait > 0:
                self._sleep(wait)
                slept = wait
            window.popleft()
        return slept

    def record_call(self, provider: str) -> None:
        self._recent.setdefault(provider, deque()).append(self._now())
        self._conn.execute(
            """
            INSERT INTO llm_usage (provider, day, calls) VALUES (?, ?, 1)
            ON CONFLICT(provider, day) DO UPDATE SET calls = calls + 1
            """,
            (provider, self._today()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
