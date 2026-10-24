"""Performance tracking: the test fortnight day by day, per policy and per team.

Run:  .venv/Scripts/python.exe eval/run_tracking.py

Why: the problem statement asks for "a dashboard for insights, recommendations, and performance
tracking". Our results are totals over 14 held-out days; a team lead tracks a floor day by day. This
re-runs the main comparison (same tickets, same luck, seeds 1-5, days 43-56) and keeps each day's and
each team's missed SLAs. Nothing is tuned: the policies and weights are the shipped ones, and the
check at the end proves the daily rows add up exactly to the totals already in results.json.

Example (real run): Saturday 17 Oct (day 48), 1,456 tickets: the industry standard missed 4.57% of
deadlines, OpsLens 1.85% (means over the 5 seeds); OpsLens was lower on all 14 days, worst day for both
the sale day Mon 19 Oct (10.60% vs 3.98%). The dashboard draws one point per day and policy.
Writes eval/parts/tracking.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import PARTS, run_jobs  # noqa: E402
from opslens.config import load_config  # noqa: E402

POLICIES = ["baseline_a", "baseline_b", "baseline_d", "opslens"]
SEEDS = [1, 2, 3, 4, 5]
FIRST, LAST = 43, 56


def day_name(day: int) -> str:
    """'Sat 17 Oct' for calendar day `day` (day 1 = the calendar's start date)."""
    date = pd.Timestamp(load_config("calendar")["start_date"]) + pd.Timedelta(days=day - 1)
    return date.strftime("%a %d %b").replace(" 0", " ")


def aggregate(rows_by_seed: list[list[dict]]) -> dict:
    """Mean over seeds of each day's (and team-day's) missed share; tickets and minutes past SLA too."""
    frames = [pd.DataFrame(rows).assign(seed=k) for k, rows in enumerate(rows_by_seed)]
    df = pd.concat(frames, ignore_index=True)
    per_day = df.groupby(["seed", "day"])[["tickets", "missed", "late_minutes"]].sum().reset_index()
    per_day["missed_pct"] = 100.0 * per_day["missed"] / per_day["tickets"]
    per_day["late_per_100"] = 100.0 * per_day["late_minutes"] / per_day["tickets"]
    days = per_day.groupby("day").agg(tickets=("tickets", "mean"), missed=("missed", "mean"),
                                      missed_pct=("missed_pct", "mean"), missed_pct_std=("missed_pct", "std"),
                                      late_per_100=("late_per_100", "mean")).reset_index()
    per_team = df.groupby(["seed", "day", "team"])[["tickets", "missed"]].sum().reset_index()
    per_team["missed_pct"] = 100.0 * per_team["missed"] / per_team["tickets"]
    teams = per_team.groupby(["team", "day"])["missed_pct"].mean().reset_index()
    return {
        "days": [{"day": int(r.day), "name": day_name(int(r.day)), "tickets": float(r.tickets), "missed": float(r.missed),
                  "missed_pct": float(r.missed_pct), "missed_pct_std": float(r.missed_pct_std),
                  "late_per_100": float(r.late_per_100)} for r in days.itertuples()],
        "teams": {team: [float(v) for v in g.sort_values("day")["missed_pct"]] for team, g in teams.groupby("team")},
        "per_seed_total_pct": [float(100.0 * g["missed"].sum() / g["tickets"].sum()) for _, g in df.groupby("seed")],
    }


def main() -> int:
    started = time.perf_counter()
    jobs = [{"policy": p, "seed": s, "first_day": FIRST, "last_day": LAST, "staffing": p == "opslens",
             "daily": True, "tag": p} for p in POLICIES for s in SEEDS]
    results = run_jobs(jobs, workers=10)
    out = {"days": list(range(FIRST, LAST + 1)), "seeds": SEEDS, "policies": {}, "checks": {}}
    for policy in POLICIES:
        runs = sorted([r for r in results if r["job"]["policy"] == policy], key=lambda r: r["job"]["seed"])
        agg = aggregate([r["daily"] for r in runs])
        kpi = [r["kpis"]["turnaround.breach_pct"] for r in runs]
        # The daily rows must add up to the run's own total, seed by seed (same tickets, nothing lost).
        out["checks"][policy] = bool(np.allclose(agg.pop("per_seed_total_pct"), kpi, atol=1e-9))
        out["policies"][policy] = agg
    d, o = out["policies"]["baseline_d"]["days"], out["policies"]["opslens"]["days"]
    better = [a["day"] for a, b in zip(o, d) if a["missed_pct"] < b["missed_pct"]]
    out["summary"] = {"days": len(o), "opslens_better_than_industry_days": len(better),
                      "worst_day_opslens": max(o, key=lambda r: r["missed_pct"])["name"],
                      "worst_day_industry": max(d, key=lambda r: r["missed_pct"])["name"]}
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "tracking.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"days where OpsLens beats the industry standard: {len(better)} of {len(o)}; "
          f"daily rows add up: {out['checks']}  ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
