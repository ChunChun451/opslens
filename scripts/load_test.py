from __future__ import annotations

import json
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE_URL = "postgresql://opslens:opslens-local@127.0.0.1:5432/"
LOAD_DB = "opslens_load"
OUT = ROOT / "docs" / "v2" / "results" / "load_test.json"
TICKETS = int(os.environ.get("LOAD_TICKETS", "1000000"))
DAYS = 30
TODAY_SHARE = 0.02
QUERY_RUNS = 25
HTTP_USERS = 40
HTTP_SECONDS = 20
PORT = 8099
TEAMS = ["A", "B", "C", "D"]
CATEGORIES = ["late_delivery", "missing_item", "wrong_item", "refund", "payment_failure", "app_bug", "account",
              "restaurant_partner"]
SLA = {"P1": 15, "P2": 30, "P3": 60}


def make_database() -> None:
    import psycopg

    with psycopg.connect(BASE_URL + "opslens", autocommit=True) as conn:
        if conn.execute("select 1 from pg_database where datname = %s", (LOAD_DB,)).fetchone():
            conn.execute(f"drop database {LOAD_DB} with (force)")
        conn.execute(f"create database {LOAD_DB} owner opslens")
    os.environ["DATABASE_URL"] = BASE_URL + LOAD_DB


def timed(fn) -> float:
    started = time.perf_counter()
    fn()
    return time.perf_counter() - started


