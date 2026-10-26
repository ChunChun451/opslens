from __future__ import annotations

import bisect
import math

from opslens.simulate import MINUTES_PER_DAY, World


def shift_intervals(world: World, agent_idx: int, first_day: int, last_day: int,
                    with_absences: bool = True) -> list[tuple[float, float]]:
    agent = world.agents[agent_idx]
    out = []
    for day in range(max(first_day, 0), last_day + 1):
        start_min, days_off = agent.schedule_on(day)
        if (world.first_weekday + day) % 7 in days_off:
            continue
        if with_absences and day < world.absent.shape[1] and world.absent[agent_idx, day]:
            continue
        start = day * MINUTES_PER_DAY + start_min
        out.append((float(start), float(start + agent.shift_minutes)))
    return out


def merge(intervals: list[tuple[float, float]]) -> tuple[list[float], list[float]]:
    starts: list[float] = []
    ends: list[float] = []
    for s, e in sorted(intervals):
        if starts and s <= ends[-1]:
            ends[-1] = max(ends[-1], e)
        else:
            starts.append(s)
            ends.append(e)
    return starts, ends


def earliest_start(cover: tuple[list[float], list[float]], t: float) -> float:
    starts, ends = cover
    k = bisect.bisect_right(starts, t) - 1
    if k >= 0 and t < ends[k]:
        return t
    return starts[k + 1] if k + 1 < len(starts) else math.inf


def best_resolution(world: World, i: int, trained: tuple, cross: tuple, p_matched: float,
                    p_mismatch: float) -> float:
    created = float(world.created_min[i])
    b1, b2 = float(world.base_handle_min[i, 0]), float(world.base_handle_min[i, 1])
    best = math.inf
    for kind1, cover1 in (("trained", trained), ("cross", cross)):
        s1 = earliest_start(cover1, created)
        if math.isinf(s1):
            continue
        f1 = s1 + b1 * (world.mismatch_factor if kind1 == "cross" else 1.0)
        reopen_p = p_mismatch if kind1 == "cross" else p_matched
        if not world.reopen_u[i] < reopen_p:
            best = min(best, f1 - created)
            continue
        back = f1 + float(world.reopen_delay_min[i])
        for kind2, cover2 in (("trained", trained), ("cross", cross)):
            s2 = earliest_start(cover2, back)
            if not math.isinf(s2):
                factor = world.reopen_handle_factor * (world.mismatch_factor if kind2 == "cross" else 1.0)
                best = min(best, s2 + b2 * factor - created)
    return best


def unavoidable(world: World, start_min: float, metric_start_min: float, end_min: float) -> set[int]:
    first_day = int(start_min // MINUTES_PER_DAY) - 1
    last_day = int(end_min // MINUTES_PER_DAY) + 3
    shifts = {k: shift_intervals(world, k, first_day, last_day) for k in range(len(world.agents))}
    cover_cache: dict[tuple[str, str, bool], tuple] = {}

    def cover(language: str, category: str, trained: bool) -> tuple:
        key = (language, category, trained)
        if key not in cover_cache:
            members = [k for k, a in enumerate(world.agents)
                       if language in a.languages and (category in a.skills) == trained]
            cover_cache[key] = merge([iv for k in members for iv in shifts[k]])
        return cover_cache[key]

    p_matched, p_mismatch = world.reopen_prob_matched, world.reopen_prob_mismatch
    out = set()
    for i in range(world.n_tickets):
        created = float(world.created_min[i])
        if not (metric_start_min <= created < end_min):
            continue
        lang, cat = world.language[i], world.true_category[i]
        r = best_resolution(world, i, cover(lang, cat, True), cover(lang, cat, False), p_matched, p_mismatch)
        if r > world.sla_min[i]:
            out.add(i)
    return out
