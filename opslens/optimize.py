"""The optimiser: give free agents the tickets where working on them NOW does the most good.

What it does: at each decision moment, builds a table "value of agent a taking ticket i" and
solves it as a min-cost flow (Google OR-Tools), so the whole set of choices is best together,
not just each agent's first pick.

Value of agent a taking ticket i:
    urgency[priority] × impact × (rescue_i + aging_i)  −  mismatch_penalty  −  scarcity_cost
- rescue_i  = P(breach if it keeps waiting) − P(breach if served now), from the risk model.
  Already-lost tickets and tickets with lots of slack have little rescue value; tickets near
  their deadline that can still make it have the most.
- impact    = 1 (+0.5 for gold) + 0.1 × log(1 + order value ÷ 350).
- aging     = (policy v3, the shipped one) 3.0 per SLA-length waited, capped at 1 SLA; once a
  ticket is past its SLA it drops to a small fixed value (0.2) — it can no longer be saved, so
  it stops outranking tickets that can. A starvation guard gives a huge bonus to a ticket
  480 min past its SLA, except while more than 150 tickets wait (crisis mode). So late
  customers ARE deprioritised for up to 8 h; the lateness KPIs in impact.py measure the cost.
- mismatch  = cost of asking an agent to handle a category they are not trained for (1.6× slower,
  more reopens). Only allowed when the agent speaks the customer's language.
- scarcity  = cost of spending a rare skill pair (e.g. Hindi + refunds) on a ticket that many
  others could take, in proportion to how much rare work is waiting per capable agent.

Why min-cost flow: it is the exact solution of "assign up to N tickets to agents with given
slots, maximising total value". OR-Tools solves our sizes (≤ 40 slots × ≤ 30 tickets per agent)
in about a millisecond. If it ever exceeds the time budget, we fall back to a greedy rule and log it.

Example (Saturday 20:31): free agents Kavita (Team B, Hindi) and Rahul (Team B, English).
Waiting: T1 Hindi refund, rescue 0.55, P2; T2 English refund, rescue 0.40, P2.
Greedy-by-agent might give Kavita T2 (it is older). Flow gives Kavita T1 and Rahul T2:
total value 1.5×0.55 + 1.5×0.40 = 1.43 instead of 0.60 (T1 cannot go to Rahul).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np
from ortools.graph.python import min_cost_flow

SCALE = 1000  # OR-Tools needs integer costs: value 1.234 → 1234


@dataclass
class Candidate:
    """One possible (ticket, agent) pair with its value and the parts that explain it."""

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


def ticket_value(priority: str, tier: str, order_value: float, rescue: float, waited_min: float,
                 w: dict, sla_min: float | None = None, guard_on: bool = True) -> float:
    """Value of serving this ticket now (before agent-specific costs).

    Two ways to value time already waited (config `aging_in_sla_units`):
    - v1 (False): +aging_per_hour per hour waited; guard after max_wait_min of waiting.
    - v2 (True): +aging_per_sla per SLA-length waited, capped at aging_cap — a P1 (60-min SLA)
      ages 24× faster than a P3 (24 h), and a ticket already past its SLA stops gaining, so lost
      tickets cannot crowd out tickets that can still be saved. The guard starts when a ticket
      is max_late_min past its SLA. v1 failed the +25% volume stress test (see PROGRESS.md, M8).
    """
    impact = 1.0 + (w["gold_weight"] - 1.0 if tier == "gold" else 0.0)
    impact += w["order_value_weight"] * math.log1p(order_value / 350.0)
    if w.get("aging_in_sla_units") and sla_min:
        aging = w["aging_per_sla"] * min(waited_min / sla_min, w["aging_cap"])
        if waited_min > sla_min and w.get("aging_lost") is not None:
            # v3: a ticket past its SLA cannot be saved any more, so it drops to a small value
            # until the guard serves it — it no longer outranks tickets that can still make it.
            aging = w["aging_lost"]
        guard = waited_min - sla_min >= w["max_late_min"]
    else:
        aging = w["aging_per_hour"] * waited_min / 60.0
        guard = waited_min >= w["max_wait_min"]
    value = w["urgency_weight"][priority] * impact * (max(rescue, w["rescue_floor"]) + aging)
    if guard and guard_on:
        value += w["starvation_bonus"]  # the guard: never leave a customer behind
    return value


def solve(candidates: list[Candidate], slots: dict[str, int], time_budget_s: float,
          stats: SolveStats | None = None) -> list[Candidate]:
    """Pick the best set of pairs: each ticket at most once, each agent at most `slots` times."""
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
        flow.add_arc_with_capacity_and_unit_cost(a_node[a], sink, slots[a], 0)  # "stay free": value 0
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
    """Fallback: best pair first, skipping used tickets and full agents."""
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


def top_k(values: np.ndarray, k: int) -> np.ndarray:
    """Indices of the k largest values (all if fewer)."""
    if len(values) <= k:
        return np.arange(len(values))
    return np.argpartition(-values, k)[:k]
