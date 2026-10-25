"""Ask OpsLens: the LLM may route a question, never invent a number; offline rules still work."""

import json

from opslens.ask import answer, check_route, rules_route, understand, whatif_request
from opslens.llm.client import LLMClient
from opslens.llm.mock import MockProvider

Q = "What if Team C loses 2 agents on Saturday and volume goes up 20%?"


def client_replying(route: dict) -> LLMClient:
    return LLMClient([MockProvider(replies=[json.dumps(route)])])


def test_grounded_route_is_accepted() -> None:
    route = {"tool": "whatif", "args": {"weekday": "saturday", "agents_delta": {"C": -2}, "volume_change_pct": 20}}
    out = understand(Q, client_replying(route))
    assert out["tool"] == "whatif" and out["understood_by"].startswith("LLM")


def test_a_number_the_user_never_typed_is_rejected() -> None:
    # 5 agents and 35% appear nowhere in the question: the LLM made them up.
    assert check_route({"tool": "whatif", "args": {"agents_delta": {"C": -5}}}, Q) is None
    assert check_route({"tool": "whatif", "args": {"volume_change_pct": 35}}, Q) is None


def test_bad_llm_route_falls_back_to_rules() -> None:
    out = understand(Q, client_replying({"tool": "whatif", "args": {"agents_delta": {"Z": -2}}}))
    assert out["understood_by"].startswith("keyword rules")
    assert out["args"] == {"weekday": "saturday", "volume_change_pct": 20, "agents_delta": {"C": -2}}


def test_offline_rules_cover_the_demo_questions() -> None:
    assert rules_route("Why is T060582 at risk?")["args"] == {"ticket_id": "T060582"}
    assert rules_route("plant a refund spike")["args"] == {"category": "refund", "effect": "volume"}
    assert rules_route("What should we fix first?")["tool"] == "fix_first"
    assert rules_route("add 3 agents to team b on friday")["args"]["agents_delta"] == {"B": 3}


def test_weekday_maps_to_the_first_test_day_with_that_weekday() -> None:
    # Day 1 is a Monday (first_weekday 0); test days 43-56 → day 43 is a Monday, day 48 a Saturday.
    req = whatif_request({"weekday": "saturday", "volume_change_pct": 20, "agents_delta": {"c": -2}}, (43, 56), 0)
    assert req == {"day": 48, "policy": "opslens", "volume_factor": 1.2, "agents_delta": {"C": -2}}


def test_answer_numbers_come_from_the_tool() -> None:
    def fake_whatif(request: dict) -> dict:
        k = {"turnaround.breach_pct": 4.25, "turnaround.p90_resolution_min": 150.0, "turnaround.max_backlog": 80.0,
             "tickets": 1300.0}
        return {"request": request, "all_policies": {"opslens": k, "baseline_b": {**k, "turnaround.breach_pct": 9.75},
                                                     "baseline_a": {**k, "turnaround.breach_pct": 15.0}}}
    out = answer(Q, None, {"whatif": fake_whatif}, {}, (43, 56), 0)
    text = " ".join(out["lines"])
    assert "4.2%" in text and "9.8%" in text and "+5.5 points" in text  # no baseline_d here → urgent-first


def test_numbers_written_as_words_ground_the_route() -> None:
    # Found 22 Oct (W6 routing test, question 6): "Two" did not ground the LLM's 2.
    route = {"tool": "whatif", "args": {"weekday": "wednesday", "agents_delta": {"D": -2}}}
    assert check_route(route, "Two agents from team D are on leave Wednesday. Impact?") == route
    assert check_route({"tool": "whatif", "args": {"agents_delta": {"C": -2}}}, "Team C mein do log kam ho gaye") is not None
    assert check_route({"tool": "whatif", "args": {"volume_change_pct": 20}}, "volume up twenty percent") is not None
    # Still strict: "do" as an English verb grounds nothing, and an unrelated number is still rejected.
    assert check_route({"tool": "whatif", "args": {"agents_delta": {"C": 2}}}, "do breaches fall on friday?") is None
    assert check_route({"tool": "whatif", "args": {"agents_delta": {"C": 3}}}, "Two agents leave team C") is None



# ---- Forecast and at-risk questions (added 24 Oct) ----------------------------------------------

def tiny_results() -> dict:
    """A hand-made results dict: two forecast hours for Team B, one day and one night bottleneck,
    and two at-risk tickets (one where acting helps, one where time has run out)."""
    hour = {"team": "B", "lo80": 1.0, "demand_hours": 2.0, "actual_hours": 2.0}
    return {
        "forecast": {"horizon": [{**hour, "time": "2026-10-24T19:00", "hi80": 3.0, "capacity_hours": 2.0},
                                 {**hour, "time": "2026-10-24T20:00", "hi80": 6.5, "capacity_hours": 2.4}],
                     "bottlenecks": [{"team": "B", "start": "2026-10-24T18:00", "end": "2026-10-24T23:00",
                                      "text": "Team B short by up to 5.2 agents", "agent_hours_short": 19.9},
                                     {"team": "B", "start": "2026-10-24T00:00", "end": "2026-10-24T07:00",
                                      "text": "night", "agent_hours_short": 9.0}]},
        "risk": {"at_risk": [
            {"ticket_id": "T000001", "category": "refund", "priority": "P2", "language": "hi", "probability": 0.99,
             "minutes_to_sla": 113, "reasons": [{"text": "no agent on shift can serve Hindi refund"}],
             "action": "assign now to a free agent who handles refund in Hindi", "probability_after_action": 0.29},
            {"ticket_id": "T000002", "category": "late_delivery", "priority": "P1", "language": "en", "probability": 1.0,
             "minutes_to_sla": 5, "reasons": [{"text": "5 min left"}],
             "action": "assign now to a free agent who handles late delivery", "probability_after_action": 1.0}]},
    }


def test_forecast_and_risk_questions_route_offline() -> None:
    assert rules_route("kal raat refund wale kitne late honge?") == {"tool": "forecast", "args": {"category": "refund"}}
    assert rules_route("How busy is tomorrow night?")["tool"] == "forecast"
    assert rules_route("Which customers will miss their deadline?") == {"tool": "at_risk", "args": {}}
    assert rules_route("kaun late hone wala hai, hindi wale?") == {"tool": "at_risk", "args": {"language": "hi"}}
    assert check_route({"tool": "forecast", "args": {"team": "Z"}}, "team Z?") is None  # no such team


def test_forecast_answer_skips_night_and_reads_the_band() -> None:
    from opslens.ask import forecast_text
    out = forecast_text(tiny_results(), {"category": "refund"})
    text = " ".join(out["lines"])
    assert "Sat 24 Oct 20:00" in text and "6.5 agent-hours" in text and "2.4 on shift" in text
    assert "short by up to 5.2" in text and "night" not in text  # the night pool covers 00:00-07:00


def test_at_risk_answer_points_to_where_acting_helps() -> None:
    from opslens.ask import at_risk_text
    out = at_risk_text(tiny_results(), {})
    text = " ".join(out["lines"])
    assert "T000001" in text and "from 99% to 29%" in text  # acting helps here, not on T000002 (5 min left)
    assert at_risk_text(tiny_results(), {"language": "other"})["lines"] == []
