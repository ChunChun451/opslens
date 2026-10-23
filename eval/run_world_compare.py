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
# Recorded only by the overload diagnosis (--diagnose, added 23 Oct after the 30-world result):
# who misses the deadline, by priority, tier and language. Same runs, more columns.
DIAGNOSE = ["segment.p1_breach_pct", "segment.gold_breach_pct", "segment.hindi_breach_pct", "quality.mean_minutes_late"]


def main() -> int:
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4
    diagnose = "--diagnose" in sys.argv
    policies = ["baseline_d", "least_slack", "opslens"] if diagnose else POLICIES
    keep = KEEP + DIAGNOSE if diagnose else KEEP
    started = time.perf_counter()
    jobs = [{"policy": p, "seed": s, "first_day": FIRST, "last_day": LAST, "staffing": p == "opslens",
             "tag": p} for p in policies for s in SEEDS]
    if "--v6-design" in sys.argv:  # W13: only the overload-mode candidates (the rest is in the counted run)
        from eval.run_design_v6 import candidate_jobs
        jobs = candidate_jobs(FIRST, LAST, SEEDS, with_v5=False)
    if "--v6" in sys.argv:  # W13 confirmation: every policy plus the chosen v6, one run
        cfg = json.loads(sys.argv[sys.argv.index("--v6") + 1])
        jobs += [{"policy": "opslens", "seed": s, "first_day": FIRST, "last_day": LAST, "staffing": True,
                  "weights": {"overload": cfg}, "tag": "opslens_v6"} for s in SEEDS]
    tags = [j["tag"] for j in jobs]
    policies = [t for i, t in enumerate(tags) if t not in tags[:i]]
    results = run_jobs(jobs, workers=workers)
    per_seed: dict[str, list[dict]] = {p: [] for p in policies}
    for r in sorted(results, key=lambda r: (r["job"]["tag"], r["job"]["seed"])):
        per_seed[r["job"]["tag"]].append({"seed": r["job"]["seed"], **{k: float(r["kpis"][k]) for k in keep}})
    mean = {p: {k: float(np.mean([row[k] for row in rows])) for k in keep} for p, rows in per_seed.items()}
    out = {"seeds": SEEDS, "first_day": FIRST, "last_day": LAST, "per_seed": per_seed, "mean": mean,
           "seconds": round(time.perf_counter() - started, 1)}
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "world_compare.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("  " + "  ".join(f"{p} {mean[p]['turnaround.breach_pct']:.2f}%" for p in policies))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
