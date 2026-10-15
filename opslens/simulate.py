"""Discrete-event simulator of a support floor: the "digital twin" we test every policy in.

What it does: given the tickets, the agents and one seed's luck draws (a `World`), it runs a
policy (who works on which ticket) through time and records when each ticket was picked
up, transferred, reopened and resolved.

How it works:
- Events sit in a heap ordered by time: FINISH (an agent ends a piece of work), REOPEN (a
  customer comes back), ARRIVAL (a new ticket), DECIDE (every `decide_every_min` minutes the
  policy assigns waiting tickets to free agents). The clock jumps from event to event.
- At equal times FINISH comes first, then REOPEN, ARRIVAL, DECIDE, so an agent freed at
  20:00 and a ticket created at 20:00 are both visible to the 20:00 decision.
- Policies only see a `TicketView` (what a real helpdesk shows: created time, channel,
  priority, language, the category the customer picked, ...). They never see the true
  category or the handle-time draws, so they cannot cheat.
- An agent who opens a ticket outside their skills, believing it was theirs, spends
  `transfer_discovery_min` and sends it back to the queue (a transfer). A policy may instead
  assign a ticket deliberately to an agent without the skill: then it is handled, 1.6x slower.

Why common random numbers (CRN): all luck (handle-time draws, reopen draws, absences) is
drawn once per seed into arrays indexed by ticket and attempt, before the run. Whatever a
policy does, ticket 812's second attempt always uses the same draw. So two policies differ
only because of their decisions, not because one got luckier.

Example (tests/test_simulate.py, hand-computed):
    2 agents, 3 tickets arriving at minute 0 with handle times 10, 10 and 5 minutes,
    decisions every minute, FIFO. Agents take tickets 1 and 2 at 0; ticket 3 starts at 10
    and is resolved at 15. Resolution times: 10, 10, 15.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd

FINISH, REOPEN, ARRIVAL, DECIDE = 0, 1, 2, 3
MINUTES_PER_DAY = 1440
SNAPSHOT_EVERY_MIN = 15


# ---- Static inputs ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Agent:
    """One agent. `skills` = team skills + extra skills."""

    agent_id: str
    name: str
    team: str
    team_skills: frozenset[str]
    skills: frozenset[str]
    languages: frozenset[str]
    shift_start_min: int  # minute of the day the shift starts (e.g. 22:00 → 1320)
    shift_minutes: int
    days_off: frozenset[int]  # 0 = Monday
    max_concurrent: int = 1
    # Week-specific schedule changes from a staffing plan (budget-neutral):
    # ((first_day, last_day, shift_start_min, days_off), ...) with days counted from 1.
    overrides: tuple = ()

    def schedule_on(self, day_index: int) -> tuple[int, frozenset[int]]:
        """(shift start minute, days off) for calendar day `day_index` (0 = day 1)."""
        for first, last, start_min, off in self.overrides:
            if first - 1 <= day_index <= last - 1:
                return start_min, off
        return self.shift_start_min, self.days_off


@dataclass
class World:
    """Everything fixed for one run: tickets, agents and this seed's luck draws.

    Ticket arrays are indexed by ticket number 0..N-1, sorted by creation time.
    """

    ticket_ids: list[str]
    created_min: np.ndarray  # minutes since day 1, 00:00
    true_category: list[str]
    selected_category: list[str]
    channel: list[str]
    priority: list[str]
    language: list[str]
    tier: list[str]
    order_value: np.ndarray
    sla_min: np.ndarray
    base_handle_min: np.ndarray  # shape (N, 3): minutes for attempt 1, 2, 3 (before mismatch factor)
    reopen_u: np.ndarray  # uniform(0, 1) per ticket; reopen if below the reopen probability
    reopen_delay_min: np.ndarray
    agents: list[Agent]
    absent: np.ndarray  # shape (n_agents, n_days) of bools
    first_weekday: int = 0  # weekday of day 1 (0 = Monday)
    mismatch_factor: float = 1.6
    reopen_prob_matched: float = 0.04
    reopen_prob_mismatch: float = 0.15
    reopen_handle_factor: float = 0.6
    transfer_discovery_min: float = 4.0

    @property
    def n_tickets(self) -> int:
        return len(self.ticket_ids)


# ---- What policies see -----------------------------------------------------------------------

@dataclass(frozen=True)
class TicketView:
    """The fields a real helpdesk would show for a waiting ticket. No hidden truth."""

    idx: int
    ticket_id: str
    created_min: float
    queue_since_min: float
    channel: str
    priority: str
    language: str
    tier: str
    order_value: float
    selected_category: str
    known_category: str | None  # set after an agent has read the ticket (transfer or reopen)
    sla_deadline_min: float
    transfers: int
    reopens: int


@dataclass(frozen=True)
class AgentView:
    agent_id: str
    team: str
    team_skills: frozenset[str]
    skills: frozenset[str]
    languages: frozenset[str]
    free_slots: int
    idle_since_min: float
    shift_end_min: float


@dataclass(frozen=True)
class Assignment:
    """A policy's decision: give ticket `ticket_idx` to agent `agent_id`."""

    ticket_idx: int
    agent_id: str
    believed_category: str  # the category the policy thinks the ticket is
    deliberate_cross_skill: bool = False  # True = "handle it even though it is not your skill"
    reason: str = ""


