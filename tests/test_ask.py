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
