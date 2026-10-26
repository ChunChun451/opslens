from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import PARTS, run_jobs
from opslens.impact import mean_std, paired_ci

POLICIES = ["baseline_a", "baseline_b", "baseline_c", "baseline_d", "opslens"]
SHOW = ["turnaround.breach_pct", "segment.p1_breach_pct", "turnaround.p90_resolution_min",
        "quality.p99_wait_min", "quality.mean_minutes_late", "quality.p90_minutes_late",
        "quality.late_minutes_per_100", "productivity.transfers_per_100", "quality.reopen_rate_pct"]


def compare(first: int, last: int, seeds: list[int]) -> dict:
    jobs = [{"policy": p, "seed": s, "first_day": first, "last_day": last, "staffing": p == "opslens"}
            for p in POLICIES for s in seeds]
    results = run_jobs(jobs, workers=min(len(jobs), 10))
    per = {p: [r["kpis"] for r in sorted((r for r in results if r["job"]["policy"] == p),
                                         key=lambda r: r["job"]["seed"])] for p in POLICIES}
    print(f"\ndays {first}-{last}, seeds {seeds}")
    print(f"{'KPI':32s}" + "".join(f"{p:>18s}" for p in POLICIES))
    for k in SHOW:
        print(f"{k:32s}" + "".join(f"{mean_std([r[k] for r in per[p]])[0]:18.2f}" for p in POLICIES))
    out = {"days": [first, last], "seeds": seeds, "per_seed": per}
    for base, label in (("baseline_c", "c"), ("baseline_d", "d")):
        diffs = {}
        for k in SHOW:
            ci = paired_ci([r[k] for r in per["opslens"]], [r[k] for r in per[base]])
            diffs[k] = ci
            print(f"OpsLens - {label.upper()}  {k:32s} {ci['mean_diff']:+9.2f} [{ci['ci_low']:+.2f}, {ci['ci_high']:+.2f}]")
        out[f"opslens_minus_{label}"] = diffs
    return out


if __name__ == "__main__":
    out = {} if "--test-only" in sys.argv else {"validation": compare(36, 42, [1, 2, 3])}
    if "--validation-only" not in sys.argv:
        out["test"] = compare(43, 56, [1, 2, 3, 4, 5])
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "baseline_c.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print("wrote eval/parts/baseline_c.json")
