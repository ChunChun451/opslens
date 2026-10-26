from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import PARTS, run_jobs
from opslens.impact import paired_ci

SEEDS = [1, 2, 3, 4, 5]
FIRST, LAST = 36, 42
V3 = {"mismatch_cost": None, "roster_margin_min": None}
VARIANTS = {"v3": V3, **{f"v5 margin {m}": {**V3, "roster_margin_min": m} for m in (10, 20, 30)}}
LOADS = {"normal": {}, "+25% volume": {"volume_boost": 0.25}}
KPIS = ["turnaround.breach_pct", "segment.p1_breach_pct", "segment.hindi_breach_pct", "quality.late_minutes_per_100",
        "quality.p99_wait_min", "quality.reopen_rate_pct"]


def main() -> int:
    started = time.perf_counter()
    jobs = [{"policy": "opslens", "seed": s, "first_day": FIRST, "last_day": LAST, "weights": w,
             "tag": f"{name}|{load}", **extra}
            for load, extra in LOADS.items() for name, w in VARIANTS.items() for s in SEEDS]
    results = run_jobs(jobs, workers=10)
    per: dict[tuple[str, str], list[dict]] = {}
    for r in sorted(results, key=lambda r: r["job"]["seed"]):
        name, load = r["job"]["tag"].split("|")
        per.setdefault((name, load), []).append(r["kpis"])
    rows = []
    base = "v3"
    for name in VARIANTS:
        row = {"variant": name}
        for load in LOADS:
            for k in KPIS:
                row[f"{load} {k}"] = float(np.mean([x[k] for x in per[(name, load)]]))
            ci = paired_ci([x["turnaround.breach_pct"] for x in per[(name, load)]],
                           [x["turnaround.breach_pct"] for x in per[(base, load)]])
            row[f"{load} breach_vs_v3"] = ci
        rows.append(row)
        print(f"{name:22s} normal {row['normal turnaround.breach_pct']:5.2f}% "
              f"(vs v3 {row['normal breach_vs_v3']['mean_diff']:+.2f} [{row['normal breach_vs_v3']['ci_low']:+.2f}, "
              f"{row['normal breach_vs_v3']['ci_high']:+.2f}]) Hindi {row['normal segment.hindi_breach_pct']:5.2f}% "
              f"late/100 {row['normal quality.late_minutes_per_100']:6.0f} reopen {row['normal quality.reopen_rate_pct']:.2f}% | "
              f"+25%: {row['+25% volume turnaround.breach_pct']:5.2f}%")
    v3 = rows[0]
    allowed = [r for r in rows[1:]
               if r["+25% volume turnaround.breach_pct"] <= v3["+25% volume turnaround.breach_pct"]
               and r["normal quality.late_minutes_per_100"] <= v3["normal quality.late_minutes_per_100"]]
    best = min(allowed, key=lambda r: r["normal turnaround.breach_pct"], default=None)
    adopt = best is not None and best["normal breach_vs_v3"]["ci_high"] < 0
    decision = {"chosen": best["variant"] if best else None, "adopt_v5": bool(adopt),
                "rule": "lowest normal breach among v5 margins not worse than v3 at +25% volume and on late minutes "
                        "per 100; adopt only if the paired 95% CI vs v3 is entirely below 0"}
    print("decision:", decision)
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "design_v5.json").write_text(json.dumps({"validation_days": [FIRST, LAST], "seeds": SEEDS, "rows": rows,
                                                      "decision": decision}, indent=1), encoding="utf-8")
    print(f"wrote eval/parts/design_v5.json ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
