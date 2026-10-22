"""CP-SAT weekly roster: every day agent's start hour and days off, chosen together (Plan v4 W5).

What it does: for one planning week, picks for each day agent ONE option — a start hour within
±2 h of today's (06:00-16:00) and two consecutive days off — so that the team-by-hour coverage
matches the forecast need as closely as possible. Same people, same 9-hour shifts, same 5 working
days, so the budget does not change. Night agents (22:00) stay as they are.

Objective (agent-hours over day hours 07:00-24:00, the same measure as staffing.plan_moves):
    Σ max(0, need − coverage) + 3 × Σ max(0, load − coverage) + change_penalty × changed agents
with at most `max_changes_per_team` changed agents per team. CP-SAT works in integers, so every
quantity is ×100.

Why: the greedy planner tries one move at a time; two half-useful moves that only pay together
are never found. CP-SAT searches all combinations and says when its answer is proven optimal.

Example: Team C is short at weekend dinner. Greedy moves C05's day off; CP-SAT may move C05 AND
start C07 two hours later, because together they cover Sat-Sun 19-23 without opening a gap on
Tuesday. Design and pre-registered test: docs/explain/roster_opt.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from ortools.sat.python import cp_model

from opslens.staffing import DAY_HOURS, DAY_NAMES, OVERLOAD_WEIGHT, Shift, shift_vector

SCALE = 100
NIGHT_START = 22


def options_for(s: Shift) -> list[Shift]:
    """Every allowed week for one agent (the current one included)."""
    if s.start_hour == NIGHT_START:
        return [s]
    starts = [h for h in range(s.start_hour - 2, s.start_hour + 3) if 6 <= h <= 16] or [s.start_hour]
    n_off = len(s.days_off)
    offs = [frozenset((d + k) % 7 for k in range(n_off)) for d in range(7)] if n_off else [frozenset()]
    if s.days_off not in offs:
        offs.append(s.days_off)  # today's pattern is always allowed, even if not consecutive
    return [Shift(s.agent_id, s.team, h, s.hours, off) for h in starts for off in offs]


def describe(old: Shift, new: Shift) -> str:
    parts = []
    if new.start_hour != old.start_hour:
        parts.append(f"start {new.start_hour:02d}:00 instead of {old.start_hour:02d}:00")
    if new.days_off != old.days_off:
        parts.append("days off " + "+".join(DAY_NAMES[d] for d in sorted(new.days_off)) + " instead of "
                     + "+".join(DAY_NAMES[d] for d in sorted(old.days_off)))
    return "; ".join(parts)


def plan_roster(shifts: list[Shift], need: pd.DataFrame, first_day: int, n_days: int, first_weekday: int,
                load: pd.DataFrame | None = None, max_changes_per_team: int = 2, change_penalty: float = 1.0,
                time_limit_s: float = 30.0, workers: int = 8) -> tuple[list[Shift], list[dict], dict]:
    """Returns (new shifts, changes in plan_moves' format, solver info)."""
    teams = list(need.columns)
    hours = n_days * 24
    day_rows = np.nonzero(np.isin(np.arange(hours) % 24, list(DAY_HOURS)))[0]
    need_arr = need.reindex(range(hours)).reindex(columns=teams).fillna(0).to_numpy()[day_rows]
    load_arr = (load.reindex(range(hours)).reindex(columns=teams).fillna(0).to_numpy()[day_rows]
                if load is not None else np.zeros_like(need_arr))

    m = cp_model.CpModel()
    opts = [options_for(s) for s in shifts]
    vecs = [[np.rint(shift_vector(o, first_day, n_days, first_weekday)[day_rows] * SCALE).astype(int) for o in os_]
            for os_ in opts]
    pick = [[m.NewBoolVar(f"x_{i}_{k}") for k in range(len(os_))] for i, os_ in enumerate(opts)]
    changed = []
    for i, s in enumerate(shifts):
        m.AddExactlyOne(pick[i])
        same = [k for k, o in enumerate(opts[i]) if o.start_hour == s.start_hour and o.days_off == s.days_off]
        changed.append(1 - sum(pick[i][k] for k in same))
    for t in teams:
        members = [i for i, s in enumerate(shifts) if s.team == t]
        m.Add(sum(changed[i] for i in members) <= max_changes_per_team)

    cost_terms = []
    for col, t in enumerate(teams):
        members = [i for i, s in enumerate(shifts) if s.team == t]
        for r in range(len(day_rows)):
            cover = sum(int(vecs[i][k][r]) * pick[i][k] for i in members for k in range(len(opts[i]))
                        if vecs[i][k][r])
            n = int(round(need_arr[r, col] * SCALE))
            ld = int(round(load_arr[r, col] * SCALE))
            if n > 0:
                gap = m.NewIntVar(0, n, f"gap_{t}_{r}")
                m.Add(gap >= n - cover)
                cost_terms.append(gap)
            if ld > 0:
                over = m.NewIntVar(0, ld, f"over_{t}_{r}")
                m.Add(over >= ld - cover)
                cost_terms.append(int(OVERLOAD_WEIGHT) * over)
    penalty = int(round(change_penalty * SCALE))
    m.Minimize(sum(cost_terms) + penalty * sum(changed))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = 7
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return list(shifts), [], {"status": solver.StatusName(status)}

    new_shifts, changes = [], []
    for i, s in enumerate(shifts):
        k = next(k for k, v in enumerate(pick[i]) if solver.Value(v))
        new = opts[i][k]
        new_shifts.append(new)
        if (new.start_hour, new.days_off) != (s.start_hour, s.days_off):
            changes.append({"agent_id": s.agent_id, "team": s.team, "change": describe(s, new)})
    info = {"status": solver.StatusName(status), "objective_agent_hours": solver.ObjectiveValue() / SCALE,
            "best_bound_agent_hours": solver.BestObjectiveBound() / SCALE, "wall_s": round(solver.WallTime(), 2),
            "changes": len(changes)}
    return new_shifts, changes, info


def weighted_shortage(shifts: list[Shift], need: pd.DataFrame, first_day: int, n_days: int, first_weekday: int,
                      load: pd.DataFrame | None = None) -> float:
    """The objective without the change penalty, for any roster (to compare planners fairly)."""
    teams = list(need.columns)
    hours = n_days * 24
    day = np.isin(np.arange(hours) % 24, list(DAY_HOURS))[:, None]
    cov = np.zeros((hours, len(teams)))
    for s in shifts:
        cov[:, teams.index(s.team)] += shift_vector(s, first_day, n_days, first_weekday)
    need_arr = need.reindex(range(hours)).reindex(columns=teams).fillna(0).to_numpy() * day
    load_arr = (load.reindex(range(hours)).reindex(columns=teams).fillna(0).to_numpy() * day
                if load is not None else np.zeros_like(need_arr))
    covered = cov * day
    return float(np.clip(need_arr - covered, 0, None).sum() + OVERLOAD_WEIGHT * np.clip(load_arr - covered, 0, None).sum())
