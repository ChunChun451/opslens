from __future__ import annotations

import bisect
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from opslens.classify import TEAM_OF
from opslens.live import LiveDay, _risk_in, danger_tickets, floor_now
from opslens.privacy import mask_pii

DAY_MIN = 1440.0


@dataclass
class MirrorState:
    day_key: tuple = ()
    seen: dict[str, tuple] = field(default_factory=dict)
    events: set[tuple] = field(default_factory=set)
    decisions: set[tuple] = field(default_factory=set)
    risk_minutes: set[float] = field(default_factory=set)


def stamp(today: date, live: LiveDay, minute: float) -> datetime:
    base = datetime.combine(today, time()).astimezone()
    return base + timedelta(minutes=float(minute) - live.start)


def latest_jobs(live: LiveDay, now: float) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for agent, jobs in live.work.items():
        for job in jobs:
            if job["minute"] > now:
                continue
            seen = out.get(job["ticket_id"])
            if seen is None or job["minute"] >= seen["minute"]:
                out[job["ticket_id"]] = {**job, "agent": agent}
    return out


def risk_now(live: LiveDay, now: float) -> tuple[float | None, dict]:
    best = None
    for minute, scores in live.risk_seen:
        if minute <= now and (best is None or minute >= best[0]):
            best = (minute, scores)
    return best if best else (None, {})


def working_now(live: LiveDay, now: float) -> dict[str, str] | None:
    frames = getattr(live, "floors", {}).get("opslens")
    if not frames:
        return None
    k = max(0, bisect.bisect_right([f["minute"] for f in frames], now) - 1)
    return {r["current"]["ticket_id"]: r["id"] for r in floor_now(live, now, frames[k]["status"]) if r["current"]}


def reasons_now(live: LiveDay, now: float) -> dict[str, list[str]]:
    past = [d for d in getattr(live, "danger", []) if d["minute"] <= now]
    if not past:
        return {}
    return {t["ticket_id"]: t["reasons"] for t in danger_tickets(live, past[-1]) if t.get("reasons")}


def ticket_rows(live: LiveDay, now: float, today: date) -> tuple[list[dict], dict[str, dict]]:
    world = live.context["world"]
    info = live.context["tickets_info"]
    teams = {a["id"]: a.get("team") for a in live.agents}
    jobs = latest_jobs(live, now)
    _, scores = risk_now(live, now)
    why = reasons_now(live, now)
    working = working_now(live, now)
    rows = []
    for i, tid in enumerate(world.ticket_ids):
        created = float(world.created_min[i])
        if created < live.start or created >= live.start + DAY_MIN or created > now:
            continue
        deadline = created + float(world.sla_min[i])
        job = jobs.get(tid)
        resolved = job["resolved"] if job else None
        solved = resolved is not None and resolved <= now
        held = job if solved or working is None or (job and working.get(tid) == job["agent"]) else None
        status = "solved" if solved else "in_progress" if held else "open"
        breached = (resolved > deadline) if solved else (True if now > deadline else None)
        category = str(job["category"]) if job else str(world.selected_category[i])
        row = info.loc[tid] if tid in info.index else None
        risk = None if solved else scores.get(i)
        rows.append({
            "id": tid, "day": live.day, "created_at": stamp(today, live, created), "channel": world.channel[i],
            "priority": world.priority[i], "language": world.language[i], "category": category,
            "customer_tier": world.tier[i], "order_value_inr": float(world.order_value[i]),
            "restaurant": None if row is None else str(row.get("restaurant_name", "")),
            "body": mask_pii(str(row["text"]) if row is not None else "").text,
            "status": status, "assignee": held["agent"] if held else None,
            "team": teams.get(held["agent"]) if held else TEAM_OF.get(category),
            "sla_due_at": stamp(today, live, deadline),
            "assigned_at": stamp(today, live, held["minute"]) if held else None,
            "solved_at": stamp(today, live, resolved) if solved else None,
            "breached": breached, "risk": None if risk is None or math.isnan(risk) else round(float(risk), 3),
            "assign_reason": job["reason"] if job else None,
            "risk_reasons": None if solved or tid not in why else json.dumps(why[tid]),
            "_created": created, "_deadline": deadline, "_job": job, "_resolved": resolved if solved else None,
        })
    return rows, jobs


