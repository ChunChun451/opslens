import math

import numpy as np
import pandas as pd
import pytest

from opslens.policies import (LiveNotes, OpsLensPolicy, OpsLensSettings, expected_residual, handle_lognormal,
                              p_longer)
from opslens.risk import RiskModel
from opslens.simulate import Agent, Overrides, simulate
from tests.test_optimize import WEIGHTS
from tests.test_simulate import make_world

LIVE = OpsLensSettings(use_risk=False, use_live_risk=True)
DIST = {"refund": (math.log(4.0), 0.3), "restaurant_partner": (math.log(12.0), 0.3), "app_bug": (math.log(5.0), 0.3)}


def agent(agent_id, skills, extra=(), langs=("en",), team="B"):
    return Agent(agent_id, agent_id, team, frozenset(skills), frozenset(skills) | frozenset(extra), frozenset(langs),
                 shift_start_min=0, shift_minutes=1440, days_off=frozenset())


def live_policy(world, weights=None, notes=None):
    policy = OpsLensPolicy(world, {}, None, {**WEIGHTS, **(weights or {})}, LIVE, handle_dist=DIST)
    if notes is not None:
        policy.notes = notes
    return policy


def run(world, policy, overrides=None, end=200):
    return simulate(world, policy, 0, end, decide_every_min=1, overrides=overrides).tickets.set_index("ticket_id")


def test_lognormal_tail_and_residual_match_simulation() -> None:
    mu, sigma = math.log(5.0), 0.5
    draws = np.exp(mu + sigma * np.random.default_rng(1).standard_normal(400_000))
    assert p_longer(mu, sigma, 5.0) == pytest.approx(0.5)
    assert p_longer(mu, sigma, 8.0) == pytest.approx((draws > 8.0).mean(), abs=0.003)
    assert p_longer(mu, sigma, 0.0) == 1.0
    assert expected_residual(mu, sigma, 0.0) == pytest.approx(draws.mean(), rel=0.01)
    assert expected_residual(mu, sigma, 4.0) == pytest.approx((draws[draws > 4.0] - 4.0).mean(), rel=0.01)


def test_handle_spread_is_learned_on_training_days_only() -> None:
    rng = np.random.default_rng(2)
    n = 4000
    history = pd.DataFrame({
        "created_at": pd.Timestamp("2026-08-31") + pd.to_timedelta(rng.uniform(0, 56 * 1440, n), unit="m"),
        "final_category": "refund", "channel": "chat", "reopens": 0, "resolution_min": 10.0,
        "handled_min": np.exp(math.log(5.0) + 0.5 * rng.standard_normal(n))})
    late = history["created_at"] >= pd.Timestamp("2026-08-31") + pd.Timedelta(days=35)
    history.loc[late, "handled_min"] = 500.0
    mu, sigma = handle_lognormal(history, "2026-08-31")["refund"]
    assert math.exp(mu) == pytest.approx(5.0, rel=0.05) and sigma == pytest.approx(0.5, rel=0.08)


def test_flag_off_keeps_the_old_policy_unchanged() -> None:
    rng = np.random.default_rng(4)
    created = np.sort(rng.uniform(0, 200, 30))
    world = make_world(created, rng.uniform(2, 9, 30), [agent("X", {"refund"}), agent("Y", {"refund"})],
                       priority=list(rng.choice(["P1", "P2", "P3"], 30)), sla=30.0)
    old = OpsLensPolicy(world, {}, None, WEIGHTS, OpsLensSettings(use_risk=False))
    with_dist = OpsLensPolicy(world, {}, None, WEIGHTS, OpsLensSettings(use_risk=False), handle_dist=DIST)
    pd.testing.assert_frame_equal(run(world, old), run(world, with_dist))


def test_fast_features_equal_the_model_features_mid_day() -> None:
    rng = np.random.default_rng(6)
    n = 60
    created = np.sort(rng.uniform(0, 120, n))
    cats = list(rng.choice(["refund", "app_bug", "late_delivery"], n))
    agents = [agent("X", {"refund"}), agent("Y", {"app_bug"}, team="D"), agent("Z", {"late_delivery"}, team="A")]
    world = make_world(created, rng.uniform(3, 12, n), agents, true_cat=cats, selected=cats,
                       priority=list(rng.choice(["P1", "P2", "P3"], n)), language=list(rng.choice(["en", "hi"], n)),
                       sla=30.0)
    categories = {"category_pred": ["app_bug", "late_delivery", "refund"], "priority": ["P1", "P2", "P3"],
                  "channel": ["chat"], "language": ["en", "hi"], "tier": ["gold", "normal"], "team": ["A", "B", "D"],
                  "hour_band": ["night", "morning"]}
    model = RiskModel(booster=None, calibrator=None, categories=categories)
    policy = OpsLensPolicy(world, {}, None, WEIGHTS, OpsLensSettings(use_risk=False))
    policy.risk_model = model
    policy._prepare_live()
    seen = []
    inner = policy.decide

    def decide(state, now):
        waiting = state.waiting_tickets()
        if len(waiting) >= 3:
            on_shift = [k for k in range(len(world.agents)) if state.shift_end(k, now) is not None]
            feats, _, _ = policy.snapshot_features(state, now, waiting)
            fast = policy.context_matrix(policy.context_columns(state, now, waiting, on_shift))
            seen.append(np.allclose(np.nan_to_num(fast), np.nan_to_num(model.matrix(feats))))
        return inner(state, now)

    policy.decide = decide
    simulate(world, policy, 0, 240, decide_every_min=1)
    assert len(seen) > 20 and all(seen)


