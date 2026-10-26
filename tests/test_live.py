import pandas as pd

from opslens.live import LiveDay, clock, matching_test_day, state_at


def test_matching_test_day_has_todays_weekday() -> None:
    assert matching_test_day(5, 0, (43, 56)) == 48
    for weekday in range(7):
        day = matching_test_day(weekday, 0, (43, 56))
        assert 43 <= day <= 49 and (day - 1) % 7 == weekday


def test_state_at_counts_waiting_and_missed_at_that_minute() -> None:
    start = 47 * 1440.0
    tickets = pd.DataFrame({
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
    assert (at_100["arrived"], at_100["waiting"], at_100["missed"], at_100["kept"]) == (3, 2, 1, 1)
    assert at_100["queues"] == {"A": [20, 0]}
    assert state_at(live, 260)["policies"]["opslens"]["missed"] == 2
    assert state_at(live, 20)["decisions"][0]["ticket_id"] == "T1"
    assert clock(1274) == "21:14"


def test_live_change_text_is_parsed_and_bounded() -> None:
    import pytest

    from server.app import _parse_agents

    assert _parse_agents("") == ()
    assert _parse_agents("C:-2,b:1,A:0") == (("B", 1), ("C", -2))
    assert _parse_agents("D:9") == (("D", 5),)
    with pytest.raises(ValueError):
        _parse_agents("E:1")


def test_floor_now_follows_one_agent_through_the_day() -> None:
    from opslens.live import floor_now

    start = 47 * 1440.0

    def job(minute, created, deadline, resolved, ticket, reason="in turn"):
        return {"minute": start + minute, "ticket_id": ticket, "reason": reason, "created": start + created,
                "deadline": start + deadline, "resolved": None if resolved is None else start + resolved,
                "priority": "P2", "category": "refund", "language": "hi", "text": "paisa wapas"}

    live = LiveDay(day=48, seed=1, start=start, agents=[{"id": "A01", "team": "A"}])
    live.work = {"A01": [job(10, 5, 65, 30, "T1"), job(40, 35, 60, 90, "T2", "cross-skill rescue"),
                         job(95, 45, 200, None, "T3")]}

    at_50 = floor_now(live, start + 50, "b")[0]
    assert (at_50["done"], at_50["kept"], at_50["rescues"]) == (1, 1, 1)
    assert at_50["current"]["ticket_id"] == "T2" and at_50["current"]["minutes_left"] == 10
    assert at_50["next"]["ticket_id"] == "T3" and at_50["next"]["waited"] == 5

    at_100 = floor_now(live, start + 100, "b")[0]
    assert (at_100["done"], at_100["kept"]) == (2, 1)
    assert at_100["current"]["ticket_id"] == "T3" and at_100["next"] is None

    assert floor_now(live, start + 50, "i")[0]["current"] is None
    assert floor_now(live, start + 50, "i")[0]["status"] == "idle"
