from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

TARGET_WAIT_MIN = 15.0
MAX_RHO = 0.85
ATTENDANCE = 0.95


def erlang_c_wait(arrivals_per_hour: float, aht_min: float, agents: int) -> float:
    if arrivals_per_hour <= 0:
        return 0.0
    load = arrivals_per_hour * aht_min / 60.0
    if agents <= load:
        return math.inf
    b = 1.0
    for k in range(1, agents + 1):
        b = load * b / (k + load * b)
    prob_wait = agents * b / (agents - load * (1 - b))
    return prob_wait * aht_min / (agents - load)


def agents_needed(arrivals_per_hour: float, aht_min: float, target_wait: float = TARGET_WAIT_MIN,
                  max_rho: float = MAX_RHO) -> int:
    if arrivals_per_hour <= 0:
        return 0
    load = arrivals_per_hour * aht_min / 60.0
    n = max(1, math.ceil(load / max_rho))
    while erlang_c_wait(arrivals_per_hour, aht_min, n) > target_wait:
        n += 1
    return n


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
    hours = n_days * 24
    vec = np.zeros(hours)
    for d in range(-1, n_days):
        weekday = (first_weekday + first_day - 1 + d) % 7
        if weekday in s.days_off:
            continue
        lo = max(d * 24 + s.start_hour, 0)
        hi = min(d * 24 + s.start_hour + s.hours, hours)
        if lo < hi:
            vec[lo:hi] += ATTENDANCE
    return vec


def coverage(shifts: list[Shift], teams: list[str], first_day: int, n_days: int, first_weekday: int) -> pd.DataFrame:
    cov = np.zeros((n_days * 24, len(teams)))
    for s in shifts:
        cov[:, teams.index(s.team)] += shift_vector(s, first_day, n_days, first_weekday)
    return pd.DataFrame(cov, columns=teams)


def needed_per_hour(workload: pd.DataFrame) -> pd.DataFrame:
    needed = workload.assign(need=[agents_needed(a, t) for a, t in zip(workload["arrivals"], workload["aht_min"])])
    return needed.pivot(index="hour_index", columns="team", values="need").fillna(0)


def shortage(cov: pd.DataFrame, need: pd.DataFrame) -> float:
    gap = need.reindex_like(cov).fillna(0) - cov
    gap = gap[np.isin(gap.index % 24, list(DAY_HOURS))]
    return float(gap.clip(lower=0).to_numpy().sum())


def candidate_moves(s: Shift) -> list[tuple[str, Shift]]:
    moves = []
    for delta in (-2, -1, 1, 2):
        start = s.start_hour + delta
        if 6 <= start <= 16 and s.start_hour != 22:
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


DAY_HOURS = range(7, 24)


OVERLOAD_WEIGHT = 3.0


def load_per_hour(workload: pd.DataFrame) -> pd.DataFrame:
    load = workload.assign(load=workload["arrivals"] * workload["aht_min"] / 60.0)
    return load.pivot(index="hour_index", columns="team", values="load").fillna(0)


def plan_moves(shifts: list[Shift], need: pd.DataFrame, first_day: int, n_days: int, first_weekday: int,
               max_moves: int = 6, min_gain: float = 1.0, load: pd.DataFrame | None = None
               ) -> tuple[list[Shift], list[dict]]:
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
                continue
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
