from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Iterator

from psycopg import Connection

from opslens import store
from opslens.config import load_env_file

_redis = None
_checked = False
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def redis_client():
    global _redis, _checked
    if _checked:
        return _redis
    _checked = True
    load_env_file()
    url = os.environ.get("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis
        client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=1, socket_connect_timeout=1)
        client.ping()
        _redis = client
    except Exception:
        _redis = None
    return _redis


def backend() -> str:
    return "redis" if redis_client() is not None else "postgres"


def publish(channel: str, message: dict) -> None:
    data = json.dumps(message, default=str)
    r = redis_client()
    if r is not None:
        r.publish(channel, data)
        return
    with store.connection() as conn:
        conn.execute("select pg_notify(%s, %s)", (channel, data))


def subscribe(channel: str, heartbeat_s: float = 15.0) -> Iterator[dict | None]:
    r = redis_client()
    if r is not None:
        sub = r.pubsub()
        sub.subscribe(channel)
        try:
            while True:
                m = sub.get_message(ignore_subscribe_messages=True, timeout=heartbeat_s)
                yield json.loads(m["data"]) if m else None
        finally:
            sub.close()
        return
    conn = Connection.connect(store.database_url(), autocommit=True)
    try:
        conn.execute(f'listen "{channel}"')
        while True:
            got = False
            for note in conn.notifies(timeout=heartbeat_s, stop_after=1):
                got = True
                yield json.loads(note.payload)
            if not got:
                yield None
    finally:
        conn.close()


def enqueue(queue: str, payload: dict) -> None:
    r = redis_client()
    if r is not None:
        r.rpush(f"queue:{queue}", json.dumps(payload, default=str))
        return
    with store.connection() as conn:
        conn.execute("insert into job_queue (queue, payload) values (%s, %s)", (queue, json.dumps(payload, default=str)))


def dequeue(queue: str, timeout_s: float = 5.0) -> tuple[int | None, dict] | None:
    r = redis_client()
    if r is not None:
        got = r.blpop(f"queue:{queue}", timeout=max(1, int(timeout_s)))
        return (None, json.loads(got[1])) if got else None
    deadline = time.monotonic() + timeout_s
    while True:
        with store.connection() as conn:
            row = conn.execute(
                "update job_queue set status = 'taken', taken_at = now(), attempts = attempts + 1 "
                "where id = (select id from job_queue where queue = %s and status = 'ready' "
                "order by id for update skip locked limit 1) returning id, payload", (queue,)).fetchone()
        if row:
            return row["id"], row["payload"]
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.25)


def finish(job_id: int | None, ok: bool = True) -> None:
    if job_id is None:
        return
    with store.connection() as conn:
        conn.execute("update job_queue set status = %s where id = %s", ("done" if ok else "failed", job_id))


def cache_get(key: str) -> Any:
    r = redis_client()
    if r is not None:
        raw = r.get(f"cache:{key}")
        return json.loads(raw) if raw else None
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        _cache.pop(key, None)
    return None


def cache_set(key: str, value: Any, ttl_s: float) -> None:
    r = redis_client()
    if r is not None:
        r.setex(f"cache:{key}", max(1, int(ttl_s)), json.dumps(value, default=str))
        return
    with _cache_lock:
        _cache[key] = (time.monotonic() + ttl_s, value)