def load(conn, agents: list[str]) -> dict:
    rng = np.random.default_rng(7)
    now = datetime.now().astimezone()
    start = (now - timedelta(days=DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)
    span = (now - start).total_seconds()
    offsets = np.where(rng.random(TICKETS) < TODAY_SHARE,
                       rng.uniform((now.replace(hour=0, minute=0, second=0) - start).total_seconds(), span, TICKETS),
                       rng.uniform(0, span, TICKETS))
    offsets.sort()
    created = [start + timedelta(seconds=float(s)) for s in offsets]
    prio = rng.choice(["P1", "P2", "P3"], TICKETS, p=[0.15, 0.45, 0.40])
    cat = rng.choice(CATEGORIES, TICKETS)
    team = rng.choice(TEAMS, TICKETS)
    who = rng.choice(agents, TICKETS)
    wait = rng.exponential(6, TICKETS)
    work = rng.gamma(2.0, 6.0, TICKETS)
    rows, events, decisions = 0, 0, 0
    started = time.perf_counter()
    with conn.cursor() as cur:
        with cur.copy("copy tickets (id, day, created_at, channel, priority, language, category, body, status, assignee, "
                      "team, sla_due_at, assigned_at, solved_at, breached, risk) from stdin") as cp:
            for i in range(TICKETS):
                c = created[i]
                due = c + timedelta(minutes=SLA[prio[i]])
                picked = c + timedelta(minutes=float(wait[i]))
                solved = picked + timedelta(minutes=float(work[i]))
                if solved <= now:
                    status, assignee, assigned, done, breached = "solved", who[i], picked, solved, solved > due
                elif picked <= now:
                    status, assignee, assigned, done, breached = "in_progress", who[i], picked, None, (now > due) or None
                else:
                    status, assignee, assigned, done, breached = "open", None, None, None, (now > due) or None
                cp.write_row((f"L{i:08d}", 0, c, "chat", prio[i], "en", cat[i], "load test ticket", status, assignee,
                              team[i] if assignee is None else assignee[0], due, assigned, done, breached,
                              None if status == "solved" else round(float(rng.random()), 3)))
                rows += 1
        tickets_s = time.perf_counter() - started
        started = time.perf_counter()
        with cur.copy("copy ticket_events (ticket_id, at, kind, actor) from stdin") as cp:
            for i in range(TICKETS):
                c = created[i]
                cp.write_row((f"L{i:08d}", c, "created", None))
                picked = c + timedelta(minutes=float(wait[i]))
                if picked <= now:
                    cp.write_row((f"L{i:08d}", picked, "assigned", who[i]))
                    events += 1
                    solved = picked + timedelta(minutes=float(work[i]))
                    if solved <= now:
                        cp.write_row((f"L{i:08d}", solved, "solved", who[i]))
                        events += 1
                events += 1
        with cur.copy("copy decisions (at, ticket_id, agent_code, reason, rescue_value) from stdin") as cp:
            for i in range(TICKETS):
                picked = created[i] + timedelta(minutes=float(wait[i]))
                if picked <= now:
                    cp.write_row((picked, f"L{i:08d}", who[i], "load test", 0.1))
                    decisions += 1
        events_s = time.perf_counter() - started
    conn.commit()
    analyze_s = timed(lambda: conn.execute("analyze"))
    conn.commit()
    return {"tickets": rows, "events": events, "decisions": decisions, "tickets_seconds": round(tickets_s, 1),
            "events_and_decisions_seconds": round(events_s, 1),
            "rows_per_second": round((rows + events + decisions) / (tickets_s + events_s)), "analyze_seconds": round(analyze_s, 1)}


QUERIES = {
    "open queue for one team (agent's team view)":
        ("select id, priority, sla_due_at, risk from tickets where status <> 'solved' and team = 'B' "
         "and created_at >= current_date and created_at < current_date + 1 order by sla_due_at limit 100", ()),
    "an agent's own open tickets":
        ("select id from tickets where assignee = 'B03' and status <> 'solved' "
         "and created_at >= current_date and created_at < current_date + 1", ()),
    "today's numbers for the console":
        ("select count(*), count(*) filter (where status = 'open'), count(*) filter (where breached) from tickets "
         "where created_at >= current_date and created_at < current_date + 1", ()),
    "one ticket with its full history":
        ("select t.*, (select json_agg(e) from ticket_events e where e.ticket_id = t.id) from tickets t where t.id = %s",
         (f"L{TICKETS // 2:08d}",)),
    "30-day missed rate per team per day":
        ("select team, created_at::date, count(*) filter (where breached)::float / count(*) from tickets "
         "where created_at >= current_date - 30 group by 1, 2", ()),
    "30-day missed rate per team per day, from team_daily":
        ("select team, day, missed::float / tickets from team_daily where day >= current_date - 30", ()),
    "last week's events for the replay":
        ("select count(*) from ticket_events where at >= now() - interval '7 days'", ()),
}


def query_times(conn) -> dict:
    out = {}
    conn.execute("refresh materialized view team_daily")
    conn.commit()
    for name, (sql, params) in QUERIES.items():
        conn.execute(sql, params).fetchall()
        times = sorted(timed(lambda: conn.execute(sql, params).fetchall()) * 1000 for _ in range(QUERY_RUNS))
        plan = conn.execute("explain " + sql, params).fetchall()
        out[name] = {"p50_ms": round(statistics.median(times), 2), "p95_ms": round(times[int(0.95 * len(times)) - 1], 2),
                     "plan": [list(r.values())[0] for r in plan][:6]}
    out["refresh team_hourly (concurrently)"] = {"seconds": round(timed(
        lambda: conn.execute("refresh materialized view concurrently team_hourly")), 2)}
    out["refresh team_daily (concurrently)"] = {"seconds": round(timed(
        lambda: conn.execute("refresh materialized view concurrently team_daily")), 2)}
    conn.commit()
    return out


def http_test() -> dict:
    import httpx
    import uvicorn

    os.environ["OPSLENS_MIRROR"] = "0"
    os.environ["OPSLENS_AGENTS"] = "0"
    os.environ["OPSLENS_WARM"] = "0"
    from opslens.seed import demo_password
    from server.app import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning", workers=1))
    runner = threading.Thread(target=server.run, daemon=True)
    runner.start()
    deadline = time.monotonic() + 60
    while not server.started:
        if not runner.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("the API server did not start")
        time.sleep(0.1)
    base = f"http://127.0.0.1:{PORT}"
    users = [("lead.b@opslens.demo", "/api/v2/summary"), ("b03@opslens.demo", "/api/v2/tickets?view=unassigned&team=B"),
             ("admin@opslens.demo", "/api/v2/tickets?view=open&limit=100"), ("b05@opslens.demo", "/api/v2/tickets?view=mine")]
    clients = []
    for n in range(HTTP_USERS):
        email, path = users[n % len(users)]
        c = httpx.Client(base_url=base, timeout=30)
        assert c.post("/api/v2/login", json={"email": email, "password": demo_password()}).status_code == 200
        clients.append((c, path))
    latencies: list[float] = []
    errors = [0]
    stop = time.monotonic() + HTTP_SECONDS
    lock = threading.Lock()

    def user(c, path):
        while time.monotonic() < stop:
            t = time.perf_counter()
            ok = c.get(path).status_code == 200
            with lock:
                latencies.append((time.perf_counter() - t) * 1000)
                errors[0] += 0 if ok else 1

    with ThreadPoolExecutor(HTTP_USERS) as pool:
        list(pool.map(lambda cp: user(*cp), clients))
    server.should_exit = True
    latencies.sort()
    return {"users": HTTP_USERS, "seconds": HTTP_SECONDS, "requests": len(latencies), "errors": errors[0],
            "requests_per_second": round(len(latencies) / HTTP_SECONDS, 1),
            "p50_ms": round(latencies[len(latencies) // 2], 1), "p95_ms": round(latencies[int(0.95 * len(latencies))], 1),
            "p99_ms": round(latencies[int(0.99 * len(latencies))], 1)}


def main() -> int:
    make_database()
    from opslens import seed, store

    store.migrate()
    store.ensure_partitions((date.today() - timedelta(days=DAYS + 1)).replace(day=1), months=3)
    with store.connection() as conn:
        seed.seed(conn)
    with store.pool().connection() as conn:
        agents = [r["agent_code"] for r in conn.execute("select agent_code from agent_profiles order by 1")]
        loaded = load(conn, agents)
        print(json.dumps(loaded, indent=1), flush=True)
        queries = query_times(conn)
        size = conn.execute("select pg_size_pretty(pg_database_size(current_database())) as s").fetchone()["s"]
    print(json.dumps(queries, indent=1), flush=True)
    http = http_test()
    print(json.dumps(http, indent=1), flush=True)
    out = {"at": datetime.now().astimezone().isoformat(), "database_size": size, "loaded": loaded, "queries": queries,
           "http": http, "machine": "laptop: i5-10500H, 16 GB RAM, Postgres 16 on Windows, default settings"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
