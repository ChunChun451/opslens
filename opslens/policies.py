"""Policies: who works on which ticket. One interface, `decide(state, now) -> list[Assignment]`.

Baselines (the status quo we must beat):
- **Baseline A — FIFO.** Each free agent takes the oldest waiting ticket from their own
  team's queue. Only when that queue has nothing they can serve do they help with their
  extra skills. Routing uses the category the customer picked (or the real one, once an
  agent has read the ticket after a transfer).
- **Baseline B — priority.** Same, but P1 before P2 before P3, oldest first inside a priority.

Both are fair, realistic floors: language is always respected, agents never take tickets
outside their skills on purpose, and longest-idle agents choose first.

**OpsLens** (bottom of this file): routes by the classifier's category, values each ticket by
how much serving it NOW cuts its breach risk (risk model), protects rare skills, and assigns
with a min-cost-flow optimiser (optimize.py). Switches turn each part off for the ablations.

Example: agent B03 (Team B, English) is free. Waiting: T1 refund P2 created 10:00,
T2 payment P1 created 10:05, T3 late_delivery P1 created 09:50 (Team A's queue).
Baseline A gives B03 T1 (oldest in Team B's queue). Baseline B gives B03 T2 (P1 first).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from opslens.classify import TEAM_OF
from opslens.features import WAITING_COLUMNS, QueueSnapshot, capability_table, features_for_snapshot
from opslens.optimize import Candidate, SolveStats, solve, ticket_value, top_k
from opslens.risk import risk_if_assigned_now
from opslens.simulate import AgentView, Assignment, SimState, TicketView, World

PRIORITY_RANK = {"P1": 0, "P2": 1, "P3": 2}
SCARCITY_FLOOR = 0.01  # a rare-skill agent still takes common work rather than sit idle


def routing_category(ticket: TicketView) -> str:
    """What the status-quo floor believes the ticket is about."""
    return ticket.known_category or ticket.selected_category


class TeamQueuePolicy:
    """Shared logic of both baselines; they differ only in how a queue is sorted."""

    def __init__(self, name: str, sort_key: Callable[[TicketView], tuple]) -> None:
        self.name = name
        self._sort_key = sort_key

    def decide(self, state: SimState, now: float) -> list[Assignment]:
        free = state.free_agents(now)
        if not free:
            return []
        queue = sorted(state.waiting_tickets(), key=self._sort_key)
        taken: set[int] = set()
        assignments: list[Assignment] = []
        for agent in free:
            for _ in range(agent.free_slots):
                ticket = self._pick(agent, queue, taken)
                if ticket is None:
                    break
                taken.add(ticket.idx)
                category = routing_category(ticket)
                own = category in agent.team_skills
                assignments.append(
                    Assignment(
                        ticket_idx=ticket.idx,
                        agent_id=agent.agent_id,
                        believed_category=category,
                        reason=f"{self.name}: {'own queue' if own else 'helping with extra skill'}",
                    )
                )
        return assignments

    @staticmethod
    def _pick(agent: AgentView, queue: list[TicketView], taken: set[int]) -> TicketView | None:
        """First ticket in the agent's own team queue; else first one in their extra skills."""
        extra_choice: TicketView | None = None
        for ticket in queue:
            if ticket.idx in taken or ticket.language not in agent.languages:
                continue
            category = routing_category(ticket)
            if category in agent.team_skills:
                return ticket
            if extra_choice is None and category in agent.skills:
                extra_choice = ticket
        return extra_choice


def baseline_a() -> TeamQueuePolicy:
    """FIFO: oldest ticket first."""
    return TeamQueuePolicy("Baseline A (FIFO)", sort_key=lambda t: (t.created_min, t.idx))


def baseline_b() -> TeamQueuePolicy:
    """Priority first (P1, P2, P3), then oldest."""
    return TeamQueuePolicy(
        "Baseline B (priority)", sort_key=lambda t: (PRIORITY_RANK[t.priority], t.created_min, t.idx)
    )


