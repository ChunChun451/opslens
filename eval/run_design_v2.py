"""M8 design check (validation days only): does SLA-relative aging survive overload?

Why this file exists: on the test days, OpsLens v1 failed the +25% volume stress test
(51.7% breaches vs 29.1% for priority-first): with aging per hour and a fixed 240-minute guard,
already-lost tickets crowded out tickets that could still be saved. v2 measures aging in SLA
units and starts the guard only when a ticket is 240 minutes PAST its SLA.
To keep the test days honest, the choice between v1 and v2 is made here, on validation days
36-42 (seeds 1-3), at normal volume and with +25% volume. The test days are then re-run once.

Run:  .venv/Scripts/python.exe eval/run_design_v2.py   → eval/parts/design_v2.json
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
