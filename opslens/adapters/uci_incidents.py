from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from opslens.config import PROJECT_ROOT

RAW_PATH = PROJECT_ROOT / "data" / "public" / "uci_incidents" / "incident_event_log.csv"
DATE_FORMAT = "%d/%m/%Y %H:%M"
PRIORITY_MAP = {"1 - Critical": "P1", "2 - High": "P1", "3 - Moderate": "P2", "4 - Low": "P3"}


def load_events(path: Path = RAW_PATH) -> pd.DataFrame:
    events = pd.read_csv(path, na_values=["?"], low_memory=False)
    for col in ("opened_at", "resolved_at", "closed_at", "sys_updated_at", "sys_created_at"):
        events[col] = pd.to_datetime(events[col], format=DATE_FORMAT, errors="coerce")
    return events.sort_values(["number", "sys_updated_at", "sys_mod_count"], kind="stable").reset_index(drop=True)


def to_incidents(events: pd.DataFrame) -> pd.DataFrame:
    last = events.groupby("number", sort=False).tail(1).set_index("number")
    first = events.groupby("number", sort=False).head(1).set_index("number")
    resolved = events.dropna(subset=["resolved_at"]).groupby("number")["resolved_at"].last()
    n_events = events.groupby("number").size()

    out = pd.DataFrame({
        "ticket_id": last.index,
        "created_at": first["opened_at"].reindex(last.index).to_numpy(),
        "channel": last["contact_type"].str.lower().to_numpy(),
        "priority": last["priority"].map(PRIORITY_MAP).to_numpy(),
        "priority_raw": last["priority"].to_numpy(),
        "impact": last["impact"].to_numpy(),
        "urgency": last["urgency"].to_numpy(),
        "final_category": last["category"].to_numpy(),
        "subcategory": last["subcategory"].to_numpy(),
        "location": last["location"].to_numpy(),
        "first_team": first["assignment_group"].reindex(last.index).to_numpy(),
        "resolved_by_team": last["assignment_group"].to_numpy(),
        "transfers": last["reassignment_count"].fillna(0).astype(int).to_numpy(),
        "reopens": last["reopen_count"].fillna(0).astype(int).to_numpy(),
        "knowledge": last["knowledge"].astype(bool).to_numpy(),
        "priority_confirmed": last["u_priority_confirmation"].astype(bool).to_numpy(),
        "resolved_at": resolved.reindex(last.index).to_numpy(),
        "made_sla": last["made_sla"].astype(bool).to_numpy(),
        "n_events": n_events.reindex(last.index).to_numpy(),
    })
    out["resolution_min"] = (out["resolved_at"] - out["created_at"]).dt.total_seconds() / 60.0
    out["breached"] = ~out["made_sla"]
    out["hour"] = out["created_at"].dt.hour
    out["weekday"] = out["created_at"].dt.weekday
    return out.sort_values("created_at", kind="stable").reset_index(drop=True)


def chronological_split(incidents: pd.DataFrame, train_share: float = 0.7) -> pd.Series:
    cutoff = incidents["created_at"].quantile(train_share)
    return pd.Series(np.where(incidents["created_at"] <= cutoff, "train", "test"), index=incidents.index)


def load_uci() -> tuple[pd.DataFrame, pd.DataFrame]:
    events = load_events()
    incidents = to_incidents(events)
    incidents["split"] = chronological_split(incidents)
    return incidents, events


def risk_features(incidents: pd.DataFrame, events: pd.DataFrame, hours_after_open: float = 1.0) -> pd.DataFrame:
    snap_time = incidents.set_index("ticket_id")["created_at"] + pd.Timedelta(hours=hours_after_open)
    ev = events.merge(snap_time.rename("snap_time"), left_on="number", right_index=True)
    known = ev[ev["sys_updated_at"] <= ev["snap_time"]]
    last = known.groupby("number").tail(1).set_index("number")
    first = events.groupby("number").head(1).set_index("number")
    inc = incidents.set_index("ticket_id")
    out = pd.DataFrame(index=inc.index)
    out["priority_raw"] = first["priority"].reindex(out.index)
    out["impact"] = first["impact"].reindex(out.index)
    out["urgency"] = first["urgency"].reindex(out.index)
    out["category"] = first["category"].reindex(out.index)
    out["channel"] = first["contact_type"].reindex(out.index)
    out["first_team"] = first["assignment_group"].reindex(out.index)
    out["team_now"] = last["assignment_group"].reindex(out.index)
    out["state_now"] = last["incident_state"].reindex(out.index)
    out["reassignments_now"] = last["reassignment_count"].reindex(out.index)
    out["updates_now"] = last["sys_mod_count"].reindex(out.index)
    out["knowledge"] = first["knowledge"].reindex(out.index).astype(float)
    out["hour"] = inc["created_at"].dt.hour
    out["weekday"] = inc["created_at"].dt.weekday
    opened = inc["created_at"].to_numpy()
    resolved = inc["resolved_at"].to_numpy()
    team = out["first_team"].to_numpy()
    snaps = snap_time.reindex(out.index).to_numpy()
    queue = np.zeros(len(out))
    order = np.argsort(opened)
    for pos, i in enumerate(order):
        lo = pos
        while lo > 0 and opened[order[lo - 1]] >= opened[i] - np.timedelta64(24, "h"):
            lo -= 1
        window = order[lo:pos]
        same = window[team[window] == team[i]]
        still_open = np.isnat(resolved[same]) | (resolved[same] > snaps[i])
        queue[i] = int(still_open.sum())
    out["open_in_team"] = queue
    out["breached"] = inc["breached"].astype(int)
    out["created_at"] = inc["created_at"]
    out["split"] = inc["split"]
    return out.reset_index()
