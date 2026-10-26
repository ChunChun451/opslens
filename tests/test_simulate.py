import dataclasses
import math

import numpy as np
import pytest

from opslens.policies import baseline_a, baseline_b
from opslens.simulate import Agent, Assignment, World, simulate


def agent(agent_id: str, team: str, team_skills: set[str], extra: set[str] = frozenset(),
          langs: set[str] = frozenset({"en"})) -> Agent:
    return Agent(agent_id, agent_id, team, frozenset(team_skills), frozenset(team_skills) | frozenset(extra),
                 frozenset(langs), shift_start_min=0, shift_minutes=1440, days_off=frozenset())


def make_world(created, handles, agents, true_cat=None, selected=None, priority=None,
               language=None, reopen_u=None, reopen_delay=None, sla=600.0) -> World:
    n = len(created)
    true_cat = true_cat or ["refund"] * n
    handles = np.asarray(handles, dtype=float)
    if handles.ndim == 1:
        handles = np.repeat(handles[:, None], 3, axis=1)
    return World(
        ticket_ids=[f"T{i:06d}" for i in range(n)],
        created_min=np.asarray(created, dtype=float),
        true_category=true_cat,
        selected_category=selected or list(true_cat),
        channel=["chat"] * n,
        priority=priority or ["P2"] * n,
        language=language or ["en"] * n,
        tier=["normal"] * n,
        order_value=np.full(n, 300.0),
        sla_min=np.full(n, sla),
        base_handle_min=handles,
        reopen_u=np.asarray(reopen_u if reopen_u is not None else [1.0] * n, dtype=float),
        reopen_delay_min=np.asarray(reopen_delay if reopen_delay is not None else [60.0] * n, dtype=float),
        agents=agents,
        absent=np.zeros((len(agents), 400), dtype=bool),
    )


def by_id(result):
    return result.tickets.set_index("ticket_id")


def test_two_agents_three_tickets_fifo() -> None:
    world = make_world([0, 0, 0], [10, 10, 5],
                       [agent("X", "B", {"refund"}), agent("Y", "B", {"refund"})])
    out = by_id(simulate(world, baseline_a(), 0, 100, decide_every_min=1))
    assert out["resolution_min"].tolist() == [10, 10, 15]
    assert out["wait_min"].tolist() == [0, 0, 10]
    assert out["breached"].sum() == 0


def test_two_chats_at_once_are_each_slower() -> None:
    two_slots = dataclasses.replace(agent("X", "B", {"refund"}), max_concurrent=2)
    world = make_world([0, 0, 0], [10, 10, 10], [two_slots])
    world.concurrency_slowdown = 0.5
    out = by_id(simulate(world, baseline_a(), 0, 100, decide_every_min=1))
    assert out["resolution_min"].tolist() == [10, 15, 25]


def test_one_chat_per_agent_ignores_the_slowdown() -> None:
    world = make_world([0, 0, 0], [10, 10, 5],
                       [agent("X", "B", {"refund"}), agent("Y", "B", {"refund"})])
    world.concurrency_slowdown = 0.5
    out = by_id(simulate(world, baseline_a(), 0, 100, decide_every_min=1))
    assert out["resolution_min"].tolist() == [10, 10, 15]


def test_priority_policy_serves_p1_first() -> None:
    world = make_world([0, 0], [10, 10], [agent("X", "B", {"refund"})], priority=["P3", "P1"])
    a = by_id(simulate(world, baseline_a(), 0, 100, decide_every_min=1))
    b = by_id(simulate(world, baseline_b(), 0, 100, decide_every_min=1))
    assert a.loc["T000000", "resolution_min"] == 10
    assert b.loc["T000001", "resolution_min"] == 10
    assert b.loc["T000000", "resolution_min"] == 20


def test_misrouted_ticket_is_transferred() -> None:
    world = make_world([0], [10], [agent("A1", "A", {"late_delivery"}), agent("B1", "B", {"refund"})],
                       true_cat=["refund"], selected=["late_delivery"])
    out = by_id(simulate(world, baseline_a(), 0, 100, decide_every_min=1))
    row = out.loc["T000000"]
    assert row["transfers"] == 1
    assert row["resolution_min"] == 14
    assert row["last_agent"] == "B1"


def test_a_transfer_does_not_reroll_the_work_time() -> None:
    world = make_world([0], [[10, 99, 99]], [agent("A1", "A", {"late_delivery"}), agent("B1", "B", {"refund"})],
                       true_cat=["refund"], selected=["late_delivery"])
    row = by_id(simulate(world, baseline_a(), 0, 300, decide_every_min=1)).loc["T000000"]
    assert row["transfers"] == 1 and row["handled_min"] == 10 and row["resolution_min"] == 14


