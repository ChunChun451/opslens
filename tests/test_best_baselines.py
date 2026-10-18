"""The published rules (least slack first, generalized c-mu) and the clairvoyant ceiling.
Tiny hand-computed cases: one agent busy with T0 until minute 30, the rest wait."""

import numpy as np
import pandas as pd
import pytest

from opslens.policies import (ClairvoyantSlackPolicy, GeneralizedCMuPolicy, LeastSlackPolicy, baseline_c,
                              expected_handle_minutes)
from opslens.simulate import TicketView, simulate
from tests.test_simulate import agent, by_id, make_world

HANDLE = {"refund": 10.0, "missing_item": 10.0}


def test_least_slack_defers_a_ticket_that_cannot_make_it() -> None:
    # At 30: T1 due 41, expected 10 → slack 1 (savable). T2 due 36 → slack −4 (hopeless).
    # T3 due 101 → slack 61. Least slack: T1 30-40 (made it), T3 40-50, T2 50-60 → 1 breach.
    # EDF (Baseline C) serves T2 first (36 < 41): T2 ends 40, T1 ends 50 → both late.
    world = make_world([0, 1, 1, 1], [30, 10, 10, 10], [agent("X", "B", {"refund"})])
    world.sla_min = np.array([600.0, 40.0, 35.0, 100.0])
    lsf = by_id(simulate(world, LeastSlackPolicy(world, {}, HANDLE), 0, 200, decide_every_min=1))
    edf = by_id(simulate(world, baseline_c(), 0, 200, decide_every_min=1))
    assert lsf["resolved_min"].tolist() == [30, 40, 60, 50]
    assert lsf["breached"].sum() == 1
    assert edf["breached"].sum() == 2


def test_least_slack_uses_the_expected_handle_time() -> None:
    # Same deadline (due 61) for both; at 30 the missing-item ticket expects 25 min (slack 6),
    # the refund 10 min (slack 21): the one with less slack goes first.
    world = make_world([0, 1, 1], [30, 10, 25], [agent("X", "B", {"refund", "missing_item"})],
                       true_cat=["refund", "refund", "missing_item"])
    world.sla_min = np.array([600.0, 60.0, 60.0])
    handle = {"refund": 10.0, "missing_item": 25.0}
    out = by_id(simulate(world, LeastSlackPolicy(world, {}, handle), 0, 200, decide_every_min=1))
    assert out.loc["T000002", "resolved_min"] == 55
    assert out.loc["T000001", "resolved_min"] == 65


def test_cmu_index_matches_the_docstring_example() -> None:
    world = make_world([0], [10], [agent("X", "B", {"refund"})])
    policy = GeneralizedCMuPolicy(world, {}, {("refund", "chat"): 9.99}, tau=0.25, beta=1.0)

    def view(created: float, sla: float) -> TicketView:
        return TicketView(0, "T000000", created, created, "chat", "P1", "en", "normal", 300.0, "refund",
                          None, created + sla, 0, 0)
    now = 20 * 60
    assert policy.index(view(19 * 60 + 15, 60), now) == pytest.approx(0.000449, abs=5e-7)
    assert policy.index(view(16 * 60 + 30, 240), now) == pytest.approx(0.000157, abs=5e-7)


def test_cmu_serves_the_late_ticket_and_then_the_short_one() -> None:
    # At 30: T1 (SLA 20) is 9 min late, T2 and T3 (SLA 60) still have time. c-mu: T1 first, the
    # opposite of least slack. Between T2 and T3 (same age and SLA) the shorter job wins:
    # T3 (missing_item, expected 5) before T2 (refund, expected 20).
    world = make_world([0, 1, 1, 1], [30, 10, 10, 5], [agent("X", "B", {"refund", "missing_item"})],
                       true_cat=["refund", "refund", "refund", "missing_item"])
    world.sla_min = np.array([600.0, 20.0, 60.0, 60.0])
    handle = {"refund": 20.0, "missing_item": 5.0}
    for beta in (0.0, 1.0):
        out = by_id(simulate(world, GeneralizedCMuPolicy(world, {}, handle, tau=0.25, beta=beta), 0, 200,
                             decide_every_min=1))
        assert out["resolved_min"].tolist() == [30, 40, 55, 45]


def test_clairvoyant_knows_the_true_handle_time_and_category() -> None:
    # At 30: T1 due 41 but its true handle time is 14 → slack −3, hopeless; T2 due 50, true 4 →
    # slack 16. Clairvoyant: T2 30-34, then T1 34-48. Least slack (expects 10 for both) takes
    # T1 first (slack 1 < 10) and then T2 ends at 48: 1 breach either way, but the clairvoyant
    # one is the hopeless ticket and T2 is done 14 min sooner.
    world = make_world([0, 1, 1], [30, 14, 4], [agent("X", "B", {"refund"})])
    world.sla_min = np.array([600.0, 40.0, 49.0])
    clair = by_id(simulate(world, ClairvoyantSlackPolicy(world), 0, 200, decide_every_min=1))
    lsf = by_id(simulate(world, LeastSlackPolicy(world, {}, HANDLE), 0, 200, decide_every_min=1))
    assert clair["resolved_min"].tolist() == [30, 48, 34]
    assert lsf["resolved_min"].tolist() == [30, 44, 48]

    # The customer picked "refund" but it is a missing item: the clairvoyant sends it straight
    # to Y (missing_item) — no transfer. Least slack trusts the (empty) prediction → menu → X.
    world = make_world([0], [10], [agent("X", "B", {"refund"}), agent("Y", "C", {"missing_item"})],
                       true_cat=["missing_item"], selected=["refund"])
    assert by_id(simulate(world, ClairvoyantSlackPolicy(world), 0, 200, decide_every_min=1))["transfers"].tolist() == [0]
    assert by_id(simulate(world, LeastSlackPolicy(world, {}, HANDLE), 0, 200, decide_every_min=1))["transfers"].tolist() == [1]


def test_expected_handle_uses_training_days_and_first_attempts_only() -> None:
    history = pd.DataFrame({
        "created_at": ["2026-08-31 10:00", "2026-09-01 10:00", "2026-09-02 10:00", "2026-10-10 10:00"],
        "final_category": ["refund"] * 4, "channel": ["chat", "chat", "email", "chat"],
        "handled_min": [8.0, 30.0, 6.0, 99.0], "reopens": [0, 1, 0, 0], "resolution_min": [20.0] * 4,
    })
    out = expected_handle_minutes(history, "2026-08-31", last_day=35)
    # Row 2 was reopened, row 4 is day 41 (validation): neither counts.
    assert out == {("refund", "chat"): 8.0, ("refund", "email"): 6.0, "refund": 7.0}
