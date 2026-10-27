from __future__ import annotations

import copy
import heapq
import math
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd

FINISH, REOPEN, ARRIVAL, DECIDE = 0, 1, 2, 3
MINUTES_PER_DAY = 1440
SNAPSHOT_EVERY_MIN = 15
FLOOR_EVERY_MIN = 5
MAX_REROUTE_ROUNDS = 4


@dataclass(frozen=True)
class Agent:
    agent_id: str
    name: str
    team: str
    team_skills: frozenset[str]
    skills: frozenset[str]
    languages: frozenset[str]
    shift_start_min: int
    shift_minutes: int
    days_off: frozenset[int]
    max_concurrent: int = 1
    overrides: tuple = ()

    def schedule_on(self, day_index: int) -> tuple[int, frozenset[int]]:
        for first, last, start_min, off in self.overrides:
            if first - 1 <= day_index <= last - 1:
                return start_min, off
        return self.shift_start_min, self.days_off


@dataclass
class World:
    ticket_ids: list[str]
    created_min: np.ndarray
    true_category: list[str]
    selected_category: list[str]
    channel: list[str]
    priority: list[str]
    language: list[str]
    tier: list[str]
    order_value: np.ndarray
    sla_min: np.ndarray
    base_handle_min: np.ndarray
    reopen_u: np.ndarray
    reopen_delay_min: np.ndarray
    agents: list[Agent]
    absent: np.ndarray
    first_weekday: int = 0
    mismatch_factor: float = 1.6
    reopen_prob_matched: float = 0.04
    reopen_prob_mismatch: float = 0.15
    reopen_handle_factor: float = 0.6
    transfer_discovery_min: float = 4.0
    concurrency_slowdown: float = 0.0

    @property
    def n_tickets(self) -> int:
        return len(self.ticket_ids)


@dataclass(frozen=True)
class TicketView:
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
    known_category: str | None
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
    ticket_idx: int
    agent_id: str
    believed_category: str
    deliberate_cross_skill: bool = False
    reason: str = ""


class Policy(Protocol):
    name: str

    def decide(self, state: "SimState", now: float) -> list[Assignment]: ...


@dataclass
class TicketState:
    status: str = "future"
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
    working_cross: bool = False


@dataclass
class AgentState:
    busy: int = 0
    idle_since_min: float = 0.0
    busy_minutes: float = 0.0


