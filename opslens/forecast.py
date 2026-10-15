"""Forecast tickets per category for every hour of the next 48 hours, with a range.

What it does:
1. LightGBM (Poisson objective, because the target is a count) predicts each category's
   tickets in a target hour from: hour, weekday, weekend, the sale-day calendar, and the counts
   in the same hour 1, 2, 3 and 4 weeks earlier. All of these are known 48 hours ahead (the
   most recent one is 168 hours before the target), so there is no leakage.
2. Baseline: "same hour last week" (seasonal naive). We report WAPE for both.
3. Range: split-conformal intervals. On validation days we measure how far off the model was,
   scaled by sqrt(forecast + 1) (count noise grows with the count), and take the 80% / 90%
   quantile. On test days we report how often the truth fell inside (coverage).
4. Workload: tickets × average handle minutes per category = agent-hours per team.

Example: Saturday 20:00, missing_item. Same hour 1-4 weeks ago: 22, 25, 19, 24 → forecast
23.4; conformal q80 = 1.3 → range 23.4 ± 1.3 × sqrt(24.4) = 17.0 to 29.8 tickets.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

PARAMS = {"objective": "poisson", "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 20,
          "feature_fraction": 0.9, "verbose": -1, "seed": 7, "deterministic": True, "num_threads": 4}
LAGS = [168, 336, 504, 672]  # same hour 1, 2, 3, 4 weeks earlier
FEATURES = ["category", "hour", "weekday", "is_weekend", "is_event", "lag_168", "lag_336", "mean_4w"]


def hourly_counts(tickets: pd.DataFrame, category_col: str, days: int, categories: list[str]) -> pd.DataFrame:
    """Tickets per category per hour index (hour 0 = day 1, 00:00), zeros included."""
    hour_index = (tickets["minute_of_run"] // 60).astype(int)
    grid = pd.MultiIndex.from_product([categories, range(days * 24)], names=["category", "hour_index"])
    counts = tickets.assign(hour_index=hour_index).groupby([category_col, "hour_index"]).size()
    counts.index = counts.index.set_names(["category", "hour_index"])
    return counts.reindex(grid, fill_value=0).rename("count").reset_index()


def add_features(counts: pd.DataFrame, first_weekday: int, event_days: set[int]) -> pd.DataFrame:
    """Calendar + same-hour-in-previous-weeks features (NaN when that week is before day 1)."""
    df = counts.sort_values(["category", "hour_index"]).reset_index(drop=True)
    day = df["hour_index"] // 24 + 1
    df["hour"] = df["hour_index"] % 24
    df["weekday"] = (first_weekday + day - 1) % 7
    df["is_weekend"] = df["weekday"].isin([5, 6]).astype(int)
    df["is_event"] = day.isin(event_days).astype(int)
    grouped = df.groupby("category")["count"]
    for lag in LAGS:
        df[f"lag_{lag}"] = grouped.shift(lag)
    df["mean_4w"] = df[[f"lag_{lag}" for lag in LAGS]].mean(axis=1)  # mean of the weeks available
    df["category"] = df["category"].astype("category")
    df["day"] = day
    return df


def wape(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Σ|forecast − actual| ÷ Σ actual (CLAUDE.md section 4)."""
    return float(np.abs(forecast - actual).sum() / max(actual.sum(), 1e-9))


def train(train_rows: pd.DataFrame, valid_rows: pd.DataFrame) -> lgb.Booster:
    dtrain = lgb.Dataset(train_rows[FEATURES], train_rows["count"], categorical_feature=["category"])
    dvalid = lgb.Dataset(valid_rows[FEATURES], valid_rows["count"], categorical_feature=["category"], reference=dtrain)
    return lgb.train(PARAMS, dtrain, 2000, valid_sets=[dvalid], callbacks=[lgb.early_stopping(50, verbose=False)])


def conformal_q(actual: np.ndarray, forecast: np.ndarray, level: float) -> float:
    """Quantile of |actual − forecast| / sqrt(forecast + 1) on validation data."""
    scores = np.abs(actual - forecast) / np.sqrt(forecast + 1.0)
    n = len(scores)
    rank = min(int(np.ceil((n + 1) * level)), n)  # finite-sample correction of split conformal
    return float(np.sort(scores)[rank - 1])


def interval(forecast: np.ndarray, q: float) -> tuple[np.ndarray, np.ndarray]:
    half = q * np.sqrt(forecast + 1.0)
    return np.clip(forecast - half, 0, None), forecast + half


def coverage(actual: np.ndarray, low: np.ndarray, high: np.ndarray) -> float:
    return float(((actual >= low) & (actual <= high)).mean())
