from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from opslens import policies
from opslens.privacy import mask_pii
from opslens.risk import risk_if_assigned_now, top_reasons
from opslens.simulate import MINUTES_PER_DAY, Overrides, simulate
from opslens.whatif import change_agents, change_volume, make_policy
from opslens.world import build_world, day_bounds

POLICIES = ("baseline_d", "opslens")
RISK_EVERY_MIN = 1
RISK_SHOWN = 5
STATUS_LETTER = {"off": "o", "idle": "i", "busy": "b", "cross": "x", "wrong": "w", "break": "k"}
CHECKPOINT_EVERY_MIN = 10
LIVE_FLOOR_EVERY_MIN = 1
LIVE_PREDICT_THREADS = 4
SPEED_PRIOR_JOBS = 2.0
SPEED_RANGE = (0.5, 2.0)
DANGER_COLUMNS = ("ticket_id", "time_left_min", "capable_on_shift", "priority", "language", "category_pred",
                  "sla_min", "team")
SIM_ACTIONS = ("decline", "done", "extra_time", "break", "back")
STATUS_WORD = {letter: word for word, letter in STATUS_LETTER.items()}


def matching_test_day(weekday: int, first_weekday: int, test_days: tuple[int, int]) -> int:
    for day in range(test_days[0], test_days[1] + 1):
        if (first_weekday + day - 1) % 7 == weekday:
            return day
    return test_days[0]


@dataclass
class LiveDay:
    day: int
    seed: int
    start: float
    agents: list[dict]
    floors: dict[str, list[dict]] = field(default_factory=dict)
    tickets: dict[str, pd.DataFrame] = field(default_factory=dict)
    danger: list[dict] = field(default_factory=list)
    risk_seen: list[tuple[float, dict]] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    work: dict[str, list[dict]] = field(default_factory=dict)
    actions: tuple = ()
    effects: list[dict] = field(default_factory=list)
    checkpoints: list = field(default_factory=list)
    context: dict = field(default_factory=dict)
    complete: bool = True
    parent: "LiveDay | None" = None
    live_risk: bool = False


def simulate_live_day(inputs: dict, day: int, seed: int = 1, agents_delta: dict[str, int] | None = None,
                      volume_factor: float = 1.0, actions: tuple = (), live_risk: bool | None = None) -> LiveDay:
    if live_risk is None:
        live_risk = bool((inputs["weights"].get("live_risk") or {}).get("enabled"))
    warm, _ = day_bounds(day - 1, day - 1)
    start, end = day_bounds(day, day)
    tickets, preds = inputs["tickets"], inputs["preds"]
    if abs(volume_factor - 1.0) > 1e-9:
        tickets, preds = change_volume(tickets, preds, day, volume_factor)
    agents = change_agents(inputs["agents"], agents_delta) if agents_delta else inputs["agents"]
    inputs = {**inputs, "tickets": tickets, "preds": preds, "agents": agents}
    tickets_info = tickets.set_index("ticket_id")
    created = inputs["tickets"]["created_min"]
    near = inputs["tickets"][(created >= warm - 60) & (created < end)]
    live = None
    for key in POLICIES:
        world = build_world(near, seed=seed, agents=inputs["agents"])
        if live is None:
            live = LiveDay(day=day, seed=seed, start=start, agents=[_agent_card(a, day) for a in world.agents],
                           actions=tuple(actions), live_risk=live_risk)
        policy = make_policy(key, world, inputs["preds"], inputs["model"], inputs["weights"],
                             live_risk=live_risk, handle_dist=inputs.get("handle_dist"))
        if key == "opslens":
            live.context = {"inputs": inputs, "tickets_info": tickets_info, "world": world, "warm": warm, "end": end,
                            "index": {tid: i for i, tid in enumerate(world.ticket_ids)},
                            "policy_dist": inputs.get("handle_dist") or {}, "job_info": {}}
            policy.log_window = (start, end)
            _run_opslens(live, policy, overrides_from(live, actions), None)
            continue
        result = simulate(world, policy, warm, end, metric_start_min=start, seed_label=str(seed),
                          floor_window=(start, end), floor_every_min=LIVE_FLOOR_EVERY_MIN)
        _keep_floor(live, key, result)
    return live


