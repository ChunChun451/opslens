"""Optimiser and OpsLens policy (tiny worlds, no risk model needed)."""

import numpy as np

from opslens.optimize import Candidate, SolveStats, greedy, solve, ticket_value
from opslens.policies import OpsLensPolicy, OpsLensSettings
from opslens.simulate import Agent, simulate
from tests.test_simulate import make_world

WEIGHTS = {
    "urgency_weight": {"P1": 3.0, "P2": 1.5, "P3": 1.0}, "gold_weight": 1.5, "order_value_weight": 0.1,
    "rescue_floor": 0.05, "aging_per_hour": 0.5, "mismatch_penalty": 2.0, "cross_skill_min_rescue": 0.5,
    "scarcity_weight": 0.3, "max_wait_min": 240, "starvation_bonus": 50.0, "risk_refresh_min": 3,
    "new_ticket_rescue": 0.3, "top_k_per_agent": 30, "time_budget_s": 1.0,
}


def test_flow_beats_greedy_on_the_docstring_example() -> None:
    # Kavita can take T1 (Hindi) or T2; Rahul only T2. Greedy gives Kavita her best (T2 here),
    # leaving T1 unserved. The flow serves both.
    cands = [Candidate(1, "kavita", 0.80, False, "refund", ""), Candidate(2, "kavita", 0.90, False, "refund", ""),
             Candidate(2, "rahul", 0.60, False, "refund", "")]
    slots = {"kavita": 1, "rahul": 1}
    flow = {(c.ticket_idx, c.agent_id) for c in solve(cands, slots, 1.0)}
    assert flow == {(1, "kavita"), (2, "rahul")}
    assert {(c.ticket_idx, c.agent_id) for c in greedy(cands, slots)} == {(2, "kavita")}


def test_solve_respects_slots_and_uniqueness() -> None:
    rng = np.random.default_rng(0)
    cands = [Candidate(t, a, float(rng.uniform(0.1, 2)), False, "x", "") for t in range(20) for a in ("a", "b", "c")]
    stats = SolveStats()
    chosen = solve(cands, {"a": 2, "b": 1, "c": 3}, 1.0, stats)
    assert len(chosen) == 6 and len({c.ticket_idx for c in chosen}) == 6
    assert sum(c.agent_id == "a" for c in chosen) == 2 and stats.solves == 1 and stats.fallbacks == 0


def test_negative_values_are_left_unassigned() -> None:
    assert solve([Candidate(1, "a", -0.5, True, "x", "")], {"a": 1}, 1.0) == []


def test_ticket_value_guard_and_gold() -> None:
    base = ticket_value("P2", "normal", 350, 0.3, 30, WEIGHTS)
    assert ticket_value("P2", "gold", 350, 0.3, 30, WEIGHTS) > base
    assert ticket_value("P2", "normal", 350, 0.3, 300, WEIGHTS) > base + 40  # starvation guard
    assert ticket_value("P1", "normal", 350, 0.3, 30, WEIGHTS) == 2 * base  # urgency 3 vs 1.5


def agent(agent_id, skills, langs=("en",), team="B"):
    return Agent(agent_id, agent_id, team, frozenset(skills), frozenset(skills), frozenset(langs),
                 shift_start_min=0, shift_minutes=1440, days_off=frozenset())


def run_policy(world, settings=None):
    policy = OpsLensPolicy(world, {}, None, WEIGHTS, settings or OpsLensSettings(use_risk=False))
    return simulate(world, policy, 0, 300, decide_every_min=1).tickets.set_index("ticket_id"), policy


def test_language_never_violated_and_cross_skill_needs_danger() -> None:
    # One Hindi refund ticket, one English-only refund agent, one Hindi app agent.
    world = make_world([0], [10], [agent("en_refund", {"refund"}), agent("hi_app", {"app_bug"}, ("en", "hi"))],
                       language=["hi"], true_cat=["refund"], sla=60)
    out, _ = run_policy(world)
    # Without the risk model rescue is 0.3 < 0.5: the Hindi app agent may NOT do a cross-skill job,
    # and the English agent can never serve Hindi. So the ticket waits (and breaches).
    assert np.isnan(out.loc["T000000", "resolution_min"])


def test_v4_prices_cross_skill_in_risk_units() -> None:
    # A Hindi P2 refund in danger (rescue 0.9) and only a Hindi-speaking agent NOT trained on refunds.
    w = {**WEIGHTS, "new_ticket_rescue": 0.9}
    world = make_world([0], [20], [agent("hi_app", {"app_bug"}, ("en", "hi"))], language=["hi"],
                       true_cat=["refund"], sla=60)
    v3 = simulate(world, OpsLensPolicy(world, {}, None, w, OpsLensSettings(use_risk=False)), 0, 300,
                  decide_every_min=1).tickets.set_index("ticket_id")
    # v3: value 1.59 x 0.9 - 2.0 < 0, so it waits until aging lifts it (~43 min); 1.6 x 20 = 32 min of work: breach.
    assert v3.loc["T000000", "wait_min"] > 40 and v3.loc["T000000", "breached"]
    v4 = simulate(world, OpsLensPolicy(world, {}, None, {**w, "mismatch_cost": 0.4}, OpsLensSettings(use_risk=False)),
                  0, 300, decide_every_min=1).tickets.set_index("ticket_id")
    # v4: 1.59 x (0.9 - 0.4) > 0 at once: served at minute 0, done at minute 32 < 60.
    assert v4.loc["T000000", "wait_min"] == 0 and not v4.loc["T000000", "breached"]


def test_rare_agent_is_never_idle_with_only_common_work() -> None:
    # Only a Hindi+refund agent (rare pair) is on shift; only English refunds are waiting.
    world = make_world([0, 0], [10, 10], [agent("kavita", {"refund"}, ("en", "hi"))], language=["en", "en"])
    out, _ = run_policy(world, OpsLensSettings(use_risk=False, use_scarcity=True))
    assert sorted(out["resolution_min"].tolist()) == [10, 20]  # she works through both, never idle


def test_v2_aging_is_in_sla_units_and_capped() -> None:
    w = {**WEIGHTS, "aging_in_sla_units": True, "aging_per_sla": 1.0, "aging_cap": 1.0, "max_late_min": 240}
    fresh_p1 = ticket_value("P1", "normal", 350, 0.0, 30, w, sla_min=60)    # half its SLA waited
    old_p3 = ticket_value("P3", "normal", 350, 0.0, 600, w, sla_min=1440)   # 10 h of a 24 h SLA
    assert fresh_p1 > old_p3  # P1 time is 24x more precious
    lost = ticket_value("P2", "normal", 350, 0.0, 400, w, sla_min=240)       # 160 min past SLA
    more_lost = ticket_value("P2", "normal", 350, 0.0, 470, w, sla_min=240)  # 230 min past SLA
    assert lost == more_lost  # stops gaining once past its SLA (cap)
    assert ticket_value("P2", "normal", 350, 0.0, 481, w, sla_min=240) > lost + 40  # guard: 241 min late
