"""Live now: today's support day, simulated on this laptop and shown at the real clock.

What it does: when the server starts (or a viewer asks for new luck), it simulates one whole
support day twice, with the industry standard and with OpsLens, on the same tickets and the same
luck. While simulating it records, every 5 minutes, the floor (who is busy, how long each queue
is), the tickets OpsLens sees in most danger with their reasons, and every OpsLens decision with
its reason. The dashboard then asks for "the state at 21:14" every few seconds, using the
viewer's real clock, so the day unfolds in real time.

Why this design:
- A real floor cannot be replayed; ours can. The tickets are the practice company's tickets for
  the test day with the same weekday as today (a day OpsLens never studied), so nothing here was
  tuned on them. Every number on the Live screen is computed by the engine on this laptop.
- Simulating the whole day once (about 20-40 s) and revealing it minute by minute keeps the page
  instant. A viewer can press "New luck" to simulate the day again with another seed.
- The date shown is today's: the screen says plainly that the tickets are simulated.

Example (Saturday, 21:14): industry standard 61 waiting and 23 promises missed so far; OpsLens
24 waiting and 6 missed; in danger now: T060582 Hindi refund 99.7%, "no agent on shift can
serve Hindi refund".
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from opslens import policies
from opslens.risk import risk_if_assigned_now, top_reasons
from opslens.simulate import FLOOR_EVERY_MIN, MINUTES_PER_DAY, simulate
from opslens.whatif import change_agents, change_volume, make_policy
from opslens.world import build_world, day_bounds

POLICIES = ("baseline_d", "opslens")  # the lead comparison, as on the Overview
RISK_EVERY_MIN = 10  # how often the "in danger now" list is recorded
RISK_SHOWN = 5
STATUS_LETTER = {"off": "o", "idle": "i", "busy": "b", "cross": "x", "wrong": "w"}


def matching_test_day(weekday: int, first_weekday: int, test_days: tuple[int, int]) -> int:
    """The first test day that falls on `weekday` (0 = Monday). Day d's weekday is
    (first_weekday + d - 1) % 7, with day 1 = the calendar's start date."""
    for day in range(test_days[0], test_days[1] + 1):
        if (first_weekday + day - 1) % 7 == weekday:
            return day
    return test_days[0]


@dataclass
class LiveDay:
    """One simulated day, ready to be read at any minute."""
    day: int
    seed: int
    start: float  # simulator minute of 00:00 on that day
    agents: list[dict]
    floors: dict[str, list[dict]] = field(default_factory=dict)  # policy -> frames
    tickets: dict[str, pd.DataFrame] = field(default_factory=dict)  # policy -> per-ticket outcome
    danger: list[dict] = field(default_factory=list)  # OpsLens: {minute, tickets: [...]}
    decisions: list[dict] = field(default_factory=list)  # OpsLens: {minute, ticket_id, agent, reason}


class _CaptureFeatures:
    """Wraps policies.features_for_snapshot so the live run can see the features OpsLens just
    scored (to explain the riskiest tickets). It returns exactly what it is given, and keeps one
    copy per thread: a What-if simulated by the server at the same moment cannot mix in."""

    def __init__(self, original) -> None:
        self.original = original
        self._mine = threading.local()

    def __call__(self, *args, **kwargs):
        self._mine.last = self.original(*args, **kwargs)
        return self._mine.last

    @property
    def last(self) -> pd.DataFrame | None:
        return getattr(self._mine, "last", None)