def _keep_floor(live: LiveDay, key: str, result) -> None:
    live.floors[key] = [{"minute": f["minute"],
                         "status": "".join(STATUS_LETTER[f["agents"][a["id"]]] for a in live.agents),
                         "queues": f["queues"]} for f in result.floor]
    t = result.tickets
    live.tickets[key] = pd.DataFrame({
        "created": t["created_min"].to_numpy(),
        "pickup": t["first_pickup_min"].to_numpy(),
        "resolved": t["resolved_min"].to_numpy(),
        "deadline": (t["created_min"] + t["sla_min"]).to_numpy(),
        "ticket_id": t["ticket_id"].to_numpy(),
    })


def _run_opslens(live: LiveDay, policy, overrides: Overrides | None, resume, pause: float | None = None,
                 pause_when: Callable[[], bool] | None = None) -> bool:
    ctx = live.context
    world, inputs, start, end = ctx["world"], ctx["inputs"], live.start, ctx["end"]
    first = resume.minute if resume is not None else start
    policy.notes = policies.LiveNotes(speed_notes(live, live.actions), extra_notes(live, live.actions))
    policy.predict_threads = LIVE_PREDICT_THREADS
    marks = tuple(float(m) for m in np.arange(start, end, CHECKPOINT_EVERY_MIN) if m >= first)
    if pause is not None:
        marks = tuple(m for m in marks if m < pause) + (pause,)
    share = (inputs["model"], policy.pred, policy.team_code, policy.w, policy._schedule, policy.handle_dist,
             policy.codes, policy.rare, policy.agent_pos, policy.team_names)
    result = simulate(world, policy, ctx["warm"], end, metric_start_min=start, seed_label=str(live.seed),
                      floor_window=(start, end), overrides=overrides, checkpoint_at=marks,
                      checkpoint_share=share, resume=resume, drain_min=0.0, pause_at=pause, pause_when=pause_when,
                      floor_every_min=LIVE_FLOOR_EVERY_MIN, watch=_danger_watch(live, policy, inputs["model"]))
    _keep_floor(live, "opslens", result)
    log = [d for d in policy.decision_log
           if overrides is None or not overrides.blocks(d["agent_id"], d["ticket_idx"], d["minute"])]
    live.decisions = [{"minute": d["minute"], "ticket_id": world.ticket_ids[d["ticket_idx"]],
                       "agent": d["agent_id"], "reason": d["reason"]} for d in log]
    live.work = _work_by_agent(log, world, result.tickets, ctx["tickets_info"], ctx.setdefault("job_info", {}))
    live.checkpoints = live.checkpoints + result.checkpoints
    return result.paused


def overrides_from(live: LiveDay, actions) -> Overrides | None:
    moves = [a for a in actions if a["kind"] in SIM_ACTIONS]
    if not moves:
        return None
    index, start = live.context["index"], live.start
    out = Overrides()
    for a in moves:
        at = start + float(a["minute"])
        i = index.get(a.get("ticket_id") or "")
        if a["kind"] == "decline" and i is not None:
            out.forbidden.setdefault((a["agent"], i), at)
        elif a["kind"] == "done" and i is not None:
            target = a["minute"] if a.get("value") is None else a["value"]
            out.finishes.append((at, a["agent"], i, "at", start + float(target)))
        elif a["kind"] == "extra_time" and i is not None:
            out.finishes.append((at, a["agent"], i, "extra", float(a["value"])))
        elif a["kind"] == "break":
            out.breaks.setdefault(a["agent"], []).append((at, math.inf))
        elif a["kind"] == "back" and out.breaks.get(a["agent"]):
            b0, _ = out.breaks[a["agent"]][-1]
            out.breaks[a["agent"]][-1] = (b0, max(b0, at))
    return out


