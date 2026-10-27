import numpy as np
import pandas as pd

from opslens.impact import summarize
from opslens.policies import baseline_a, baseline_b
from opslens.simulate import Overrides, simulate
from tests.test_simulate import agent, by_id, make_world


def two_agents_three_tickets():
    return make_world([0, 0, 0], [10, 20, 5], [agent("X", "B", {"refund"}), agent("Y", "B", {"refund"})])


def test_no_overrides_and_empty_overrides_give_the_same_day() -> None:
    rng = np.random.default_rng(7)
    created = np.sort(rng.uniform(0, 300, 40))
    world = make_world(created, rng.uniform(5, 30, 40), [agent("X", "B", {"refund"}), agent("Y", "B", {"refund"})],
                       priority=list(rng.choice(["P1", "P2", "P3"], 40)), sla=60.0)
    plain = simulate(world, baseline_b(), 0, 300, decide_every_min=1)
    empty = simulate(world, baseline_b(), 0, 300, decide_every_min=1, overrides=Overrides())
    pd.testing.assert_frame_equal(plain.tickets, empty.tickets)
    assert summarize(plain) == summarize(empty)
    assert plain.agent_busy_minutes == empty.agent_busy_minutes


def test_resuming_from_a_checkpoint_gives_the_same_day() -> None:
    rng = np.random.default_rng(3)
    created = np.sort(rng.uniform(0, 300, 40))
    world = make_world(created, rng.uniform(5, 30, 40), [agent("X", "B", {"refund"}), agent("Y", "B", {"refund"})])
    whole = simulate(world, baseline_b(), 0, 300, decide_every_min=1, checkpoint_at=(100.0, 200.0))
    assert [c.minute for c in whole.checkpoints] == [100.0, 200.0]
    cp = whole.checkpoints[0]
    again = simulate(world, cp.restore_policy(), 0, 300, decide_every_min=1, resume=cp)
    pd.testing.assert_frame_equal(whole.tickets, again.tickets)


def test_decline_sends_the_ticket_to_the_other_agent() -> None:
    world = two_agents_three_tickets()
    plain = by_id(simulate(world, baseline_a(), 0, 100, decide_every_min=1))
    assert plain.loc["T000002", "last_agent"] == "X" and plain.loc["T000002", "resolved_min"] == 15
    declined = Overrides(forbidden={("X", 2): 0.0})
    out = by_id(simulate(world, baseline_a(), 0, 100, decide_every_min=1, overrides=declined))
    assert out.loc["T000002", "last_agent"] == "Y"
    assert out.loc["T000002", "first_pickup_min"] == 20 and out.loc["T000002", "resolved_min"] == 25
    assert out["resolved_min"].tolist()[:2] == [10, 20]


def test_decline_only_counts_from_its_minute() -> None:
    world = two_agents_three_tickets()
    late = Overrides(forbidden={("X", 2): 12.0})
    out = by_id(simulate(world, baseline_a(), 0, 100, decide_every_min=1, overrides=late))
    assert out.loc["T000002", "last_agent"] == "X" and out.loc["T000002", "resolved_min"] == 15


def test_done_early_frees_the_agent_at_that_minute() -> None:
    world = two_agents_three_tickets()
    done = Overrides(finishes=[(6.0, "X", 0, "at", 6.0)])
    result = simulate(world, baseline_a(), 0, 100, decide_every_min=1, overrides=done)
    out = by_id(result)
    assert out.loc["T000000", "resolved_min"] == 6 and out.loc["T000000", "handled_min"] == 6
    assert out.loc["T000002", "first_pickup_min"] == 6 and out.loc["T000002", "resolved_min"] == 11
    assert result.agent_busy_minutes["X"] == 11


def test_done_later_than_simulated_keeps_the_agent_busy() -> None:
    world = two_agents_three_tickets()
    done = Overrides(finishes=[(8.0, "X", 0, "at", 30.0)])
    out = by_id(simulate(world, baseline_a(), 0, 100, decide_every_min=1, overrides=done))
    assert out.loc["T000000", "resolved_min"] == 30
    assert out.loc["T000002", "last_agent"] == "Y" and out.loc["T000002", "resolved_min"] == 25


def test_extra_time_moves_the_end_of_the_current_work() -> None:
    world = two_agents_three_tickets()
    extra = Overrides(finishes=[(3.0, "X", 0, "extra", 5.0)])
    out = by_id(simulate(world, baseline_a(), 0, 100, decide_every_min=1, overrides=extra))
    assert out.loc["T000000", "resolved_min"] == 15
    assert out.loc["T000002", "first_pickup_min"] == 15 and out.loc["T000002", "resolved_min"] == 20


def test_a_change_for_work_that_already_ended_does_nothing() -> None:
    world = two_agents_three_tickets()
    plain = simulate(world, baseline_a(), 0, 100, decide_every_min=1)
    stale = Overrides(finishes=[(12.0, "X", 0, "at", 12.0)])
    again = simulate(world, baseline_a(), 0, 100, decide_every_min=1, overrides=stale)
    pd.testing.assert_frame_equal(plain.tickets, again.tickets)


