"""What-if: re-run one day in the simulator with the judge's changes, in a few seconds.

What it does: takes a test day, a policy, a volume factor and "agents added/removed per team",
builds that world, simulates the day (with the previous day as warm-up), and returns the KPIs —
for the chosen policy and, under the same changes, for the other two policies.

How the changes are made (simple and reproducible):
- Volume ×1.25: 25% of that day's tickets are copied as extra tickets 0-30 minutes later
  (new ticket numbers, so they get their own luck). Volume ×0.8: 20% of the day's tickets
  are removed. A fixed seed picks which ones, so the same request always gives the same answer.
- Team C +2: two agents are added to Team C as copies of Team C's agents with the latest
  shifts (evening cover is where most teams need help). Team D −2: the two Team D agents
  with the latest shifts are removed. Copies keep their languages and skills.

Example request: {"day": 48, "policy": "opslens", "volume_factor": 1.0, "agents_delta": {"C": 2}}
→ the day's KPIs for all three policies with two extra Team C agents. The numbers are computed
by the simulator at request time and are never stored or typed by hand.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from opslens.impact import summarize
from opslens.policies import OpsLensPolicy, OpsLensSettings, baseline_a, baseline_b
from opslens.simulate import MINUTES_PER_DAY, Agent, simulate
from opslens.world import build_world, day_bounds

SHOW = ["turnaround.breach_pct", "turnaround.p90_resolution_min", "turnaround.mean_wait_min",
        "turnaround.max_backlog", "productivity.transfers_per_100", "quality.p99_wait_min",
        "quality.mean_utilisation", "tickets"]
MAX_VOLUME, MIN_VOLUME, MAX_DELTA = 2.0, 0.5, 5


def change_volume(tickets: pd.DataFrame, preds: dict[str, str], day: int, factor: float,
                  seed: int = 11) -> tuple[pd.DataFrame, dict[str, str]]:
    """Scale the day's ticket volume by `factor` (copies above 1, removals below 1)."""
    lo, hi = (day - 1) * MINUTES_PER_DAY, day * MINUTES_PER_DAY
    in_day = (tickets["created_min"] >= lo) & (tickets["created_min"] < hi)
    rng = np.random.default_rng(seed)
    if factor < 1.0:
        day_rows = tickets.index[in_day]
        drop = rng.choice(day_rows, size=int(round((1 - factor) * len(day_rows))), replace=False)
        return tickets.drop(index=drop).reset_index(drop=True), preds
    if factor > 1.0:
        extra = tickets[in_day].sample(frac=factor - 1.0, random_state=seed).copy()
        extra["created_min"] = np.minimum(extra["created_min"] + rng.uniform(0, 30, len(extra)), hi - 1)
        new_ids = [f"T{800000 + k}" for k in range(len(extra))]
        preds = {**preds, **{new: preds.get(old, "") for new, old in zip(new_ids, extra["ticket_id"])}}
        extra["ticket_id"] = new_ids
        return pd.concat([tickets, extra], ignore_index=True), preds
    return tickets, preds


def change_agents(agents: list[Agent], delta: dict[str, int]) -> list[Agent]:
    """Add or remove agents per team (latest shifts first)."""
    out = list(agents)
    for team, k in delta.items():
        k = int(max(-MAX_DELTA, min(MAX_DELTA, k)))
        members = sorted([a for a in out if a.team == team and a.shift_start_min < 22 * 60],
                         key=lambda a: -a.shift_start_min)
        if k < 0:
            remove = {a.agent_id for a in members[:-k]}
            out = [a for a in out if a.agent_id not in remove]
        for i in range(k):
            template = members[i % len(members)]
            out.append(replace(template, agent_id=f"{team}+{i + 1}", name=f"Extra {team}{i + 1}"))
    return out


def run_whatif(request: dict, tickets: pd.DataFrame, agents: list[Agent], preds: dict[str, str],
               risk_model, weights: dict, test_days: tuple[int, int], seed: int = 1) -> dict:
    """Simulate the requested day for all three policies; return the chosen one's KPIs first."""
    day = int(request.get("day", test_days[0]))
    if not test_days[0] <= day <= test_days[1]:
        raise ValueError(f"day must be a test day ({test_days[0]}-{test_days[1]})")
    factor = float(min(MAX_VOLUME, max(MIN_VOLUME, request.get("volume_factor", 1.0))))
    chosen = str(request.get("policy", "opslens"))
    t, p = change_volume(tickets, preds, day, factor)
    team_agents = change_agents(agents, {k: int(v) for k, v in (request.get("agents_delta") or {}).items()})
    world = build_world(t, seed=seed, agents=team_agents)
    warm, _ = day_bounds(day - 1, day - 1)
    start, end = day_bounds(day, day)
    answers = {}
    for key in ("baseline_a", "baseline_b", "opslens"):
        if key == "opslens":
            policy = OpsLensPolicy(world, p, risk_model, weights, OpsLensSettings())
        else:
            policy = baseline_a() if key == "baseline_a" else baseline_b()
        k = summarize(simulate(world, policy, warm, end, metric_start_min=start))
        answers[key] = {name: round(float(k[name]), 3) for name in SHOW}
    return {
        "request": {"day": day, "policy": chosen, "volume_factor": factor,
                    "agents_delta": request.get("agents_delta") or {}},
        "kpis": answers.get(chosen, answers["opslens"]),
        "all_policies": answers,
        "agents_on_roster": len(team_agents),
    }
