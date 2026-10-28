from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import run_jobs
from opslens.config import load_config
from opslens.impact import paired_ci

OUT = ROOT / "eval" / "parts" / "food_1530"
FIRST, LAST, SEEDS = 36, 42, [1, 2, 3, 4, 5]
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
    "urgency_weight": [{"P1": 3.0, "P2": 1.5, "P3": 1.0}, {"P1": 5.0, "P2": 1.5, "P3": 1.0},
                       {"P1": 2.0, "P2": 1.5, "P3": 1.0}],
}
KPIS = ["turnaround.breach_pct", "segment.p1_breach_pct", "quality.p99_wait_min", "quality.late_minutes_per_100"]


def opslens_job(seed: int, weights: dict, tag: str) -> dict:
    return {"policy": "opslens", "seed": seed, "first_day": FIRST, "last_day": LAST, "staffing": True,
            "weights": weights, "tag": tag}


def mean_kpi(results: list[dict], key: str) -> float:
    return float(np.mean([r["kpis"][key] for r in results]))


def main() -> int:
    started = time.perf_counter()
    base = run_jobs([{"policy": "baseline_d", "seed": s, "first_day": FIRST, "last_day": LAST} for s in SEEDS],
                    workers=5)
    d_breach, d_p99 = mean_kpi(base, "turnaround.breach_pct"), mean_kpi(base, "quality.p99_wait_min")
    print(f"validation days {FIRST}-{LAST}, industry standard: breach {d_breach:.2f}%, P99 wait {d_p99:.0f} min",
          flush=True)
    shipped = load_config("optimizer")
    chosen = {name: shipped[name] for name in GRID}
    history = []
    current_runs = None
    cache: dict[str, list[dict]] = {}
    for name, values in GRID.items():
        keys = [json.dumps({**chosen, name: v}, sort_keys=True) for v in values]
        jobs = [opslens_job(s, {**chosen, name: v}, key) for key, v in zip(keys, values) if key not in cache
                for s in SEEDS]
        for r in run_jobs(jobs, workers=15) if jobs else []:
            cache.setdefault(r["job"]["tag"], []).append(r)
        scores = []
        for key, v in zip(keys, values):
            rs = sorted(cache[key], key=lambda r: r["job"]["seed"])
            score = {"value": v, **{kpi: mean_kpi(rs, kpi) for kpi in KPIS}}
            scores.append((score, rs))
            history.append({"weight": name, **score})
            print(f"  {name}={v}: breach {score['turnaround.breach_pct']:.3f}%  P1 "
                  f"{score['segment.p1_breach_pct']:.3f}%  P99 wait {score['quality.p99_wait_min']:.0f} min",
                  flush=True)
            if current_runs is None and v == chosen[name]:
                current_runs = rs
        allowed = [s for s in scores if s[0]["quality.p99_wait_min"] <= d_p99] or scores
        best = min(allowed, key=lambda s: (s[0]["turnaround.breach_pct"], s[0]["quality.p99_wait_min"]))
        current = next(s for s in scores if s[0]["value"] == chosen[name])
        if current in allowed and current[0]["turnaround.breach_pct"] - best[0]["turnaround.breach_pct"] <= TIE_POINTS:
            best = current
        chosen[name] = best[0]["value"]
        last_runs = best[1]
        print(f"-> {name} = {best[0]['value']}", flush=True)
    changed = {k: {"before": shipped[k], "after": chosen[k]} for k in GRID if shipped[k] != chosen[k]}
    paired = {kpi: paired_ci([r["kpis"][kpi] for r in last_runs], [r["kpis"][kpi] for r in current_runs])
              for kpi in KPIS}
    out = {"validation_days": [FIRST, LAST], "seeds": SEEDS, "tie_points": TIE_POINTS, "staffing_plan": True,
           "rule": ("Coordinate search in the fixed order of GRID (the 15/60/240 re-tune grid plus the P1 urgency "
                    "weight); for each weight, the value with the lowest mean validation breach among values whose "
                    "mean P99 wait is at most the industry standard's; the current value stays unless another is "
                    "better by more than tie_points. Test days never used. Reported only, not adopted."),
           "baseline_d": {"breach_pct": d_breach, "p99_wait_min": d_p99},
           "before": {name: shipped[name] for name in GRID}, "chosen": chosen, "changed": changed,
           "rechosen_minus_current_in_sample": paired,
           "in_sample_note": ("the re-chosen weights are scored on the same days and seeds they were chosen on, "
                              "so this difference is optimistic"),
           "history": history, "seconds": round(time.perf_counter() - started, 1)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "retune_1530.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("changed:", changed)
    b = paired["turnaround.breach_pct"]
    p = paired["segment.p1_breach_pct"]
    print(f"re-chosen - current (in sample): breach {b['mean_diff']:+.3f} [{b['ci_low']:+.3f}, {b['ci_high']:+.3f}]  "
          f"P1 {p['mean_diff']:+.3f} [{p['ci_low']:+.3f}, {p['ci_high']:+.3f}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
