"""Live now (opslens/live.py): the right test day for today's weekday, and the floor at a minute."""

import pandas as pd

from opslens.live import LiveDay, clock, matching_test_day, state_at


def test_matching_test_day_has_todays_weekday() -> None:
    # Day 1 = Monday 31 Aug 2026 (first_weekday 0); test days 43-56. Saturday (5) -> day 48.
    assert matching_test_day(5, 0, (43, 56)) == 48
    for weekday in range(7):
        day = matching_test_day(weekday, 0, (43, 56))
        assert 43 <= day <= 49 and (day - 1) % 7 == weekday


def test_state_at_counts_waiting_and_missed_at_that_minute() -> None:
    start = 47 * 1440.0
    tickets = pd.DataFrame({  # minutes since the start of the simulation
        "created": [start + 10, start + 20, start + 30],
        "pickup": [start + 15, float("nan"), start + 200],
        "resolved": [start + 25, float("nan"), start + 260],
        "deadline": [start + 70, start + 80, start + 250],
    })
    live = LiveDay(day=48, seed=1, start=start, agents=[{"id": "A01", "team": "A"}])
    live.floors["opslens"] = [{"minute": start + 5 * k, "status": "b", "queues": {"A": [k, 0]}} for k in range(288)]
    live.tickets["opslens"] = tickets
    live.decisions = [{"minute": start + 15, "ticket_id": "T1", "agent": "A01", "reason": "r"}]
    at_100 = state_at(live, 100)["policies"]["opslens"]
    # At 01:40: all 3 arrived; T2 and T3 are still waiting; T2's deadline (80) passed unresolved.
    assert (at_100["arrived"], at_100["waiting"], at_100["missed"], at_100["kept"]) == (3, 2, 1, 1)
    assert at_100["queues"] == {"A": [20, 0]}  # the 5-minute frame of minute 100
    # At 04:20: T3 was resolved at 260, after its deadline 250 -> missed too.
    assert state_at(live, 260)["policies"]["opslens"]["missed"] == 2
    assert state_at(live, 20)["decisions"][0]["ticket_id"] == "T1"
    assert clock(1274) == "21:14"


def test_live_change_text_is_parsed_and_bounded() -> None:
    import pytest

    from server.app import _parse_agents

    assert _parse_agents("") == ()
    assert _parse_agents("C:-2,b:1,A:0") == (("B", 1), ("C", -2))
    assert _parse_agents("D:9") == (("D", 5),)  # at most 5 agents either way, as in What-if
    with pytest.raises(ValueError):
        _parse_agents("E:1")