# ---- OpsLens ---------------------------------------------------------------------------------

@dataclass
class OpsLensSettings:
    """Switches for the ablations (CLAUDE.md section 7.6). All True = full OpsLens."""

    use_risk: bool = True        # rescue value from the risk model (else a flat value)
    use_optimizer: bool = True   # min-cost flow (else: each agent greedily takes its best ticket)
    use_classifier: bool = True  # route by predicted category (else by the customer's menu choice)
    use_scarcity: bool = True    # protect rare skill pairs
    label: str = "OpsLens"


class OpsLensPolicy:
    """Risk-aware, skill-aware assignment with an optimiser. See opslens/optimize.py."""

    def __init__(self, world: World, predicted: dict[str, str], risk_model, weights: dict,
                 settings: OpsLensSettings | None = None, log_window: tuple[float, float] | None = None) -> None:
        self.settings = settings or OpsLensSettings()
        self.log_window = log_window  # record decisions made in this time window (for the dashboard)
        self.decision_log: list[dict] = []
        self.name = self.settings.label
        self.world = world
        self.w = weights
        self.risk_model = risk_model
        # Category known at arrival: the classifier's prediction (or the menu choice).
        self.pred = [predicted.get(tid, sel) for tid, sel in zip(world.ticket_ids, world.selected_category)]
        self.team_names = sorted(set(TEAM_OF.values()))
        code = {t: k for k, t in enumerate(self.team_names)}
        self.team_code = np.array([code[TEAM_OF.get(c, "A")] for c in self.pred])
        self.rescue: dict[int, float] = {}
        self.risk_wait: dict[int, float] = {}  # P(breach) if the ticket keeps waiting (for the reason text)
        self.pressure: dict[tuple[str, str], float] = {}
        self.last_refresh = -1e9
        self.stats = SolveStats()
        counts: dict[tuple[str, str], int] = {}
        for a in world.agents:
            for lang in a.languages:
                for skill in a.skills:
                    counts[(lang, skill)] = counts.get((lang, skill), 0) + 1
        # A (language, skill) pair is rare if at most 5 agents on the whole floor have it.
        self.rare = {pair for pair, n in counts.items() if n <= 5 and pair[0] != "en"}

    def category(self, t: TicketView) -> str:
        if t.known_category:
            return t.known_category
        return self.pred[t.idx] if self.settings.use_classifier else t.selected_category

    # -- risk ----------------------------------------------------------------------------------

    def refresh(self, state: SimState, now: float) -> None:
        """Score every waiting ticket: rescue = P(breach if it waits) − P(breach if served now)."""
        waiting = state.waiting_tickets()
        self.last_refresh = now
        if not waiting:
            return
        on_shift = [{"agent_id": a.agent_id, "team": a.team, "languages": set(a.languages), "skills": set(a.skills)}
                    for k, a in enumerate(self.world.agents) if state.shift_end(k, now) is not None]
        on_shift_df = pd.DataFrame(on_shift, columns=["agent_id", "team", "languages", "skills"])
        waiting_df = pd.DataFrame([
            {"ticket_id": t.ticket_id, "created_min": t.created_min, "category_pred": self.category(t),
             "priority": t.priority, "channel": t.channel, "language": t.language, "tier": t.tier,
             "order_value_inr": t.order_value, "sla_min": t.sla_deadline_min - t.created_min,
             "transfers_so_far": t.transfers, "idx": t.idx}
            for t in waiting])
        in_work = list(state.in_work)
        busy = np.bincount(self.team_code[in_work], minlength=len(self.team_names)) if in_work else np.zeros(4, int)
        lo = np.searchsorted(self.world.created_min, now - 60.0)
        hi = np.searchsorted(self.world.created_min, now)
        arrived = np.bincount(self.team_code[lo:hi], minlength=len(self.team_names))
        snap = QueueSnapshot(
            t=now, waiting=waiting_df[WAITING_COLUMNS],
            in_progress_by_team={t: int(busy[k]) for k, t in enumerate(self.team_names)},
            arrivals_last_hour_by_team={t: int(arrived[k]) for k, t in enumerate(self.team_names)},
            on_shift=on_shift_df, first_weekday=self.world.first_weekday,
        )
        feats = features_for_snapshot(snap, TEAM_OF)
        live = (feats["time_left_min"] > 0).to_numpy()
        rescue = np.zeros(len(feats))
        p_wait_all = np.ones(len(feats))  # past their SLA: already breached
        if live.any():
            p_wait = self.risk_model.predict(feats[live])
            p_now = risk_if_assigned_now(self.risk_model, feats[live])
            rescue[live] = np.clip(p_wait - p_now, 0.0, 1.0)
            p_wait_all[live] = p_wait
        # Past-SLA tickets get rescue 0: aging and the starvation guard still serve them.
        self.rescue = dict(zip(waiting_df["idx"], rescue))
        self.risk_wait = dict(zip(waiting_df["idx"], p_wait_all))
        capable = capability_table(on_shift_df)
        need: dict[tuple[str, str], int] = {}
        for t in waiting:
            pair = (t.language, self.category(t))
            if pair in self.rare:
                need[pair] = need.get(pair, 0) + 1
        # Rare work waiting per capable agent on shift: how precious each rare skill is right now.
        self.pressure = {pair: n / max(1, capable.get(pair, 0)) for pair, n in need.items()}

    # -- decision ------------------------------------------------------------------------------

    def decide(self, state: SimState, now: float) -> list[Assignment]:
        free = state.free_agents(now)
        if not free:
            return []
        waiting = state.waiting_tickets()
        if self.settings.use_risk:
            # Re-score every few minutes; a ticket that arrived since then gets a default
            # rescue value until the next scoring (a new ticket rarely needs rescue at once).
            if now - self.last_refresh >= self.w["risk_refresh_min"]:
                self.refresh(state, now)
        elif self.settings.use_scarcity and now - self.last_refresh >= self.w["risk_refresh_min"]:
            self.refresh_pressure_only(state, now, waiting)
        candidates = self.candidates(free, waiting, now)
        slots = {a.agent_id: a.free_slots for a in free}
        if self.settings.use_optimizer:
            chosen = solve(candidates, slots, self.w["time_budget_s"], self.stats)
        else:
            chosen = greedy_by_agent(candidates, free)
        if self.log_window and self.log_window[0] <= now < self.log_window[1]:
            for c in chosen:
                self.decision_log.append({"minute": now, "ticket_idx": c.ticket_idx, "agent_id": c.agent_id,
                                          "value": round(c.value, 3), "reason": c.reason})
        return [Assignment(c.ticket_idx, c.agent_id, c.believed_category, deliberate_cross_skill=c.cross_skill,
                           reason=c.reason) for c in chosen]

    def refresh_pressure_only(self, state: SimState, now: float, waiting: list[TicketView]) -> None:
        """Ablation 'without risk scores': keep the scarcity signal, skip the risk model."""
        self.last_refresh = now
        on_shift = [{"agent_id": a.agent_id, "team": a.team, "languages": set(a.languages), "skills": set(a.skills)}
                    for k, a in enumerate(self.world.agents) if state.shift_end(k, now) is not None]
        capable = capability_table(pd.DataFrame(on_shift, columns=["agent_id", "team", "languages", "skills"]))
        need: dict[tuple[str, str], int] = {}
        for t in waiting:
            pair = (t.language, self.category(t))
            if pair in self.rare:
                need[pair] = need.get(pair, 0) + 1
        self.pressure = {pair: n / max(1, capable.get(pair, 0)) for pair, n in need.items()}

    def candidates(self, free: list[AgentView], waiting: list[TicketView], now: float) -> list[Candidate]:
        """Every (agent, ticket) pair the agent can serve, with its value; top-k per agent."""
        out: list[Candidate] = []
        # Crisis mode: with a very long queue, serving long-lost tickets first would sink tickets
        # that can still be saved, so the fairness guard pauses until the queue is back to normal.
        guard_on = len(waiting) <= self.w.get("guard_queue_limit", float("inf"))
        for agent in free:
            rare_here = [p for p in self.rare if p[0] in agent.languages and p[1] in agent.skills]
            values: list[float] = []
            cands: list[Candidate] = []
            for t in waiting:
                if t.language not in agent.languages:
                    continue  # language is never negotiable
                cat = self.category(t)
                skilled = cat in agent.skills
                default = self.w["new_ticket_rescue"]
                rescue = self.rescue.get(t.idx, default) if self.settings.use_risk else default
                if not skilled and rescue < self.w["cross_skill_min_rescue"]:
                    continue  # cross-skill work (1.6x slower) only to save a ticket that is in real danger
                value = ticket_value(t.priority, t.tier, t.order_value, rescue, now - t.created_min, self.w,
                                     sla_min=t.sla_deadline_min - t.created_min, guard_on=guard_on)
                if not skilled:
                    value -= self.w["mismatch_penalty"]
                scarcity = 0.0
                if self.settings.use_scarcity and value > 0:
                    scarcity = sum(self.pressure.get(p, 0.0) for p in rare_here if p != (t.language, cat))
                    # Scarcity changes WHICH ticket a rare agent prefers; it must never make the agent
                    # idle, so the value stays above a small floor.
                    value = max(value - self.w["scarcity_weight"] * scarcity, SCARCITY_FLOOR)
                values.append(value)
                cands.append(Candidate(t.idx, agent.agent_id, value, not skilled, cat,
                                       assignment_reason(t, cat, rescue, self.risk_wait.get(t.idx),
                                                         now - t.created_min, skilled, scarcity)))
            for k in top_k(np.asarray(values), self.w["top_k_per_agent"]):
                out.append(cands[k])
        return out


