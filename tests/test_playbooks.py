import json

import pandas as pd

from opslens.llm.client import LLMClient
from opslens.llm.mock import MockProvider
from opslens.playbooks import Playbook, apply_scenario, draft_message, pick_cross_trainees, playbooks_from_cards
from opslens.simulate import Agent

CFG = {"partner_fix_share": 1.0, "cross_train_agents": 1, "banner_hours": 4, "banner_deflect_share": 0.5,
       "self_serve_categories": ["missing_item", "refund"], "self_serve_max_order_inr": 300, "self_serve_uptake": 1.0}
TEAM_SKILLS = {"B": ["refund", "payment_failure"], "C": ["missing_item", "wrong_item"]}


def agent(agent_id: str, team: str, skills: set[str], langs: tuple[str, ...], start_h: int) -> Agent:
    return Agent(agent_id, agent_id, team, frozenset(TEAM_SKILLS.get(team, [])), frozenset(skills), frozenset(langs),
                 start_h * 60, 9 * 60, frozenset())


def tickets(rows: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = {"day": 43, "created_min": 42 * 1440 + 600, "channel": "chat", "category": "refund",
            "selected_category": "refund", "order_value_inr": 500, "restaurant_cluster_id": 1}
    t = pd.DataFrame([{**base, **r, "ticket_id": f"T{i:06d}"} for i, r in enumerate(rows)])
    return t, pd.DataFrame({"ticket_id": t["ticket_id"], "pred_final": t["selected_category"]})


def test_partner_fix_brings_the_cluster_back_to_the_normal_share() -> None:
    rows = [{"restaurant_cluster_id": 7, "category": "wrong_item"}] * 5 + [{"restaurant_cluster_id": 7}] * 5
    t, p = tickets(rows + [{"category": "wrong_item"}] * 3)
    spec = {"kind": "partner_fix", "restaurant_cluster_id": 7, "category": "wrong_item", "normal_share": 0.2, "fix_share": 1.0}
    out, _, _, info = apply_scenario(t, p, [], spec, 43, 56, 0)
    assert info["removed"] == 4 and len(out) == len(t) - 4
    assert (out["restaurant_cluster_id"] != 7).sum() == 3


def test_fix_menu_corrects_menu_and_prediction_only_on_that_channel() -> None:
    wrong = {"channel": "call", "category": "refund", "selected_category": "account"}
    t, p = tickets([wrong] * 10 + [{**wrong, "channel": "chat"}] * 4)
    spec = {"kind": "fix_menu", "channel": "call", "keep_error_share": 0.2}
    out, preds, _, info = apply_scenario(t, p, [], spec, 43, 56, 0)
    assert info["changed"] == 8 and info["removed"] == 0
    assert (out[out["channel"] == "call"]["selected_category"] == "refund").sum() == 8
    assert (out[out["channel"] == "chat"]["selected_category"] == "account").all()
    assert (preds["pred_final"] == "refund").sum() == 8


def test_cross_trainee_covers_the_uncovered_hours() -> None:
    day_b = agent("B01", "B", {"refund", "payment_failure"}, ("en", "hi"), 9)
    night = agent("A09", "A", {"late_delivery"}, ("en", "hi"), 22)
    day_a = agent("A01", "A", {"late_delivery"}, ("en", "hi"), 9)
    english = agent("A02", "A", {"late_delivery"}, ("en",), 22)
    skills = frozenset(TEAM_SKILLS["B"])
    assert pick_cross_trainees([day_b, night, day_a, english], "hi", skills, 2) == ["A09"]
    _, _, agents, _ = apply_scenario(*tickets([{}]), [day_b, night], {"kind": "cross_train", "agents": ["A09"],
                                                                      "skills": sorted(skills)}, 43, 56, 0)
    assert skills <= agents[1].skills and agents[0] is day_b


def test_status_banner_only_after_the_alert_and_only_its_category() -> None:
    at = 46 * 1440 + 600
    t, p = tickets([{"day": 47, "created_min": at + 10, "category": "app_bug", "selected_category": "app_bug"}] * 10
                   + [{"day": 47, "created_min": at - 10, "category": "app_bug", "selected_category": "app_bug"}] * 5
                   + [{"day": 47, "created_min": at + 10}] * 5)
    out, _, _, info = apply_scenario(t, p, [], {"kind": "status_banner", "hours": 4, "deflect_share": 0.5}, 43, 56, 0,
                                     alerts=[{"minute": at, "category": "app_bug"}])
    assert info["removed"] == 5 and (out["category"] == "refund").sum() == 5
    assert (out["created_min"] < at).sum() == 5


def test_self_serve_only_small_orders_in_the_window() -> None:
    sat_dinner = 47 * 1440 + 20 * 60
    rows = ([{"day": 48, "created_min": sat_dinner, "selected_category": "missing_item", "order_value_inr": 200}] * 4
            + [{"day": 48, "created_min": sat_dinner, "selected_category": "missing_item", "order_value_inr": 900}] * 2
            + [{"day": 48, "created_min": sat_dinner - 8 * 60, "selected_category": "missing_item", "order_value_inr": 200}] * 3)
    t, p = tickets(rows)
    spec = {"kind": "self_serve", "when": "weekend dinner", "categories": ["missing_item"], "max_order_inr": 300, "uptake": 1.0}
    out, _, _, info = apply_scenario(t, p, [], spec, 43, 56, 0)
    assert info["removed"] == 4 and len(out) == 5


def test_every_cause_type_gets_a_playbook_except_other() -> None:
    card = {"title": "a problem 5x worse", "value": 10.0, "comparison_value": 2.0, "metric": "m", "affected_tickets": 100}
    cards = [{**card, "id": "F1", "cause_type": "process", "segment": {"channel": "call"}},
             {**card, "id": "F2", "cause_type": "partner_issue", "segment": {"category": "wrong_item", "restaurant_cluster_id": 3}},
             {**card, "id": "F3", "cause_type": "volume_spike", "segment": {"category": "app_bug", "day": 18}},
             {**card, "id": "F4", "cause_type": "capacity", "segment": {"team": "C", "when": "weekend dinner"}},
             {**card, "id": "F5", "cause_type": "other", "segment": {"language": "other"}}]
    books = playbooks_from_cards(cards, [], TEAM_SKILLS, CFG)
    assert [b.card_id for b in books] == ["F1", "F2", "F3", "F4"]
    assert books[0].scenario["keep_error_share"] == 0.2
    assert all(b.assumptions for b in books)


def test_llm_message_with_a_digit_falls_back_to_the_template() -> None:
    pb = Playbook("pb", "F1", "process", "Fix the phone menu", "Product", "template text", {},
                  facts={"issue_value": ("13", "transfers per 100 phone tickets")})
    good = MockProvider(replies=[json.dumps({"message": "Phone tickets transfer {{issue_value}} times per hundred."})])
    assert draft_message(pb, LLMClient([good]))["source"] == "template"
    good = MockProvider(replies=[json.dumps({"message": "Phone tickets are transferred {{issue_value}} times as often."})])
    assert draft_message(pb, LLMClient([good])) == {"text": "Phone tickets are transferred 13 times as often.", "source": "llm"}
    bad = MockProvider(replies=[json.dumps({"message": "Please fix 13 menu options."})])
    assert draft_message(pb, LLMClient([bad])) == {"text": "template text", "source": "template"}
