"""M2 check: Baseline A vs Baseline B on the held-out test days (43-56), 5 seeds.

Run:  .venv/Scripts/python.exe eval/run_baselines.py

Each seed = one set of luck draws (handle times, reopens, absences), shared by both
policies (common random numbers). Day 42 is a warm-up day: both policies start from an
empty floor at day 42 00:00, and only tickets created on days 43-56 are counted.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens.config import load_config  # noqa: E402
from opslens.impact import mean_std, paired_ci, summarize  # noqa: E402
from opslens.policies import baseline_a, baseline_b  # noqa: E402
from opslens.simulate import simulate  # noqa: E402
from opslens.world import build_world, day_bounds  # noqa: E402

SEEDS = [1, 2, 3, 4, 5]
SHOW = [
    "turnaround.breach_pct", "turnaround.mean_resolution_min", "turnaround.p90_resolution_min",
    "turnaround.mean_wait_min", "turnaround.max_backlog", "productivity.tickets_per_agent_hour",
    "productivity.transfers_per_100", "quality.reopen_rate_pct", "quality.p99_wait_min",
    "quality.mean_utilisation", "quality.load_fairness_std",
]


def main() -> int:
    cfg = load_config("generator")
    splits = cfg["splits"]
    tickets = pd.read_csv(ROOT / "data" / "generated" / "world_tickets.csv")
    warmup_start, _ = day_bounds(splits["validation_last_day"], splits["validation_last_day"])
    test_start, test_end = day_bounds(splits["validation_last_day"] + 1, splits["test_last_day"])

    kpis: dict[str, list[dict]] = {"A": [], "B": []}
    started = time.perf_counter()
    for seed in SEEDS:
        world = build_world(tickets, seed=seed)
        for key, policy in (("A", baseline_a()), ("B", baseline_b())):
            result = simulate(world, policy, warmup_start, test_end, metric_start_min=test_start,
                              seed_label=str(seed))
            kpis[key].append(summarize(result))
    print(f"{len(SEEDS)} seeds x 2 policies in {time.perf_counter() - started:.1f}s "
          f"(test days {splits['validation_last_day'] + 1}-{splits['test_last_day']}, "
          f"{int(kpis['A'][0]['tickets']):,} tickets)")
    print(f"{'KPI':38s} {'Baseline A':>16s} {'Baseline B':>16s} {'B - A (95% CI)':>26s}")
    for name in SHOW:
        a = [k[name] for k in kpis["A"]]
        b = [k[name] for k in kpis["B"]]
        (ma, sa), (mb, sb) = mean_std(a), mean_std(b)
        ci = paired_ci(b, a)
        print(f"{name:38s} {ma:9.2f} ±{sa:5.2f} {mb:9.2f} ±{sb:5.2f}   "
              f"{ci['mean_diff']:+8.2f} [{ci['ci_low']:+.2f}, {ci['ci_high']:+.2f}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
