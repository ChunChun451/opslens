"""Staffing: how many agents each team needs per hour, and budget-neutral moves to get there.

What it does:
1. Needed agents per team and hour, from the forecast's UPPER (80%) band, with **Erlang C**:
   the smallest number of agents for which the average wait stays under a target and
   utilisation ρ stays ≤ 0.85. (Erlang C is the call-centre standard; our simulator matches it.)
2. Scheduled agents per team and hour, from the roster (× 0.95 for absences).
3. Moves that keep headcount AND total agent-hours the same, chosen to cut the weighted
   shortage: hours where work exceeds people (overload, the backlog grows) count 3×, hours
   that are only below the comfortable Erlang-C level count 1×. Night hours are excluded
   (three cross-trained night agents cover every team by design):
   - shift a person's start time by 1 or 2 hours for one week,
   - swap a day off to a quieter day in the same week.
   Greedy: try every such change, keep the one that removes the most shortage, repeat up to
   `max_moves` times. A team lead can read and apply every move.
4. Cross-trained agents who can cover another team's shortage are listed as "help" suggestions
   (the optimiser already routes work to them; the list makes it visible to people).

Example: Team C, Saturday 19:00-23:00. Forecast upper band 31 missing/wrong-item tickets per
hour × 7.4 min average handling → λ = 31/h, AHT 7.4 min. Erlang C with a 10-min wait target
needs 6 agents; the roster has 3.8 → shortage 2.2. Best move: C05 swaps Saturday off for
Tuesday off (Tuesday dinner has a surplus of 1.6).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

TARGET_WAIT_MIN = 15.0  # a quarter of the tightest SLA (P1, 60 min)
MAX_RHO = 0.85
ATTENDANCE = 0.95


# ---- Erlang C --------------------------------------------------------------------------------

def erlang_c_wait(arrivals_per_hour: float, aht_min: float, agents: int) -> float:
    """Average wait in minutes for M/M/c. Infinite when the agents cannot keep up."""
    if arrivals_per_hour <= 0:
        return 0.0
    load = arrivals_per_hour * aht_min / 60.0  # offered load in Erlangs
    if agents <= load:
        return math.inf
    # Erlang C with the stable recurrence for the Erlang B blocking probability.
    b = 1.0
    for k in range(1, agents + 1):
        b = load * b / (k + load * b)
    prob_wait = agents * b / (agents - load * (1 - b))
    return prob_wait * aht_min / (agents - load)


def agents_needed(arrivals_per_hour: float, aht_min: float, target_wait: float = TARGET_WAIT_MIN,
                  max_rho: float = MAX_RHO) -> int:
    """Smallest number of agents with average wait ≤ target and utilisation ≤ max_rho."""
    if arrivals_per_hour <= 0:
        return 0
    load = arrivals_per_hour * aht_min / 60.0
    n = max(1, math.ceil(load / max_rho))
    while erlang_c_wait(arrivals_per_hour, aht_min, n) > target_wait:
        n += 1
    return n


# ---- Schedule --------------------------------------------------------------------------------

@dataclass
class Shift:
    agent_id: str
    team: str
    start_hour: int
    hours: int
    days_off: frozenset[int]


def shifts_from_agents(agents: pd.DataFrame) -> list[Shift]:
    return [Shift(a.agent_id, a.team, int(a.shift_start_hour), int(a.shift_hours),
                  frozenset(int(d) for d in str(a.days_off).split("|") if d != ""))
            for a in agents.itertuples()]


def shift_vector(s: Shift, first_day: int, n_days: int, first_weekday: int) -> np.ndarray:
    """Expected presence (0 or 0.95) of one agent in each hour of the planning window."""
    hours = n_days * 24
    vec = np.zeros(hours)
    for d in range(-1, n_days):  # d = -1: a night shift that started the day before
        weekday = (first_weekday + first_day - 1 + d) % 7
        if weekday in s.days_off:
            continue
        lo = max(d * 24 + s.start_hour, 0)
        hi = min(d * 24 + s.start_hour + s.hours, hours)
        if lo < hi:
            vec[lo:hi] += ATTENDANCE
    return vec


def coverage(shifts: list[Shift], teams: list[str], first_day: int, n_days: int, first_weekday: int) -> pd.DataFrame:
    """Expected agents on shift per team per hour (rows: hour index from first_day 00:00)."""
    cov = np.zeros((n_days * 24, len(teams)))
    for s in shifts:
        cov[:, teams.index(s.team)] += shift_vector(s, first_day, n_days, first_weekday)
    return pd.DataFrame(cov, columns=teams)


def needed_per_hour(workload: pd.DataFrame) -> pd.DataFrame:
    """workload: columns hour_index, team, arrivals, aht_min → agents needed per team per hour."""
    needed = workload.assign(need=[agents_needed(a, t) for a, t in zip(workload["arrivals"], workload["aht_min"])])
    return needed.pivot(index="hour_index", columns="team", values="need").fillna(0)


def shortage(cov: pd.DataFrame, need: pd.DataFrame) -> float:
    """Total agent-hours missing in day hours (surplus elsewhere does not cancel it)."""
    gap = need.reindex_like(cov).fillna(0) - cov
    gap = gap[np.isin(gap.index % 24, list(DAY_HOURS))]
    return float(gap.clip(lower=0).to_numpy().sum())


# ---- Budget-neutral moves --------------------------------------------------------------------

def candidate_moves(s: Shift) -> list[tuple[str, Shift]]:
    """Every small change for one agent: start ±1/±2 h, or one day off moved to another day."""
    moves = []
    for delta in (-2, -1, 1, 2):
        start = s.start_hour + delta
        if 6 <= start <= 16 and s.start_hour != 22:  # night shifts stay as they are
            moves.append((f"start {start:02d}:00 instead of {s.start_hour:02d}:00",
                          Shift(s.agent_id, s.team, start, s.hours, s.days_off)))
    for off in sorted(s.days_off):
        for new_off in range(7):
            if new_off in s.days_off:
                continue
            new = frozenset((s.days_off - {off}) | {new_off})
            moves.append((f"day off on {DAY_NAMES[new_off]} instead of {DAY_NAMES[off]}",
                          Shift(s.agent_id, s.team, s.start_hour, s.hours, new)))
    return moves


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


DAY_HOURS = range(7, 24)  # nights are covered by the cross-trained night pool, planned separately


OVERLOAD_WEIGHT = 3.0  # an hour with more work than people (backlog grows) counts 3x


def load_per_hour(workload: pd.DataFrame) -> pd.DataFrame:
    """Offered load in agents (arrivals × handle time ÷ 60): below this, the backlog grows."""
    load = workload.assign(load=workload["arrivals"] * workload["aht_min"] / 60.0)
    return load.pivot(index="hour_index", columns="team", values="load").fillna(0)


def plan_moves(shifts: list[Shift], need: pd.DataFrame, first_day: int, n_days: int, first_weekday: int,
               max_moves: int = 6, min_gain: float = 1.0, load: pd.DataFrame | None = None
               ) -> tuple[list[Shift], list[dict]]:
    """Greedy budget-neutral schedule changes. Returns the new shifts and the moves taken.

    Only day hours (07:00-24:00) count: at night three cross-trained agents cover all teams by
    design, so a team-by-team count would show a fake shortage every night.
    Speed trick: the floor's coverage is the sum of one array per shift, so trying a move
    only means "total − old array + new array" for that agent's team.
    """
    teams = list(need.columns)
    need_arr = need.reindex(range(n_days * 24)).fillna(0).to_numpy()
    day_mask = np.isin(np.arange(n_days * 24) % 24, list(DAY_HOURS))[:, None]
    need_arr = need_arr * day_mask
    load_arr = (load.reindex(range(n_days * 24)).reindex(columns=teams).fillna(0).to_numpy() * day_mask
                if load is not None else np.zeros_like(need_arr))
    current = list(shifts)
    vectors = [shift_vector(s, first_day, n_days, first_weekday) for s in current]
    cov = np.zeros_like(need_arr, dtype=float)
    for s, v in zip(current, vectors):
        cov[:, teams.index(s.team)] += v

    def short(c: np.ndarray) -> float:
        covered = c * day_mask
        comfort_gap = np.clip(need_arr - covered, 0, None).sum()
        overload = np.clip(load_arr - covered, 0, None).sum()
        return float(comfort_gap + OVERLOAD_WEIGHT * overload)

    best_short = short(cov)
    taken: list[dict] = []
    for _ in range(max_moves):
        best = None
        for i, s in enumerate(current):
            if any(m["agent_id"] == s.agent_id for m in taken):
                continue  # at most one change per person per week
            col = teams.index(s.team)
            for text, new in candidate_moves(s):
                new_vec = shift_vector(new, first_day, n_days, first_weekday)
                trial = cov.copy()
                trial[:, col] += new_vec - vectors[i]
                value = short(trial)
                if best is None or value < best[0]:
                    best = (value, i, new, text, new_vec)
        if best is None or best_short - best[0] < min_gain:
            break
        value, i, new, text, new_vec = best
        cov[:, teams.index(new.team)] += new_vec - vectors[i]
        vectors[i] = new_vec
        taken.append({"agent_id": new.agent_id, "team": new.team, "change": text,
                      "shortage_before": round(best_short, 1), "shortage_after": round(value, 1)})
        current[i] = new
        best_short = value
    return current, taken
