from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import PARTS, run_jobs

POLICIES = ["baseline_a", "baseline_b", "baseline_c", "baseline_d", "least_slack", "opslens"]
SEEDS = [1, 2, 3]
FIRST, LAST = 43, 56
KEEP = ["turnaround.breach_pct", "turnaround.p90_resolution_min", "quality.late_minutes_per_100",
        "quality.mean_utilisation", "quality.p99_wait_min", "productivity.transfers_per_100"]
DIAGNOSE = ["segment.p1_breach_pct", "segment.gold_breach_pct", "segment.hindi_breach_pct", "quality.mean_minutes_late"]


def main() -> int:
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4
    diagnose = "--diagnose" in sys.argv
    policies = ["baseline_d", "least_slack", "opslens"] if diagnose else POLICIES
    keep = KEEP + DIAGNOSE if diagnose else KEEP
    started = time.perf_counter()
    jobs = [{"policy": p, "seed": s, "first_day": FIRST, "last_day": LAST, "staffing": p == "opslens",
             "tag": p} for p in policies for s in SEEDS]
    if "--v6-design" in sys.argv:
        from eval.run_design_v6 import candidate_jobs
        from eval.run_design_v6 import ROUND2
        jobs = candidate_jobs(FIRST, LAST, SEEDS, with_v5=False, names=ROUND2 if "--round2" in sys.argv else None)
    if "--v6" in sys.argv:
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
