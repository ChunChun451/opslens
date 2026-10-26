from __future__ import annotations

import pandas as pd


def kpi_table(df: pd.DataFrame, by: list[str], min_tickets: int = 1) -> pd.DataFrame:
    grouped = df.groupby(by, observed=True, dropna=False)
    table = pd.DataFrame({
        "tickets": grouped.size(),
        "breach_pct": 100.0 * grouped["breached"].mean(),
        "mean_wait_min": grouped["wait_min"].mean() if "wait_min" in df else float("nan"),
        "p90_wait_min": grouped["wait_min"].quantile(0.9) if "wait_min" in df else float("nan"),
        "mean_resolution_min": grouped["resolution_min"].mean(),
        "p90_resolution_min": grouped["resolution_min"].quantile(0.9),
        "transfers_per_100": 100.0 * grouped["transfers"].mean() if "transfers" in df else float("nan"),
        "reopen_pct": 100.0 * (grouped["reopens"].apply(lambda s: (s > 0).mean())) if "reopens" in df else float("nan"),
    })
    table["share_pct"] = 100.0 * table["tickets"] / len(df)
    return table[table["tickets"] >= min_tickets].sort_values("tickets", ascending=False)


def overall(df: pd.DataFrame) -> dict[str, float]:
    one = df.assign(_all="all")
    return kpi_table(one, ["_all"]).iloc[0].to_dict()
