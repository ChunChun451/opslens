import numpy as np
import pandas as pd
import pytest

from opslens.policies import (ClairvoyantSlackPolicy, GeneralizedCMuPolicy, LeastSlackPolicy,
                              LeastSlackRescuePolicy, baseline_c, expected_handle_minutes)
from opslens.simulate import TicketView, simulate
from tests.test_simulate import agent, by_id, make_world

HANDLE = {"refund": 10.0, "missing_item": 10.0}


def test_least_slack_defers_a_ticket_that_cannot_make_it() -> None:
    world = make_world([0, 1, 1, 1], [30, 10, 10, 10], [agent("X", "B", {"refund"})])
    world.sla_min = np.array([600.0, 40.0, 35.0, 100.0])
    lsf = by_id(simulate(world, LeastSlackPolicy(world, {}, HANDLE), 0, 200, decide_every_min=1))
    edf = by_id(simulate(world, baseline_c(), 0, 200, decide_every_min=1))
    assert lsf["resolved_min"].tolist() == [30, 40, 60, 50]
    assert lsf["breached"].sum() == 1
    assert edf["breached"].sum() == 2


def test_least_slack_uses_the_expected_handle_time() -> None:
    world = make_world([0, 1, 1], [30, 10, 25], [agent("X", "B", {"refund", "missing_item"})],
                       true_cat=["refund", "refund", "missing_item"])
    world.sla_min = np.array([600.0, 60.0, 60.0])
    handle = {"refund": 10.0, "missing_item": 25.0}
    out = by_id(simulate(world, LeastSlackPolicy(world, {}, handle), 0, 200, decide_every_min=1))
    assert out.loc["T000002", "resolved_min"] == 55
    assert out.loc["T000001", "resolved_min"] == 65


def test_rescue_sends_a_savable_ticket_to_a_free_cross_skill_agent() -> None:
    world = make_world([0, 1, 1, 1], [30, 10, 10, 10],
                       [agent("X", "B", {"refund"}), agent("Y", "A", {"late_delivery"})])
    world.sla_min = np.array([600.0, 35.0, 12.0, 600.0])
    rescue = by_id(simulate(world, LeastSlackRescuePolicy(world, {}, HANDLE, threshold_min=30), 0, 200,
                            decide_every_min=1))
    lsf = by_id(simulate(world, LeastSlackPolicy(world, {}, HANDLE), 0, 200, decide_every_min=1))
    assert rescue["resolved_min"].tolist() == [30, 17, 50, 40]
    assert rescue["mismatch_used"].tolist() == [False, True, False, False]
    assert rescue["breached"].sum() == 1
    assert lsf["resolved_min"].tolist() == [30, 60, 50, 40]
    assert lsf["breached"].sum() == 2
    strict = by_id(simulate(world, LeastSlackRescuePolicy(world, {}, HANDLE, threshold_min=20), 0, 200,
                            decide_every_min=1))
    assert strict["resolved_min"].tolist() == [30, 23, 50, 40]


def test_rescue_never_beats_a_free_skilled_agent_or_the_language() -> None:
    world = make_world([0], [10], [agent("Y", "A", {"late_delivery"}), agent("Z", "B", {"refund"})])
    world.sla_min = np.array([15.0])
    out = by_id(simulate(world, LeastSlackRescuePolicy(world, {}, HANDLE, threshold_min=30), 0, 200,
                         decide_every_min=1))
    assert out["resolved_min"].tolist() == [10]
    assert out["mismatch_used"].tolist() == [False]
    world = make_world([0, 1], [30, 10], [agent("X", "B", {"refund"}, langs={"en", "hi"}),
                                          agent("Y", "A", {"late_delivery"})], language=["en", "hi"])
    world.sla_min = np.array([600.0, 35.0])
    out = by_id(simulate(world, LeastSlackRescuePolicy(world, {}, HANDLE, threshold_min=30), 0, 200,
                         decide_every_min=1))
    assert out["resolved_min"].tolist() == [30, 40]
    assert out["mismatch_used"].tolist() == [False, False]


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
    world = make_world([0, 1, 1, 1], [30, 10, 10, 5], [agent("X", "B", {"refund", "missing_item"})],
                       true_cat=["refund", "refund", "refund", "missing_item"])
    world.sla_min = np.array([600.0, 20.0, 60.0, 60.0])
    handle = {"refund": 20.0, "missing_item": 5.0}
    for beta in (0.0, 1.0):
        out = by_id(simulate(world, GeneralizedCMuPolicy(world, {}, handle, tau=0.25, beta=beta), 0, 200,
                             decide_every_min=1))
        assert out["resolved_min"].tolist() == [30, 40, 55, 45]


def test_clairvoyant_knows_the_true_handle_time_and_category() -> None:
    world = make_world([0, 1, 1], [30, 14, 4], [agent("X", "B", {"refund"})])
    world.sla_min = np.array([600.0, 40.0, 49.0])
    clair = by_id(simulate(world, ClairvoyantSlackPolicy(world), 0, 200, decide_every_min=1))
    lsf = by_id(simulate(world, LeastSlackPolicy(world, {}, HANDLE), 0, 200, decide_every_min=1))
    assert clair["resolved_min"].tolist() == [30, 48, 34]
    assert lsf["resolved_min"].tolist() == [30, 44, 48]

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
    assert out == {("refund", "chat"): 8.0, ("refund", "email"): 6.0, "refund": 7.0}
