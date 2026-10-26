from __future__ import annotations

import numpy as np
import pandas as pd

from opslens.patterns import robust_z

Z = 3.5
WINDOW_DAYS = 28
MIN_HISTORY_DAYS = 5
MIN_USUAL_COUNT = 3.0
MIN_EXCESS_COUNT = 5
MIN_DAY_COUNT = 8
MIN_HISTORY_COUNT = 3
MIN_EXCESS_SHARE = 3
MIN_SHARE_FLOOR = 0.02


def as_of_table(incidents: pd.DataFrame, events: pd.DataFrame, hours: float = 24.0) -> pd.DataFrame:
    snap = incidents.set_index("ticket_id")["created_at"] + pd.Timedelta(hours=hours)
    ev = events[["number", "sys_updated_at", "reassignment_count"]].merge(snap.rename("snap"), left_on="number", right_index=True)
    known = ev[ev["sys_updated_at"] <= ev["snap"]]
    reassigned = known.groupby("number")["reassignment_count"].max()
    first = events.groupby("number").head(1).set_index("number")
    inc = incidents.set_index("ticket_id")
    out = pd.DataFrame(index=inc.index)
    out["created_at"] = inc["created_at"]
    out["date"] = inc["created_at"].dt.normalize()
    out["category"] = first["category"].reindex(out.index)
    out["team"] = inc["first_team"]
    out["resolution_h"] = inc["resolution_min"] / 60.0
    out["open_24h"] = ~(out["resolution_h"] <= hours)
    out["open_2h"] = ~(out["resolution_h"] <= 2.0)
    out["bounced_24h"] = reassigned.reindex(out.index).fillna(0).to_numpy() >= 1
    return out.reset_index().rename(columns={"index": "ticket_id"})


def share_z(k: int, n: int, past_shares: np.ndarray) -> float:
    p = float(np.median(past_shares))
    mad = float(np.median(np.abs(past_shares - p)))
    q = max(p, MIN_SHARE_FLOOR)
    chance = np.sqrt(q * (1 - q) / n)
    return 0.6745 * (k / n - p) / max(mad, 0.6745 * chance)


def comparable_days(dates: pd.DatetimeIndex, day: pd.Timestamp) -> np.ndarray:
    weekend = day.weekday() >= 5
    lo = day - pd.Timedelta(days=WINDOW_DAYS)
    ok = (dates >= lo) & (dates < day) & ((dates.weekday >= 5) == weekend)
    return np.flatnonzero(ok)


def spike_alerts(table: pd.DataFrame, days: pd.DatetimeIndex, z_alert: float = Z) -> list[dict]:
    counts = table.groupby(["category", "date"]).size().unstack(fill_value=0)
    all_dates = pd.date_range(days[0] - pd.Timedelta(days=WINDOW_DAYS), days[-1])
    counts = counts.reindex(columns=all_dates, fill_value=0)
    values = counts.to_numpy(dtype=float)
    alerts = []
    for day in days:
        past = comparable_days(all_dates, day)
        if len(past) < MIN_HISTORY_DAYS:
            continue
        col = all_dates.get_loc(day)
        for row, category in enumerate(counts.index):
            usual = values[row, past]
            median = float(np.median(usual))
            x = values[row, col]
            if median < MIN_USUAL_COUNT or x - median < MIN_EXCESS_COUNT:
                continue
            z = robust_z(x, usual)
            if z >= z_alert:
                alerts.append({"type": "spike", "segment": str(category), "day": day, "known_on": day,
                               "value": int(x), "usual": median, "z": round(float(z), 1)})
    return alerts


def pooled_windows(all_dates: pd.DatetimeIndex, opened: pd.Timestamp, pool_days: int) -> tuple[np.ndarray, np.ndarray]:
    weekend = opened.weekday() >= 5
    same = np.flatnonzero((all_dates <= opened) & ((all_dates.weekday >= 5) == weekend))
    today = same[-pool_days:]
    windows = []
    for end in comparable_days(all_dates, opened):
        rank = int(np.searchsorted(same, end))
        if rank >= pool_days - 1 and rank <= len(same) - 1 - pool_days:
            windows.append(same[rank - pool_days + 1: rank + 1])
    return today, np.array(windows, dtype=int).reshape(-1, pool_days)


def share_alerts(table: pd.DataFrame, days: pd.DatetimeIndex, by: str, flag: str, kind: str,
                 z_alert: float = Z, pool_days: int = 1) -> list[dict]:
    n = table.groupby([by, "date"]).size().unstack(fill_value=0)
    k = table[table[flag]].groupby([by, "date"]).size().unstack(fill_value=0)
    all_dates = pd.date_range(days[0] - pd.Timedelta(days=WINDOW_DAYS + 1 + 7 * pool_days), days[-1])
    n = n.reindex(columns=all_dates, fill_value=0)
    k = k.reindex(index=n.index, columns=all_dates, fill_value=0)
    n_val, k_val = n.to_numpy(dtype=float), k.to_numpy(dtype=float)
    alerts = []
    for known_on in days:
        opened = known_on - pd.Timedelta(days=1)
        today, windows = pooled_windows(all_dates, opened, pool_days)
        if len(today) < pool_days:
            continue
        for row, segment in enumerate(n.index):
            today_n, today_k = n_val[row, today].sum(), k_val[row, today].sum()
            if today_n < MIN_DAY_COUNT:
                continue
            past_n, past_k = n_val[row][windows].sum(axis=1), k_val[row][windows].sum(axis=1)
            usable = past_n >= MIN_HISTORY_COUNT
            if usable.sum() < MIN_HISTORY_DAYS:
                continue
            shares = past_k[usable] / past_n[usable]
            if today_k - today_n * float(np.median(shares)) < MIN_EXCESS_SHARE:
                continue
            z = share_z(int(today_k), int(today_n), shares)
            if z >= z_alert:
                alerts.append({"type": kind, "segment": str(segment), "day": opened, "known_on": known_on,
                               "value": round(float(today_k / today_n), 3), "usual": round(float(np.median(shares)), 3),
                               "z": round(float(z), 1), "incidents": int(today_n)})
    return alerts


V1 = {"name": "v1", "slow_flag": "open_24h", "pool_days": 1, "z": 3.5}
V2_CANDIDATES = [{"name": f"{flag}_pool{pool}_z{z}", "slow_flag": flag, "pool_days": pool, "z": z}
                 for flag in ("open_24h", "open_2h") for pool in (1, 3) for z in (3.5, 3.0)]


def watch(table: pd.DataFrame, first_day: str, last_day: str, settings: dict | None = None) -> pd.DataFrame:
    s = settings or V1
    days = pd.date_range(first_day, last_day)
    alerts = spike_alerts(table, days, s["z"])
    alerts += share_alerts(table, days[1:], "team", s["slow_flag"], "slowdown", s["z"], s["pool_days"])
    alerts += share_alerts(table, days[1:], "category", "bounced_24h", "bounce", s["z"], s["pool_days"])
    columns = ["type", "segment", "day", "known_on", "value", "usual", "z", "incidents"]
    return pd.DataFrame(alerts, columns=columns).sort_values(["known_on", "type", "segment"], kind="stable").reset_index(drop=True)