class GiveToFirstAgentAnyway:
    name = "cross-skill"

    def decide(self, state, now):
        free = state.free_agents(now)
        out = []
        for ticket in state.waiting_tickets():
            if not free:
                break
            ag = free.pop(0)
            out.append(Assignment(ticket.idx, ag.agent_id, "refund", deliberate_cross_skill=True))
        return out


def test_deliberate_cross_skill_is_slower() -> None:
    world = make_world([0], [10], [agent("A1", "A", {"late_delivery"})], true_cat=["refund"])
    out = by_id(simulate(world, GiveToFirstAgentAnyway(), 0, 100, decide_every_min=1))
    assert out.loc["T000000", "resolution_min"] == pytest.approx(16.0)
    assert bool(out.loc["T000000", "mismatch_used"]) is True


def test_reopen_adds_a_second_round() -> None:
    world = make_world([0], [10], [agent("B1", "B", {"refund"})], reopen_u=[0.0], reopen_delay=[60])
    out = by_id(simulate(world, baseline_a(), 0, 200, decide_every_min=1))
    row = out.loc["T000000"]
    assert row["reopens"] == 1
    assert row["resolution_min"] == pytest.approx(76.0)


def test_language_is_respected() -> None:
    world = make_world([0], [10], [agent("B1", "B", {"refund"})], language=["hi"], sla=60)
    out = by_id(simulate(world, baseline_a(), 0, 100, decide_every_min=1, drain_min=200))
    assert math.isnan(out.loc["T000000", "resolution_min"])
    assert bool(out.loc["T000000", "breached"]) is True


class BadPolicy:
    name = "bad"

    def decide(self, state, now):
        t = state.waiting_tickets()[0]
        return [Assignment(t.idx, "B1", "refund")]


def test_illegal_assignment_raises() -> None:
    world = make_world([0], [10], [agent("B1", "B", {"refund"})], language=["hi"])
    with pytest.raises(ValueError, match="language"):
        simulate(world, BadPolicy(), 0, 100, decide_every_min=1)


class UsesOffShiftAgent:
    name = "off-shift"

    def decide(self, state, now):
        return [Assignment(t.idx, "late", "refund") for t in state.waiting_tickets()]


def test_off_shift_agent_cannot_start_work() -> None:
    late = Agent("late", "late", "B", frozenset({"refund"}), frozenset({"refund"}), frozenset({"en"}),
                 shift_start_min=600, shift_minutes=60, days_off=frozenset())
    world = make_world([0], [10], [late, agent("early", "A", {"late_delivery"})])
    with pytest.raises(ValueError, match="not on shift"):
        simulate(world, UsesOffShiftAgent(), 0, 100, decide_every_min=1)


def test_same_ticket_same_luck_across_policies() -> None:
    rng = np.random.default_rng(0)
    n = 200
    created = np.sort(rng.uniform(0, 600, n))
    handles = rng.exponential(8, (n, 3))
    pr = list(rng.choice(["P1", "P2", "P3"], n))
    agents = [agent(f"B{k}", "B", {"refund"}) for k in range(3)]
    world = make_world(created, handles, agents, priority=pr)
    a = by_id(simulate(world, baseline_a(), 0, 600, decide_every_min=2))
    b = by_id(simulate(world, baseline_b(), 0, 600, decide_every_min=2))
    assert np.allclose(a["handled_min"].to_numpy(), b["handled_min"].to_numpy())
    assert not np.allclose(a["resolution_min"].to_numpy(), b["resolution_min"].to_numpy())


def erlang_c_wait(arrival_rate: float, mean_service: float, servers: int) -> float:
    a = arrival_rate * mean_service
    top = a**servers / math.factorial(servers) * servers / (servers - a)
    bottom = sum(a**k / math.factorial(k) for k in range(servers)) + top
    prob_wait = top / bottom
    return prob_wait / (servers / mean_service - arrival_rate)


def test_matches_erlang_c() -> None:
    rng = np.random.default_rng(42)
    n = 60_000
    created = np.cumsum(rng.exponential(1 / 0.24, n))
    handles = rng.exponential(10.0, (n, 3))
    agents = [agent(f"B{k}", "B", {"refund"}) for k in range(3)]
    world = make_world(created, handles, agents, sla=1e9)
    end = float(created[-1]) + 1
    warmup = 2_000.0
    out = simulate(world, baseline_a(), 0, end, metric_start_min=warmup, decide_every_min=5).tickets
    simulated = out["wait_min"].mean()
    expected = erlang_c_wait(0.24, 10.0, 3)
    assert simulated == pytest.approx(expected, rel=0.05)
