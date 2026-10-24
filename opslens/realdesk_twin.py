"""A calibrated digital twin of the real UCI service desk (Plan v4 W14).

What it does: replays the real incidents through a small queueing model of the desk — one pickup
queue per team, the agents who really worked in that team that week, k slots per agent — so two
dispatch policies can be compared on the same incidents, the same delays and the same agent-hours.
Before any comparison the twin must reproduce the real check months (the gate in
docs/explain/realdesk_twin.md, pre-registered in e53d623).

How it works:
1. stages(): each incident's real event log becomes a list of stages in the real order:
   WORK(team, hours) for Active time, WAIT(hours) for waits on the user, a vendor or another fix.
   New time is not copied: the twin makes its own pickup waits. Teams follow the real sequence.
2. rosters(): agents on duty 08:00-19:00 on the weekdays of a week in which they had an event in the
   team (weekend days: only agents with an event that day). A team-week with events but no named
   agent gets one unnamed agent.
3. run(): a heapq event loop. WORK needs a free slot of an on-duty agent of its team, may start only on
   duty, then runs share × real hours to completion. WAIT is a fixed real delay. Policies only order
   each team's queue.

Example (tests/test_realdesk_twin.py, hand-computed): one agent with 1 slot, on duty 08:00-19:00;
incidents A (priority 3) and B (priority 1) open at 07:00 and 07:30, each with WORK 2 h at share 0.5.
At 08:00 the desk takes B first (higher priority): B 08:00-09:00, A 09:00-10:00. Pickup waits:
A 2 h, B 0.5 h.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

WORK, WAIT = "work", "wait"
WAIT_STATES = {"Awaiting User Info", "Awaiting Vendor", "Awaiting Problem", "Awaiting Evidence"}
DONE_STATES = {"Resolved", "Closed"}
DUTY_START_H, DUTY_HOURS = 8.0, 11.0          # 08:00-19:00 (88.6% of the learning months' events)
END_SLACK_DAYS = 30
# Event kinds; at equal times a finished stage frees its slot before new work arrives.
DONE, ARRIVE, SWITCH, SHIFT, SCORE, DEADLINE = 0, 1, 2, 3, 4, 5


# ---- Inputs ----------------------------------------------------------------------------------

def stages(events: pd.DataFrame) -> dict[str, list[tuple[str, str, float]]]:
    """Per incident: [(kind, team, hours)] in the real order, until the first Resolved/Closed.
    An incident with no Active time (New straight to Resolved: the fix happened while the log said New)
    gets one WORK at the team that held it, for its New hours.
    Example: New 1 h (G1) → Active 3 h (G1) → Awaiting User 20 h → Active 2 h (G2) → Resolved
    = [(work, G1, 3), (wait, G1, 20), (work, G2, 2)]."""
    ev = events[["number", "incident_state", "assignment_group", "sys_updated_at"]]
    out: dict[str, list[tuple[str, str, float]]] = {}
    for number, g in ev.groupby("number", sort=False):
        states = g["incident_state"].to_numpy()
        teams = g["assignment_group"].astype(str).to_numpy()
        times = g["sys_updated_at"].to_numpy()
        seq: list[list] = []
        new_hours, new_team, resolved = 0.0, teams[0], False
        for j in range(len(g) - 1):
            if states[j] in DONE_STATES:
                resolved = True
                break
            hours = float((times[j + 1] - times[j]) / np.timedelta64(1, "h"))
            if states[j] == "New":
                new_hours, new_team = new_hours + hours, teams[j]
                continue
            kind = WAIT if states[j] in WAIT_STATES else WORK
            if seq and seq[-1][0] == kind and (kind == WAIT or seq[-1][1] == teams[j]):
                seq[-1][2] += hours
            else:
                seq.append([kind, teams[j], hours])
        resolved = resolved or states[-1] in DONE_STATES
        if not any(s[0] == WORK for s in seq) and resolved:
            seq = [[WORK, new_team, new_hours]] + seq
        out[number] = [(k, t, h) for k, t, h in seq]
    return out


@dataclass
class Roster:
    """Who is on duty: day index → {agent: [teams]} and day index → {team: [agents]}."""

    agent_teams: dict[int, dict[str, list[str]]] = field(default_factory=dict)
    team_agents: dict[int, dict[str, list[str]]] = field(default_factory=dict)


def rosters(events: pd.DataFrame, t0: pd.Timestamp, n_days: int) -> Roster:
    """The availability rule of the pre-registration (see the module docstring, step 2)."""
    ev = events[["assignment_group", "assigned_to", "sys_updated_at"]].dropna(subset=["assignment_group"]).copy()
    ev["team"] = ev["assignment_group"].astype(str)
    ev["day"] = ((ev["sys_updated_at"] - t0) / pd.Timedelta(days=1)).astype(int)
    ev["week"] = (ev["day"] + t0.weekday()) // 7
    named = ev.dropna(subset=["assigned_to"])
    weekly = named.groupby(["team", "week"])["assigned_to"].unique()
    weekend = named.groupby(["team", "day"])["assigned_to"].unique()
    teams_with_events = ev.groupby(["team", "week"]).size()
    roster = Roster()
    for day in range(n_days):
        weekday = (t0.weekday() + day) % 7
        week = (day + t0.weekday()) // 7
        on: dict[str, list[str]] = {}
        for (team, wk) in teams_with_events.index:
            if wk != week:
                continue
            if weekday < 5:
                agents = list(weekly.get((team, week), []))
                agents = agents or [f"unnamed {team}"]
            else:
                agents = list(weekend.get((team, day), []))
            if agents:
                on[team] = sorted(str(a) for a in agents)
        roster.team_agents[day] = on
        by_agent: dict[str, list[str]] = {}
        for team, agents in on.items():
            for a in agents:
                by_agent.setdefault(a, []).append(team)
        roster.agent_teams[day] = by_agent
    return roster


# ---- The event loop --------------------------------------------------------------------------

@dataclass
class TwinInput:
    """Everything a run needs, in minutes from t0 (midnight of the first day)."""

    ids: list[str]
    opened: np.ndarray             # minutes
    prio: np.ndarray               # 1 = Critical .. 4 = Low
    deadline: np.ndarray           # minutes after opening (inf when not scored)
    stage_list: list[list[tuple[str, str, float]]]
    roster: Roster
    n_days: int


@dataclass
class TwinResult:
    pickup: np.ndarray             # minutes from opening to the first WORK start (nan: never)
    resolved: np.ndarray           # minutes from opening to the end of the last stage (nan: never)


def on_duty_until(minute: float, cut: float) -> float | None:
    """End of the duty window containing `minute`, or None when off duty."""
    day_start = (minute // 1440) * 1440
    start = day_start + DUTY_START_H * 60
    end = start + DUTY_HOURS * (1.0 - cut) * 60
    return end if start <= minute < end else None


class Policy:
    """Orders a team's queue: a smaller key goes first. The desk: priority, then oldest."""

    def key(self, i: int, twin: "Twin") -> tuple:
        return (int(twin.inp.prio[i]), float(twin.inp.opened[i]), i)

    def prepare(self, twin: "Twin") -> None:
        """Schedule the policy's own events (the desk has none)."""

    def event(self, twin: "Twin", kind: int, i: int) -> None:
        """Handle the policy's own events (the desk has none)."""


