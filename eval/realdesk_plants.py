"""Blind plants in the REAL service-desk log: 20 random problem sets, fixed before the test ran.

What it does: takes the real UCI incidents of the busy test weeks (2 May - 5 Jun 2016) as they
happened, injects three problems of random place and size, and lets the detectors in
opslens/realdesk_watch.py look for them. Only this file (eval/) knows the plants.

The three problems (one of each per set), with the ranges fixed here BEFORE the first run:
- spike     one category, one weekday: extra incidents = multiplier × its usual weekday count,
            multiplier uniform in [0.5, 2.0]. The extra incidents are copies of real incidents of
            the same category from other test days (same time of day, same team, same outcome).
- slowdown  one team, 7 days: every incident sent to that team in the window takes `factor` ×
            as long to resolve, factor uniform in [1.5, 3.0] (so more are still open after 24 h).
- bounce    one category, 7 days: a share uniform in [0.15, 0.40] of its incidents that were NOT
            passed on within 24 h are passed to another team once within 24 h.
Places: categories and teams with a median of at least 8 incidents per weekday in the 4 weeks
before the test period (4 Apr - 1 May 2016) — smaller ones cannot be watched day by day.
Days: a spike on a weekday 2 May - 3 Jun; a 7-day window starting on a weekday 2 - 27 May.
Seeds 9101-9120. A plant is FOUND when an alert of the same type and segment is raised between
its first day and 2 days after its last day; delay = alert day − first day.

Why: recall on problems we chose ourselves could be tuning. Problems drawn at random, inside a
real company's log whose own noise we did not make, after the detectors were frozen, cannot be.

Example: set 9101 might plant [spike: Category 42 on Wed 11 May, ×1.3 = +70 incidents],
[slowdown: Group 24 from Mon 16 May, ×2.2], [bounce: Category 53 from Tue 3 May, 31%].
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SEEDS = list(range(9101, 9121))
FIRST_DAY, LAST_DAY = "2016-05-02", "2016-06-05"   # the busy test weeks (the tail after is sparse)
SPIKE_DAYS = ("2016-05-02", "2016-06-03")
WINDOW_STARTS = ("2016-05-02", "2016-05-27")
WINDOW_DAYS = 7
SPIKE_MULTIPLIER = (0.5, 2.0)
SLOW_FACTOR = (1.5, 3.0)
BOUNCE_SHARE = (0.15, 0.40)
ELIGIBLE_FROM, ELIGIBLE_TO = "2016-04-04", "2016-05-01"
MIN_WEEKDAY_MEDIAN = 8
MATCH_SLACK_DAYS = 2


def usual_weekday(table: pd.DataFrame, by: str) -> pd.Series:
    """Median incidents per weekday per segment in the 4 weeks before the test period."""
    days = pd.date_range(ELIGIBLE_FROM, ELIGIBLE_TO)
    days = days[days.weekday < 5]
    window = table[table["date"].isin(days)]
    counts = window.groupby([by, "date"]).size().unstack(fill_value=0).reindex(columns=days, fill_value=0)
    return counts.median(axis=1).sort_values(ascending=False)


def weekdays(first: str, last: str) -> list[pd.Timestamp]:
    days = pd.date_range(first, last)
    return list(days[days.weekday < 5])


def random_plant_set(rng: np.random.Generator, table: pd.DataFrame) -> list[dict]:
    """One spike, one slowdown, one bounce with random place, day and size (ranges above)."""
    cats = usual_weekday(table, "category")
    teams = usual_weekday(table, "team")
    cats, teams = cats[cats >= MIN_WEEKDAY_MEDIAN], teams[teams >= MIN_WEEKDAY_MEDIAN]
    spike_cat = str(rng.choice(cats.index.to_numpy()))
    multiplier = float(rng.uniform(*SPIKE_MULTIPLIER))
    spike_day = rng.choice(weekdays(*SPIKE_DAYS))
    slow_team = str(rng.choice(teams.index.to_numpy()))
    slow_start = rng.choice(weekdays(*WINDOW_STARTS))
    bounce_cat = str(rng.choice(cats.index.to_numpy()))
    bounce_start = rng.choice(weekdays(*WINDOW_STARTS))
    week = pd.Timedelta(days=WINDOW_DAYS - 1)
    return [
        {"type": "spike", "segment": spike_cat, "first_day": pd.Timestamp(spike_day), "last_day": pd.Timestamp(spike_day),
         "size": round(multiplier, 2), "extra_incidents": int(round(multiplier * cats[spike_cat]))},
        {"type": "slowdown", "segment": slow_team, "first_day": pd.Timestamp(slow_start),
         "last_day": pd.Timestamp(slow_start) + week, "size": round(float(rng.uniform(*SLOW_FACTOR)), 2)},
        {"type": "bounce", "segment": bounce_cat, "first_day": pd.Timestamp(bounce_start),
         "last_day": pd.Timestamp(bounce_start) + week, "size": round(float(rng.uniform(*BOUNCE_SHARE)), 2)},
    ]


def apply_plants(table: pd.DataFrame, plants: list[dict], rng: np.random.Generator) -> pd.DataFrame:
    """The real table with the plants injected (the input is not changed)."""
    out = table.copy()
    for plant in plants:
        if plant["type"] == "spike":
            out = plant_spike(out, plant, rng)
        elif plant["type"] == "slowdown":
            out = plant_slowdown(out, plant)
        else:
            out = plant_bounce(out, plant, rng)
    return out


def plant_spike(table: pd.DataFrame, plant: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Copies of real incidents of the category from other test weekdays, moved to the spike day."""
    day = plant["first_day"]
    test_days = pd.DatetimeIndex(weekdays(FIRST_DAY, LAST_DAY))
    pool = table[(table["category"] == plant["segment"]) & table["date"].isin(test_days) & (table["date"] != day)]
    picks = pool.iloc[rng.integers(0, len(pool), plant["extra_incidents"])].copy()
    picks["created_at"] = day + (picks["created_at"] - picks["date"])
    picks["date"] = day
    picks["ticket_id"] = [f"{t}-P{i}" for i, t in enumerate(picks["ticket_id"])]
    return pd.concat([table, picks], ignore_index=True)


