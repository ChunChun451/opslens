from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime
from typing import Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from server.auth import require

ANY_ROLE = require("admin", "lead", "agent")
MANAGERS = require("admin", "lead")

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
    "mine": "status <> 'solved'",
    "my_solved": "status = 'solved'",
}
MINE = ("mine", "my_solved")
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


def scope(user: dict) -> tuple[str, list]:
    if user["role"] == "agent":
        return "(assignee = %s or (status = 'open' and team = %s))", [user["agent_code"], user["team"]]
    if user["role"] == "lead":
        return "team = %s", [user["team"]]
    return "true", []


def can_see(user: dict, ticket: dict) -> bool:
    if user["role"] == "admin":
        return True
    if user["role"] == "lead":
        return ticket["team"] == user["team"]
    return ticket["assignee"] == user["agent_code"] or (ticket["status"] == "open" and ticket["team"] == user["team"])


@router.get("/tickets")
def tickets(view: str = "open", team: str = "", assignee: str = "", limit: int = 100,
            user: dict = Depends(ANY_ROLE)) -> JSONResponse:
    if view not in VIEWS:
        return JSONResponse({"error": f"view is one of {', '.join(VIEWS)}"}, status_code=400)
    allowed, params = scope(user)
    where = [VIEWS[view], "created_at::date = current_date", allowed]
    if view in MINE:
        if user["role"] != "agent":
            return JSONResponse({"error": "only agents have their own queue"}, status_code=400)
        where.append("assignee = %s")
        params.append(user["agent_code"])
    if team:
        where.append("team = %s")
        params.append(team.upper())
    if assignee:
        where.append("assignee = %s")
        params.append(assignee.upper())
    order = "solved_at desc" if view in ("solved", "my_solved") else "sla_due_at asc"
    found = rows(f"select id, priority, category, language, channel, status, assignee, team, created_at, sla_due_at, "
                 f"assigned_at, solved_at, breached, risk, left(body, 120) as subject from tickets where {' and '.join(where)} "
                 f"order by {order} limit %s", (*params, max(1, min(limit, 500))))
    return JSONResponse({"view": view, "count": len(found), "tickets": jsonable(found)})


@router.get("/tickets/{ticket_id}")
def ticket(ticket_id: str, user: dict = Depends(ANY_ROLE)) -> JSONResponse:
    found = rows("select * from tickets where id = %s", (ticket_id,))
    if not found or not can_see(user, found[0]):
        return JSONResponse({"error": "no such ticket"}, status_code=404)
    events = rows("select at, kind, actor, detail from ticket_events where ticket_id = %s order by at", (ticket_id,))
    decided = rows("select at, agent_code, reason, rescue_value from decisions where ticket_id = %s order by at", (ticket_id,))
    risk = rows("select at, risk from risk_scores where ticket_id = %s order by at", (ticket_id,))
    return JSONResponse(jsonable({"ticket": found[0], "events": events, "decisions": decided, "risk": risk}))


@router.get("/summary")
def summary(user: dict = Depends(MANAGERS)) -> JSONResponse:
    from opslens import bus

    team = None if user["role"] == "admin" else user["team"]
    key = f"v2_summary:{team or 'all'}"
    cached = bus.cache_get(key)
    if cached:
        return JSONResponse(cached)
    only = "and team = %s" if team else ""
    params = (team,) if team else ()
    today = rows("select count(*) as arrived, count(*) filter (where status = 'open') as unassigned, "
                 "count(*) filter (where status = 'in_progress') as in_progress, count(*) filter (where status = 'solved') as solved, "
                 "count(*) filter (where breached) as breached, "
                 f"count(*) filter (where status <> 'solved' and risk >= {AT_RISK}) as at_risk "
                 f"from tickets where created_at::date = current_date {only}", params)[0]
    teams = rows("select t.code as team, t.name, count(k.*) filter (where k.status <> 'solved') as open, "
                 f"count(k.*) filter (where k.status <> 'solved' and k.risk >= {AT_RISK}) as at_risk, "
                 "count(k.*) filter (where k.breached) as breached, count(k.*) as arrived "
                 "from teams t left join tickets k on k.team = t.code and k.created_at::date = current_date "
                 f"where {'t.code = %s' if team else 'true'} group by t.code, t.name order by t.code", params)
    hourly = rows("select team, hour, created, breached from team_hourly where hour::date = current_date "
                  f"{only} order by hour, team", params)
    arrived = today["arrived"] or 0
    out = jsonable({"today": {**today, "breached_pct": round(100 * today["breached"] / arrived, 2) if arrived else None},
                    "teams": teams, "hourly": hourly, "at": datetime.now().astimezone()})
    bus.cache_set(key, out, SUMMARY_TTL_S)
    return JSONResponse(out)


