"""Random planted problems for the blind recall test (and, later, the live Plant-a-problem demo).

What it does: starts from a CLEAN floor (the main problems removed: Hindi refund cover restored,
Team C's evening agents back at weekends, no spikes, no partner or IVR problem), then plants
3 problems of random type, place and size. The pattern finder has never seen these choices.

Problem types (one per cause type), each with random parameters:
- skill_gap      a random language × team: only 1-2 agents of that team keep the language
- capacity       a random team at weekend dinner: 2 evening agents off at weekends + 1.35× volume
- volume_spike   a random category on a random day, 4-6 hours at 3-5×
- partner_issue  a random restaurant cluster sends 3× its usual share of one category
- process        a random channel's menu choice is wrong 25% of the time

Example: set 7 → [capacity: Team A weekend dinner], [volume_spike: refund on day 29,
13:00-17:00, ×4.2], [process: email menu wrong 25%].
"""

from __future__ import annotations

import copy

import numpy as np

PLANT_TYPES = ["skill_gap", "capacity", "volume_spike", "partner_issue", "process"]
DINNER = [19, 20, 21, 22]


def clean_config(cfg: dict) -> dict:
    """The generator config with every main planted problem switched off."""
    out = copy.deepcopy(cfg)
    for plant in out["planted"].values():
        plant["enabled"] = False
    out["extra_lifts"], out["extra_partners"], out["extra_misrouting"] = [], [], {}
    return out


def clean_roster(roster: dict) -> dict:
    """The roster without the two main planted problems."""
    out = copy.deepcopy(roster)
    for agent in out["agents"]:
        if agent["id"] in ("B03", "B06", "B08", "B10") and "hi" not in agent["langs"]:
            agent["langs"] = agent["langs"] + ["hi"]  # Hindi refund cover across the day
        if agent["id"] == "C05":
            agent["days_off"] = [1, 2]  # Team C evening agents work weekends again
        if agent["id"] == "C07":
            agent["days_off"] = [3, 4]
    return out


def random_plant_set(rng: np.random.Generator, roster: dict, cfg: dict, n: int = 3, days: int | None = None) -> list[dict]:
    """Pick `n` different problem types with random parameters (spikes fall inside the first `days`)."""
    teams = list(roster["teams"])
    days = days or int(cfg["days"])
    types = rng.choice(PLANT_TYPES, size=n, replace=False)
    plants = []
    for kind in types:
        if kind == "skill_gap":
            language = str(rng.choice(["hi", "other"]))
            team = str(rng.choice(teams))
            plants.append({"type": kind, "language": language, "team": team,
                           "keep": 2 if language == "hi" else 1})
        elif kind == "capacity":
            plants.append({"type": kind, "team": str(rng.choice(teams))})
        elif kind == "volume_spike":
            known = {e["day"] for e in cfg["known_events"]} | {d["day"] for d in cfg["decoys"]}
            day = int(rng.choice([d for d in range(9, days + 1) if d not in known]))
            start = int(rng.integers(10, 19))
            hours = list(range(start, min(start + int(rng.integers(4, 7)), 24)))
            plants.append({"type": kind, "category": str(rng.choice(list(cfg["categories"]))), "day": day,
                           "hours": hours, "multiplier": round(float(rng.uniform(3.0, 5.0)), 1)})
        elif kind == "partner_issue":
            plants.append({"type": kind, "category": str(rng.choice(["wrong_item", "missing_item", "restaurant_partner"])),
                           "cluster_id": int(rng.integers(3, 21)), "multiplier": 3.0})
        else:
            plants.append({"type": kind, "channel": str(rng.choice(["call", "email"])), "wrong_prob": 0.25})
    return plants


def apply_plants(cfg: dict, roster: dict, plants: list[dict]) -> tuple[dict, dict, list[dict]]:
    """Return (config, roster, planted records in the planted.json format)."""
    cfg, roster = copy.deepcopy(cfg), copy.deepcopy(roster)
    team_skills = {t: v["skills"] for t, v in roster["teams"].items()}
    records = []
    for i, p in enumerate(plants):
        pid = f"R{i + 1}"
        if p["type"] == "skill_gap":
            categories = team_skills[p["team"]]
            speakers = [a for a in roster["agents"] if p["language"] in a["langs"] and a["team"] == p["team"]
                        and a["start"] != 22]
            keep = {a["id"] for a in speakers[: p["keep"]]}
            for a in roster["agents"]:
                extra = a.get("extra_skills", [])
                serves = a["team"] == p["team"] or extra == "all" or any(c in extra for c in categories)
                if serves and p["language"] in a["langs"] and a["id"] not in keep:
                    a["langs"] = [x for x in a["langs"] if x != p["language"]]
            records.append({"id": pid, "name": f"{p['language']} x Team {p['team']} skill gap", "cause_type": "skill_gap",
                            "segment": {"language": p["language"], "category": categories}})
        elif p["type"] == "capacity":
            evening = [a for a in roster["agents"] if a["team"] == p["team"] and 12 <= a["start"] <= 16]
            for a in evening[-2:]:
                a["days_off"] = [5, 6]
            cfg["extra_lifts"].append({"categories": team_skills[p["team"]], "weekdays": [5, 6],
                                       "hours": DINNER, "multiplier": 1.35})
            records.append({"id": pid, "name": f"Team {p['team']} weekend dinner overload", "cause_type": "capacity",
                            "segment": {"team": p["team"], "weekday": [5, 6], "hour": DINNER}})
        elif p["type"] == "volume_spike":
            cfg["extra_lifts"].append({"categories": [p["category"]], "days": [p["day"]], "hours": p["hours"],
                                       "multiplier": p["multiplier"]})
            records.append({"id": pid, "name": f"{p['category']} spike day {p['day']}", "cause_type": "volume_spike",
                            "segment": {"category": p["category"], "day": p["day"], "hour": p["hours"]}})
        elif p["type"] == "partner_issue":
            cfg["extra_partners"].append({"category": p["category"], "cluster_id": p["cluster_id"],
                                          "multiplier": p["multiplier"]})
            records.append({"id": pid, "name": f"cluster {p['cluster_id']} {p['category']}", "cause_type": "partner_issue",
                            "segment": {"category": p["category"], "restaurant_cluster_id": p["cluster_id"]}})
        else:
            cfg["extra_misrouting"][p["channel"]] = p["wrong_prob"]
            records.append({"id": pid, "name": f"{p['channel']} menu mislabels", "cause_type": "process",
                            "segment": {"channel": p["channel"]}})
    return cfg, roster, records