def in_window(table: pd.DataFrame, plant: dict) -> np.ndarray:
    return ((table["date"] >= plant["first_day"]) & (table["date"] <= plant["last_day"])).to_numpy()


def plant_slowdown(table: pd.DataFrame, plant: dict) -> pd.DataFrame:
    """The team's incidents opened in the window take `size` × as long to resolve."""
    out = table.copy()
    hit = in_window(out, plant) & (out["team"] == plant["segment"]).to_numpy()
    out.loc[hit, "resolution_h"] = out.loc[hit, "resolution_h"] * plant["size"]
    out.loc[hit, "open_24h"] = ~(out.loc[hit, "resolution_h"] <= 24.0)
    return out


def plant_bounce(table: pd.DataFrame, plant: dict, rng: np.random.Generator) -> pd.DataFrame:
    """A share of the category's not-yet-passed incidents in the window are passed on within 24 h."""
    out = table.copy()
    hit = in_window(out, plant) & (out["category"] == plant["segment"]).to_numpy() & ~out["bounced_24h"].to_numpy()
    flip = hit & (rng.uniform(0, 1, len(out)) < plant["size"])
    out.loc[flip, "bounced_24h"] = True
    return out


def score_set(alerts: pd.DataFrame, plants: list[dict]) -> tuple[list[dict], int]:
    """For each plant: found? delay in days. Also the alerts that match no plant (false alarms)."""
    used = np.zeros(len(alerts), dtype=bool)
    scored = []
    for plant in plants:
        until = plant["last_day"] + pd.Timedelta(days=MATCH_SLACK_DAYS)
        ok = ((alerts["type"] == plant["type"]) & (alerts["segment"] == plant["segment"])
              & (alerts["known_on"] >= plant["first_day"]) & (alerts["known_on"] <= until)).to_numpy()
        used |= ok
        first = alerts.loc[ok, "known_on"].min() if ok.any() else None
        scored.append({**plant, "first_day": str(plant["first_day"].date()), "last_day": str(plant["last_day"].date()),
                       "found": bool(ok.any()), "delay_days": int((first - plant["first_day"]).days) if ok.any() else None})
    return scored, int((~used).sum())
