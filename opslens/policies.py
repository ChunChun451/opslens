from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from opslens.classify import TEAM_OF
from opslens.features import WAITING_COLUMNS, QueueSnapshot, capability_table, features_for_snapshot
from opslens.optimize import (Candidate, SolveStats, solve, ticket_value, top_k, urgency_impact,
                              with_runner_up)
from opslens.risk import risk_if_assigned_now
from opslens.floor import shift_intervals
from opslens.simulate import MINUTES_PER_DAY, AgentView, Assignment, SimState, TicketView, World

PRIORITY_RANK = {"P1": 0, "P2": 1, "P3": 2}
SCARCITY_FLOOR = 0.01


def routing_category(ticket: TicketView) -> str:
    return ticket.known_category or ticket.selected_category


class TeamQueuePolicy:
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
    return TeamQueuePolicy("Baseline A (FIFO)", sort_key=lambda t: (t.created_min, t.idx))


def baseline_b() -> TeamQueuePolicy:
    return TeamQueuePolicy(
        "Baseline B (priority)", sort_key=lambda t: (PRIORITY_RANK[t.priority], t.created_min, t.idx)
    )


class DeadlineQueuePolicy(TeamQueuePolicy):
    def __init__(self) -> None:
        super().__init__("Baseline C (SLA due)", sort_key=lambda t: (t.sla_deadline_min, t.idx))

    def decide(self, state: SimState, now: float) -> list[Assignment]:
        self._sort_key = lambda t: (t.sla_deadline_min <= now, t.sla_deadline_min, t.idx)
        return super().decide(state, now)


def baseline_c() -> DeadlineQueuePolicy:
    return DeadlineQueuePolicy()


class SkillsRoutingPolicy:
    def __init__(self, world: World, predicted: dict[str, str]) -> None:
        self.name = "Baseline D (industry standard)"
        self.pred = [predicted.get(tid) or sel for tid, sel in zip(world.ticket_ids, world.selected_category)]

    def category(self, t: TicketView) -> str:
        return t.known_category or self.pred[t.idx]

    def decide(self, state: SimState, now: float) -> list[Assignment]:
        free = state.free_agents(now)
        if not free:
            return []
        queue = sorted(state.waiting_tickets(),
                       key=lambda t: (PRIORITY_RANK[t.priority], t.sla_deadline_min, t.created_min, t.idx))
        taken: set[int] = set()
        out: list[Assignment] = []
        for agent in free:
            for _ in range(agent.free_slots):
                pick = next((t for t in queue if t.idx not in taken and t.language in agent.languages
                             and self.category(t) in agent.skills), None)
                if pick is None:
                    break
                taken.add(pick.idx)
                out.append(Assignment(pick.idx, agent.agent_id, self.category(pick),
                                      reason=f"{self.name}: skills-based, priority then SLA due"))
        return out


def baseline_d(world: World, predicted: dict[str, str]) -> SkillsRoutingPolicy:
    return SkillsRoutingPolicy(world, predicted)


def expected_handle_minutes(history: pd.DataFrame, first_weekday_date: str, last_day: int = 35) -> dict:
    start = pd.Timestamp(first_weekday_date)
    created = pd.to_datetime(history["created_at"])
    train = history[(created < start + pd.Timedelta(days=last_day)) & (history["reopens"] == 0)
                    & history["resolution_min"].notna()]
    out: dict = {}
    for (cat, channel), minutes in train.groupby(["final_category", "channel"])["handled_min"].mean().items():
        out[(cat, channel)] = float(minutes)
    for cat, minutes in train.groupby("final_category")["handled_min"].mean().items():
        out[cat] = float(minutes)
    return out


class RankedSkillsPolicy:
    name = "ranked skills routing"

    def __init__(self, world: World, predicted: dict[str, str], handle: dict) -> None:
        self.world = world
        self.pred = [predicted.get(tid) or sel for tid, sel in zip(world.ticket_ids, world.selected_category)]
        self.handle = handle

    def category(self, t: TicketView) -> str:
        return t.known_category or self.pred[t.idx]

    def expected_handle(self, t: TicketView) -> float:
        cat = self.category(t)
        return self.handle.get((cat, t.channel)) or self.handle.get(cat) or 8.0

    def rank(self, t: TicketView, now: float, state: SimState) -> tuple:
        raise NotImplementedError

    def decide(self, state: SimState, now: float) -> list[Assignment]:
        free = state.free_agents(now)
        if not free:
            return []
        queue = sorted(state.waiting_tickets(), key=lambda t: self.rank(t, now, state))
        taken: set[int] = set()
        out: list[Assignment] = []
        for agent in free:
            for _ in range(agent.free_slots):
                pick = next((t for t in queue if t.idx not in taken and t.language in agent.languages
                             and self.category(t) in agent.skills), None)
                if pick is None:
                    break
                taken.add(pick.idx)
                out.append(Assignment(pick.idx, agent.agent_id, self.category(pick), reason=self.name))
        return out


