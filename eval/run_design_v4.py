"""Design check v4 (validation days only): what should a cross-skill job cost?

Why this file exists: a breach diagnosis on validation days 36-42 (seeds 1-3) found that of
OpsLens v3's 2.13% breaches, 1.36 points happen even with unlimited agents and perfect routing
(the work alone is longer than the SLA, or the customer reopens too late). Of the 0.77 points
left, the largest group is Hindi and regional-language P2 tickets at night: they waited a median
682 minutes and were never given to an agent who speaks the language but is not trained on the
category, although that would have saved most of them. Cause: v3 subtracts a FLAT mismatch
penalty (2.0, tuned for v1's value scale) after multiplying by urgency, so a cross-skill job costs
a P2 about 1.2 breach-probability units — more than any P2 can be worth — but a P1 only 0.6.
v4 prices it in breach-probability units scaled like the ticket's value (`mismatch_cost`).

PRE-REGISTERED (written before the first run):
- Grid: mismatch_cost 0.2 / 0.4 / 0.6 / 0.8 / 1.0, against v3; validation days 36-42, seeds 1-5,
  normal volume and +25% volume (the stress that v1 and v2 failed).
- Pick the cost with the lowest normal-volume breach % among those that are (a) not worse than v3
  at +25% volume and (b) not worse than v3 on minutes past SLA per 100 tickets (normal volume).
- Adopt v4 only if its normal-volume breach % beats v3 with a paired 95% CI entirely below 0.
  Otherwise v3 stays. If adopted: test days run once, then a new sealed world; both reported.

Run:  .venv/Scripts/python.exe eval/run_design_v4.py   → eval/parts/design_v4.json
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

SEEDS = [1, 2, 3, 4, 5]
FIRST, LAST = 36, 42
VARIANTS = {"v3 (flat penalty 2.0)": {}, **{f"v4 cost {c}": {"mismatch_cost": c} for c in (0.2, 0.4, 0.6, 0.8, 1.0)}}
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
    base = "v3 (flat penalty 2.0)"
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
    decision = {"chosen": best["variant"] if best else None, "adopt_v4": bool(adopt),
                "rule": "lowest normal breach among variants not worse than v3 at +25% volume and on late minutes "
                        "per 100; adopt only if the paired 95% CI vs v3 is entirely below 0"}
    print("decision:", decision)
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "design_v4.json").write_text(json.dumps({"validation_days": [FIRST, LAST], "seeds": SEEDS, "rows": rows,
                                                      "decision": decision}, indent=1), encoding="utf-8")
    print(f"wrote eval/parts/design_v4.json ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
