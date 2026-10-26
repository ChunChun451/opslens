from __future__ import annotations

import numpy as np
import pandas as pd

SEEDS = list(range(9101, 9121))
FIRST_DAY, LAST_DAY = "2016-05-02", "2016-06-05"
SPIKE_DAYS = ("2016-05-02", "2016-06-03")
WINDOW_STARTS = ("2016-05-02", "2016-05-27")
WINDOW_DAYS = 7
SPIKE_MULTIPLIER = (0.5, 2.0)
SLOW_FACTOR = (1.5, 3.0)
BOUNCE_SHARE = (0.15, 0.40)
ELIGIBLE_FROM, ELIGIBLE_TO = "2016-04-04", "2016-05-01"
MIN_WEEKDAY_MEDIAN = 8
MATCH_SLACK_DAYS = 2
TEST = {"first_day": FIRST_DAY, "last_day": LAST_DAY, "spike_days": SPIKE_DAYS, "window_starts": WINDOW_STARTS,
        "eligible": (ELIGIBLE_FROM, ELIGIBLE_TO)}
CHECK = {"first_day": "2016-04-18", "last_day": "2016-05-01", "spike_days": ("2016-04-18", "2016-04-29"),
         "window_starts": ("2016-04-18", "2016-04-22"), "eligible": ("2016-03-21", "2016-04-17")}
CHECK_SEEDS = list(range(9301, 9321))
SECOND_SEEDS = list(range(9201, 9221))


def usual_weekday(table: pd.DataFrame, by: str, period: dict = TEST) -> pd.Series:
    days = pd.date_range(*period["eligible"])
    days = days[days.weekday < 5]
    window = table[table["date"].isin(days)]
    counts = window.groupby([by, "date"]).size().unstack(fill_value=0).reindex(columns=days, fill_value=0)
    return counts.median(axis=1).sort_values(ascending=False)


def weekdays(first: str, last: str) -> list[pd.Timestamp]:
    days = pd.date_range(first, last)
    return list(days[days.weekday < 5])


def random_plant_set(rng: np.random.Generator, table: pd.DataFrame, period: dict = TEST) -> list[dict]:
    cats = usual_weekday(table, "category", period)
    teams = usual_weekday(table, "team", period)
    cats, teams = cats[cats >= MIN_WEEKDAY_MEDIAN], teams[teams >= MIN_WEEKDAY_MEDIAN]
    spike_cat = str(rng.choice(cats.index.to_numpy()))
    multiplier = float(rng.uniform(*SPIKE_MULTIPLIER))
    spike_day = rng.choice(weekdays(*period["spike_days"]))
    slow_team = str(rng.choice(teams.index.to_numpy()))
    slow_start = rng.choice(weekdays(*period["window_starts"]))
    bounce_cat = str(rng.choice(cats.index.to_numpy()))
    bounce_start = rng.choice(weekdays(*period["window_starts"]))
    week = pd.Timedelta(days=WINDOW_DAYS - 1)
    return [
        {"type": "spike", "segment": spike_cat, "first_day": pd.Timestamp(spike_day), "last_day": pd.Timestamp(spike_day),
         "size": round(multiplier, 2), "extra_incidents": int(round(multiplier * cats[spike_cat]))},
        {"type": "slowdown", "segment": slow_team, "first_day": pd.Timestamp(slow_start),
         "last_day": pd.Timestamp(slow_start) + week, "size": round(float(rng.uniform(*SLOW_FACTOR)), 2)},
        {"type": "bounce", "segment": bounce_cat, "first_day": pd.Timestamp(bounce_start),
         "last_day": pd.Timestamp(bounce_start) + week, "size": round(float(rng.uniform(*BOUNCE_SHARE)), 2)},
    ]


def apply_plants(table: pd.DataFrame, plants: list[dict], rng: np.random.Generator, period: dict = TEST) -> pd.DataFrame:
    out = table.copy()
    for plant in plants:
        if plant["type"] == "spike":
            out = plant_spike(out, plant, rng, period)
        elif plant["type"] == "slowdown":
            out = plant_slowdown(out, plant)
        else:
            out = plant_bounce(out, plant, rng)
    return out


def plant_spike(table: pd.DataFrame, plant: dict, rng: np.random.Generator, period: dict = TEST) -> pd.DataFrame:
    day = plant["first_day"]
    test_days = pd.DatetimeIndex(weekdays(period["first_day"], period["last_day"]))
    pool = table[(table["category"] == plant["segment"]) & table["date"].isin(test_days) & (table["date"] != day)]
    picks = pool.iloc[rng.integers(0, len(pool), plant["extra_incidents"])].copy()
    picks["created_at"] = day + (picks["created_at"] - picks["date"])
    picks["date"] = day
    picks["ticket_id"] = [f"{t}-P{i}" for i, t in enumerate(picks["ticket_id"])]
    return pd.concat([table, picks], ignore_index=True)


def in_window(table: pd.DataFrame, plant: dict) -> np.ndarray:
    return ((table["date"] >= plant["first_day"]) & (table["date"] <= plant["last_day"])).to_numpy()


def plant_slowdown(table: pd.DataFrame, plant: dict) -> pd.DataFrame:
    out = table.copy()
    hit = in_window(out, plant) & (out["team"] == plant["segment"]).to_numpy()
    out.loc[hit, "resolution_h"] = out.loc[hit, "resolution_h"] * plant["size"]
    out.loc[hit, "open_24h"] = ~(out.loc[hit, "resolution_h"] <= 24.0)
    if "open_2h" in out:
        out.loc[hit, "open_2h"] = ~(out.loc[hit, "resolution_h"] <= 2.0)
    return out


def plant_bounce(table: pd.DataFrame, plant: dict, rng: np.random.Generator) -> pd.DataFrame:
    out = table.copy()
    hit = in_window(out, plant) & (out["category"] == plant["segment"]).to_numpy() & ~out["bounced_24h"].to_numpy()
    flip = hit & (rng.uniform(0, 1, len(out)) < plant["size"])
    out.loc[flip, "bounced_24h"] = True
    return out


def score_set(alerts: pd.DataFrame, plants: list[dict]) -> tuple[list[dict], int]:
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
