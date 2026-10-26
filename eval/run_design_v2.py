from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import PARTS, run_jobs

SEEDS = [1, 2, 3]
FIRST, LAST = 36, 42
VARIANTS = {
    "v1 (aging per hour)": {"aging_in_sla_units": False},
    "v2 aging 0.5 per SLA": {"aging_in_sla_units": True, "aging_per_sla": 0.5},
    "v2 aging 1.0 per SLA": {"aging_in_sla_units": True, "aging_per_sla": 1.0},
    "v2 aging 2.0 per SLA": {"aging_in_sla_units": True, "aging_per_sla": 2.0},
    "v2 aging 3.0 per SLA": {"aging_in_sla_units": True, "aging_per_sla": 3.0},
    "v2 aging 4.0 per SLA": {"aging_in_sla_units": True, "aging_per_sla": 4.0},
}
LOADS = {"normal": {}, "+25% volume": {"volume_boost": 0.25}}


def main() -> int:
    started = time.perf_counter()
    jobs = []
    for load, extra in LOADS.items():
        for s in SEEDS:
            jobs.append({"policy": "baseline_b", "seed": s, "first_day": FIRST, "last_day": LAST,
                         "tag": f"Baseline B|{load}", **extra})
            for name, weights in VARIANTS.items():
                jobs.append({"policy": "opslens", "seed": s, "first_day": FIRST, "last_day": LAST,
                             "weights": weights, "tag": f"{name}|{load}", **extra})
    results = run_jobs(jobs, workers=10)
    table: dict[str, dict] = {}
    for r in results:
        name, load = r["job"]["tag"].split("|")
        row = table.setdefault(name, {})
        row.setdefault(load, []).append(r["kpis"])
    out = []
    print(f"validation days {FIRST}-{LAST}, seeds {SEEDS}:")
    for name, row in table.items():
        entry = {"variant": name}
        for load in LOADS:
            entry[f"{load} breach_pct"] = float(np.mean([k["turnaround.breach_pct"] for k in row[load]]))
            entry[f"{load} p99_wait_min"] = float(np.mean([k["quality.p99_wait_min"] for k in row[load]]))
            entry[f"{load} p1_breach_pct"] = float(np.mean([k["segment.p1_breach_pct"] for k in row[load]]))
        out.append(entry)
        print(f"  {name:22s} normal {entry['normal breach_pct']:5.2f}% (P99 wait {entry['normal p99_wait_min']:5.0f})"
              f"   +25%: {entry['+25% volume breach_pct']:5.2f}% (P1 {entry['+25% volume p1_breach_pct']:5.2f}%)")
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "design_v2.json").write_text(json.dumps({"validation_days": [FIRST, LAST], "seeds": SEEDS,
                                                      "rows": out}, indent=1), encoding="utf-8")
    print(f"wrote eval/parts/design_v2.json ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