AGENT_ONLY = require("agent")
AGENT_ACTIONS = ("take", "decline", "done", "extra_time", "break", "back")


def floor_state():
    from opslens.live import state_at
    from server.app import _current_live

    now = datetime.now()
    live = _current_live(now.weekday())
    minute = now.hour * 60 + now.minute + now.second / 60
    return (None, minute) if live is None else (state_at(live, minute), minute)


@router.get("/floor/me")
def floor_me(user: dict = Depends(AGENT_ONLY)) -> JSONResponse:
    state, minute = floor_state()
    if state is None:
        return JSONResponse({"error": "Today's floor is still starting. Try again in a few seconds."}, status_code=409)
    me = next((r for r in state.get("floor", []) if r["id"] == user["agent_code"]), None)
    profile = rows("select name, team, skills, languages, shift_start_hour, shift_hours from agent_profiles where agent_code = %s",
                   (user["agent_code"],))
    return JSONResponse(jsonable({"minute": round(minute, 1), "me": me, "profile": profile[0] if profile else None}))


@router.get("/floor")
def floor(user: dict = Depends(MANAGERS)) -> JSONResponse:
    state, minute = floor_state()
    if state is None:
        return JSONResponse({"error": "Today's floor is still starting. Try again in a few seconds."}, status_code=409)
    profiles = {p["agent_code"]: p for p in rows("select agent_code, name, team from agent_profiles")}
    people = [{**r, "team": profiles.get(r["id"], {}).get("team"), "name": profiles.get(r["id"], {}).get("name")}
              for r in state.get("floor", []) if user["role"] == "admin" or profiles.get(r["id"], {}).get("team") == user["team"]]
    by_team: dict[str, dict] = {}
    for p in people:
        t = by_team.setdefault(p["team"], {"team": p["team"], "working": 0, "free": 0, "break": 0, "off": 0})
        word = "working" if p["status"] in ("busy", "cross", "wrong") else "free" if p["status"] == "idle" else p["status"]
        t[word if word in t else "off"] += 1
    policies = state["policies"]
    compare = {k: {"missed": v["missed"], "waiting": v["waiting"], "arrived": v["arrived"]} for k, v in policies.items()}
    return JSONResponse(jsonable({"minute": round(minute, 1), "teams": sorted(by_team.values(), key=lambda t: t["team"]),
                                  "people": people, "compare": compare, "danger": state["danger"][:8]}))


@router.post("/actions")
def act(request: dict, user: dict = Depends(AGENT_ONLY)) -> JSONResponse:
    from server.app import live_action

    kind = request.get("kind")
    if kind not in AGENT_ACTIONS:
        return JSONResponse({"error": f"kind is one of {', '.join(AGENT_ACTIONS)}"}, status_code=400)
    now = datetime.now()
    payload = {"weekday": now.weekday(), "seed": 1, "minute": now.hour * 60 + now.minute + now.second / 60,
               "kind": kind, "agent": user["agent_code"]}
    for key in ("ticket_id", "value", "reason"):
        if request.get(key) is not None:
            payload[key] = request[key]
    return live_action(payload)


def floor_rows() -> list[dict]:
    state, _ = floor_state()
    return state.get("floor", []) if state else []


def start_agents() -> None:
    from opslens import agents, store

    if os.environ.get("OPSLENS_AGENTS", "1") == "0" or not store.available():
        return
    store.migrate()
    threading.Thread(target=agents.work_forever, args=(floor_rows,), daemon=True, name="opslens-agents").start()


def team_of(user: dict) -> str | None:
    return None if user["role"] == "admin" else user["team"]


@router.post("/copilot")
def copilot(request: dict, user: dict = Depends(ANY_ROLE)) -> JSONResponse:
    from opslens import agents

    found = rows("select id, team, status, assignee from tickets where id = %s", (str(request.get("ticket_id", "")),))
    if not found or not can_see(user, found[0]):
        return JSONResponse({"error": "no such ticket"}, status_code=404)
    return JSONResponse({"run_id": agents.submit("copilot", "asked by " + user["email"], user["id"], ticket_id=found[0]["id"])})


@router.post("/ask")
def ask(request: dict, user: dict = Depends(MANAGERS)) -> JSONResponse:
    from opslens import agents

    question = str(request.get("question", "")).strip()[:300]
    if not question:
        return JSONResponse({"error": "ask a question"}, status_code=400)
    return JSONResponse({"run_id": agents.submit("ask", "asked by " + user["email"], user["id"],
                                                 question=question, team=team_of(user))})


@router.post("/analyst")
def analyst(user: dict = Depends(MANAGERS)) -> JSONResponse:
    from opslens import agents

    return JSONResponse({"run_id": agents.submit("analyst", "asked by " + user["email"], user["id"], team=team_of(user))})