class LeastSlackPolicy(RankedSkillsPolicy):
    def __init__(self, world: World, predicted: dict[str, str], handle: dict, name: str = "Least slack first") -> None:
        super().__init__(world, predicted, handle)
        self.name = name

    def slack(self, t: TicketView, now: float, state: SimState) -> float:
        return t.sla_deadline_min - now - self.expected_handle(t)

    def rank(self, t: TicketView, now: float, state: SimState) -> tuple:
        s = self.slack(t, now, state)
        return (s < 0, s, t.idx)


class GeneralizedCMuPolicy(RankedSkillsPolicy):
    def __init__(self, world: World, predicted: dict[str, str], handle: dict, tau: float, beta: float,
                 name: str = "Generalized c-mu") -> None:
        super().__init__(world, predicted, handle)
        self.tau, self.beta, self.name = tau, beta, name

    def index(self, t: TicketView, now: float) -> float:
        sla = t.sla_deadline_min - t.created_min
        x = (now - t.created_min - sla) / (self.tau * sla)
        marginal_cost = sla ** (-self.beta) / (1.0 + math.exp(-x))
        return float(marginal_cost / self.expected_handle(t))

    def rank(self, t: TicketView, now: float, state: SimState) -> tuple:
        return (-self.index(t, now), t.idx)


class LeastSlackRescuePolicy(LeastSlackPolicy):
    def __init__(self, world: World, predicted: dict[str, str], handle: dict, threshold_min: float,
                 name: str = "Least slack + cross-skill rescue") -> None:
        super().__init__(world, predicted, handle, name=name)
        self.threshold_min = threshold_min

    def rescue_candidate(self, t: TicketView, now: float, state: SimState) -> bool:
        in_danger = self.slack(t, now, state) < self.threshold_min
        slow_slack = t.sla_deadline_min - now - self.world.mismatch_factor * self.expected_handle(t)
        return in_danger and slow_slack >= 0

    def decide(self, state: SimState, now: float) -> list[Assignment]:
        out = super().decide(state, now)
        taken = {a.ticket_idx for a in out}
        slots = {a.agent_id: a.free_slots for a in state.free_agents(now)}
        for a in out:
            slots[a.agent_id] -= 1
        left = [a for a in state.free_agents(now) if slots[a.agent_id] > 0]
        if not left:
            return out
        queue = sorted(state.waiting_tickets(), key=lambda t: self.rank(t, now, state))
        for t in queue:
            if t.idx in taken or not self.rescue_candidate(t, now, state):
                continue
            agent = next((a for a in left if slots[a.agent_id] > 0 and t.language in a.languages), None)
            if agent is None:
                continue
            slots[agent.agent_id] -= 1
            taken.add(t.idx)
            out.append(Assignment(t.idx, agent.agent_id, self.category(t), deliberate_cross_skill=True,
                                  reason=f"{self.name}: cross-skill rescue, slack {self.slack(t, now, state):.0f} min"))
        return out


class ClairvoyantSlackPolicy(LeastSlackPolicy):
    def __init__(self, world: World, name: str = "Clairvoyant least slack (not implementable)") -> None:
        super().__init__(world, {}, {}, name=name)

    def category(self, t: TicketView) -> str:
        return self.world.true_category[t.idx]

    def slack(self, t: TicketView, now: float, state: SimState) -> float:
        w = self.world
        attempt = min(state.tickets[t.idx].attempts, w.base_handle_min.shape[1] - 1)
        minutes = float(w.base_handle_min[t.idx, attempt])
        if t.reopens > 0:
            minutes *= w.reopen_handle_factor
        return t.sla_deadline_min - now - minutes


@dataclass
class OpsLensSettings:
    use_risk: bool = True
    use_optimizer: bool = True
    use_classifier: bool = True
    use_scarcity: bool = True
    label: str = "OpsLens"


