from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

CATEGORICAL = ["category_pred", "priority", "channel", "language", "tier", "team", "hour_band"]
NUMERIC = [
    "age_min", "time_left_min", "sla_min", "order_value_inr", "hour", "is_weekend",
    "queue_total", "queue_team", "queue_team_language", "ahead_in_team_queue",
    "on_shift_team", "capable_on_shift", "in_progress_team", "arrivals_team_last_hour",
    "transfers_so_far",
]
FEATURES = CATEGORICAL + NUMERIC
HOUR_BAND = {h: b for lo, hi, b in [(0, 6, "night"), (7, 11, "morning"), (12, 15, "lunch"),
                                    (16, 18, "afternoon"), (19, 22, "dinner"), (23, 23, "late")]
             for h in range(lo, hi + 1)}


@dataclass
class QueueSnapshot:
    t: float
    waiting: pd.DataFrame
    in_progress_by_team: dict[str, int]
    arrivals_last_hour_by_team: dict[str, int]
    on_shift: pd.DataFrame
    first_weekday: int = 0


WAITING_COLUMNS = ["ticket_id", "created_min", "category_pred", "priority", "channel", "language",
                   "tier", "order_value_inr", "sla_min", "transfers_so_far"]


def features_for_snapshot(snap: QueueSnapshot, team_of: dict[str, str]) -> pd.DataFrame:
    w = snap.waiting.copy()
    if w.empty:
        return pd.DataFrame(columns=["ticket_id", "t"] + FEATURES)
    w["team"] = w["category_pred"].map(team_of).fillna("?")
    w["age_min"] = snap.t - w["created_min"]
    w["time_left_min"] = w["sla_min"] - w["age_min"]
    minute_of_day = snap.t % 1440
    day = int(snap.t // 1440)
    w["hour"] = int(minute_of_day // 60)
    w["hour_band"] = HOUR_BAND[int(minute_of_day // 60)]
    w["is_weekend"] = int((snap.first_weekday + day) % 7 in (5, 6))
    w["queue_total"] = len(w)
    w["queue_team"] = w.groupby("team")["ticket_id"].transform("size")
    w["queue_team_language"] = w.groupby(["team", "language"])["ticket_id"].transform("size")
    w["ahead_in_team_queue"] = w.groupby("team")["created_min"].rank(method="first") - 1
    team_counts = snap.on_shift["team"].value_counts() if len(snap.on_shift) else pd.Series(dtype=int)
    w["on_shift_team"] = w["team"].map(team_counts).fillna(0)
    capable = capability_table(snap.on_shift)
    w["capable_on_shift"] = [capable.get((lang, cat), 0) for lang, cat in zip(w["language"], w["category_pred"])]
    w["in_progress_team"] = w["team"].map(snap.in_progress_by_team).fillna(0)
    w["arrivals_team_last_hour"] = w["team"].map(snap.arrivals_last_hour_by_team).fillna(0)
    w["t"] = snap.t
    return w[["ticket_id", "t"] + FEATURES]


def capability_table(on_shift: pd.DataFrame) -> dict[tuple[str, str], int]:
    table: dict[tuple[str, str], int] = {}
    for langs, skills in zip(on_shift["languages"], on_shift["skills"]):
        for lang in langs:
            for skill in skills:
                table[(lang, skill)] = table.get((lang, skill), 0) + 1
    return table


def capable_count(on_shift: pd.DataFrame, language: str, category: str) -> int:
    if on_shift.empty:
        return 0
    ok = on_shift["languages"].map(lambda langs: language in langs) & on_shift["skills"].map(lambda s: category in s)
    return int(ok.sum())


def roster_on_shift(agents: pd.DataFrame, t: float, first_weekday: int) -> pd.DataFrame:
    day = int(t // 1440)
    hour = (t % 1440) / 60.0
    rows = []
    for a in agents.itertuples():
        off = {int(d) for d in str(a.days_off).split("|") if d != ""}
        start, length = float(a.shift_start_hour), float(a.shift_hours)
        today, yesterday = (first_weekday + day) % 7, (first_weekday + day - 1) % 7
        on = (today not in off and start <= hour < start + length) or \
             (yesterday not in off and hour < start + length - 24)
        if on:
            rows.append({"agent_id": a.agent_id, "team": a.team,
                         "languages": set(str(a.languages).split("|")), "skills": set(str(a.skills).split("|"))})
    return pd.DataFrame(rows, columns=["agent_id", "team", "languages", "skills"])


def snapshots_from_history(history: pd.DataFrame, agents: pd.DataFrame, team_of: dict[str, str],
                           first_day: int, last_day: int, every_min: float = 30.0,
                           first_weekday: int = 0) -> pd.DataFrame:
    h = history
    created = h["minute_of_run"].to_numpy()
    start = pd.Timestamp(h["created_at"].min().normalize())
    picked = ((h["first_pickup_at"] - start).dt.total_seconds() / 60.0).to_numpy()
    resolved = ((h["resolved_at"] - start).dt.total_seconds() / 60.0).to_numpy()
    picked = np.where(np.isnan(picked), np.inf, picked)
    resolved = np.where(np.isnan(resolved), np.inf, resolved)
    team = h["category_pred"].map(team_of).fillna("?").to_numpy()
    base = h[["ticket_id", "category_pred", "priority", "channel", "language", "customer_tier",
              "order_value_inr", "sla_min"]].rename(columns={"customer_tier": "tier"})
    base = base.assign(created_min=created, transfers_so_far=0)
    rows = []
    t = (first_day - 1) * 1440.0 + every_min
    end = last_day * 1440.0
    while t <= end:
        waiting_mask = (created < t) & (picked >= t)
        in_progress = (picked < t) & (resolved >= t)
        recent = (created >= t - 60) & (created < t)
        snap = QueueSnapshot(
            t=t,
            waiting=base.loc[waiting_mask, WAITING_COLUMNS],
            in_progress_by_team=pd.Series(team[in_progress]).value_counts().to_dict(),
            arrivals_last_hour_by_team=pd.Series(team[recent]).value_counts().to_dict(),
            on_shift=roster_on_shift(agents, t, first_weekday),
            first_weekday=first_weekday,
        )
        rows.append(features_for_snapshot(snap, team_of))
        t += every_min
    feats = pd.concat([r for r in rows if len(r)], ignore_index=True)
    feats = feats[feats["time_left_min"] > 0].reset_index(drop=True)
    labels = h.set_index("ticket_id")["breached"]
    feats["breached"] = feats["ticket_id"].map(labels).astype(int)
    return feats