def speed_notes(live: LiveDay, actions) -> list[tuple[float, str, float]]:
    model = live.context.get("policy_dist") or {}
    info = live.context.get("tickets_info")
    seen: dict[str, list[float]] = {}
    out = []
    for a in actions:
        if a["kind"] not in ("done", "extra_time") or a.get("started") is None or info is None:
            continue
        if a.get("ticket_id") not in info.index:
            continue
        mu, _ = model.get(str(info.loc[a["ticket_id"], "category"]), (math.log(6.0), 0.5))
        expected = math.exp(mu) * (1.6 if a.get("cross") else 1.0)
        if a["kind"] == "done":
            took = float(a["minute"] if a.get("value") is None else a["value"]) - float(a["started"])
        elif a.get("planned_end") is not None:
            took = float(a["planned_end"]) + float(a["value"]) - float(a["started"])
        else:
            continue
        mine = seen.setdefault(a["agent"], [])
        mine.append(max(0.0, took) / expected)
        factor = (SPEED_PRIOR_JOBS + sum(mine)) / (SPEED_PRIOR_JOBS + len(mine))
        out.append((live.start + float(a["minute"]), a["agent"], min(SPEED_RANGE[1], max(SPEED_RANGE[0], factor))))
    return out


def agent_speed(live: LiveDay, agent: str) -> float:
    notes = [f for _, who, f in speed_notes(live, live.actions) if who == agent]
    return notes[-1] if notes else 1.0


def extra_notes(live: LiveDay, actions) -> list[tuple[float, str, int, float]]:
    index = live.context.get("index", {})
    return [(live.start + float(a["minute"]), a["agent"], index[a["ticket_id"]], float(a["value"]))
            for a in actions if a["kind"] == "extra_time" and a.get("ticket_id") in index]


def with_actions(base: LiveDay, actions, ahead_min: float | None = None) -> LiveDay:
    actions = tuple(actions)
    if base.actions != actions[:len(base.actions)]:
        raise ValueError("the new action log must extend the old one")
    new = [a for a in actions[len(base.actions):] if a["kind"] in SIM_ACTIONS]
    live = _copy_day(base, actions, base)
    if new:
        first = min(base.start + float(a["minute"]) for a in new)
        usable = [c for c in base.checkpoints if c.minute <= first]
        if not usable:
            raise ValueError("no checkpoint before the action")
        cp = usable[-1]
        pause = first + ahead_min if ahead_min is not None and first + ahead_min < live.context["end"] else None
        live.danger = [d for d in base.danger if d["minute"] < cp.minute]
        live.risk_seen = [r for r in base.risk_seen if r[0] < cp.minute]
        live.checkpoints = [c for c in base.checkpoints if c.minute < cp.minute]
        _run_opslens(live, cp.restore_policy(), overrides_from(live, actions), cp, pause)
        live.complete = pause is None
    live.effects = _effects(live)
    return live


def finish_day(partial: LiveDay, should_pause: Callable[[], bool] | None = None) -> LiveDay:
    if partial.complete:
        return partial
    cp = partial.checkpoints[-1]
    live = _copy_day(partial, partial.actions, partial.parent)
    live.danger = [d for d in partial.danger if d["minute"] < cp.minute]
    live.risk_seen = [r for r in partial.risk_seen if r[0] < cp.minute]
    paused = _run_opslens(live, cp.restore_policy(), overrides_from(live, live.actions), cp, pause_when=should_pause)
    live.complete = not paused
    live.effects = _effects(live)
    return live


def simulated_until(live: LiveDay) -> float:
    if live.complete:
        return live.start + MINUTES_PER_DAY
    return live.checkpoints[-1].minute if live.checkpoints else live.start


def relink(live: LiveDay, parent: LiveDay) -> None:
    live.parent = parent
    live.effects = _effects(live)


def _copy_day(day: LiveDay, actions: tuple, parent: LiveDay | None) -> LiveDay:
    return LiveDay(day=day.day, seed=day.seed, start=day.start, agents=day.agents, floors=dict(day.floors),
                   tickets=dict(day.tickets), danger=list(day.danger), risk_seen=list(day.risk_seen),
                   decisions=day.decisions, work=day.work,
                   actions=actions, context=day.context, checkpoints=list(day.checkpoints), parent=parent,
                   complete=day.complete, live_risk=day.live_risk)