class OpsLensPolicy:
    def __init__(self, world: World, predicted: dict[str, str], risk_model, weights: dict,
                 settings: OpsLensSettings | None = None, log_window: tuple[float, float] | None = None,
                 handle: dict | None = None) -> None:
        self.settings = settings or OpsLensSettings()
        self.handle = handle
        self.mean_handle = float(np.mean([v for k, v in handle.items() if isinstance(k, str)])) if handle else 0.0
        self.switch = None
        if handle and (weights.get("overload") or {}).get("switch_to") == "least_slack":
            self.switch = LeastSlackPolicy(world, predicted, handle)
        self.overload = False
        self._overload_checked = -1e9
        self.overload_minutes = 0.0
        self.log_window = log_window
        self.decision_log: list[dict] = []
        self.name = self.settings.label
        self.world = world
        self.w = weights
        self.risk_model = risk_model
        self.pred = [predicted.get(tid, sel) for tid, sel in zip(world.ticket_ids, world.selected_category)]
        self.team_names = sorted(set(TEAM_OF.values()))
        code = {t: k for k, t in enumerate(self.team_names)}
        self.team_code = np.array([code[TEAM_OF.get(c, "A")] for c in self.pred])
        self.rescue: dict[int, float] = {}
        self.risk_wait: dict[int, float] = {}
        self.pressure: dict[tuple[str, str], float] = {}
        self.only_cross: dict[int, bool] = {}
        self._schedule: dict[tuple[str, str], list[float]] = {}
        self._roster_checked = -1e9
        self.last_refresh = -1e9
        self.stats = SolveStats()
        counts: dict[tuple[str, str], int] = {}
        for a in world.agents:
            for lang in a.languages:
                for skill in a.skills:
                    counts[(lang, skill)] = counts.get((lang, skill), 0) + 1
        self.rare = {pair for pair, n in counts.items() if n <= 5 and pair[0] != "en"}

    def category(self, t: TicketView) -> str:
        if t.known_category:
            return t.known_category
        return self.pred[t.idx] if self.settings.use_classifier else t.selected_category


    def refresh(self, state: SimState, now: float) -> None:
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
        p_wait_all = np.ones(len(feats))
        if live.any():
            p_wait = self.risk_model.predict(feats[live])
            p_now = risk_if_assigned_now(self.risk_model, feats[live])
            rescue[live] = np.clip(p_wait - p_now, 0.0, 1.0)
            p_wait_all[live] = p_wait
        self.rescue = dict(zip(waiting_df["idx"], rescue))
        self.risk_wait = dict(zip(waiting_df["idx"], p_wait_all))
        capable = capability_table(on_shift_df)
        need: dict[tuple[str, str], int] = {}
        for t in waiting:
            pair = (t.language, self.category(t))
            if pair in self.rare:
                need[pair] = need.get(pair, 0) + 1
        self.pressure = {pair: n / max(1, capable.get(pair, 0)) for pair, n in need.items()}

    def only_cross_skill_can_save(self, t: TicketView, on_shift: list[dict], now: float) -> bool:
        lang, cat = t.language, self.category(t)
        if any(lang in a["languages"] and cat in a["skills"] for a in on_shift):
            return False
        starts = self._schedule.get((lang, cat))
        if starts is None:
            last_day = int(self.world.created_min.max() // MINUTES_PER_DAY) + 3
            starts = sorted(iv[0] for k, a in enumerate(self.world.agents) if lang in a.languages and cat in a.skills
                            for iv in shift_intervals(self.world, k, 0, last_day, with_absences=False))
            self._schedule[(lang, cat)] = starts
        k = bisect.bisect_right(starts, now)
        next_start = starts[k] if k < len(starts) else math.inf
        return next_start > t.sla_deadline_min - self.w["roster_margin_min"]


    def decide(self, state: SimState, now: float) -> list[Assignment]:
        free = state.free_agents(now)
        if not free:
            return []
        waiting = state.waiting_tickets()
        if self.settings.use_risk:
            if now - self.last_refresh >= self.w["risk_refresh_min"]:
                self.refresh(state, now)
        elif self.settings.use_scarcity and now - self.last_refresh >= self.w["risk_refresh_min"]:
            self.refresh_pressure_only(state, now, waiting)
        if self.w.get("roster_margin_min") is not None and now - self._roster_checked >= self.w["risk_refresh_min"]:
            self._roster_checked = now
            on_shift = [{"languages": set(a.languages), "skills": set(a.skills)}
                        for k, a in enumerate(self.world.agents) if state.shift_end(k, now) is not None]
            self.only_cross = {t.idx: self.only_cross_skill_can_save(t, on_shift, now) for t in waiting}
        if self.w.get("overload") and self.handle and now - self._overload_checked >= self.w["risk_refresh_min"]:
            if self.overload:
                self.overload_minutes += now - self._overload_checked
            self._overload_checked = now
            self.overload = self.projected_overload(state, now, waiting)
        if self.overload and self.switch is not None:
            return self.switch.decide(state, now)
        candidates = self.candidates(free, waiting, now)
        slots = {a.agent_id: a.free_slots for a in free}
        if self.settings.use_optimizer:
            chosen = solve(candidates, slots, self.w["time_budget_s"], self.stats)
        else:
            chosen = greedy_by_agent(candidates, free)
        chosen = with_runner_up(chosen, candidates, lambda i: self.world.ticket_ids[i])
        if self.log_window and self.log_window[0] <= now < self.log_window[1]:
            for c in chosen:
                self.decision_log.append({"minute": now, "ticket_idx": c.ticket_idx, "agent_id": c.agent_id,
                                          "value": round(c.value, 3), "reason": c.reason})
        return [Assignment(c.ticket_idx, c.agent_id, c.believed_category, deliberate_cross_skill=c.cross_skill,
                           reason=c.reason) for c in chosen]

    def expected_handle(self, t: TicketView) -> float:
        cat = self.category(t)
        return self.handle.get((cat, t.channel), self.handle.get(cat, self.mean_handle))

    def projected_overload(self, state: SimState, now: float, waiting: list[TicketView]) -> bool:
        cfg = self.w["overload"]
        horizon = float(cfg["horizon_min"])
        work = sum(self.expected_handle(t) for t in waiting)
        created = self.world.created_min
        arrived_last_hour = int(np.searchsorted(created, now, side="right") - np.searchsorted(created, now - 60.0))
        work += arrived_last_hour * horizon / 60.0 * self.mean_handle
        capacity = 0.0
        for k, a in enumerate(self.world.agents):
            end = state.shift_end(k, now)
            if end is not None:
                capacity += min(horizon, end - now) * a.max_concurrent
        return work > float(cfg["threshold"]) * capacity

    def refresh_pressure_only(self, state: SimState, now: float, waiting: list[TicketView]) -> None:
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
        out: list[Candidate] = []
        guard_on = len(waiting) <= self.w.get("guard_queue_limit", float("inf")) and not self.overload
        value_w = self.w
        if self.overload and self.w["overload"].get("flat_urgency"):
            value_w = {**self.w, "urgency_weight": {p: 1.0 for p in self.w["urgency_weight"]}}
        for agent in free:
            rare_here = [p for p in self.rare if p[0] in agent.languages and p[1] in agent.skills]
            values: list[float] = []
            cands: list[Candidate] = []
            for t in waiting:
                if t.language not in agent.languages:
                    continue
                cat = self.category(t)
                skilled = cat in agent.skills
                default = self.w["new_ticket_rescue"]
                rescue = self.rescue.get(t.idx, default) if self.settings.use_risk else default
                if not skilled and rescue < self.w["cross_skill_min_rescue"]:
                    continue
                value = ticket_value(t.priority, t.tier, t.order_value, rescue, now - t.created_min, value_w,
                                     sla_min=t.sla_deadline_min - t.created_min, guard_on=guard_on)
                if self.overload:
                    value *= self.mean_handle / max(1.0, self.expected_handle(t))
                if not skilled and self.only_cross.get(t.idx, False):
                    pass
                elif not skilled and self.w.get("mismatch_cost") is not None:
                    value -= self.w["mismatch_cost"] * urgency_impact(t.priority, t.tier, t.order_value, self.w)
                elif not skilled:
                    value -= self.w["mismatch_penalty"]
                scarcity = 0.0
                if self.settings.use_scarcity and value > 0:
                    scarcity = sum(self.pressure.get(p, 0.0) for p in rare_here if p != (t.language, cat))
                    value = max(value - self.w["scarcity_weight"] * scarcity, SCARCITY_FLOOR)
                values.append(value)
                cands.append(Candidate(t.idx, agent.agent_id, value, not skilled, cat,
                                       assignment_reason(t, cat, rescue, self.risk_wait.get(t.idx),
                                                         now - t.created_min, skilled, scarcity)))
            for k in top_k(np.asarray(values), self.w["top_k_per_agent"]):
                out.append(cands[k])
        return out


def greedy_by_agent(candidates: list[Candidate], free: list[AgentView]) -> list[Candidate]:
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
