"""Confirmation test for v5 (validation days only), written BEFORE it was run (18 Oct).

Why: eval/run_design_v5.py chose roster_margin_min 10 but, with 5 seeds, its gain (-0.11 points,
CI [-0.27, +0.04]) could not be told apart from luck; its interval is about +/-0.17 points wide.
Adding seeds to that experiment after seeing it would be cheating, so this is a NEW experiment:
- ONE candidate fixed in advance: v5 with roster_margin_min 10 (no choosing among variants);
- 20 seeds never used before (6-25), validation days 36-42, normal and +25% volume;
- adopt v5 only if its normal-volume breach % beats v3 with a paired 95% CI entirely below 0,
  and it is not worse than v3 at +25% volume nor on minutes past SLA per 100 tickets.
Run:  .venv/Scripts/python.exe eval/run_confirm_v5.py   -> eval/parts/confirm_v5.json
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
from opslens.impact import paired_ci  # noqa: E402

SEEDS = list(range(6, 26))
FIRST, LAST = 36, 42
V3 = {"mismatch_cost": None, "roster_margin_min": None}
VARIANTS = {"v3": V3, "v5 margin 10": {**V3, "roster_margin_min": 10}}
LOADS = {"normal": {}, "+25% volume": {"volume_boost": 0.25}}
KPIS = ["turnaround.breach_pct", "segment.hindi_breach_pct", "quality.late_minutes_per_100", "quality.p99_wait_min",
        "quality.reopen_rate_pct"]


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
    out = {"validation_days": [FIRST, LAST], "seeds": SEEDS, "means": {}, "v5_minus_v3": {}}
    for load in LOADS:
        for name in VARIANTS:
            out["means"][f"{name}|{load}"] = {k: float(np.mean([x[k] for x in per[(name, load)]])) for k in KPIS}
        out["v5_minus_v3"][load] = {k: paired_ci([x[k] for x in per[("v5 margin 10", load)]],
                                                 [x[k] for x in per[("v3", load)]]) for k in KPIS}
    d = out["v5_minus_v3"]
    adopt = (d["normal"]["turnaround.breach_pct"]["ci_high"] < 0
             and d["+25% volume"]["turnaround.breach_pct"]["mean_diff"] <= 0
             and d["normal"]["quality.late_minutes_per_100"]["mean_diff"] <= 0)
    out["decision"] = {"adopt_v5": bool(adopt), "rule": "normal breach CI entirely below 0, not worse at +25% "
                                                         "volume, not worse on late minutes per 100"}
    for load in LOADS:
        for k in KPIS:
            c = d[load][k]
            print(f"{load:12s} {k:32s} v5-v3 {c['mean_diff']:+8.3f} [{c['ci_low']:+.3f}, {c['ci_high']:+.3f}]")
    print("decision:", out["decision"])
    (PARTS / "confirm_v5.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote eval/parts/confirm_v5.json ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
