from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from opslens.config import load_env_file, project_path

MIGRATIONS = project_path("db/migrations")
PARTITIONED = ("ticket_events", "decisions", "risk_scores")
DEFAULT_URL = "postgresql://opslens:opslens-local@127.0.0.1:5432/opslens"

_pool: ConnectionPool | None = None


def database_url() -> str:
    load_env_file()
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(database_url(), min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=True)
    return _pool


@contextmanager
def connection() -> Iterator[Connection]:
    with pool().connection() as conn:
        yield conn


def available() -> bool:
    try:
        with connection() as conn:
            conn.execute("select 1")
        return True
    except Exception:
        return False


def migrate(folder: Path = MIGRATIONS) -> list[str]:
    applied = []
    with connection() as conn:
        conn.execute("create table if not exists schema_migrations (version text primary key, applied_at timestamptz not null default now())")
        done = {r["version"] for r in conn.execute("select version from schema_migrations")}
        for path in sorted(folder.glob("*.sql")):
            if path.stem in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("insert into schema_migrations (version) values (%s)", (path.stem,))
            applied.append(path.stem)
    return applied


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def next_month(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def ensure_partitions(first: date, months: int = 3) -> list[str]:
    made = []
    with connection() as conn:
        lo = month_start(first)
        for _ in range(months):
            hi = next_month(lo)
            for table in PARTITIONED:
                name = f"{table}_{lo:%Y_%m}"
                conn.execute(f"create table if not exists {name} partition of {table} for values from ('{lo}') to ('{hi}')")
                made.append(name)
            lo = hi
    return made


def reset(conn: Connection) -> None:
    conn.execute("truncate ticket_events, decisions, risk_scores, ticket_embeddings, tickets restart identity cascade")
