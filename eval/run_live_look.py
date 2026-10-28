from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_best_baselines import by_key, job, mean
from eval.run_opslens import PARTS, run_jobs
from opslens.impact import paired_ci

FIRST, LAST = 36, 42
RESCUE_GRID = [2, 5, 10, 15, 20, 30]
LIVE = {"use_live_risk": True}


def main() -> int:
    seeds = [int(s) for s in (sys.argv[1] if len(sys.argv) > 1 else "1,2,3").split(",")]
    jobs = [job(k, s, FIRST, LAST) for k in ("baseline_a", "baseline_d", "least_slack", "opslens") for s in seeds]
    jobs += [job("opslens_live", s, FIRST, LAST) | {"policy": "opslens", "staffing": True, "settings": LIVE}
             for s in seeds]
    jobs += [job(f"rescue {th}", s, FIRST, LAST, {"threshold_min": th}) | {"policy": "least_slack_rescue"}
             for th in RESCUE_GRID for s in seeds]
    results = run_jobs(jobs, workers=min(len(jobs), 15))
    per = by_key(results)
    seconds: dict[str, list[float]] = {}
    for r in results:
        seconds.setdefault(r["job"]["key"], []).append(r["seconds"] / (LAST - FIRST + 2))
    grid = [{"threshold_min": th, "breach_pct": mean(per, f"rescue {th}"),
             "late_minutes_per_100": mean(per, f"rescue {th}", "quality.late_minutes_per_100")} for th in RESCUE_GRID]
    best = min(grid, key=lambda g: (g["breach_pct"], g["late_minutes_per_100"]))
    per["least_slack_rescue"] = per[f"rescue {best['threshold_min']}"]
    keys = ["baseline_a", "baseline_d", "least_slack", "least_slack_rescue", "opslens", "opslens_live"]
    rows = {k: {"breach_pct": mean(per, k), "p1_breach_pct": mean(per, k, "segment.p1_breach_pct"),
                "late_minutes_per_100": mean(per, k, "quality.late_minutes_per_100"),
                "p99_wait_min": mean(per, k, "quality.p99_wait_min"),
                "seconds_per_sim_day": sum(seconds.get(k, [0.0])) / max(1, len(seconds.get(k, [])))} for k in keys}
    vs = {}
    for a, b in (("opslens_live", "opslens"), ("opslens_live", "baseline_d"), ("opslens_live", "least_slack_rescue"),
                 ("opslens", "baseline_d"), ("opslens", "least_slack_rescue")):
        vs[f"{a} - {b}"] = {kpi: paired_ci([r[kpi] for r in per[a]], [r[kpi] for r in per[b]])
                            for kpi in ("turnaround.breach_pct", "segment.p1_breach_pct")}
    print(f"validation days {FIRST}-{LAST}, seeds {seeds}; least slack + rescue threshold chosen "
          f"{best['threshold_min']} min (grid {[(g['threshold_min'], round(g['breach_pct'], 2)) for g in grid]})")
    for k in keys:
        r = rows[k]
        print(f"  {k:20s} breach {r['breach_pct']:6.2f}%  P1 {r['p1_breach_pct']:6.2f}%  "
              f"late min/100 {r['late_minutes_per_100']:7.1f}  p99 wait {r['p99_wait_min']:6.1f}  "
              f"{r['seconds_per_sim_day']:.1f} s per simulated day")
    for name, d in vs.items():
        b, p = d["turnaround.breach_pct"], d["segment.p1_breach_pct"]
        print(f"  {name:36s} breach {b['mean_diff']:+.2f} [{b['ci_low']:+.2f}, {b['ci_high']:+.2f}]  "
              f"P1 {p['mean_diff']:+.2f} [{p['ci_low']:+.2f}, {p['ci_high']:+.2f}]")
    out = {"days": [FIRST, LAST], "seeds": seeds, "rescue_grid": grid, "rescue_chosen": best["threshold_min"],
           "rows": rows, "paired": vs, "per_seed": {k: per[k] for k in keys},
           "note": "validation days only; a first look, not an adoption test"}
    (PARTS / "live_look.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
