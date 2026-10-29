from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime
from typing import Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

log = logging.getLogger("opslens.v2")
router = APIRouter(prefix="/api/v2")
MIRROR_EVERY_S = 5.0
SUMMARY_TTL_S = 3.0
AT_RISK = 0.5
VIEWS = {
    "open": "status <> 'solved'",
    "unassigned": "status = 'open'",
    "due_soon": "status <> 'solved' and sla_due_at <= now() + interval '15 minutes'",
    "at_risk": f"status <> 'solved' and risk >= {AT_RISK}",
    "solved": "status = 'solved'",
}
_state = {"running": False, "last": None, "error": None}


def mirror_forever(current_live: Callable[[int], object]) -> None:
    from opslens import bus, mirror, store

    if os.environ.get("OPSLENS_MIRROR", "1") == "0" or _state["running"] or not store.available():
        return
    _state["running"] = True
    store.migrate()
    store.ensure_partitions(date.today().replace(day=1), months=3)
    state = mirror.MirrorState()
    last_view = 0.0
    while True:
        try:
            now = datetime.now()
            live = current_live(now.weekday())
            if live is not None:
                with store.connection() as conn:
                    summary = mirror.sync(conn, live, now.hour * 60 + now.minute + now.second / 60, now.date(), state)
                    if time.monotonic() - last_view > 60:
                        conn.execute("refresh materialized view concurrently team_hourly")
                        last_view = time.monotonic()
                _state["last"], _state["error"] = summary, None
                if summary["changed"] or summary["events"]:
                    bus.publish("floor", summary)
        except Exception as exc:
            _state["error"] = f"{exc.__class__.__name__}: {exc}"
            log.exception("mirror sync failed")
        time.sleep(MIRROR_EVERY_S)


def start_mirror(current_live: Callable[[int], object]) -> None:
    threading.Thread(target=mirror_forever, args=(current_live,), daemon=True, name="opslens-mirror").start()


def rows(sql: str, params: tuple = ()) -> list[dict]:
    from opslens import store

    with store.connection() as conn:
        return conn.execute(sql, params).fetchall()


def jsonable(value):
    return json.loads(json.dumps(value, default=str))


@router.get("/health")
def health() -> JSONResponse:
    from opslens import bus, store

    ok = store.available()
    return JSONResponse({"database": "up" if ok else "down", "bus": bus.backend() if ok else "none",
                         "mirror": {"running": _state["running"], "last": _state["last"], "error": _state["error"]}})


@router.get("/tickets")
def tickets(view: str = "open", team: str = "", assignee: str = "", limit: int = 100) -> JSONResponse:
    if view not in VIEWS:
        return JSONResponse({"error": f"view is one of {', '.join(VIEWS)}"}, status_code=400)
    where, params = [VIEWS[view], "created_at::date = current_date"], []
    if team:
        where.append("team = %s")
        params.append(team.upper())
    if assignee:
        where.append("assignee = %s")
        params.append(assignee.upper())
    order = "solved_at desc" if view == "solved" else "sla_due_at asc"
    found = rows(f"select id, priority, category, language, channel, status, assignee, team, created_at, sla_due_at, "
                 f"assigned_at, solved_at, breached, risk, left(body, 120) as subject from tickets where {' and '.join(where)} "
                 f"order by {order} limit %s", (*params, max(1, min(limit, 500))))
    return JSONResponse({"view": view, "count": len(found), "tickets": jsonable(found)})


@router.get("/tickets/{ticket_id}")
def ticket(ticket_id: str) -> JSONResponse:
    found = rows("select * from tickets where id = %s", (ticket_id,))
    if not found:
        return JSONResponse({"error": "no such ticket"}, status_code=404)
    events = rows("select at, kind, actor, detail from ticket_events where ticket_id = %s order by at", (ticket_id,))
    decided = rows("select at, agent_code, reason, rescue_value from decisions where ticket_id = %s order by at", (ticket_id,))
    risk = rows("select at, risk from risk_scores where ticket_id = %s order by at", (ticket_id,))
    return JSONResponse(jsonable({"ticket": found[0], "events": events, "decisions": decided, "risk": risk}))


@router.get("/summary")
def summary() -> JSONResponse:
    from opslens import bus

    cached = bus.cache_get("v2_summary")
    if cached:
        return JSONResponse(cached)
    today = rows("select count(*) as arrived, count(*) filter (where status = 'open') as unassigned, "
                 "count(*) filter (where status = 'in_progress') as in_progress, count(*) filter (where status = 'solved') as solved, "
                 "count(*) filter (where breached) as breached, "
                 f"count(*) filter (where status <> 'solved' and risk >= {AT_RISK}) as at_risk "
                 "from tickets where created_at::date = current_date")[0]
    teams = rows("select t.code as team, t.name, count(k.*) filter (where k.status <> 'solved') as open, "
                 f"count(k.*) filter (where k.status <> 'solved' and k.risk >= {AT_RISK}) as at_risk, "
                 "count(k.*) filter (where k.breached) as breached, count(k.*) as arrived "
                 "from teams t left join tickets k on k.team = t.code and k.created_at::date = current_date "
                 "group by t.code, t.name order by t.code")
    hourly = rows("select team, hour, created, breached from team_hourly where hour::date = current_date order by hour, team")
    arrived = today["arrived"] or 0
    out = jsonable({"today": {**today, "breached_pct": round(100 * today["breached"] / arrived, 2) if arrived else None},
                    "teams": teams, "hourly": hourly, "at": datetime.now().astimezone()})
    bus.cache_set("v2_summary", out, SUMMARY_TTL_S)
    return JSONResponse(out)


@router.get("/stream")
def stream() -> StreamingResponse:
    from opslens import bus

    def events():
        yield "retry: 3000\n\n"
        for message in bus.subscribe("floor", heartbeat_s=15):
            yield f"event: floor\ndata: {json.dumps(message)}\n\n" if message else ": keep-alive\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})