def run(inp: TwinInput, share: float, k: int, policy: Policy, switch_minute: float = float("inf"),
        cut: float = 0.0, cut_from_minute: float = float("inf")) -> TwinResult:
    """Replay every incident; `policy` orders the queues from `switch_minute` on (the desk before).
    `cut` shortens every duty window from `cut_from_minute` on (the hours-equivalent test)."""
    twin = Twin(inp, share, k, policy, switch_minute, cut, cut_from_minute)
    return twin.go()


class Twin:
    """State of one run. Plain loops, so every line can be checked by hand."""

    def __init__(self, inp, share, k, policy, switch_minute, cut, cut_from_minute):
        self.inp, self.share, self.k, self.policy = inp, share, k, policy
        self.switch, self.cut, self.cut_from = switch_minute, cut, cut_from_minute
        self.desk = Policy()
        n = len(inp.ids)
        self.pos = np.zeros(n, dtype=int)                  # index of the current stage
        self.pickup = np.full(n, np.nan)
        self.resolved = np.full(n, np.nan)
        self.in_work = np.zeros(n, dtype=bool)
        self.version = np.zeros(n, dtype=int)
        self.queued_team: dict[int, str] = {}
        self.queues: dict[str, list] = {}
        self.free: dict[str, int] = {}
        self.load: dict[str, int] = {}                     # queued + in work, per team (OpsLens features)
        self.heap: list = []
        self.seq = 0
        self.now = 0.0

    # -- helpers --
    def push(self, minute: float, kind: int, payload: int) -> None:
        self.seq += 1
        heapq.heappush(self.heap, (minute, kind, self.seq, payload))

    def active_policy(self) -> Policy:
        return self.policy if self.now >= self.switch else self.desk

    def cut_now(self) -> float:
        return self.cut if self.now >= self.cut_from else 0.0

    def enqueue(self, i: int, team: str) -> None:
        self.version[i] += 1
        self.queued_team[i] = team
        heapq.heappush(self.queues.setdefault(team, []), (self.active_policy().key(i, self), int(self.version[i]), i))

    def best(self, team: str):
        q = self.queues.get(team, [])
        while q and (q[0][2] not in self.queued_team or q[0][1] != self.version[q[0][2]]):
            heapq.heappop(q)                               # stale entry (re-keyed or already taken)
        return q[0] if q else None

    def start_work(self, i: int, agent: str, team: str) -> None:
        heapq.heappop(self.queues[team])
        del self.queued_team[i]
        self.free[agent] = self.free.get(agent, self.k) - 1
        if np.isnan(self.pickup[i]):
            self.pickup[i] = self.now - self.inp.opened[i]
        self.in_work[i] = True
        hours = self.inp.stage_list[i][self.pos[i]][2]
        self.agent_of[i] = agent
        self.push(self.now + self.share * hours * 60.0, DONE, i)

    def fill(self, agent: str) -> None:
        """A free, on-duty agent takes the best queued items of the teams it serves today."""
        if on_duty_until(self.now, self.cut_now()) is None:
            return
        teams = self.inp.roster.agent_teams.get(int(self.now // 1440), {}).get(agent, [])
        while self.free.get(agent, self.k) > 0:
            tops = [(self.best(t), t) for t in teams]
            tops = [(top, t) for top, t in tops if top is not None]
            if not tops:
                return
            top, team = min(tops, key=lambda x: x[0])
            self.start_work(top[2], agent, team)

    def dispatch_team(self, team: str) -> None:
        """New work in a team's queue: give it to the on-duty agent with the most free slots."""
        if on_duty_until(self.now, self.cut_now()) is None:
            return
        agents = self.inp.roster.team_agents.get(int(self.now // 1440), {}).get(team, [])
        while self.best(team) is not None:
            agent, most = None, 0
            for a in agents:                               # agents are sorted: ties go to the first id
                if self.free.get(a, self.k) > most:
                    agent, most = a, self.free.get(a, self.k)
            if agent is None:
                return
            self.start_work(self.best(team)[2], agent, team)

    def advance(self, i: int) -> None:
        """Move incident i to its next stage (or finish it)."""
        stages_i = self.inp.stage_list[i]
        if not stages_i:
            return                                         # nothing ever happened to it: never resolved
        if self.pos[i] >= len(stages_i):
            self.resolved[i] = self.now - self.inp.opened[i]
            return
        kind, team, hours = stages_i[self.pos[i]]
        if kind == WAIT:
            self.push(self.now + hours * 60.0, DONE, i)
            return
        self.load[team] = self.load.get(team, 0) + 1
        self.enqueue(i, team)
        self.dispatch_team(team)

    # -- the loop --
    def go(self) -> TwinResult:
        self.agent_of: dict[int, str] = {}
        for i in np.argsort(self.inp.opened, kind="stable"):
            self.push(float(self.inp.opened[i]), ARRIVE, int(i))
        for day in range(self.inp.n_days):
            self.push(day * 1440 + DUTY_START_H * 60, SHIFT, day)
        if np.isfinite(self.switch):
            self.push(self.switch, SWITCH, -1)
        self.policy.prepare(self)
        end = self.inp.n_days * 1440
        while self.heap:
            minute, kind, _, payload = heapq.heappop(self.heap)
            if minute > end:
                break
            self.now = minute
            if kind == ARRIVE:
                self.advance(payload)
            elif kind == DONE:
                self.finish_stage(payload)
            elif kind == SHIFT:
                for agent in sorted(self.inp.roster.agent_teams.get(payload, {})):
                    self.fill(agent)
            elif kind == SWITCH:
                self.rekey_all()
            else:
                self.policy.event(self, kind, payload)
        return TwinResult(pickup=self.pickup, resolved=self.resolved)

    def finish_stage(self, i: int) -> None:
        kind, team, _ = self.inp.stage_list[i][self.pos[i]]
        self.pos[i] += 1
        if kind == WORK:
            self.in_work[i] = False
            self.load[team] -= 1
            agent = self.agent_of.pop(i)
            self.free[agent] = self.free.get(agent, self.k) + 1
            self.advance(i)
            self.fill(agent)
        else:
            self.advance(i)

    def rekey_all(self) -> None:
        """At the switch, every queued incident is re-ordered by the new policy."""
        for i, team in list(self.queued_team.items()):
            self.enqueue(i, team)

    def rekey(self, i: int) -> None:
        if i in self.queued_team:
            self.enqueue(i, self.queued_team[i])


# ---- Building the input from the real log ----------------------------------------------------

def build_input(incidents: pd.DataFrame, events: pd.DataFrame, limits: dict[str, float]) -> TwinInput:
    """The real incidents, their stages and the rosters, in minutes from the first day's midnight."""
    t0 = incidents["created_at"].min().normalize()
    last = events["sys_updated_at"].max()
    n_days = int((last - t0) / pd.Timedelta(days=1)) + 1 + END_SLACK_DAYS
    st = stages(events)
    priority = incidents["priority_raw"].astype(str)
    deadline = np.array([limits.get(p, np.inf) * 60.0 for p in priority])
    return TwinInput(ids=incidents["ticket_id"].tolist(),
                     opened=((incidents["created_at"] - t0) / pd.Timedelta(minutes=1)).to_numpy(dtype=float),
                     prio=priority.str[0].astype(int).to_numpy(), deadline=deadline,
                     stage_list=[st.get(t, []) for t in incidents["ticket_id"]],
                     roster=rosters(events, t0, n_days), n_days=n_days)


# ---- Measuring a run against reality --------------------------------------------------------

def real_pickup(incidents: pd.DataFrame, events: pd.DataFrame) -> np.ndarray:
    """Real minutes from opening to the first event that is not New; nan when the log records no
    pickup (New straight to Resolved/Closed, or never left New)."""
    later = events[events["incident_state"] != "New"].groupby("number").head(1).set_index("number")
    at = later["sys_updated_at"].reindex(incidents["ticket_id"]).to_numpy()
    state = later["incident_state"].reindex(incidents["ticket_id"]).astype(str).to_numpy()
    wait = (at - incidents["created_at"].to_numpy()) / np.timedelta64(1, "m")
    wait = np.where(np.isin(state, list(DONE_STATES)) | pd.isna(at), np.nan, wait)
    return np.clip(wait.astype(float), 0, None)


def measure(mask: np.ndarray, scored: np.ndarray, deadline: np.ndarray, resolved: np.ndarray,
            pickup: np.ndarray, recorded: np.ndarray) -> dict:
    """Missed % (deadline rule; never resolved = missed) on scored incidents in `mask`; median pickup
    (hours) and % picked up within 1 h on incidents in `mask` whose real log records a pickup."""
    s = mask & scored
    missed = ~(resolved[s] <= deadline[s])
    p = mask & recorded
    wait = pickup[p]
    return {"scored": int(s.sum()), "missed_pct": float(missed.mean() * 100),
            "pickup_incidents": int(p.sum()), "median_pickup_h": float(np.nanmedian(wait) / 60.0),
            "picked_within_1h_pct": float(np.mean(wait <= 60.0) * 100)}