def _effects(live: LiveDay) -> list[dict]:
    parent = live.parent
    return list(parent.effects) + [measure_effect(parent, live, a) for a in live.actions[len(parent.actions):]]


def _first_job(live: LiveDay, ticket_id: str, after: float) -> dict | None:
    jobs = [{**j, "agent": agent} for agent, mine in live.work.items() for j in mine
            if j["ticket_id"] == ticket_id and j["minute"] >= after]
    return min(jobs, key=lambda j: j["minute"]) if jobs else None


def _job_of(live: LiveDay, agent: str, ticket_id: str, at: float) -> dict | None:
    mine = [j for j in live.work.get(agent, []) if j["ticket_id"] == ticket_id and j["minute"] <= at]
    return {**mine[-1], "agent": agent} if mine else None


def _risk_in(reason: str | None) -> float | None:
    found = re.search(r"breach risk ([\d.]+) -> ([\d.]+)", reason or "")
    if found:
        return float(found.group(1))
    return 1.0 if reason and "already past its SLA" in reason else None


def missed_today(live: LiveDay, key: str = "opslens") -> int | None:
    if not live.complete:
        return None
    t = live.tickets[key]
    due = t["deadline"] <= live.start + MINUTES_PER_DAY
    return int((due & ~(t["resolved"] <= t["deadline"])).sum())


def measure_effect(before: LiveDay, after: LiveDay, action: dict) -> dict:
    at = after.start + float(action["minute"])
    out = {**action, "missed_before": missed_today(before), "missed_after": missed_today(after),
           "complete": after.complete and before.complete}
    ticket = action.get("ticket_id")
    if action["kind"] in ("decline", "take") and ticket:
        out["planned"] = _job_view(_first_job(before, ticket, at), after.start, before)
        out["went_to"] = _job_view(_first_job(after, ticket, at), after.start, after)
        if out["went_to"] is None:
            out["went_to"] = _ticket_view(after, ticket)
    elif action["kind"] in ("done", "extra_time") and ticket:
        out["planned"] = _job_view(_job_of(before, action["agent"], ticket, at), after.start, before)
        out["went_to"] = _job_view(_job_of(after, action["agent"], ticket, at), after.start, after)
        later = next((j for j in after.work.get(action["agent"], []) if j["minute"] > at), None)
        out["next_ticket"] = _job_view(later and {**later, "agent": action["agent"]}, after.start, after)
    return out


def _rel(value, start: float) -> float | None:
    if value is None or math.isnan(float(value)):
        return None
    return round(float(value) - start, 1)


def _risk_when_decided(live: LiveDay, ticket_id: str, minute: float) -> float | None:
    i = live.context.get("index", {}).get(ticket_id)
    for at, risks in reversed(live.risk_seen):
        if at <= minute:
            p = risks.get(i)
            return None if p is None else round(float(p), 2)
    return None


def _job_view(job: dict | None, start: float, live: LiveDay | None = None) -> dict | None:
    if job is None:
        return None
    risk = _risk_in(job.get("reason"))
    if risk is None and live is not None:
        risk = _risk_when_decided(live, job["ticket_id"], job["minute"])
    return {"agent": job["agent"], "ticket_id": job["ticket_id"], "minute": _rel(job["minute"], start),
            "deadline": _rel(job["deadline"], start), "resolved": _rel(job["resolved"], start), "risk": risk}


def _ticket_view(live: LiveDay, ticket_id: str) -> dict | None:
    t = live.tickets["opslens"]
    row = t[t["ticket_id"] == ticket_id]
    if row.empty:
        return None
    return {"agent": None, "ticket_id": ticket_id, "minute": None, "risk": None,
            "deadline": _rel(row["deadline"].iloc[0], live.start), "resolved": _rel(row["resolved"].iloc[0], live.start)}


