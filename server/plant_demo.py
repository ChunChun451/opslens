"""Live Plant-a-problem: the judge hides a problem in fresh data, OpsLens has to find it.

What it does: turns the judge's choice (category, language, effect, day) into a planted problem,
generates 21 fresh days on a CLEAN floor (the main planted problems removed) with only that
problem hidden in it, runs Baseline A to make the history, runs the SAME pattern finder that the
rest of OpsLens uses — which is not told what was planted — and scores the answer with the SAME
matcher as the 20-set blind test (eval/recall.py). About 20 seconds.

Effects:
- "volume":    the category gets 4× its tickets for 5 hours on one day (a spike)
- "wait":      a skill gap — only 2 agents (1 for a regional language) of the team keep it
               (Hindi if the judge picks English or "any", since everyone speaks English)
- "transfers": the category's menu choice is wrong 30% of the time (a process problem)

Example request: {"category": "refund", "language": "", "effect": "volume", "day": 47}
→ spike planted on day 13 of the fresh data (the judge's day 47 mapped into the 21-day window),
answer: found = true, diagnosed = true, the matching evidence card, and the seconds it took.
"""

from __future__ import annotations

import time

from data.plant import apply_plants, clean_config, clean_roster
from eval.recall import score
from eval.run_blind import run_set
from opslens.classify import CATEGORIES, TEAM_OF
from opslens.config import load_config

FRESH_DAYS = 21
FIRST_SPIKE_DAY = 9  # the spike scan needs a week of normal days before the spike


def plant_spec(request: dict) -> dict:
    category = str(request.get("category", "refund"))
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r}")
    effect = str(request.get("effect", "volume"))
    if effect == "volume":
        day = FIRST_SPIKE_DAY + (int(request.get("day", 43)) - 43) % (FRESH_DAYS - FIRST_SPIKE_DAY + 1)
        return {"type": "volume_spike", "category": category, "day": day, "hours": list(range(16, 21)),
                "multiplier": 4.0}
    if effect == "wait":
        language = request.get("language") or "hi"
        language = "hi" if language == "en" else language
        return {"type": "skill_gap", "language": language, "team": TEAM_OF[category], "keep": 2 if language == "hi" else 1}
    if effect == "transfers":
        return {"type": "process_category", "category": category, "wrong_prob": 0.30}
    raise ValueError(f"unknown effect {effect!r}")


def run_plant(request: dict, seed: int = 777) -> dict:
    started = time.perf_counter()
    calendar = load_config("calendar")
    base_cfg = clean_config({**load_config("generator"), **calendar})
    base_roster = clean_roster(load_config("roster"))
    spec = plant_spec(request)
    cfg, roster, records = apply_plants(base_cfg, base_roster, [spec])
    cards = run_set(cfg, roster, load_config("sla"), calendar, seed, days=FRESH_DAYS)
    team_skills = {t: v["skills"] for t, v in roster["teams"].items()}
    result = score(cards, records, team_skills)
    detail = result["details"][0]
    match = next((c for c in cards if c["id"] == detail["card"]), None)
    return {
        "planted": {"description": records[0]["name"], "cause_type": records[0]["cause_type"],
                    "segment": records[0]["segment"], "fresh_days": FRESH_DAYS},
        "found": detail["found"], "diagnosed": detail["diagnosed"],
        "card": match, "other_cards": [c["title"] for c in cards if c is not match][:5],
        "seconds": round(time.perf_counter() - started, 1),
    }
