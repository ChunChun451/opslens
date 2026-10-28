import math

import numpy as np
import pandas as pd
import pytest

from opslens.policies import OpsLensPolicy, OpsLensSettings, cross_estimates, reopen_estimates
from tests.test_live_risk import DIST, agent, run
from tests.test_optimize import WEIGHTS
from tests.test_simulate import make_world

EST = {"cross_factor": 1.6, "reopen_trained": 0.04, "reopen_cross": 0.15, "reopen_handle_factor": 0.6}


def policy(world, **flags):
    return OpsLensPolicy(world, {}, None, WEIGHTS, OpsLensSettings(use_risk=False, **flags), handle_dist=DIST,
                         estimates=EST)


def test_reopen_rate_and_work_factor_come_from_training_history_only() -> None:
    rng = np.random.default_rng(3)
    n = 60_000
    first = np.exp(math.log(5.0) + 0.5 * rng.standard_normal(n))
    second = np.exp(math.log(5.0) + 0.5 * rng.standard_normal(n))
    reopened = rng.random(n) < 0.05
    history = pd.DataFrame({
        "created_at": pd.Timestamp("2026-08-31") + pd.to_timedelta(rng.uniform(0, 56 * 1440, n), unit="m"),
        "final_category": "refund", "channel": "chat", "transfers": 0, "resolution_min": 10.0,
        "reopens": reopened.astype(int), "handled_min": first + np.where(reopened, 0.6 * second, 0.0)})
    late = history["created_at"] >= pd.Timestamp("2026-08-31") + pd.Timedelta(days=35)
    history.loc[late, "reopens"] = 1
    est = reopen_estimates(history, "2026-08-31")
    assert est["reopen_trained"] == pytest.approx(0.05, abs=0.004)
    assert est["reopen_handle_factor"] == pytest.approx(0.6, abs=0.06)


def test_cross_slowdown_and_reopen_are_fitted_from_observed_jobs() -> None:
    rng = np.random.default_rng(5)
    n = 3000
    reopened = rng.random(n) < 0.15
    jobs = pd.DataFrame({"category": "refund", "channel": "chat", "transfers": 0, "reopens": reopened.astype(int),
                         "reopened": reopened,
                         "minutes": 1.6 * np.exp(math.log(4.0) + 0.3 * rng.standard_normal(n))})
    est = cross_estimates(jobs, DIST)
    assert est["cross_factor"] == pytest.approx(1.6, rel=0.03)
    assert est["reopen_cross"] == pytest.approx(0.15, abs=0.02)


def test_lost_ticket_waits_behind_a_savable_one() -> None:
    world = make_world([0.0, 1.0, 15.0], [20.0, 5.0, 5.0], [agent("X", {"refund"})],
                       priority=["P2", "P1", "P3"], sla=60.0)
    world.sla_min[1] = 15.0
    plain = run(world, policy(world))
    lane = run(world, policy(world, lost_lane=True))
    assert plain.loc["T000001", "first_pickup_min"] < plain.loc["T000002", "first_pickup_min"]
    assert lane.loc["T000002", "first_pickup_min"] < lane.loc["T000001", "first_pickup_min"]
    assert not math.isnan(lane.loc["T000001", "resolved_min"])


def test_cross_skill_only_when_the_slower_work_can_fit() -> None:
    for sla, served in ((15.0, True), (3.0, False)):
        world = make_world([0.0], [4.0], [agent("Y", {"app_bug"}, team="D")], priority=["P1"], sla=sla)
        out = run(world, policy(world, clock_cross_gate=True), end=60)
        assert (not math.isnan(out.loc["T000000", "first_pickup_min"])) == served


def test_p1_guard_keeps_the_only_agent_for_a_savable_p1() -> None:
    world = make_world([0.0, 1.0, 100.0], [100.0, 5.0, 5.0], [agent("X", {"refund"})],
                       priority=["P2", "P3", "P1"], sla=600.0)
    world.sla_min[2] = 15.0
    plain = run(world, policy(world), end=300)
    guard = run(world, policy(world, p1_guard=True), end=300)
    assert plain.loc["T000001", "first_pickup_min"] < plain.loc["T000002", "first_pickup_min"]
    assert guard.loc["T000002", "first_pickup_min"] < guard.loc["T000001", "first_pickup_min"]
