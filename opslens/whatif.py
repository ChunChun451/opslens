from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from opslens.impact import summarize
from opslens.policies import OpsLensPolicy, OpsLensSettings, baseline_a, baseline_b, baseline_d
from opslens.simulate import MINUTES_PER_DAY, Agent, simulate
from opslens.world import build_world, day_bounds

SHOW = ["turnaround.breach_pct", "turnaround.p90_resolution_min", "turnaround.mean_wait_min",
        "turnaround.max_backlog", "productivity.transfers_per_100", "quality.p99_wait_min",
        "quality.mean_utilisation", "quality.late_minutes_per_100", "tickets"]
MAX_VOLUME, MIN_VOLUME, MAX_DELTA = 2.0, 0.5, 5


def change_volume(tickets: pd.DataFrame, preds: dict[str, str], day: int, factor: float,
                  seed: int = 11) -> tuple[pd.DataFrame, dict[str, str]]:
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


def check_day(day: int, test_days: tuple[int, int]) -> None:
    if not test_days[0] <= day <= test_days[1]:
        raise ValueError(f"day must be a test day ({test_days[0]}-{test_days[1]})")


def make_policy(key: str, world, preds: dict[str, str], risk_model, weights: dict):
    if key == "opslens":
        return OpsLensPolicy(world, preds, risk_model, weights, OpsLensSettings())
    if key == "baseline_d":
        return baseline_d(world, preds)
    return baseline_a() if key == "baseline_a" else baseline_b()


def simulate_day(tickets: pd.DataFrame, agents: list[Agent], preds: dict[str, str], risk_model, weights: dict,
                 day: int, seed: int, policy_key: str = "opslens") -> dict[str, float]:
    world = build_world(tickets, seed=seed, agents=agents)
    warm, _ = day_bounds(day - 1, day - 1)
    start, end = day_bounds(day, day)
    policy = make_policy(policy_key, world, preds, risk_model, weights)
    return summarize(simulate(world, policy, warm, end, metric_start_min=start))


def run_whatif(request: dict, tickets: pd.DataFrame, agents: list[Agent], preds: dict[str, str],
               risk_model, weights: dict, test_days: tuple[int, int], seed: int = 1) -> dict:
    day = int(request.get("day", test_days[0]))
    check_day(day, test_days)
    factor = float(min(MAX_VOLUME, max(MIN_VOLUME, request.get("volume_factor", 1.0))))
    chosen = str(request.get("policy", "opslens"))
    t, p = change_volume(tickets, preds, day, factor)
    team_agents = change_agents(agents, {k: int(v) for k, v in (request.get("agents_delta") or {}).items()})
    answers = {}
    for key in ("baseline_a", "baseline_b", "baseline_d", "opslens"):
        k = simulate_day(t, team_agents, p, risk_model, weights, day, seed, policy_key=key)
        answers[key] = {name: round(float(k[name]), 3) for name in SHOW}
    return {
        "request": {"day": day, "policy": chosen, "volume_factor": factor,
                    "agents_delta": request.get("agents_delta") or {}},
        "kpis": answers.get(chosen, answers["opslens"]),
        "all_policies": answers,
        "agents_on_roster": len(team_agents),
    }
