from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, replace
from typing import Callable

import numpy as np
from ortools.graph.python import min_cost_flow

SCALE = 1000


@dataclass
class Candidate:
    ticket_idx: int
    agent_id: str
    value: float
    cross_skill: bool
    believed_category: str
    reason: str


@dataclass
class SolveStats:
    solves: int = 0
    fallbacks: int = 0
    solve_ms: list[float] = field(default_factory=list)


def urgency_impact(priority: str, tier: str, order_value: float, w: dict) -> float:
    impact = 1.0 + (w["gold_weight"] - 1.0 if tier == "gold" else 0.0)
    impact += w["order_value_weight"] * math.log1p(order_value / 350.0)
    return w["urgency_weight"][priority] * impact


def ticket_value(priority: str, tier: str, order_value: float, rescue: float, waited_min: float,
                 w: dict, sla_min: float | None = None, guard_on: bool = True) -> float:
    if w.get("aging_in_sla_units") and sla_min:
        aging = w["aging_per_sla"] * min(waited_min / sla_min, w["aging_cap"])
        if waited_min > sla_min and w.get("aging_lost") is not None:
            aging = w["aging_lost"]
        guard = waited_min - sla_min >= w["max_late_min"]
    else:
        aging = w["aging_per_hour"] * waited_min / 60.0
        guard = waited_min >= w["max_wait_min"]
    value = urgency_impact(priority, tier, order_value, w) * (max(rescue, w["rescue_floor"]) + aging)
    if guard and guard_on:
        value += w["starvation_bonus"]
    return value


def solve(candidates: list[Candidate], slots: dict[str, int], time_budget_s: float,
          stats: SolveStats | None = None) -> list[Candidate]:
    good = [c for c in candidates if c.value > 0]
    if not good:
        return []
    started = time.perf_counter()
    agents = sorted({c.agent_id for c in good})
    tickets = sorted({c.ticket_idx for c in good})
    a_node = {a: 1 + i for i, a in enumerate(agents)}
    t_node = {t: 1 + len(agents) + i for i, t in enumerate(tickets)}
    source, sink = 0, 1 + len(agents) + len(tickets)
    flow = min_cost_flow.SimpleMinCostFlow()
    total = sum(slots[a] for a in agents)
    for a in agents:
        flow.add_arc_with_capacity_and_unit_cost(source, a_node[a], slots[a], 0)
        flow.add_arc_with_capacity_and_unit_cost(a_node[a], sink, slots[a], 0)
    arc_of = {}
    for c in good:
        arc = flow.add_arc_with_capacity_and_unit_cost(a_node[c.agent_id], t_node[c.ticket_idx], 1,
                                                       -int(round(c.value * SCALE)))
        arc_of[arc] = c
    for t in tickets:
        flow.add_arc_with_capacity_and_unit_cost(t_node[t], sink, 1, 0)
    flow.set_node_supply(source, total)
    flow.set_node_supply(sink, -total)
    status = flow.solve()
    elapsed = time.perf_counter() - started
    if stats is not None:
        stats.solves += 1
        stats.solve_ms.append(1000 * elapsed)
    if status != flow.OPTIMAL or elapsed > time_budget_s:
        if stats is not None:
            stats.fallbacks += 1
        return greedy(good, slots)
    return [c for arc, c in arc_of.items() if flow.flow(arc) > 0]


def greedy(candidates: list[Candidate], slots: dict[str, int]) -> list[Candidate]:
    left = dict(slots)
    used: set[int] = set()
    chosen = []
    for c in sorted(candidates, key=lambda c: -c.value):
        if c.value <= 0 or c.ticket_idx in used or left.get(c.agent_id, 0) <= 0:
            continue
        chosen.append(c)
        used.add(c.ticket_idx)
        left[c.agent_id] -= 1
    return chosen


def with_runner_up(chosen: list[Candidate], candidates: list[Candidate],
                   ticket_name: Callable[[int], str] = str) -> list[Candidate]:
    if not chosen:
        return chosen
    by_ticket: dict[int, list[Candidate]] = {}
    for c in candidates:
        by_ticket.setdefault(c.ticket_idx, []).append(c)
    took = {c.agent_id: c.ticket_idx for c in chosen}
    out = []
    for c in chosen:
        others = [o for o in by_ticket.get(c.ticket_idx, []) if o.agent_id != c.agent_id]
        if not others:
            note = "no other free agent could take it now"
        else:
            best = max(others, key=lambda o: o.value)
            gap = c.value - best.value
            if gap >= 0:
                note = f"runner-up {best.agent_id}, value {gap:.2f} lower"
            elif best.agent_id in took:
                note = f"{best.agent_id} valued it {-gap:.2f} higher but took {ticket_name(took[best.agent_id])}"
            else:
                note = f"{best.agent_id} valued it {-gap:.2f} higher but the plan as a whole is better this way"
        out.append(replace(c, reason=f"{c.reason}; {note}"))
    return out


def top_k(values: np.ndarray, k: int) -> np.ndarray:
    if len(values) <= k:
        return np.arange(len(values))
    return np.argpartition(-values, k)[:k]
