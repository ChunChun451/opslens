"""The physical floor: tickets that breach under EVERY policy — computed exactly, ticket by ticket.

What it does: for each ticket, the earliest it could possibly be resolved if every agent on shift
were free for it the moment it needs one (unlimited capacity). A ticket whose earliest possible
resolution is still past its SLA breaches under any policy. Their share is the floor.

Theorem. Fix a world: tickets, roster with days off and absences, staffing plan, and all random
draws (one seed). Let π be ANY policy the simulator accepts — every piece of work starts at a
decision moment, on a waiting ticket, with an agent who is on shift and speaks its language
(simulate._start_work enforces these). Then for every ticket i, resolution_π(i) ≥ R*(i), where
R*(i) is computed below. So breaches(π) ⊇ {i : R*(i) > SLA(i)} and breach%(π) ≥ floor.

Proof. Follow ticket i under π. (1) A transfer only adds time: since 18 Oct the k-th piece of real
work always uses draw k, so misrouting cannot change later work times. (2) Each piece of work k
starts at some s_k at which an on-shift agent with the language exists, either trained on the
category (duration b_k) or not (deliberate cross-skill, 1.6 × b_k); after a reopen the work is
0.6 × as long. (3) A reopen happens iff u_i < p, where p is 4% after trained work and 15% after
cross-skill work — the same rule in both worlds; it happens at most once, reopen_delay_i after the
first resolution. (4) With unlimited capacity nothing else delays i, and finishing earlier never
hurts (the reopen comes a fixed delay after the finish), so the best plan starts each piece of
work at the EARLIEST feasible moment for its kind (trained / cross-skill). (5) R*(i) is the
minimum over the four plans (kind of work 1 × kind of work 2). Every real trajectory is one of
these plans with starts no earlier than the earliest ones, so resolution_π(i) ≥ R*(i). ∎

What the theorem does NOT say: the number is not universal. It holds for any data, roster and
seed, but the value (e.g. 1.31% on the test days) belongs to that data. Change the roster, the
SLAs or the tickets and the floor changes. It is also optimistic: no real floor has unlimited
agents, so the best achievable breach rate is somewhere between the floor and the best policy.

Example: a Hindi P2 refund (SLA 240) created 23:30 with work draw 20 min; nobody trained on refunds
speaks Hindi until 09:00, but a Hindi app agent is on shift. Trained plan: 23:30 → 09:00 + 20 min =
590 min > 240. Cross-skill plan: start 23:30, 32 min → resolved in 32 min (if no reopen). R* = 32:
savable, so this ticket is NOT in the floor.
"""

from __future__ import annotations

import bisect
import math

from opslens.simulate import MINUTES_PER_DAY, World


def shift_intervals(world: World, agent_idx: int, first_day: int, last_day: int,
                    with_absences: bool = True) -> list[tuple[float, float]]:
    """[start, end) minutes of every shift the agent works on days first_day..last_day (0-based day
    index), with days off and staffing-plan overrides, like shift_end_if_on. `with_absences=False`
    gives the published schedule only — what a policy may know in advance (OpsLens v5)."""
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
    """Union of intervals as two sorted lists (starts, ends) with no overlaps."""
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
    """Earliest moment ≥ t at which someone in `cover` is on shift (math.inf if never).
    The simulator can only start work at decision moments (events and its 2-minute tick), which
    are never earlier than this, so using it keeps the bound valid (at worst slightly loose)."""
    starts, ends = cover
    k = bisect.bisect_right(starts, t) - 1
    if k >= 0 and t < ends[k]:
        return t
    return starts[k + 1] if k + 1 < len(starts) else math.inf


def best_resolution(world: World, i: int, trained: tuple, cross: tuple, p_matched: float,
                    p_mismatch: float) -> float:
    """R*(i): minimum over the four plans (trained / cross-skill for work 1 and, after a reopen, work 2)."""
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
    """Indices of tickets created in [metric_start_min, end_min) that breach under any policy."""
    first_day = int(start_min // MINUTES_PER_DAY) - 1
    last_day = int(end_min // MINUTES_PER_DAY) + 3  # tickets can still be worked in the drain window
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
