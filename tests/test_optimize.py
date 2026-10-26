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
    assert ticket_value("P2", "normal", 350, 0.3, 300, WEIGHTS) > base + 40
    assert ticket_value("P1", "normal", 350, 0.3, 30, WEIGHTS) == 2 * base


def agent(agent_id, skills, langs=("en",), team="B"):
    return Agent(agent_id, agent_id, team, frozenset(skills), frozenset(skills), frozenset(langs),
                 shift_start_min=0, shift_minutes=1440, days_off=frozenset())


def run_policy(world, settings=None):
    policy = OpsLensPolicy(world, {}, None, WEIGHTS, settings or OpsLensSettings(use_risk=False))
    return simulate(world, policy, 0, 300, decide_every_min=1).tickets.set_index("ticket_id"), policy


def test_language_never_violated_and_cross_skill_needs_danger() -> None:
    world = make_world([0], [10], [agent("en_refund", {"refund"}), agent("hi_app", {"app_bug"}, ("en", "hi"))],
                       language=["hi"], true_cat=["refund"], sla=60)
    out, _ = run_policy(world)
    assert np.isnan(out.loc["T000000", "resolution_min"])


def test_v4_prices_cross_skill_in_risk_units() -> None:
    w = {**WEIGHTS, "new_ticket_rescue": 0.9}
    world = make_world([0], [20], [agent("hi_app", {"app_bug"}, ("en", "hi"))], language=["hi"],
                       true_cat=["refund"], sla=60)
    v3 = simulate(world, OpsLensPolicy(world, {}, None, w, OpsLensSettings(use_risk=False)), 0, 300,
                  decide_every_min=1).tickets.set_index("ticket_id")
    assert v3.loc["T000000", "wait_min"] > 40 and v3.loc["T000000", "breached"]
    v4 = simulate(world, OpsLensPolicy(world, {}, None, {**w, "mismatch_cost": 0.4}, OpsLensSettings(use_risk=False)),
                  0, 300, decide_every_min=1).tickets.set_index("ticket_id")
    assert v4.loc["T000000", "wait_min"] == 0 and not v4.loc["T000000", "breached"]


def test_v5_rescues_cross_skill_only_when_no_trained_agent_comes_in_time() -> None:
    w = {**WEIGHTS, "new_ticket_rescue": 0.9, "roster_margin_min": 15}

    def trained_from(start_min):
        return Agent("hi_refund", "hi_refund", "B", frozenset({"refund"}), frozenset({"refund"}),
                     frozenset({"en", "hi"}), shift_start_min=start_min, shift_minutes=480, days_off=frozenset())

    def run(world, weights):
        policy = OpsLensPolicy(world, {}, None, weights, OpsLensSettings(use_risk=False))
        return simulate(world, policy, 0, 300, decide_every_min=1).tickets.set_index("ticket_id").loc["T000000"]

    late = make_world([0], [20], [agent("hi_app", {"app_bug"}, ("en", "hi")), trained_from(600)], language=["hi"],
                      true_cat=["refund"], sla=60)
    assert run(late, w)["wait_min"] == 0 and not run(late, w)["breached"]
    assert run(late, WEIGHTS | {"new_ticket_rescue": 0.9})["breached"]
    soon = make_world([0], [20], [agent("hi_app", {"app_bug"}, ("en", "hi")), trained_from(20)], language=["hi"],
                      true_cat=["refund"], sla=60)
    row = run(soon, w)
    assert row["wait_min"] == 20 and row["last_agent"] == "hi_refund" and not row["breached"]


def test_rare_agent_is_never_idle_with_only_common_work() -> None:
    world = make_world([0, 0], [10, 10], [agent("kavita", {"refund"}, ("en", "hi"))], language=["en", "en"])
    out, _ = run_policy(world, OpsLensSettings(use_risk=False, use_scarcity=True))
    assert sorted(out["resolution_min"].tolist()) == [10, 20]


def test_v2_aging_is_in_sla_units_and_capped() -> None:
    w = {**WEIGHTS, "aging_in_sla_units": True, "aging_per_sla": 1.0, "aging_cap": 1.0, "max_late_min": 240}
    fresh_p1 = ticket_value("P1", "normal", 350, 0.0, 30, w, sla_min=60)
    old_p3 = ticket_value("P3", "normal", 350, 0.0, 600, w, sla_min=1440)
    assert fresh_p1 > old_p3
    lost = ticket_value("P2", "normal", 350, 0.0, 400, w, sla_min=240)
    more_lost = ticket_value("P2", "normal", 350, 0.0, 470, w, sla_min=240)
    assert lost == more_lost
    assert ticket_value("P2", "normal", 350, 0.0, 481, w, sla_min=240) > lost + 40