class Policy(Protocol):
    name: str

    def decide(self, state: "SimState", now: float) -> list[Assignment]: ...


# ---- Mutable state during a run --------------------------------------------------------------

@dataclass
class TicketState:
    status: str = "future"  # future | waiting | in_work | resolved
    queue_since_min: float = 0.0
    first_pickup_min: float = math.nan
    resolved_min: float = math.nan
    attempts: int = 0
    transfers: int = 0
    reopens: int = 0
    known_category: str | None = None
    handled_min: float = 0.0
    mismatch_used: bool = False
    last_agent: str = ""


@dataclass
class AgentState:
    busy: int = 0
    idle_since_min: float = 0.0
    busy_minutes: float = 0.0


@dataclass
class SimState:
    """Read-only window the policy gets each decision."""

    world: World
    tickets: list[TicketState]
    agent_states: dict[str, AgentState]
    # Waiting tickets and their view. The view is built once when the ticket (re)enters the
    # queue — building it at every decision was 70% of the run time.
    waiting: dict[int, TicketView] = field(default_factory=dict)
    # Per agent: (valid_until, shift_end or None). Shift status only changes at shift
    # boundaries, so we remember it until the next boundary. (Simulation time never goes back.)
    _shift_cache: dict[int, tuple[float, float | None]] = field(default_factory=dict)
    in_work: set[int] = field(default_factory=set)  # tickets an agent is working on right now

    def add_waiting(self, i: int) -> None:
        self.waiting[i] = self._view(i)

    def waiting_tickets(self) -> list[TicketView]:
        """Waiting tickets, oldest first."""
        return sorted(self.waiting.values(), key=lambda v: v.created_min)

    def _view(self, i: int) -> TicketView:
        w, t = self.world, self.tickets[i]
        return TicketView(
            idx=i,
            ticket_id=w.ticket_ids[i],
            created_min=float(w.created_min[i]),
            queue_since_min=t.queue_since_min,
            channel=w.channel[i],
            priority=w.priority[i],
            language=w.language[i],
            tier=w.tier[i],
            order_value=float(w.order_value[i]),
            selected_category=w.selected_category[i],
            known_category=t.known_category,
            sla_deadline_min=float(w.created_min[i] + w.sla_min[i]),
            transfers=t.transfers,
            reopens=t.reopens,
        )

    def shift_end(self, agent_idx: int, now: float) -> float | None:
        """Cached version of `shift_end_if_on`."""
        cached = self._shift_cache.get(agent_idx)
        if cached is not None and now < cached[0]:
            return cached[1]
        end = shift_end_if_on(self.world, agent_idx, now)
        if end is not None:
            valid_until = end
        else:
            # Off now: nothing can change before the next possible shift start.
            agent = self.world.agents[agent_idx]
            today = int(now // MINUTES_PER_DAY)
            starts = [d * MINUTES_PER_DAY + agent.schedule_on(d)[0] for d in (today, today + 1)]
            starts += [d * MINUTES_PER_DAY for d in (today + 1, today + 2)]  # midnight: a weekly override may begin
            valid_until = min(s for s in starts if s > now)
        self._shift_cache[agent_idx] = (float(valid_until), end)
        return end

    def any_free_agent(self, now: float) -> bool:
        """Cheap check used by the simulator to skip pointless decisions."""
        for agent_idx, agent in enumerate(self.world.agents):
            if self.agent_states[agent.agent_id].busy < agent.max_concurrent:
                if self.shift_end(agent_idx, now) is not None:
                    return True
        return False

    def free_agents(self, now: float) -> list[AgentView]:
        """Agents on shift, present today, with at least one free slot. Longest-idle first."""
        free: list[AgentView] = []
        for agent_idx, agent in enumerate(self.world.agents):
            shift_end = self.shift_end(agent_idx, now)
            if shift_end is None:
                continue
            st = self.agent_states[agent.agent_id]
            slots = agent.max_concurrent - st.busy
            if slots > 0:
                free.append(
                    AgentView(agent.agent_id, agent.team, agent.team_skills, agent.skills,
                              agent.languages, slots, st.idle_since_min, shift_end)
                )
        free.sort(key=lambda a: (a.idle_since_min, a.agent_id))
        return free


def shift_end_if_on(world: World, agent_idx: int, now: float) -> float | None:
    """If the agent is working at `now`, return when their current shift ends; else None.

    A shift that starts at 22:00 on day d runs into day d+1, so we check the shift that
    started today and the one that started yesterday.
    """
    agent = world.agents[agent_idx]
    today = int(now // MINUTES_PER_DAY)
    for day in (today, today - 1):
        if day < 0:
            continue
        start_min, days_off = agent.schedule_on(day)
        weekday = (world.first_weekday + day) % 7
        if weekday in days_off:
            continue
        if day < world.absent.shape[1] and world.absent[agent_idx, day]:
            continue
        start = day * MINUTES_PER_DAY + start_min
        end = start + agent.shift_minutes
        if start <= now < end:
            return float(end)
    return None


# ---- Results ---------------------------------------------------------------------------------

@dataclass
class SimResult:
    policy: str
    seed_label: str
    tickets: pd.DataFrame  # one row per ticket created inside the metric window
    snapshots: pd.DataFrame  # queue length and breaches every 15 min
    agent_busy_minutes: dict[str, float]
    agent_available_minutes: dict[str, float]
    decisions: int


# ---- The simulation loop ---------------------------------------------------------------------

def simulate(
    world: World,
    policy: Policy,
    start_min: float,
    end_min: float,
    metric_start_min: float | None = None,
    decide_every_min: float = 2.0,  # periodic tick (shift starts); events trigger decisions at once
    drain_min: float = 2 * MINUTES_PER_DAY,
    seed_label: str = "",
) -> SimResult:
    """Run `policy` on tickets created in [start_min, end_min); report those created after
    `metric_start_min` (earlier ones are warm-up). After `end_min` no new tickets arrive and
    the floor keeps working for up to `drain_min` so late tickets can finish."""
    metric_start = start_min if metric_start_min is None else metric_start_min
    tickets = [TicketState() for _ in range(world.n_tickets)]
    agent_states = {a.agent_id: AgentState(idle_since_min=start_min) for a in world.agents}
    agent_by_id = {a.agent_id: a for a in world.agents}
    state = SimState(world, tickets, agent_states)
    stop_min = end_min + drain_min

    heap: list[tuple[float, int, int, tuple]] = []
    seq = 0
    in_window = np.nonzero((world.created_min >= start_min) & (world.created_min < end_min))[0]
    for i in in_window:
        heapq.heappush(heap, (float(world.created_min[i]), ARRIVAL, seq, (int(i),)))
        seq += 1
    # Two kinds of DECIDE: "event" right after something changed (a ticket arrived, an agent
    # finished, a customer reopened) — like a real floor where the next ticket is pulled at
    # once — and a periodic "tick" that catches agents starting their shift.
    heapq.heappush(heap, (start_min, DECIDE, seq, ("tick",)))
    seq += 1
    decide_pending: set[float] = {start_min}

    snapshots: list[dict] = []
    next_snapshot = math.ceil(start_min / SNAPSHOT_EVERY_MIN) * SNAPSHOT_EVERY_MIN
    decisions = 0

    while heap:
        now, kind, _, payload = heapq.heappop(heap)
        if now > stop_min:
            break
        while next_snapshot <= now:
            snapshots.append(_snapshot(world, tickets, state.waiting, next_snapshot))
            next_snapshot += SNAPSHOT_EVERY_MIN

        if kind == DECIDE:
            decide_pending.discard(now)
            if state.waiting and state.any_free_agent(now):
                decisions += 1
                for assignment in policy.decide(state, now):
                    seq = _start_work(world, tickets, state, agent_by_id, heap, seq, now, assignment)
            if payload[0] == "tick":
                # Keep ticking while tickets can still arrive, wait, finish or reopen.
                work_remains = now < end_min or bool(state.waiting) or bool(heap)
                if work_remains and now + decide_every_min <= stop_min:
                    heapq.heappush(heap, (now + decide_every_min, DECIDE, seq, ("tick",)))
                    seq += 1
                    decide_pending.add(now + decide_every_min)
            continue

        if kind == ARRIVAL:
            i = payload[0]
            tickets[i].status = "waiting"
            tickets[i].queue_since_min = now
            state.add_waiting(i)
        elif kind == FINISH:
            seq = _finish(world, tickets, state, agent_by_id, heap, seq, now, payload)
        elif kind == REOPEN:
            i = payload[0]
            t = tickets[i]
            t.status, t.queue_since_min, t.reopens = "waiting", now, t.reopens + 1
            t.resolved_min = math.nan
            state.add_waiting(i)
        # Something changed: decide at this same minute, after all other events at `now`
        # (DECIDE sorts last among equal times). One DECIDE per timestamp is enough.
        if now not in decide_pending:
            heapq.heappush(heap, (now, DECIDE, seq, ("event",)))
            seq += 1
            decide_pending.add(now)

    return _collect(world, tickets, agent_states, snapshots, policy.name, seed_label,
                    metric_start, end_min, decisions)


def _start_work(world, tickets, state, agent_by_id, heap, seq, now, a: Assignment) -> int:
    """Begin one piece of work. Checks the assignment is legal (a policy bug raises)."""
    i, agent = a.ticket_idx, agent_by_id[a.agent_id]
    t, ast = tickets[i], state.agent_states[a.agent_id]
    if i not in state.waiting:
        raise ValueError(f"ticket {i} is not waiting")
    if ast.busy >= agent.max_concurrent:
        raise ValueError(f"agent {a.agent_id} has no free slot")
    if world.language[i] not in agent.languages:
        raise ValueError(f"agent {a.agent_id} cannot serve language {world.language[i]}")

    state.waiting.pop(i, None)
    state.in_work.add(i)
    t.status = "in_work"
    if math.isnan(t.first_pickup_min):
        t.first_pickup_min = now
    attempt = min(t.attempts, world.base_handle_min.shape[1] - 1)
    t.attempts += 1
    ast.busy += 1
    t.last_agent = a.agent_id

    true_cat = world.true_category[i]
    base = float(world.base_handle_min[i, attempt])
    if t.reopens > 0:
        base *= world.reopen_handle_factor
    if true_cat in agent.skills:
        duration, outcome, mismatch = base, "resolve", False
    elif a.deliberate_cross_skill:
        duration, outcome, mismatch = base * world.mismatch_factor, "resolve", True
    else:
        # The agent believed it was theirs; reading it shows it belongs elsewhere.
        duration, outcome, mismatch = world.transfer_discovery_min, "transfer", False

    ast.busy_minutes += duration
    heapq.heappush(heap, (now + duration, FINISH, seq, (i, a.agent_id, outcome, mismatch, duration)))
    return seq + 1


def _finish(world, tickets, state, agent_by_id, heap, seq, now, payload) -> int:
    i, agent_id, outcome, mismatch, duration = payload
    t, ast = tickets[i], state.agent_states[agent_id]
    ast.busy -= 1
    state.in_work.discard(i)
    if ast.busy == 0:
        ast.idle_since_min = now
    t.known_category = world.true_category[i]  # whoever opened it now knows what it is

    if outcome == "transfer":
        t.status, t.queue_since_min, t.transfers = "waiting", now, t.transfers + 1
        state.add_waiting(i)
        return seq

    t.handled_min += duration
    t.mismatch_used = t.mismatch_used or mismatch
    t.status, t.resolved_min = "resolved", now
    reopen_p = world.reopen_prob_mismatch if mismatch else world.reopen_prob_matched
    if t.reopens == 0 and world.reopen_u[i] < reopen_p:
        heapq.heappush(heap, (now + float(world.reopen_delay_min[i]), REOPEN, seq, (i,)))
        return seq + 1
    return seq


def _snapshot(world: World, tickets: list[TicketState], waiting: dict[int, TicketView], at: float) -> dict:
    """Queue length and breached-so-far, for the replay animation and max-backlog KPI."""
    breached_open = sum(
        1 for i in waiting if at > world.created_min[i] + world.sla_min[i]
    )
    return {"minute": at, "waiting": len(waiting), "waiting_breached": breached_open}


def _collect(world, tickets, agent_states, snapshots, policy_name, seed_label,
             metric_start, end_min, decisions) -> SimResult:
    rows = []
    for i in range(world.n_tickets):
        created = float(world.created_min[i])
        if not (metric_start <= created < end_min):
            continue
        t = tickets[i]
        resolved = t.resolved_min
        resolution = resolved - created if not math.isnan(resolved) else math.nan
        breached = math.isnan(resolution) or resolution > world.sla_min[i]
        rows.append({
            "ticket_id": world.ticket_ids[i],
            "idx": i,
            "created_min": created,
            "first_pickup_min": t.first_pickup_min,
            "resolved_min": resolved,
            "wait_min": t.first_pickup_min - created,
            "resolution_min": resolution,
            "handled_min": t.handled_min,
            "transfers": t.transfers,
            "reopens": t.reopens,
            "mismatch_used": t.mismatch_used,
            "last_agent": t.last_agent,
            "breached": bool(breached),
            "priority": world.priority[i],
            "tier": world.tier[i],
            "language": world.language[i],
            "category": world.true_category[i],
        })
    tickets_df = pd.DataFrame(rows)
    snaps = pd.DataFrame(snapshots)
    available = {
        a.agent_id: available_minutes(world, k, metric_start, end_min)
        for k, a in enumerate(world.agents)
    }
    busy = {aid: st.busy_minutes for aid, st in agent_states.items()}
    return SimResult(policy_name, seed_label, tickets_df, snaps, busy, available, decisions)


def available_minutes(world: World, agent_idx: int, start: float, end: float) -> float:
    """Minutes the agent is on shift (and present) between start and end."""
    agent = world.agents[agent_idx]
    total = 0.0
    first_day = int(start // MINUTES_PER_DAY) - 1
    last_day = int(end // MINUTES_PER_DAY) + 1
    for day in range(max(first_day, 0), last_day + 1):
        start_min, days_off = agent.schedule_on(day)
        weekday = (world.first_weekday + day) % 7
        if weekday in days_off:
            continue
        if day < world.absent.shape[1] and world.absent[agent_idx, day]:
            continue
        s = day * MINUTES_PER_DAY + start_min
        e = s + agent.shift_minutes
        total += max(0.0, min(e, end) - max(s, start))
    return total