def greedy_by_agent(candidates: list[Candidate], free: list[AgentView]) -> list[Candidate]:
    """Ablation 'without optimiser': the longest-idle agent takes its single best ticket, and so on."""
    by_agent: dict[str, list[Candidate]] = {}
    for c in candidates:
        by_agent.setdefault(c.agent_id, []).append(c)
    used: set[int] = set()
    chosen = []
    for agent in free:
        for _ in range(agent.free_slots):
            options = [c for c in by_agent.get(agent.agent_id, []) if c.ticket_idx not in used and c.value > 0]
            if not options:
                break
            best = max(options, key=lambda c: c.value)
            used.add(best.ticket_idx)
            chosen.append(best)
    return chosen


def assignment_reason(t: TicketView, cat: str, rescue: float, risk_wait: float | None, waited_min: float,
                      skilled: bool, scarcity: float) -> str:
    """One line a team lead can read."""
    lang = {"hi": "Hindi", "other": "regional language", "en": "English"}.get(t.language, t.language)
    parts = [f"{t.priority} {cat.replace('_', ' ')}, {lang}, waiting {waited_min:.0f} min"]
    if risk_wait is not None and risk_wait >= 1.0:
        parts.append("already past its SLA - served so no customer is left behind")
    elif risk_wait is not None and rescue >= 0.05:
        parts.append(f"breach risk {risk_wait:.2f} -> {risk_wait - rescue:.2f} if served now")
    else:
        parts.append("low risk - served in turn (fairness by waiting time)")
    if not skilled:
        parts.append("cross-skill job (1.6x slower) to rescue a ticket in danger")
    if scarcity > 0:
        parts.append("rare-skill agent, no rare work is more urgent")
    return "; ".join(parts)
