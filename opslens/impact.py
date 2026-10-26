from __future__ import annotations

import math

import numpy as np

from opslens.simulate import SimResult

T_975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}


def summarize(result: SimResult) -> dict[str, float]:
    t = result.tickets
    resolved = t["resolution_min"].dropna()
    busy_min = sum(result.agent_busy_minutes.values())
    avail_min = sum(result.agent_available_minutes.values())
    utils = np.array([
        result.agent_busy_minutes[a] / result.agent_available_minutes[a]
        for a in result.agent_available_minutes
        if result.agent_available_minutes[a] > 0
    ])
    snaps = result.snapshots
    in_window = snaps[(snaps["minute"] >= t["created_min"].min()) & (snaps["minute"] <= t["created_min"].max())]
    return {
        "turnaround.breach_pct": 100.0 * float(t["breached"].mean()),
        "turnaround.mean_resolution_min": float(resolved.mean()),
        "turnaround.p90_resolution_min": float(np.percentile(resolved, 90)),
        "turnaround.mean_wait_min": float(t["wait_min"].mean()),
        "turnaround.max_backlog": float(in_window["waiting"].max()) if len(in_window) else 0.0,
        "productivity.tickets_per_agent_hour": len(resolved) / (avail_min / 60.0) if avail_min else 0.0,
        "productivity.transfers_per_100": 100.0 * float(t["transfers"].mean()),
        "productivity.busy_agent_hours": busy_min / 60.0,
        "quality.reopen_rate_pct": 100.0 * float((t["reopens"] > 0).mean()),
        "quality.p99_wait_min": float(np.percentile(t["wait_min"].dropna(), 99)),
        "quality.mean_utilisation": float(utils.mean()) if len(utils) else 0.0,
        "quality.load_fairness_std": float(utils.std()) if len(utils) else 0.0,
        **lateness(t),
        "segment.p1_breach_pct": segment_rate(t, t["priority"] == "P1"),
        "segment.gold_breach_pct": segment_rate(t, t["tier"] == "gold"),
        "segment.hindi_breach_pct": segment_rate(t, t["language"] == "hi"),
        "tickets": float(len(t)),
    }


def lateness(t) -> dict[str, float]:
    if "sla_min" not in t:
        return {}
    end = t["resolved_min"].max()
    resolution = t["resolution_min"].fillna(end - t["created_min"])
    late = (resolution - t["sla_min"]).clip(lower=0.0)
    breached = late[t["breached"]]
    return {
        "quality.mean_minutes_late": float(breached.mean()) if len(breached) else 0.0,
        "quality.p90_minutes_late": float(np.percentile(breached, 90)) if len(breached) else 0.0,
        "quality.late_minutes_per_100": 100.0 * float(late.sum()) / max(1, len(t)),
    }


def segment_rate(t, mask) -> float:
    return 100.0 * float(t.loc[mask, "breached"].mean()) if mask.any() else 0.0


def mean_std(values: list[float]) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    return float(arr.mean()), float(arr.std(ddof=1)) if len(arr) > 1 else 0.0


def paired_ci(treatment: list[float], control: list[float]) -> dict[str, float]:
    diffs = np.asarray(treatment, dtype=float) - np.asarray(control, dtype=float)
    n = len(diffs)
    mean = float(diffs.mean())
    if n < 2:
        return {"mean_diff": mean, "ci_low": mean, "ci_high": mean, "n": n}
    half = T_975.get(n - 1, 1.96) * float(diffs.std(ddof=1)) / math.sqrt(n)
    return {"mean_diff": mean, "ci_low": mean - half, "ci_high": mean + half, "n": n}
