from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import PARTS, run_jobs
from opslens.config import load_config

FIRST, LAST, SEEDS = 36, 42, [1, 2, 3]
TIE_POINTS = 0.02
GRID = {
    "aging_per_sla": [3.0, 1.5, 6.0],
    "aging_lost": [0.2, 0.1, 0.5],
    "max_late_min": [480, 120, 240],
    "guard_queue_limit": [150, 100, 250],
    "cross_skill_min_rescue": [0.5, 0.3, 0.7],
    "mismatch_penalty": [2.0, 1.0, 3.0],
    "scarcity_weight": [0.3, 0.0, 1.0],
    "rescue_floor": [0.2, 0.05],
    "roster_margin_min": [10, 5],
}


def mean_kpi(results: list[dict], key: str) -> float:
    return float(np.mean([r["kpis"][key] for r in results]))


def main() -> int:
    started = time.perf_counter()
    base = run_jobs([{"policy": "baseline_d", "seed": s, "first_day": FIRST, "last_day": LAST} for s in SEEDS])
    d_breach, d_p99 = mean_kpi(base, "turnaround.breach_pct"), mean_kpi(base, "quality.p99_wait_min")
    print(f"validation days {FIRST}-{LAST}, industry standard: breach {d_breach:.2f}%, P99 wait {d_p99:.0f} min", flush=True)
    shipped = load_config("optimizer")
    chosen = {name: shipped[name] for name in GRID}
    history = []
    for name, values in GRID.items():
        jobs = [{"policy": "opslens", "seed": s, "first_day": FIRST, "last_day": LAST, "weights": {**chosen, name: v}}
                for v in values for s in SEEDS]
        results = run_jobs(jobs, workers=12)
        scores = []
        for v in values:
            rs = [r for r in results if r["job"]["weights"][name] == v]
            breach, p99 = mean_kpi(rs, "turnaround.breach_pct"), mean_kpi(rs, "quality.p99_wait_min")
            scores.append({"value": v, "breach_pct": breach, "p99_wait_min": p99})
            history.append({"weight": name, **scores[-1]})
            print(f"  {name}={v}: breach {breach:.3f}%, P99 wait {p99:.0f} min", flush=True)
        allowed = [s for s in scores if s["p99_wait_min"] <= d_p99] or scores
        best = min(allowed, key=lambda s: (s["breach_pct"], s["p99_wait_min"]))
        current = next(s for s in scores if s["value"] == chosen[name])
        if current in allowed and current["breach_pct"] - best["breach_pct"] <= TIE_POINTS:
            best = current
        chosen[name] = best["value"]
        print(f"-> {name} = {best['value']}", flush=True)
    out = {"validation_days": [FIRST, LAST], "seeds": SEEDS, "tie_points": TIE_POINTS,
           "rule": ("Coordinate search in the fixed order of GRID; for each weight, the value with the lowest mean "
                    "validation breach among values whose mean P99 wait is at most the industry standard's; the "
                    "current value stays unless another is better by more than tie_points. Test days never used."),
           "baseline_d": {"breach_pct": d_breach, "p99_wait_min": d_p99},
           "before": {name: shipped[name] for name in GRID}, "chosen": chosen, "history": history,
           "seconds": round(time.perf_counter() - started, 1)}
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "tuning_sla.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("chosen weights:", chosen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