def _agent_card(agent, day: int) -> dict:
    start_min, _ = agent.schedule_on(day - 1)
    end_min = start_min + agent.shift_minutes
    return {"id": agent.agent_id, "team": agent.team, "name": agent.name, "languages": sorted(agent.languages),
            "skills": sorted(agent.team_skills), "extra_skills": sorted(agent.skills - agent.team_skills),
            "shift": f"{clock(start_min % MINUTES_PER_DAY)}-{clock(end_min % MINUTES_PER_DAY)}"}


def _work_by_agent(decision_log: list[dict], world, tickets: pd.DataFrame, tickets_info: pd.DataFrame,
                   cache: dict | None = None) -> dict[str, list[dict]]:
    resolved_by_idx = dict(zip(tickets["idx"].to_numpy(), tickets["resolved_min"].to_numpy()))
    cache = {} if cache is None else cache
    work: dict[str, list[dict]] = {}
    for d in decision_log:
        i = d["ticket_idx"]
        ticket_id = world.ticket_ids[i]
        info = cache.get(ticket_id)
        if info is None:
            row = tickets_info.loc[ticket_id]
            info = cache[ticket_id] = {"priority": str(row["priority"]), "category": str(row["category"]),
                                       "language": str(row["language"]),
                                       "text": mask_pii(str(row["text"])).text[:140]}
        resolved = resolved_by_idx.get(i, math.nan)
        work.setdefault(d["agent_id"], []).append({
            "minute": float(d["minute"]), "ticket_id": ticket_id, "reason": d["reason"],
            "created": float(world.created_min[i]), "deadline": float(world.created_min[i] + world.sla_min[i]),
            "resolved": None if math.isnan(resolved) else float(resolved),
            "priority": info["priority"], "category": str(d.get("believed") or info["category"]),
            "language": info["language"], "text": info["text"]})
    return work


def _ticket_now(job: dict, now: float, start: float) -> dict:
    return {"ticket_id": job["ticket_id"], "priority": job["priority"], "category": job["category"],
            "language": job["language"], "text": job["text"], "reason": job["reason"],
            "minutes_left": round(job["deadline"] - now, 1), "promise_min": round(job["deadline"] - job["created"], 1), "waited": round(min(job["minute"], now) - job["created"], 1),
            "assigned_at": round(job["minute"] - start, 1)}


def floor_now(live: LiveDay, now: float, status: str) -> list[dict]:
    rows = []
    for i, agent in enumerate(live.agents):
        word = STATUS_WORD.get(status[i], "off") if i < len(status) else "off"
        mine = live.work.get(agent["id"], [])
        started = [j for j in mine if live.start <= j["minute"] <= now]
        done = [j for j in started if j["resolved"] is not None and j["resolved"] <= now]
        last = started[-1] if started else None
        working = word in ("busy", "cross", "wrong") and last is not None and (last["resolved"] is None or last["resolved"] > now)
        lined_up = next((j for j in mine if j["minute"] > now and j["created"] <= now), None)
        rows.append({"id": agent["id"], "status": word, "done": len(done),
                     "kept": sum(1 for j in done if j["resolved"] <= j["deadline"]),
                     "rescues": sum(1 for j in started if "cross-skill" in j["reason"]),
                     "current": _ticket_now(last, now, live.start) if working else None,
                     "next": _ticket_now(lined_up, now, live.start) if lined_up else None})
    return rows


