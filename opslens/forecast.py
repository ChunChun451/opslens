from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

PARAMS = {"objective": "poisson", "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 20,
          "feature_fraction": 0.9, "verbose": -1, "seed": 7, "deterministic": True, "num_threads": 4}
LAGS = [168, 336, 504, 672]
FEATURES = ["category", "hour", "weekday", "is_weekend", "is_event", "lag_168", "lag_336", "mean_4w"]


def hourly_counts(tickets: pd.DataFrame, category_col: str, days: int, categories: list[str]) -> pd.DataFrame:
    hour_index = (tickets["minute_of_run"] // 60).astype(int)
    grid = pd.MultiIndex.from_product([categories, range(days * 24)], names=["category", "hour_index"])
    counts = tickets.assign(hour_index=hour_index).groupby([category_col, "hour_index"]).size()
    counts.index = counts.index.set_names(["category", "hour_index"])
    return counts.reindex(grid, fill_value=0).rename("count").reset_index()


def add_features(counts: pd.DataFrame, first_weekday: int, event_days: set[int]) -> pd.DataFrame:
    df = counts.sort_values(["category", "hour_index"]).reset_index(drop=True)
    day = df["hour_index"] // 24 + 1
    df["hour"] = df["hour_index"] % 24
    df["weekday"] = (first_weekday + day - 1) % 7
    df["is_weekend"] = df["weekday"].isin([5, 6]).astype(int)
    df["is_event"] = day.isin(event_days).astype(int)
    grouped = df.groupby("category")["count"]
    for lag in LAGS:
        df[f"lag_{lag}"] = grouped.shift(lag)
    df["mean_4w"] = df[[f"lag_{lag}" for lag in LAGS]].mean(axis=1)
    df["category"] = df["category"].astype("category")
    df["day"] = day
    return df


def wape(actual: np.ndarray, forecast: np.ndarray) -> float:
    return float(np.abs(forecast - actual).sum() / max(actual.sum(), 1e-9))


def train(train_rows: pd.DataFrame, valid_rows: pd.DataFrame) -> lgb.Booster:
    dtrain = lgb.Dataset(train_rows[FEATURES], train_rows["count"], categorical_feature=["category"])
    dvalid = lgb.Dataset(valid_rows[FEATURES], valid_rows["count"], categorical_feature=["category"], reference=dtrain)
    return lgb.train(PARAMS, dtrain, 2000, valid_sets=[dvalid], callbacks=[lgb.early_stopping(50, verbose=False)])


def conformal_q(actual: np.ndarray, forecast: np.ndarray, level: float) -> float:
    scores = np.abs(actual - forecast) / np.sqrt(forecast + 1.0)
    n = len(scores)
    rank = min(int(np.ceil((n + 1) * level)), n)
    return float(np.sort(scores)[rank - 1])


def interval(forecast: np.ndarray, q: float) -> tuple[np.ndarray, np.ndarray]:
    half = q * np.sqrt(forecast + 1.0)
    return np.clip(forecast - half, 0, None), forecast + half


def coverage(actual: np.ndarray, low: np.ndarray, high: np.ndarray) -> float:
    return float(((actual >= low) & (actual <= high)).mean())
