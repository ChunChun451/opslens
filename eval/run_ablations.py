"""M8: which part of OpsLens creates the gain, how sensitive it is, and whether it survives
conditions it never saw. Test days 43-56, 5 seeds, same luck for every variant.

Run:  .venv/Scripts/python.exe eval/run_ablations.py

1. Ablations: full OpsLens, then one part switched off at a time — staffing plan, risk model,
   optimiser (each agent greedily takes its best ticket), classifier (route by the customer's
   menu choice), scarcity cost.
2. Sensitivity: gold weight ×1 / ×1.5 / ×2 (overall breach % vs gold customers' breach %).
3. Stress: +25% volume, 10% absenteeism — Baseline A, Baseline B and OpsLens each.
Writes eval/parts/ablations.json.
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
from opslens.impact import mean_std, paired_ci  # noqa: E402

SEEDS = [1, 2, 3, 4, 5]
FIRST, LAST = 43, 56
ABLATIONS = {
    "full": ("OpsLens (full)", {}, True),
    "no_staffing": ("without staffing plan", {}, False),
    "no_risk": ("without risk scores", {"use_risk": False}, True),
    "no_optimizer": ("without optimiser (greedy per agent)", {"use_optimizer": False}, True),
    "no_classifier": ("without classifier (menu choice routing)", {"use_classifier": False}, True),
    "no_scarcity": ("without scarcity cost", {"use_scarcity": False}, True),
}
STRESS = {"+25% volume": {"volume_boost": 0.25}, "10% absenteeism": {"absent_prob": 0.10}}


def kpi(results: list[dict], name: str) -> list[float]:
    return [r["kpis"][name] for r in sorted(results, key=lambda r: r["job"]["seed"])]


def main() -> int:
    started = time.perf_counter()
    jobs = []
    for key, (_, settings, staffing) in ABLATIONS.items():
        for s in SEEDS:
            jobs.append({"policy": "opslens", "seed": s, "first_day": FIRST, "last_day": LAST,
                         "settings": {**settings, "label": key}, "staffing": staffing, "tag": f"ablation:{key}"})
    for gold in (1.0, 1.5, 2.0):
        for s in SEEDS:
            jobs.append({"policy": "opslens", "seed": s, "first_day": FIRST, "last_day": LAST, "staffing": True,
                         "weights": {"gold_weight": gold}, "tag": f"gold:{gold}"})
    for name, extra in STRESS.items():
        for policy in ("baseline_a", "baseline_b", "opslens"):
            for s in SEEDS:
                jobs.append({"policy": policy, "seed": s, "first_day": FIRST, "last_day": LAST,
                             "staffing": policy == "opslens", "tag": f"stress:{name}:{policy}", **extra})
    results = run_jobs(jobs, workers=10)
    by_tag: dict[str, list[dict]] = {}
    for r in results:
        by_tag.setdefault(r["job"]["tag"], []).append(r)

    full_breach = kpi(by_tag["ablation:full"], "turnaround.breach_pct")
    ablations = []
    print("ablations (test days, 5 seeds):")
    for key, (label, _, _) in ABLATIONS.items():
        rs = by_tag[f"ablation:{key}"]
        b = kpi(rs, "turnaround.breach_pct")
        p90 = kpi(rs, "turnaround.p90_resolution_min")
        ci = paired_ci(b, full_breach)
        ablations.append({"key": key, "label": label, "breach_pct": dict(zip(("mean", "std"), mean_std(b))),
                          "p90_resolution_min": dict(zip(("mean", "std"), mean_std(p90))),
                          "delta_breach_vs_full": ci["mean_diff"], "ci_low": ci["ci_low"], "ci_high": ci["ci_high"],
                          "transfers_per_100": float(np.mean(kpi(rs, "productivity.transfers_per_100"))),
                          "reopen_rate_pct": float(np.mean(kpi(rs, "quality.reopen_rate_pct")))})
        print(f"  {label:44s} breach {np.mean(b):5.2f}%  ({ci['mean_diff']:+.2f} [{ci['ci_low']:+.2f}, {ci['ci_high']:+.2f}] vs full)  P90 {np.mean(p90):6.1f}")

    sensitivity = []
    print("gold weight sensitivity:")
    for gold in (1.0, 1.5, 2.0):
        rs = by_tag[f"gold:{gold}"]
        sensitivity.append({"gold_weight": gold, "breach_pct": float(np.mean(kpi(rs, "turnaround.breach_pct"))),
                            "gold_breach_pct": float(np.mean(kpi(rs, "segment.gold_breach_pct")))})
        print(f"  gold x{gold}: breach {sensitivity[-1]['breach_pct']:.2f}%, gold customers {sensitivity[-1]['gold_breach_pct']:.2f}%")

    stress = []
    print("stress tests:")
    for name in STRESS:
        row = {"scenario": name}
        for policy in ("baseline_a", "baseline_b", "opslens"):
            row[policy] = float(np.mean(kpi(by_tag[f"stress:{name}:{policy}"], "turnaround.breach_pct")))
            row[policy + "_p99_wait"] = float(np.mean(kpi(by_tag[f"stress:{name}:{policy}"], "quality.p99_wait_min")))
        ci = paired_ci(kpi(by_tag[f"stress:{name}:opslens"], "turnaround.breach_pct"),
                       kpi(by_tag[f"stress:{name}:baseline_b"], "turnaround.breach_pct"))
        row["opslens_minus_b"], row["ci_low"], row["ci_high"] = ci["mean_diff"], ci["ci_low"], ci["ci_high"]
        stress.append(row)
        print(f"  {name:16s} A {row['baseline_a']:5.2f}%  B {row['baseline_b']:5.2f}%  OpsLens {row['opslens']:5.2f}%  "
              f"(OpsLens - B {ci['mean_diff']:+.2f} [{ci['ci_low']:+.2f}, {ci['ci_high']:+.2f}])")

    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "ablations.json").write_text(json.dumps({"ablations": ablations, "sensitivity": sensitivity,
                                                      "stress": stress, "seeds": SEEDS}, indent=1), encoding="utf-8")
    print(f"wrote eval/parts/ablations.json ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