@dataclass
class SimState:
    world: World
    tickets: list[TicketState]
    agent_states: dict[str, AgentState]
    waiting: dict[int, TicketView] = field(default_factory=dict)
    _shift_cache: dict[int, tuple[float, float | None]] = field(default_factory=dict)
    in_work: set[int] = field(default_factory=set)
    agent_index: dict[str, int] = field(default_factory=dict)
    breaks: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    hidden_agents: set[str] = field(default_factory=set)

    def on_break(self, agent_id: str, now: float) -> bool:
        return any(b0 <= now < b1 for b0, b1 in self.breaks.get(agent_id, ()))

    def add_waiting(self, i: int) -> None:
        self.waiting[i] = self._view(i)

    def waiting_tickets(self) -> list[TicketView]:
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
        if self.breaks and self.on_break(self.world.agents[agent_idx].agent_id, now):
            return None
        cached = self._shift_cache.get(agent_idx)
        if cached is not None and now < cached[0]:
            return cached[1]
        end = shift_end_if_on(self.world, agent_idx, now)
        if end is not None:
            valid_until = end
        else:
            agent = self.world.agents[agent_idx]
            today = int(now // MINUTES_PER_DAY)
            starts = [d * MINUTES_PER_DAY + agent.schedule_on(d)[0] for d in (today, today + 1)]
            starts += [d * MINUTES_PER_DAY for d in (today + 1, today + 2)]
            valid_until = min(s for s in starts if s > now)
        self._shift_cache[agent_idx] = (float(valid_until), end)
        return end

    def any_free_agent(self, now: float) -> bool:
        for agent_idx, agent in enumerate(self.world.agents):
            if agent.agent_id in self.hidden_agents:
                continue
            if self.agent_states[agent.agent_id].busy < agent.max_concurrent:
                if self.shift_end(agent_idx, now) is not None:
                    return True
        return False

    def free_agents(self, now: float) -> list[AgentView]:
        free: list[AgentView] = []
        for agent_idx, agent in enumerate(self.world.agents):
            if agent.agent_id in self.hidden_agents:
                continue
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


@dataclass
class SimResult:
    policy: str
    seed_label: str
    tickets: pd.DataFrame
    snapshots: pd.DataFrame
    agent_busy_minutes: dict[str, float]
    agent_available_minutes: dict[str, float]
    decisions: int
    floor: list[dict] = field(default_factory=list)
    checkpoints: list["Checkpoint"] = field(default_factory=list)


@dataclass
class Overrides:
    forbidden: dict[tuple[str, int], float] = field(default_factory=dict)
    finishes: list[tuple[float, str, int, str, float]] = field(default_factory=list)
    breaks: dict[str, list[tuple[float, float]]] = field(default_factory=dict)

    def blocks(self, agent_id: str, ticket_idx: int, now: float) -> bool:
        since = self.forbidden.get((agent_id, ticket_idx))
        return since is not None and now >= since


@dataclass
class Checkpoint:
    minute: float
    touched: dict[int, TicketState]
    agent_states: dict[str, AgentState]
    waiting: dict[int, TicketView]
    in_work: set[int]
    heap: list
    seq: int
    decide_pending: set[float]
    snapshots: list[dict]
    next_snapshot: float
    decisions: int
    floor: list[dict]
    next_floor: float
    policy: object
    share: list

    def restore_policy(self):
        return copy.deepcopy(self.policy, {id(x): x for x in self.share})


def take_checkpoint(minute: float, tickets: list[TicketState], state: SimState, heap: list, seq: int,
                    decide_pending: set[float], snapshots: list[dict], next_snapshot: float, decisions: int,
                    floor: list[dict], next_floor: float, policy, share: list) -> Checkpoint:
    keep = [state.world, *share, *getattr(policy, "decision_log", [])]
    return Checkpoint(
        minute=minute,
        touched={i: copy.copy(t) for i, t in enumerate(tickets) if t.status != "future"},
        agent_states={k: copy.copy(v) for k, v in state.agent_states.items()},
        waiting=dict(state.waiting), in_work=set(state.in_work), heap=list(heap), seq=seq,
        decide_pending=set(decide_pending), snapshots=list(snapshots), next_snapshot=next_snapshot,
        decisions=decisions, floor=list(floor), next_floor=next_floor,
        policy=copy.deepcopy(policy, {id(x): x for x in keep}), share=keep,
    )


def _restore(world: World, cp: Checkpoint) -> tuple:
    tickets = [TicketState() for _ in range(world.n_tickets)]
    for i, t in cp.touched.items():
        tickets[i] = copy.copy(t)
    agent_states = {k: copy.copy(v) for k, v in cp.agent_states.items()}
    state = SimState(world, tickets, agent_states, waiting=dict(cp.waiting), in_work=set(cp.in_work),
                     agent_index={a.agent_id: k for k, a in enumerate(world.agents)})
    return (tickets, agent_states, state, list(cp.heap), cp.seq, set(cp.decide_pending), list(cp.snapshots),
            cp.next_snapshot, cp.decisions, list(cp.floor), cp.next_floor)


def simulate(
    world: World,
    policy: Policy,
    start_min: float,
    end_min: float,
    metric_start_min: float | None = None,
    decide_every_min: float = 2.0,
    drain_min: float = 2 * MINUTES_PER_DAY,
    seed_label: str = "",
    floor_window: tuple[float, float] | None = None,
    overrides: Overrides | None = None,
    checkpoint_at: tuple[float, ...] = (),
    checkpoint_share: tuple = (),
    resume: Checkpoint | None = None,
    pause_at: float | None = None,
) -> SimResult:
    metric_start = start_min if metric_start_min is None else metric_start_min
    tickets = [TicketState() for _ in range(world.n_tickets)]
    agent_states = {a.agent_id: AgentState(idle_since_min=start_min) for a in world.agents}
    agent_by_id = {a.agent_id: a for a in world.agents}
    state = SimState(world, tickets, agent_states, agent_index={a.agent_id: k for k, a in enumerate(world.agents)})
    stop_min = end_min + drain_min

    heap: list[tuple[float, int, int, tuple]] = []
    seq = 0
    in_window = np.nonzero((world.created_min >= start_min) & (world.created_min < end_min))[0]
    for i in in_window:
        heapq.heappush(heap, (float(world.created_min[i]), ARRIVAL, seq, (int(i),)))
        seq += 1
    heapq.heappush(heap, (start_min, DECIDE, seq, ("tick",)))
    seq += 1
    decide_pending: set[float] = {start_min}

    snapshots: list[dict] = []
    next_snapshot = math.ceil(start_min / SNAPSHOT_EVERY_MIN) * SNAPSHOT_EVERY_MIN
    decisions = 0
    floor: list[dict] = []
    next_floor = floor_window[0] if floor_window else math.inf
    if resume is not None:
        (tickets, agent_states, state, heap, seq, decide_pending, snapshots,
         next_snapshot, decisions, floor, next_floor) = _restore(world, resume)
    if overrides is not None:
        state.breaks = overrides.breaks
    first = resume.minute if resume is not None else start_min
    changes = sorted(c for c in (overrides.finishes if overrides else []) if c[0] >= first)
    marks = sorted(m for m in checkpoint_at if m >= first)
    checkpoints: list[Checkpoint] = []

    while heap:
        now, kind, _, payload = heapq.heappop(heap)
        next_change = changes[0][0] if changes else math.inf
        next_mark = marks[0] if marks else math.inf
        if min(next_change, next_mark) <= now:
            heapq.heappush(heap, (now, kind, _, payload))
            if next_mark <= next_change:
                checkpoints.append(take_checkpoint(marks.pop(0), tickets, state, heap, seq, decide_pending,
                                                   snapshots, next_snapshot, decisions, floor, next_floor,
                                                   policy, list(checkpoint_share)))
                if pause_at is not None and checkpoints[-1].minute >= pause_at:
                    break
            else:
                _change_finish(state, heap, changes.pop(0))
            continue
        if now > stop_min:
            break
        while next_snapshot <= now:
            snapshots.append(_snapshot(world, tickets, state.waiting, next_snapshot))
            next_snapshot += SNAPSHOT_EVERY_MIN
        while next_floor <= now and next_floor <= floor_window[1]:
            floor.append(floor_snapshot(state, next_floor))
            next_floor += FLOOR_EVERY_MIN

        if kind == DECIDE:
            decide_pending.discard(now)
            if state.waiting and state.any_free_agent(now):
                decisions += 1
                if overrides is not None and overrides.forbidden:
                    seq = _decide_around(world, tickets, state, agent_by_id, heap, seq, now, policy, overrides)
                else:
                    for assignment in policy.decide(state, now):
                        seq = _start_work(world, tickets, state, agent_by_id, heap, seq, now, assignment)
            if payload[0] == "tick":
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
        if now not in decide_pending:
            heapq.heappush(heap, (now, DECIDE, seq, ("event",)))
            seq += 1
            decide_pending.add(now)

    result = _collect(world, tickets, agent_states, snapshots, policy.name, seed_label,
                      metric_start, end_min, decisions)
    result.floor = floor
    result.checkpoints = checkpoints
    return result


def _decide_around(world, tickets, state, agent_by_id, heap, seq, now, policy, overrides: Overrides) -> int:
    blocked: list[Assignment] = []
    hidden: dict[int, TicketView] = {}
    for _ in range(MAX_REROUTE_ROUNDS):
        refused = []
        for a in policy.decide(state, now):
            if overrides.blocks(a.agent_id, a.ticket_idx, now):
                refused.append(a)
            else:
                seq = _start_work(world, tickets, state, agent_by_id, heap, seq, now, a)
        if not refused:
            break
        blocked += refused
        for a in refused:
            hidden[a.ticket_idx] = state.waiting.pop(a.ticket_idx)
    state.waiting.update(hidden)
    if not blocked:
        return seq
    state.hidden_agents = {a.agent_id for a in blocked}
    try:
        for _ in range(MAX_REROUTE_ROUNDS):
            refused = []
            for a in policy.decide(state, now):
                if overrides.blocks(a.agent_id, a.ticket_idx, now):
                    refused.append(a)
                else:
                    seq = _start_work(world, tickets, state, agent_by_id, heap, seq, now, a)
            if not refused:
                break
            state.hidden_agents |= {a.agent_id for a in refused}
    finally:
        state.hidden_agents = set()
    return seq


def _change_finish(state: SimState, heap: list, change: tuple[float, str, int, str, float]) -> None:
    minute, agent_id, idx, how, value = change
    for k, (end, kind, s, payload) in enumerate(heap):
        if kind == FINISH and payload[0] == idx and payload[1] == agent_id:
            break
    else:
        return
    i, aid, outcome, mismatch, duration = payload
    begun = end - duration
    new_end = max(minute, value if how == "at" else end + value)
    heap[k] = heap[-1]
    heap.pop()
    heapq.heapify(heap)
    state.agent_states[aid].busy_minutes += new_end - end
    heapq.heappush(heap, (new_end, FINISH, s, (i, aid, outcome, mismatch, new_end - begun)))


def _start_work(world, tickets, state, agent_by_id, heap, seq, now, a: Assignment) -> int:
    i, agent = a.ticket_idx, agent_by_id[a.agent_id]
    t, ast = tickets[i], state.agent_states[a.agent_id]
    if i not in state.waiting:
        raise ValueError(f"ticket {i} is not waiting")
    if ast.busy >= agent.max_concurrent:
        raise ValueError(f"agent {a.agent_id} has no free slot")
    if world.language[i] not in agent.languages:
        raise ValueError(f"agent {a.agent_id} cannot serve language {world.language[i]}")
    if state.shift_end(state.agent_index[a.agent_id], now) is None:
        raise ValueError(f"agent {a.agent_id} is not on shift at minute {now:.0f}")

    state.waiting.pop(i, None)
    state.in_work.add(i)
    t.status = "in_work"
    if math.isnan(t.first_pickup_min):
        t.first_pickup_min = now
    ast.busy += 1
    t.last_agent = a.agent_id
    t.working_cross = a.deliberate_cross_skill

    true_cat = world.true_category[i]
    if true_cat in agent.skills or a.deliberate_cross_skill:
        attempt = min(t.attempts, world.base_handle_min.shape[1] - 1)
        t.attempts += 1
        base = float(world.base_handle_min[i, attempt])
        if t.reopens > 0:
            base *= world.reopen_handle_factor
        mismatch = true_cat not in agent.skills
        duration, outcome = (base * world.mismatch_factor if mismatch else base), "resolve"
    else:
        duration, outcome, mismatch = world.transfer_discovery_min, "transfer", False
    if ast.busy > 1:
        duration *= 1.0 + world.concurrency_slowdown * (ast.busy - 1)

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
    t.known_category = world.true_category[i]

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
    breached_open = sum(
        1 for i in waiting if at > world.created_min[i] + world.sla_min[i]
    )
    return {"minute": at, "waiting": len(waiting), "waiting_breached": breached_open}


def floor_snapshot(state: SimState, at: float) -> dict:
    world, tickets = state.world, state.tickets
    status = {}
    for k, agent in enumerate(world.agents):
        status[agent.agent_id] = "idle" if state.shift_end(k, at) is not None else "off"
        if state.breaks and status[agent.agent_id] == "off" and state.on_break(agent.agent_id, at):
            status[agent.agent_id] = "break"
    by_id = {a.agent_id: a for a in world.agents}
    for i in state.in_work:
        t = tickets[i]
        if t.working_cross:
            status[t.last_agent] = "cross"
        elif world.true_category[i] not in by_id[t.last_agent].skills:
            status[t.last_agent] = "wrong"
        else:
            status[t.last_agent] = "busy"
    team_of = {cat: a.team for a in world.agents for cat in a.team_skills}
    queues: dict[str, list[int]] = {}
    for i in state.waiting:
        team = team_of.get(world.true_category[i], "?")
        late = at > world.created_min[i] + world.sla_min[i]
        queues.setdefault(team, [0, 0])[1 if late else 0] += 1
    return {"minute": at, "agents": status, "queues": queues}


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
            "sla_min": float(world.sla_min[i]),
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
