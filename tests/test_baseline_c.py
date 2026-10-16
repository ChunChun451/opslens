"""Baseline C ("SLA due" sort) and the lateness KPIs (Claude 2 review)."""

import numpy as np
import pandas as pd

from opslens.impact import lateness
from opslens.policies import baseline_a, baseline_c
from opslens.simulate import simulate
from tests.test_simulate import agent, by_id, make_world


def test_sla_due_serves_earliest_deadline_first() -> None:
    # One agent, busy with T0 from 0 to 30. T1 (SLA 100) and T2 (SLA 40) arrive at 1 and wait.
    # At 30 FIFO takes T1 (lower index); Baseline C takes T2 (due at 41, before T1 at 101).
    world = make_world([0, 1, 1], [30, 10, 10], [agent("X", "B", {"refund"})])
    world.sla_min = np.array([600.0, 100.0, 40.0])
    a = by_id(simulate(world, baseline_a(), 0, 200, decide_every_min=1))
    c = by_id(simulate(world, baseline_c(), 0, 200, decide_every_min=1))
    assert a.loc["T000001", "resolved_min"] == 40
    assert c.loc["T000002", "resolved_min"] == 40
    assert not c.loc["T000002", "breached"]


def test_sla_due_puts_already_late_tickets_after_savable_ones() -> None:
    # At 30, T1 is already late (due at 21) and T2 is due at 61: T2 first, then T1.
    world = make_world([0, 1, 1], [30, 10, 10], [agent("X", "B", {"refund"})])
    world.sla_min = np.array([600.0, 20.0, 60.0])
    c = by_id(simulate(world, baseline_c(), 0, 200, decide_every_min=1))
    assert c.loc["T000002", "resolved_min"] == 40
    assert c.loc["T000001", "resolved_min"] == 50
    assert c["breached"].sum() == 1


def test_lateness_matches_the_docstring_example() -> None:
    t = pd.DataFrame({"created_min": [0.0, 0.0, 0.0], "resolved_min": [50.0, 90.0, 150.0],
                      "resolution_min": [50.0, 90.0, 150.0], "sla_min": [60.0, 60.0, 60.0],
                      "breached": [False, True, True]})
    out = lateness(t)
    assert out["quality.mean_minutes_late"] == 60.0
    assert out["quality.late_minutes_per_100"] == 4000.0


def test_floor_recorder_does_not_change_the_run() -> None:
    world = make_world([0, 1, 2, 3], [30, 30, 30, 30], [agent("X", "B", {"refund"}), agent("Y", "C", {"missing_item"})])
    plain = simulate(world, baseline_a(), 0, 200, decide_every_min=1)
    recorded = simulate(world, baseline_a(), 0, 200, decide_every_min=1, floor_window=(0, 60))
    assert plain.tickets["resolved_min"].tolist() == recorded.tickets["resolved_min"].tolist()
    # At minute 5: X works on T0 (refund, Team B), Y has nothing it can do; 3 refunds wait.
    assert recorded.floor[1] == {"minute": 5, "agents": {"X": "busy", "Y": "idle"}, "queues": {"B": [3, 0]}}
