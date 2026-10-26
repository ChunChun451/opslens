import numpy as np
import pandas as pd

from data.plant import apply_plants, clean_config, clean_roster, random_plant_set
from eval.recall import expand, finds, score
from opslens.config import load_config
from opslens.patterns import hour_band, live_alerts, merge_overlapping, robust_z, scan_interactions, scan_transfers, Finding

TEAM_SKILLS = {"A": ["late_delivery"], "B": ["refund", "payment_failure"],
               "C": ["missing_item", "wrong_item"], "D": ["account", "app_bug", "restaurant_partner"]}


def test_robust_z_matches_definition() -> None:
    history = np.array([35, 40, 45, 40, 35, 45, 40], dtype=float)
    assert abs(robust_z(95.0, history) - 7.42) < 0.01


def test_hour_bands() -> None:
    assert [hour_band(h) for h in (3, 9, 13, 17, 20, 23)] == ["night", "morning", "lunch", "afternoon", "dinner", "late"]


def toy_frame(n: int = 3000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "category": rng.choice(["refund", "late_delivery", "account"], n),
        "language": rng.choice(["en", "hi"], n, p=[0.7, 0.3]),
        "channel": rng.choice(["chat", "call"], n, p=[0.8, 0.2]),
        "team": "X", "priority": "P2", "tier": "normal", "when": "weekday lunch",
        "wait_min": rng.exponential(20, n), "transfers": (rng.random(n) < 0.03).astype(int),
    })
    hi_refund = (df["language"] == "hi") & (df["category"] == "refund")
    df.loc[hi_refund, "wait_min"] *= 6
    calls = df["channel"] == "call"
    df.loc[calls, "transfers"] = (rng.random(calls.sum()) < 0.18).astype(int)
    return df


def test_interaction_scan_needs_both_parents() -> None:
    findings = scan_interactions(toy_frame())
    segments = [f.segment for f in findings]
    assert {"category": "refund", "language": "hi"} in segments
    assert all(len(s) == 2 for s in segments)


def test_transfer_scan_finds_the_channel() -> None:
    findings = scan_transfers(toy_frame())
    assert any(f.segment == {"channel": "call"} and f.cause_type == "process" for f in findings)


def test_merge_keeps_the_stronger_of_overlapping_findings() -> None:
    mask_a = np.array([1, 1, 1, 1, 0, 0], dtype=bool)
    mask_b = np.array([1, 1, 1, 0, 0, 0], dtype=bool)
    mask_c = np.array([0, 0, 0, 0, 1, 1], dtype=bool)
    make = lambda name, mask, strength: Finding(name, "other", "m", 1, 1, "", {}, mask, strength)
    kept = merge_overlapping([make("a", mask_a, 5), make("b", mask_b, 9), make("c", mask_c, 1)])
    assert [f.title for f in kept] == ["b", "c"]


def test_live_alerts_catch_a_surge_and_ignore_known_days() -> None:
    rng = np.random.default_rng(1)
    rows = []
    for day in range(1, 36):
        for minute in rng.uniform(0, 1440, 200):
            rows.append({"minute_of_run": (day - 1) * 1440 + minute, "cat": "app_bug"})
        if day in (29, 33):
            for minute in rng.uniform(18 * 60, 21 * 60, 120):
                rows.append({"minute_of_run": (day - 1) * 1440 + minute, "cat": "app_bug"})
    alerts = live_alerts(pd.DataFrame(rows), "cat", 29, 35, known_event_days={33})
    surge = alerts[alerts["day"] == 29]
    assert len(surge) == 1 and 18 * 60 < surge["minute"].iloc[0] - 28 * 1440 <= 20 * 60
    assert alerts[alerts["day"] == 33]["explained"].all()


def test_expand_team_and_when() -> None:
    have = expand({"team": "C", "when": "weekend dinner"}, TEAM_SKILLS)
    assert have["category"] == {"missing_item", "wrong_item"}
    assert have["weekday"] == {5, 6} and have["hour"] == {19, 20, 21, 22}


def test_matcher_found_and_diagnosed() -> None:
    planted = [{"id": "P1", "name": "hi B", "cause_type": "skill_gap",
                "segment": {"language": "hi", "category": ["refund", "payment_failure"]}},
               {"id": "P5", "name": "ivr", "cause_type": "process", "segment": {"channel": "call"}}]
    cards = [{"id": "F1", "segment": {"language": "hi", "team": "B"}, "cause_type": "skill_gap"},
             {"id": "F2", "segment": {"channel": "call"}, "cause_type": "other"},
             {"id": "F3", "segment": {"channel": "email"}, "cause_type": "process"}]
    result = score(cards, planted, TEAM_SKILLS)
    assert result["found"] == 2 and result["diagnosed"] == 1
    assert [c["id"] for c in result["unmatched"]] == ["F3"]
    assert not finds(cards[0], {"segment": {"language": "other"}}, TEAM_SKILLS)


def test_plants_change_config_and_roster() -> None:
    cfg = clean_config({**load_config("generator"), **load_config("calendar")})
    roster = clean_roster(load_config("roster"))
    assert not any(p["enabled"] for p in cfg["planted"].values())
    plants = [{"type": "skill_gap", "language": "hi", "team": "A", "keep": 2},
              {"type": "process", "channel": "email", "wrong_prob": 0.25},
              {"type": "volume_spike", "category": "refund", "day": 20, "hours": [12, 13], "multiplier": 4.0}]
    cfg2, roster2, records = apply_plants(cfg, roster, plants)
    hindi_a = [a["id"] for a in roster2["agents"] if "hi" in a["langs"] and (a["team"] == "A" or a.get("extra_skills") == "all")]
    assert len(hindi_a) == 2
    assert cfg2["extra_misrouting"] == {"email": 0.25} and cfg2["extra_lifts"][0]["days"] == [20]
    assert [r["cause_type"] for r in records] == ["skill_gap", "process", "volume_spike"]


def test_random_plants_stay_inside_the_run() -> None:
    cfg = clean_config({**load_config("generator"), **load_config("calendar")})
    roster = clean_roster(load_config("roster"))
    rng = np.random.default_rng(0)
    for _ in range(30):
        for p in random_plant_set(rng, roster, cfg, days=42):
            if p["type"] == "volume_spike":
                assert 9 <= p["day"] <= 42 and max(p["hours"]) <= 23