def run_visible(user: dict, run: dict) -> bool:
    if user["role"] == "admin" or run["requested_by"] == user["id"]:
        return True
    if user["role"] != "lead":
        return False
    if run["ticket_id"]:
        found = rows("select team from tickets where id = %s", (run["ticket_id"],))
        return bool(found) and found[0]["team"] == user["team"]
    return True


@router.get("/runs")
def runs(limit: int = 30, agent: str = "", user: dict = Depends(MANAGERS)) -> JSONResponse:
    where, params = ["true"], []
    if agent:
        where.append("r.agent = %s")
        params.append(agent)
    if user["role"] == "lead":
        where.append("(r.ticket_id is null or t.team = %s or r.requested_by = %s)")
        params += [user["team"], user["id"]]
    found = rows("select r.id, r.agent, r.trigger, r.ticket_id, r.status, r.summary, r.started_at, r.finished_at, "
                 "(select count(*) from agent_steps s where s.run_id = r.id and s.kind = 'tool_call') as tools_used "
                 "from agent_runs r left join tickets t on t.id = r.ticket_id "
                 f"where {' and '.join(where)} order by r.id desc limit %s", (*params, max(1, min(limit, 200))))
    counts = rows("select agent, count(*) as runs, count(*) filter (where status = 'failed') as failed, "
                  "round(avg(extract(epoch from finished_at - started_at))::numeric, 1) as avg_seconds "
                  "from agent_runs where started_at > now() - interval '24 hours' group by agent order by agent")
    return JSONResponse(jsonable({"runs": found, "last_day": counts}))


@router.get("/runs/{run_id}")
def run(run_id: int, user: dict = Depends(ANY_ROLE)) -> JSONResponse:
    found = rows("select * from agent_runs where id = %s", (run_id,))
    if not found or not run_visible(user, found[0]):
        return JSONResponse({"error": "no such run"}, status_code=404)
    steps = rows("select n, kind, tool, payload, at from agent_steps where run_id = %s order by n", (run_id,))
    return JSONResponse(jsonable({"run": found[0], "steps": steps}))


@router.get("/proposals")
def proposals(status: str = "waiting", user: dict = Depends(MANAGERS)) -> JSONResponse:
    team = team_of(user)
    found = rows("select p.*, u.name as decided_by_name from proposals p left join users u on u.id = p.decided_by "
                 f"where p.status = %s {'and (p.team = %s or p.team is null)' if team else ''} "
                 "order by p.id desc limit 50", (status, team) if team else (status,))
    return JSONResponse(jsonable({"proposals": found}))


@router.post("/proposals/{proposal_id}")
def decide(proposal_id: int, request: dict, user: dict = Depends(MANAGERS)) -> JSONResponse:
    from opslens import agents, store
    from server.app import live_action

    decision = request.get("decision")
    if decision not in ("approve", "reject"):
        return JSONResponse({"error": "decision is approve or reject"}, status_code=400)
    found = rows("select * from proposals where id = %s", (proposal_id,))
    if not found or (team_of(user) and found[0]["team"] not in (None, user["team"])):
        return JSONResponse({"error": "no such proposal"}, status_code=404)
    p = found[0]
    if p["status"] != "waiting":
        return JSONResponse({"error": f"this proposal is already {p['status']}"}, status_code=409)
    status, result = ("rejected", None) if decision == "reject" else ("approved", None)
    if decision == "approve" and p["kind"] == "reassign":
        problem = agents.check_reassign(p["ticket_id"], p["agent_code"], floor_rows)
        if problem:
            status, result = "expired", {"error": f"Things moved on: {problem}."}
        else:
            now = datetime.now()
            out = live_action({"weekday": now.weekday(), "seed": 1, "minute": now.hour * 60 + now.minute + now.second / 60,
                               "kind": "take", "agent": p["agent_code"], "ticket_id": p["ticket_id"],
                               "reason": f"approved by {user['name']}"})
            body = json.loads(out.body)
            status, result = ("approved", body) if out.status_code == 200 else ("failed", body)
    with store.connection() as conn:
        conn.execute("update proposals set status = %s, result = %s, decided_by = %s, decided_at = now() where id = %s",
                     (status, json.dumps(result, default=str), user["id"], proposal_id))
    return JSONResponse(jsonable({"status": status, "result": result}))


@router.get("/stream")
def stream(user: dict = Depends(ANY_ROLE)) -> StreamingResponse:
    from opslens import bus

    def events():
        yield "retry: 3000\n\n"
        for message in bus.subscribe("floor", heartbeat_s=15):
            yield f"event: floor\ndata: {json.dumps(message)}\n\n" if message else ": keep-alive\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})