UPSERT = """
insert into tickets (id, day, created_at, channel, priority, language, category, customer_tier, order_value_inr,
  restaurant, body, status, assignee, team, sla_due_at, assigned_at, solved_at, breached, risk, risk_reasons, assign_reason, updated_at)
values (%(id)s, %(day)s, %(created_at)s, %(channel)s, %(priority)s, %(language)s, %(category)s, %(customer_tier)s,
  %(order_value_inr)s, %(restaurant)s, %(body)s, %(status)s, %(assignee)s, %(team)s, %(sla_due_at)s, %(assigned_at)s,
  %(solved_at)s, %(breached)s, %(risk)s, %(risk_reasons)s, %(assign_reason)s, now())
on conflict (id) do update set status = excluded.status, assignee = excluded.assignee, team = excluded.team,
  category = excluded.category, assigned_at = excluded.assigned_at, solved_at = excluded.solved_at,
  breached = excluded.breached, risk = excluded.risk, risk_reasons = excluded.risk_reasons, assign_reason = excluded.assign_reason, updated_at = now()
"""


def sync(conn, live: LiveDay, minute_of_day: float, today: date, state: MirrorState) -> dict:
    key = (today, live.day, live.seed)
    if state.day_key != key:
        state.day_key = key
        state.seen.clear()
        state.events.clear()
        state.decisions.clear()
        state.risk_minutes.clear()
    now = live.start + minute_of_day
    rows, _ = ticket_rows(live, now, today)
    changed = []
    events = []
    decisions = []
    for r in rows:
        print_ = (r["status"], r["assignee"], r["breached"], r["risk"], r["risk_reasons"])
        if state.seen.get(r["id"]) != print_:
            changed.append(r)
            state.seen[r["id"]] = print_
        wanted = [("created", r["_created"], None)]
        if r["_job"]:
            wanted.append(("assigned", r["_job"]["minute"], r["_job"]["agent"]))
            dkey = (r["id"], r["_job"]["agent"], r["_job"]["minute"])
            if dkey not in state.decisions:
                state.decisions.add(dkey)
                decisions.append({"at": stamp(today, live, r["_job"]["minute"]), "ticket_id": r["id"],
                                  "agent_code": r["_job"]["agent"], "reason": r["_job"]["reason"],
                                  "rescue_value": _risk_in(r["_job"]["reason"])})
        if r["_resolved"] is not None:
            wanted.append(("solved", r["_resolved"], r["assignee"]))
        if r["breached"]:
            wanted.append(("breached", r["_deadline"], None))
        for kind, minute, actor in wanted:
            ekey = (r["id"], kind, round(minute, 3))
            if ekey not in state.events:
                state.events.add(ekey)
                events.append({"ticket_id": r["id"], "at": stamp(today, live, minute), "kind": kind, "actor": actor,
                               "detail": json.dumps({"priority": r["priority"], "team": r["team"]})})
    risk_rows = []
    minute, scores = risk_now(live, now)
    if minute is not None and minute not in state.risk_minutes:
        state.risk_minutes.add(minute)
        world = live.context["world"]
        open_ids = {r["id"] for r in rows if r["status"] != "solved"}
        for idx, risk in scores.items():
            tid = world.ticket_ids[idx]
            if tid in open_ids and risk is not None and not math.isnan(risk):
                risk_rows.append({"ticket_id": tid, "at": stamp(today, live, minute), "risk": round(float(risk), 3)})
    with conn.transaction():
        with conn.cursor() as cur:
            if changed:
                cur.executemany(UPSERT, [{k: v for k, v in r.items() if not k.startswith("_")} for r in changed])
            if events:
                cur.executemany("insert into ticket_events (ticket_id, at, kind, actor, detail) values "
                                "(%(ticket_id)s, %(at)s, %(kind)s, %(actor)s, %(detail)s) on conflict do nothing", events)
            if decisions:
                cur.executemany("insert into decisions (at, ticket_id, agent_code, reason, rescue_value) values "
                                "(%(at)s, %(ticket_id)s, %(agent_code)s, %(reason)s, %(rescue_value)s) on conflict do nothing",
                                decisions)
            if risk_rows:
                cur.executemany("insert into risk_scores (ticket_id, at, risk) values (%(ticket_id)s, %(at)s, %(risk)s) "
                                "on conflict do nothing", risk_rows)
    open_now = sum(1 for r in rows if r["status"] == "open")
    return {"minute": round(minute_of_day, 1), "arrived": len(rows), "open": open_now,
            "in_progress": sum(1 for r in rows if r["status"] == "in_progress"),
            "solved": sum(1 for r in rows if r["status"] == "solved"),
            "breached": sum(1 for r in rows if r["breached"]), "changed": len(changed), "events": len(events),
            "decisions": len(decisions), "risk_rows": len(risk_rows)}
