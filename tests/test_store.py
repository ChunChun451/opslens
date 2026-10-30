from __future__ import annotations

import threading
import time
from datetime import date

import pytest

from opslens import bus, store

pytestmark = pytest.mark.skipif(not store.available(), reason="Postgres is not running")


def test_migrations_and_partitions_are_idempotent():
    store.migrate()
    assert store.migrate() == []
    made = store.ensure_partitions(date(2026, 10, 1), months=2)
    assert "ticket_events_2026_10" in made and "risk_scores_2026_11" in made
    with store.connection() as conn:
        versions = [r["version"] for r in conn.execute("select version from schema_migrations order by version")]
    assert versions[:2] == ["001_init", "002_vector"]


def test_seed_creates_one_login_per_agent_and_one_admin_and_no_leads():
    from opslens.seed import seed
    with store.connection() as conn:
        counts = seed(conn)
        roles = {r["role"]: r["n"] for r in conn.execute("select role, count(*) n from users group by role")}
        linked = conn.execute("select count(*) n from users where role = 'agent' and agent_code is not null").fetchone()["n"]
    assert roles == {"admin": 1, "agent": counts["agents"]} and linked == counts["agents"]


def test_publish_reaches_a_subscriber():
    got = []

    def listen():
        for message in bus.subscribe("opslens_test_pubsub", heartbeat_s=3):
            got.append(message)
            break

    t = threading.Thread(target=listen)
    t.start()
    time.sleep(1)
    bus.publish("opslens_test_pubsub", {"n": 7})
    t.join(6)
    assert got == [{"n": 7}]


def test_two_workers_never_take_the_same_job():
    for n in range(6):
        bus.enqueue("test_skip_locked", {"n": n})
    seen: list[int] = []
    lock = threading.Lock()

    def work():
        while (job := bus.dequeue("test_skip_locked", timeout_s=1)) is not None:
            with lock:
                seen.append(job[1]["n"])
            bus.finish(job[0])

    threads = [threading.Thread(target=work) for _ in range(3)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    assert sorted(seen) == list(range(6))


def test_cache_expires():
    bus.cache_set("test_ttl", {"v": 1}, ttl_s=0.3)
    assert bus.cache_get("test_ttl") == {"v": 1}
    time.sleep(0.5)
    assert bus.cache_get("test_ttl") is None