def tight_p1_world():
    world = make_world([0.0, 1.0], [12.0, 4.0],
                       [agent("X", {"refund", "restaurant_partner"}), agent("Z", {"app_bug"}, team="D")],
                       true_cat=["restaurant_partner", "refund"], priority=["P3", "P1"], sla=30.0)
    world.sla_min = np.array([60.0, 9.0])
    return world


def test_clock_part_sends_a_cross_skill_rescue_only_when_waiting_would_miss() -> None:
    world = tight_p1_world()
    out = run(world, live_policy(world))
    assert out.loc["T000001", "last_agent"] == "Z" and out.loc["T000001", "first_pickup_min"] == 1.0
    roomy = tight_p1_world()
    roomy.sla_min = np.array([60.0, 40.0])
    out = run(roomy, live_policy(roomy))
    assert out.loc["T000001", "last_agent"] == "X" and out.loc["T000001", "first_pickup_min"] == 12.0


def test_cross_skill_that_cannot_fit_the_promise_is_not_tried() -> None:
    world = tight_p1_world()
    world.sla_min = np.array([60.0, 5.0])
    out = run(world, live_policy(world))
    assert out.loc["T000001", "last_agent"] == "X"


def test_every_new_ticket_is_scored_at_once() -> None:
    world = tight_p1_world()
    policy = live_policy(world)
    calls = []
    inner = policy.score_clock

    def score_clock(state, now, waiting, free, on_shift):
        inner(state, now, waiting, free, on_shift)
        calls.append((now, sorted(policy.risk_wait)))

    policy.score_clock = score_clock
    run(world, policy)
    assert (1.0, [1]) in calls


def two_refund_agents_world():
    world = make_world([0.0, 0.0, 2.0], [10.0, 30.0, 4.0],
                       [agent("X", {"refund"}), agent("Y", {"refund", "restaurant_partner"}),
                        agent("Z", {"app_bug"}, team="D")],
                       true_cat=["refund", "restaurant_partner", "refund"], priority=["P3", "P3", "P1"])
    world.sla_min = np.array([90.0, 90.0, 12.0])
    return world


def test_decline_changes_the_decision_in_that_minute() -> None:
    world = make_world([0.0, 0.0], [5.0, 5.0], [agent("X", {"refund"}), agent("Z", {"app_bug"}, team="D")],
                       priority=["P1", "P2"], sla=60.0)
    plain = run(world, live_policy(world))
    assert plain.loc["T000000", "last_agent"] == "X" and plain.loc["T000000", "first_pickup_min"] == 0.0
    declined = run(world, live_policy(world), Overrides(forbidden={("X", 0): 0.0}))
    assert declined.loc["T000001", "last_agent"] == "X" and declined.loc["T000001", "first_pickup_min"] == 0.0
    assert declined.loc["T000000", "first_pickup_min"] > 0.0


def test_done_early_changes_the_decision_in_that_minute() -> None:
    world = two_refund_agents_world()
    plain = run(world, live_policy(world))
    assert plain.loc["T000002", "first_pickup_min"] == 10.0 and plain.loc["T000002", "last_agent"] == "X"
    done = run(world, live_policy(world), Overrides(finishes=[(6.0, "X", 0, "at", 6.0)]))
    assert done.loc["T000002", "first_pickup_min"] == 6.0 and done.loc["T000002", "last_agent"] == "X"


def test_extra_time_changes_the_decision_in_that_minute() -> None:
    world = two_refund_agents_world()
    plain = run(world, live_policy(world))
    assert plain.loc["T000002", "last_agent"] == "X"
    notes = LiveNotes(speed=[], extra=[(3.0, "X", 0, 15.0)])
    extra = run(world, live_policy(world, notes=notes), Overrides(finishes=[(3.0, "X", 0, "extra", 15.0)]))
    assert extra.loc["T000002", "last_agent"] == "Z" and extra.loc["T000002", "first_pickup_min"] == 3.0
    assert extra.loc["T000000", "resolved_min"] == 25.0


def test_a_slow_agent_is_trusted_less_with_a_tight_ticket() -> None:
    world = tight_p1_world()
    world.sla_min = np.array([60.0, 9.0])
    slow = LiveNotes(speed=[(0.0, "Z", 1.8)], extra=[])
    out = run(world, live_policy(world, notes=slow))
    assert out.loc["T000001", "last_agent"] == "X"
    assert slow.speed_of("Z", 0.0) == 1.8 and slow.speed_of("Z", -1.0) == 1.0 and slow.speed_of("X", 5.0) == 1.0


def test_speed_notes_learn_from_done_and_extra_time() -> None:
    from opslens.live import LiveDay, agent_speed, speed_notes

    start = 47 * 1440.0
    live = LiveDay(day=48, seed=1, start=start, agents=[])
    live.context = {"index": {"T1": 0, "T2": 1}, "policy_dist": {"refund": (math.log(5.0), 0.3)},
                    "tickets_info": pd.DataFrame({"category": ["refund", "refund"]}, index=["T1", "T2"])}
    log = ({"kind": "done", "agent": "A", "ticket_id": "T1", "minute": 12.0, "started": 10.0},
           {"kind": "extra_time", "agent": "A", "ticket_id": "T2", "minute": 14.0, "value": 5.0, "started": 12.0,
            "planned_end": 17.0},
           {"kind": "done", "agent": "B", "ticket_id": "T2", "minute": 30.0})
    notes = speed_notes(live, log)
    assert [(at - start, who) for at, who, _ in notes] == [(12.0, "A"), (14.0, "A")]
    assert notes[0][2] == pytest.approx((2 + 0.4) / 3)
    assert notes[1][2] == pytest.approx((2 + 0.4 + 2.0) / 4)
    live.actions = log
    assert agent_speed(live, "A") == pytest.approx(1.1) and agent_speed(live, "B") == 1.0
