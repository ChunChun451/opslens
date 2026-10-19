"""One random world's test (Plan v4 W1): every policy on this world's test days, same tickets and luck.

Run inside a world's copy of the repo (eval/run_worlds.py does this), after the routine pipeline
(generate → classifier → risk model → forecast + staffing plan):
    .venv/Scripts/python.exe eval/run_world_compare.py --workers 4

Why a separate script: eval/run_worlds.py runs 30 worlds; each needs the same small comparison,
and nothing in it may be tuned to the world. Policies: first come (A), urgent first (B), SLA due
(C), industry standard (D), least slack first (the strongest published rule we tested on the main
world) and OpsLens with its frozen weights. Seeds 1-3, test days 43-56.
Writes eval/parts/world_compare.json.

Example: a world with volume x1.2 and a 1.9x skill-mismatch slowdown → six policies x 3 seeds =
18 runs; the file keeps each run's KPIs so the orchestrator can pair them seed by seed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import PARTS, run_jobs  # noqa: E402

POLICIES = ["baseline_a", "baseline_b", "baseline_c", "baseline_d", "least_slack", "opslens"]
SEEDS = [1, 2, 3]
FIRST, LAST = 43, 56
KEEP = ["turnaround.breach_pct", "turnaround.p90_resolution_min", "quality.late_minutes_per_100",
        "quality.mean_utilisation", "quality.p99_wait_min", "productivity.transfers_per_100"]


def main() -> int:
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4
    started = time.perf_counter()
    jobs = [{"policy": p, "seed": s, "first_day": FIRST, "last_day": LAST, "staffing": p == "opslens",
             "tag": p} for p in POLICIES for s in SEEDS]
    results = run_jobs(jobs, workers=workers)
    per_seed: dict[str, list[dict]] = {p: [] for p in POLICIES}
    for r in sorted(results, key=lambda r: (r["job"]["policy"], r["job"]["seed"])):
        per_seed[r["job"]["policy"]].append({"seed": r["job"]["seed"], **{k: float(r["kpis"][k]) for k in KEEP}})
    mean = {p: {k: float(np.mean([row[k] for row in rows])) for k in KEEP} for p, rows in per_seed.items()}
    out = {"seeds": SEEDS, "first_day": FIRST, "last_day": LAST, "per_seed": per_seed, "mean": mean,
           "seconds": round(time.perf_counter() - started, 1)}
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "world_compare.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("  " + "  ".join(f"{p} {mean[p]['turnaround.breach_pct']:.2f}%" for p in POLICIES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