def simulate_live_day(inputs: dict, day: int, seed: int = 1, agents_delta: dict[str, int] | None = None,
                      volume_factor: float = 1.0) -> LiveDay:
    """Simulate `day` (with the day before as warm-up) for every policy and record the floor.
    `agents_delta` ({"C": -2}) and `volume_factor` (1.3 = 30% more customers) change the day the
    same way the What-if panel does (opslens/whatif.py), so a viewer can stress today live."""
    warm, _ = day_bounds(day - 1, day - 1)
    start, end = day_bounds(day, day)
    tickets, preds = inputs["tickets"], inputs["preds"]
    if abs(volume_factor - 1.0) > 1e-9:
        tickets, preds = change_volume(tickets, preds, day, volume_factor)
    agents = change_agents(inputs["agents"], agents_delta) if agents_delta else inputs["agents"]
    inputs = {**inputs, "tickets": tickets, "preds": preds, "agents": agents}
    tickets_info = tickets.set_index("ticket_id")
    live = None
    for key in POLICIES:
        world = build_world(inputs["tickets"], seed=seed, agents=inputs["agents"])
        if live is None:
            live = LiveDay(day=day, seed=seed, start=start,
                           agents=[{"id": a.agent_id, "team": a.team, "name": a.name,
                                    "languages": sorted(a.languages)} for a in world.agents])
        policy = make_policy(key, world, inputs["preds"], inputs["model"], inputs["weights"])
        capture = None
        if key == "opslens":
            policy.log_window = (start, end)  # record every decision of the day with its reason
            capture = _CaptureFeatures(policies.features_for_snapshot)
            policies.features_for_snapshot = capture
            _record_danger(policy, capture, live, inputs, tickets_info, start, end)
        try:
            result = simulate(world, policy, warm, end, metric_start_min=start, seed_label=str(seed),
                              floor_window=(start, end))
        finally:
            if capture is not None:
                policies.features_for_snapshot = capture.original
        live.floors[key] = [{"minute": f["minute"],
                             "status": "".join(STATUS_LETTER[f["agents"][a["id"]]] for a in live.agents),
                             "queues": f["queues"]} for f in result.floor]
        t = result.tickets
        live.tickets[key] = pd.DataFrame({
            "created": t["created_min"].to_numpy(),
            "pickup": t["first_pickup_min"].to_numpy(),
            "resolved": t["resolved_min"].to_numpy(),
            "deadline": (t["created_min"] + t["sla_min"]).to_numpy(),
        })
        if key == "opslens":
            live.decisions = [{"minute": d["minute"], "ticket_id": world.ticket_ids[d["ticket_idx"]],
                               "agent": d["agent_id"], "reason": d["reason"]} for d in policy.decision_log]
    return live


def _record_danger(policy, capture: _CaptureFeatures, live: LiveDay, inputs: dict,
                   tickets_info: pd.DataFrame, start: float, end: float) -> None:
    """Every RISK_EVERY_MIN, keep OpsLens's riskiest waiting tickets with their top reasons."""
    original_refresh = policy.refresh
    next_at = [start]

    def refresh(state, now):
        original_refresh(state, now)
        if not (start <= now < end) or now < next_at[0] or capture.last is None or capture.last.empty:
            return
        next_at[0] = now + RISK_EVERY_MIN
        feats = capture.last
        live_rows = feats[feats["time_left_min"] > 0]
        if live_rows.empty:
            return
        p = inputs["model"].predict(live_rows)
        order = np.argsort(-p)[:RISK_SHOWN]
        top = live_rows.iloc[order]
        reasons = top_reasons(inputs["model"], top)
        served_now = risk_if_assigned_now(inputs["model"], top)  # the same what-if as the Risks screen
        rows = []
        for (_, row), prob, now_p, why in zip(top.iterrows(), p[order], served_now, reasons):
            info = tickets_info.loc[row["ticket_id"]]
            rows.append({"ticket_id": row["ticket_id"], "probability": round(float(prob), 3),
                         "if_served_now": round(float(now_p), 3),
                         "nobody_capable": bool(row["capable_on_shift"] < 0.5),
                         "minutes_left": round(float(row["time_left_min"]), 1),
                         "priority": str(row["priority"]), "language": str(row["language"]),
                         "category": str(row["category_pred"]), "text": str(info["text"])[:140],
                         "reasons": [r["text"] for r in why]})
        live.danger.append({"minute": now, "tickets": rows})

    policy.refresh = refresh


def state_at(live: LiveDay, minute_of_day: float) -> dict:
    """What the floor looks like at `minute_of_day` (0-1439) of the simulated day."""
    now = live.start + max(0.0, min(float(minute_of_day), MINUTES_PER_DAY - 1))
    out = {"day": live.day, "seed": live.seed, "minute_of_day": round(now - live.start, 1),
           "agents": live.agents, "policies": {}}
    for key, frames in live.floors.items():
        k = min(len(frames) - 1, max(0, int((now - live.start) // FLOOR_EVERY_MIN)))
        t = live.tickets[key]
        arrived = t["created"] <= now
        waiting = arrived & ~(t["pickup"] <= now)  # NaN pickup = never picked up: still waiting
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
    out["danger"] = past[-1]["tickets"] if past else []
    out["danger_minute"] = round(past[-1]["minute"] - live.start, 1) if past else None
    recent = [d for d in live.decisions if now - 15 <= d["minute"] <= now]
    out["decisions"] = [{**d, "minute": round(d["minute"] - live.start, 1)} for d in recent[-8:]][::-1]
    return out


def clock(minute_of_day: float) -> str:
    """'21:14' for minute 1274."""
    m = int(math.floor(minute_of_day))
    return f"{m // 60:02d}:{m % 60:02d}"