def _danger_watch(live: LiveDay, policy, model) -> Callable:
    world = live.context["world"]
    every = [0.0]

    def watch(state, now: float) -> None:
        if now < every[0]:
            return
        every[0] = now + RISK_EVERY_MIN
        waiting = state.waiting_tickets()
        if not waiting:
            live.danger.append({"minute": now, "rows": None})
            return
        on_shift = [k for k in range(len(world.agents)) if state.shift_end(k, now) is not None]
        cols = policy.context_columns(state, now, waiting, on_shift)
        live_rows = np.nonzero(cols["time_left_min"] > 0)[0]
        if len(live_rows) == 0:
            live.danger.append({"minute": now, "rows": None})
            return
        X = policy.context_matrix(cols)[live_rows]
        p = model.predict_matrix(X, LIVE_PREDICT_THREADS)
        live.risk_seen.append((now, dict(zip(np.asarray(cols["idx"])[live_rows].tolist(), p.tolist()))))
        order = live_rows[np.argsort(-p, kind="stable")[:RISK_SHOWN]]
        top = {c: np.asarray(cols[c])[order] for c in cols if c != "idx"}
        live.danger.append({"minute": now, "rows": top, "p": np.sort(p)[::-1][:RISK_SHOWN]})

    return watch


def danger_tickets(live: LiveDay, entry: dict) -> list[dict]:
    if "tickets" in entry:
        return entry["tickets"]
    top = entry.get("rows")
    if top is None:
        entry["tickets"] = []
        return []
    model, tickets_info = live.context["inputs"]["model"], live.context["tickets_info"]
    top = pd.DataFrame(top)
    reasons = top_reasons(model, top)
    served_now = risk_if_assigned_now(model, top)
    rows = []
    for (_, row), prob, now_p, why in zip(top.iterrows(), entry["p"], served_now, reasons):
        info = tickets_info.loc[row["ticket_id"]]
        rows.append({"ticket_id": row["ticket_id"], "probability": round(float(prob), 3),
                     "if_served_now": round(float(now_p), 3),
                     "nobody_capable": bool(row["capable_on_shift"] < 0.5),
                     "minutes_left": round(float(row["time_left_min"]), 1),
                     "priority": str(row["priority"]), "language": str(row["language"]),
                     "category": str(row["category_pred"]),
                     "text": mask_pii(str(info["text"])).text[:140],
                     "reasons": [r["text"] for r in why]})
    entry["tickets"] = rows
    return rows


def state_at(live: LiveDay, minute_of_day: float) -> dict:
    now = live.start + max(0.0, min(float(minute_of_day), MINUTES_PER_DAY - 1))
    out = {"day": live.day, "seed": live.seed, "minute_of_day": round(now - live.start, 1),
           "agents": live.agents, "policies": {}}
    for key, frames in live.floors.items():
        k = max(0, bisect.bisect_right([f["minute"] for f in frames], now) - 1)
        t = live.tickets[key]
        arrived = t["created"] <= now
        waiting = arrived & ~(t["pickup"] <= now)
        due = t["deadline"] <= now
        missed = due & ~(t["resolved"] <= t["deadline"])
        out["policies"][key] = {
            "arrived": int(arrived.sum()),
            "waiting": int(waiting.sum()),
            "missed": int(missed.sum()),
            "kept": int((due & ~missed).sum()),
            "status": frames[k]["status"] if frames else "",
            "queues": frames[k]["queues"] if frames else {},
        }
    past = [d for d in live.danger if d["minute"] <= now]
    out["danger"] = danger_tickets(live, past[-1]) if past else []
    out["danger_minute"] = round(past[-1]["minute"] - live.start, 1) if past else None
    recent = [d for d in live.decisions if now - 15 <= d["minute"] <= now]
    out["decisions"] = [{**d, "minute": round(d["minute"] - live.start, 1)} for d in recent[-8:]][::-1]
    if "opslens" in out["policies"]:
        out["floor"] = floor_now(live, now, out["policies"]["opslens"]["status"])
    out["actions"] = [{**e, "outcome": outcome_at(e.get("went_to"), now - live.start)} for e in live.effects]
    return out


def outcome_at(job: dict | None, minute: float) -> str | None:
    if job is None or job.get("deadline") is None:
        return None
    if job.get("resolved") is not None and job["resolved"] <= minute:
        return "kept" if job["resolved"] <= job["deadline"] else "missed"
    return "missed" if job["deadline"] <= minute else "open"


def clock(minute_of_day: float) -> str:
    m = int(math.floor(minute_of_day))
    return f"{m // 60:02d}:{m % 60:02d}"
