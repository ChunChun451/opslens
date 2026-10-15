"""Keep each provider under its free-tier limits: requests per minute and per day.

Why this design:
- Per minute: a sliding window. We remember the time of each call in the last 60 s; if the
  window is full, we sleep until the oldest call is 60 s old. Simple and exact.
- Per day: a counter in SQLite, so the budget survives restarts (the eval can run many
  times a day). Days are counted in UTC. Google resets at midnight Pacific time, so our
  day boundary is off by some hours; the configured budgets sit well below the real
  limits, which covers that gap.
- `now_fn` and `sleep_fn` can be replaced in tests, so tests never really sleep.

Example (limit 2 per minute):
    t=0 s call, t=1 s call, t=2 s → must wait until t=60 s for the third call.
"""

from __future__ import annotations

import sqlite3
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class RateLimiter:
    """Tracks calls per provider and blocks until a call is allowed."""

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
        """Sleep until one more call fits in the last-60-seconds window. Returns seconds slept."""
        window = self._recent.setdefault(provider, deque())
        now = self._now()
        # Forget calls older than 60 s.
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
        """Remember a call for both the minute window and the daily counter."""
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