def test_break_keeps_new_work_away_until_back() -> None:
    world = two_agents_three_tickets()
    away = Overrides(breaks={"X": [(10.0, 30.0)]})
    result = simulate(world, baseline_a(), 0, 100, decide_every_min=1, overrides=away, floor_window=(0, 40))
    out = by_id(result)
    assert out.loc["T000002", "last_agent"] == "Y" and out.loc["T000002", "resolved_min"] == 25
    status = {f["minute"]: f["agents"]["X"] for f in result.floor}
    assert (status[5], status[15], status[30]) == ("busy", "break", "idle")


def test_resume_with_a_new_action_matches_a_fresh_run() -> None:
    world = two_agents_three_tickets()
    base = simulate(world, baseline_a(), 0, 100, decide_every_min=1, checkpoint_at=(5.0,))
    change = Overrides(finishes=[(6.0, "X", 0, "at", 6.0)], forbidden={("X", 2): 6.0})
    fresh = simulate(world, baseline_a(), 0, 100, decide_every_min=1, overrides=change)
    cp = base.checkpoints[0]
    resumed = simulate(world, cp.restore_policy(), 0, 100, decide_every_min=1, overrides=change, resume=cp)
    pd.testing.assert_frame_equal(fresh.tickets, resumed.tickets)
    out = by_id(resumed)
    assert out.loc["T000000", "resolved_min"] == 6 and out.loc["T000002", "last_agent"] == "Y"


def small_live_day():
    from opslens.live import LiveDay

    start = 47 * 1440.0
    live = LiveDay(day=48, seed=1, start=start, agents=[{"id": "A01", "team": "A"}, {"id": "A02", "team": "A"}])
    live.floors["opslens"] = [{"minute": start + 5 * k, "status": "bi", "queues": {}} for k in range(288)]
    live.tickets["opslens"] = pd.DataFrame({"created": [start + 5], "pickup": [start + 10], "resolved": [start + 40],
                                            "deadline": [start + 65], "ticket_id": ["T1"]})
    job = {"minute": start + 10, "ticket_id": "T1", "reason": "in turn", "created": start + 5, "deadline": start + 65,
           "resolved": start + 40, "priority": "P2", "category": "refund", "language": "en", "text": "refund please"}
    live.work = {"A01": [job]}
    live.context = {"index": {"T1": 0, "T2": 1}}
    return live


def test_an_action_names_the_ticket_the_agent_is_on() -> None:
    import pytest

    from server.app import _new_action

    live = small_live_day()
    done = _new_action({"kind": "done", "agent": "A01"}, live, 20.0)
    assert done == {"kind": "done", "agent": "A01", "minute": 20.0, "ticket_id": "T1"}
    extra = _new_action({"kind": "extra_time", "agent": "A01", "value": 10}, live, 20.0)
    assert extra["value"] == 10 and extra["ticket_id"] == "T1"
    assert _new_action({"kind": "decline", "agent": "A02", "ticket_id": "T2", "reason": "Language"}, live, 20.0)["reason"] == "Language"
    for bad in ({"kind": "done", "agent": "A02"}, {"kind": "fly", "agent": "A01"}, {"kind": "decline", "agent": "A01", "ticket_id": "T9"},
                {"kind": "extra_time", "agent": "A01", "value": 500}, {"kind": "back", "agent": "A01"}, {"kind": "done", "agent": "Z"}):
        with pytest.raises(ValueError):
            _new_action(bad, live, 20.0)


def test_outcome_is_only_known_once_it_happened() -> None:
    from opslens.live import outcome_at

    job = {"deadline": 60.0, "resolved": 50.0}
    assert (outcome_at(job, 40), outcome_at(job, 55)) == ("open", "kept")
    late = {"deadline": 60.0, "resolved": 80.0}
    assert (outcome_at(late, 59), outcome_at(late, 61), outcome_at(late, 90)) == ("open", "missed", "missed")
    assert outcome_at(None, 10) is None


def test_overrides_from_turns_the_log_into_simulator_changes() -> None:
    from opslens.live import overrides_from

    live = small_live_day()
    log = ({"kind": "decline", "agent": "A02", "ticket_id": "T2", "minute": 30.0},
           {"kind": "done", "agent": "A01", "ticket_id": "T1", "minute": 31.0},
           {"kind": "extra_time", "agent": "A01", "ticket_id": "T1", "minute": 32.0, "value": 10.0},
           {"kind": "break", "agent": "A02", "minute": 40.0}, {"kind": "back", "agent": "A02", "minute": 55.0},
           {"kind": "take", "agent": "A01", "ticket_id": "T2", "minute": 56.0})
    out = overrides_from(live, log)
    s = live.start
    assert out.forbidden == {("A02", 1): s + 30}
    assert out.finishes == [(s + 31, "A01", 0, "at", s + 31), (s + 32, "A01", 0, "extra", 10.0)]
    assert out.breaks == {"A02": [(s + 40, s + 55)]}
    assert overrides_from(live, log[-1:]) is None
