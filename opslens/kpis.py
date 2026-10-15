"""KPI tables: volume, breach %, waits, transfers and reopens, sliced any way you like.

Why this design: every pattern card (M4) and every dashboard table starts as "group the
tickets by X and compare". One small function does it for any columns, so there is exactly
one definition of each KPI in the code (the same as CLAUDE.md section 4).

Example:
    >>> kpi_table(history, ["language"]).loc["hi", "mean_wait_min"]
    ... # Hindi tickets' mean wait, from the same function the dashboard uses
"""

from __future__ import annotations

import pandas as pd


def kpi_table(df: pd.DataFrame, by: list[str], min_tickets: int = 1) -> pd.DataFrame:
    """One row per group with the standard KPIs. Groups smaller than `min_tickets` are dropped."""
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
    """The same KPIs for the whole table, as a flat dict."""
    one = df.assign(_all="all")
    return kpi_table(one, ["_all"]).iloc[0].to_dict()
