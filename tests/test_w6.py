import numpy as np

from eval.run_llm_eval import EVIDENCE_KEYS, matched_pairs, paired, same_args, score_route


def test_route_scoring_checks_tool_and_every_labelled_argument() -> None:
    q = {"tool": "whatif", "args": {"weekday": "saturday", "agents_delta": {"C": -2}}}
    assert score_route(q, {"tool": "whatif", "args": {"weekday": "Saturday", "agents_delta": {"c": "-2"}}}) == \
        ("whatif", True, True)
    assert score_route(q, {"tool": "whatif", "args": {"weekday": "saturday"}}) == ("whatif", True, False)
    assert score_route(q, None) == ("none", False, False)
    assert score_route({"tool": "none", "args": {}}, None) == ("none", True, True)
    assert same_args("whatif", {"volume_change_pct": -10}, {"volume_change_pct": "-10.0"})


def test_attribution_hides_the_answer_and_matches_cards_to_plants() -> None:
    assert not {"cause_type", "title", "recommendation"} & set(EVIDENCE_KEYS)
    card = {"id": "F1", "segment": {"language": "hi", "team": "B"}, "cause_type": "skill_gap"}
    plant = {"id": "P1", "name": "Hindi refunds", "cause_type": "skill_gap",
             "segment": {"language": "hi", "category": ["refund", "payment_failure"]}}
    other = {"id": "P2", "name": "Team C dinner", "cause_type": "capacity", "segment": {"team": "C"}}
    pairs = matched_pairs({"main": {"cards": [card], "plants": [plant, other]}, "blind": []},
                          {"B": ["refund", "payment_failure"], "C": ["missing_item"]})
    assert [(p["plant"], p["card"]["id"]) for p in pairs] == [("P1", "F1")]


def test_paired_difference_and_its_interval() -> None:
    a, b = np.array([1, 1, 1, 0] * 10, bool), np.array([1, 0, 1, 0] * 10, bool)
    d = paired(a, b, np.random.default_rng(0))
    assert d["diff_pts"] == 25.0 and d["ci95"][0] > 0 and d["above_zero"]
