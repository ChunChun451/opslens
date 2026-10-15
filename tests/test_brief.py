"""The LLM can never put a number of its own on screen."""

import json

from opslens.brief import check_and_fill, write_brief
from opslens.llm.client import LLMClient
from opslens.llm.mock import MockProvider

FACTS = {"opslens_breach": ("4.2%", "breaches with OpsLens", "sim.x"), "priority_breach": ("6.8%", "priority", "sim.y")}


def test_keys_are_filled_from_results() -> None:
    text = "Breaches fell to {{opslens_breach}} against {{ priority_breach }} for priority routing."
    assert check_and_fill(text, FACTS) == "Breaches fell to 4.2% against 6.8% for priority routing."


def test_a_digit_written_by_the_llm_is_rejected() -> None:
    assert check_and_fill("Breaches fell to 3.9% this week.", FACTS) is None
    assert check_and_fill("Breaches fell to {{opslens_breach}}, down 2 points.", FACTS) is None


def test_unknown_keys_are_rejected() -> None:
    assert check_and_fill("Saved {{money_saved}} rupees.", FACTS) is None


def results_stub() -> dict:
    k = lambda v: {"mean": v, "std": 0.1}  # noqa: E731
    pol = {p: {"kpis": {"turnaround.breach_pct": k(b), "turnaround.p90_resolution_min": k(t)}}
           for p, b, t in (("opslens", 5.08, 130.2), ("baseline_b", 6.82, 198.4), ("baseline_a", 13.11, 184.8))}
    return {"sim": {"policies": pol}, "patterns": {"cards": [{"title": "Hindi x Team B wait 5.1x longer", "affected_tickets": 2871,
                                                            "value": 336.0, "comparison_value": 66.0, "metric": "mean wait (min)"}]}}


def test_llm_brief_or_template_fallback() -> None:
    good = MockProvider(replies=[json.dumps({"brief": "OpsLens kept breaches at {{opslens_breach}}."})])
    out = write_brief(results_stub(), LLMClient([good]))
    assert out["source"] == "llm" and out["text"] == "OpsLens kept breaches at 5.1%."
    bad = MockProvider(replies=[json.dumps({"brief": "Breaches were 4% lower."})])
    out = write_brief(results_stub(), LLMClient([bad]))
    assert out["source"] == "template" and "13.1%" in out["text"]


def test_numbers_in_words_are_rejected() -> None:
    assert check_and_fill("Ninety percent of tickets closed fast at {{opslens_breach}}.", FACTS) is None
    assert check_and_fill("Breaches doubled to {{opslens_breach}}.", FACTS) is not None  # "doubled" is not a number word
