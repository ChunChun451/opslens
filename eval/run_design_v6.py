"""W13 design: which v6 overload-mode candidate, if any? (pre-registered in docs/PLAN_V4.md, W13)

Run:  .venv/Scripts/python.exe eval/run_design_v6.py --main     (main world, validation days 36-42, seeds 1-5)
      .venv/Scripts/python.exe eval/run_worlds.py --v6-design   (20 design worlds, candidates only)
      .venv/Scripts/python.exe eval/run_design_v6.py --choose   (apply the pre-registered choice)

Why: OpsLens loses the 11 sustained-overload worlds to least slack. The mode predicts whether the
floor will fall behind in the next window and, if so, values work per expected minute (c-mu).
Nothing here touches the test days; the choice uses validation days and the design worlds only.

Example: candidate A turns the mode on when the predicted work for the next 120 minutes exceeds the
minutes the agents on shift can give (threshold 1.0).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CANDIDATES = {
    "A": {"threshold": 1.0, "horizon_min": 120, "flat_urgency": False},
    "B": {"threshold": 1.0, "horizon_min": 120, "flat_urgency": True},
    "C": {"threshold": 1.2, "horizon_min": 60, "flat_urgency": False},
}
DESIGN_WORLDS = [7001, 7005, 7006, 7007, 7008, 7011, 7014, 7019, 7023, 7025, 7026,  # the 11 losses
                 7029, 7018, 7002, 7013, 7012, 7015,                                   # heavy wins
                 7022, 7004, 7009]                                                     # normal wins
OTHERS = ["baseline_a", "baseline_b", "baseline_c", "baseline_d", "least_slack"]
TIE = 0.05


def candidate_jobs(first: int, last: int, seeds: list[int], with_v5: bool) -> list[dict]:
    """One OpsLens run per candidate and seed (+ plain v5 if asked), same tickets and luck."""
    jobs = [{"policy": "opslens", "seed": s, "first_day": first, "last_day": last, "staffing": True,
             "weights": {"overload": cfg}, "tag": f"v6_{name}"} for name, cfg in CANDIDATES.items() for s in seeds]
    if with_v5:
        jobs += [{"policy": "opslens", "seed": s, "first_day": first, "last_day": last, "staffing": True,
                  "tag": "v5"} for s in seeds]
    return jobs


def main_world() -> int:
    """Main world, validation days 36-42, seeds 1-5: each candidate vs v5, paired by seed."""
    from eval.run_opslens import PARTS, run_jobs
    from opslens.impact import paired_ci
    started = time.perf_counter()
    results = run_jobs(candidate_jobs(36, 42, [1, 2, 3, 4, 5], with_v5=True), workers=8)
    by: dict[str, list] = {}
    for r in sorted(results, key=lambda r: r["job"]["seed"]):
        by.setdefault(r["job"]["tag"], []).append(r)
    v5 = [r["kpis"]["turnaround.breach_pct"] for r in by["v5"]]
    out = {"days": [36, 42], "seeds": [1, 2, 3, 4, 5], "v5_breach_pct": float(np.mean(v5)), "candidates": {}}
    for name in CANDIDATES:
        b = [r["kpis"]["turnaround.breach_pct"] for r in by[f"v6_{name}"]]
        ci = paired_ci(b, v5)
        on = float(np.mean([r.get("overload_minutes", 0.0) for r in by[f"v6_{name}"]]))
        out["candidates"][name] = {"breach_pct": float(np.mean(b)), "vs_v5": ci, "overload_minutes": on}
        print(f"  {name}: {np.mean(b):.3f}% vs v5 {np.mean(v5):.3f}%  diff {ci['mean_diff']:+.3f} "
              f"[{ci['ci_low']:+.3f}, {ci['ci_high']:+.3f}]  mode on {on:.0f} min")
    (PARTS / "design_v6_main.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote eval/parts/design_v6_main.json ({time.perf_counter() - started:.0f}s)")
    return 0


def choose() -> int:
    """The pre-registered choice: smallest total loss margin over the design worlds, among candidates
    not above v5 on main validation and keeping every design world v5 won."""
    parts = ROOT / "eval" / "parts"
    main = json.loads((parts / "design_v6_main.json").read_text(encoding="utf-8"))
    counted = {s: json.loads((parts / "worlds" / f"{s}.json").read_text(encoding="utf-8"))["compare"]["mean"]
               for s in DESIGN_WORLDS}
    design = {s: json.loads((parts / "worlds_v6design" / f"{s}.json").read_text(encoding="utf-8"))["compare"]["mean"]
              for s in DESIGN_WORLDS}
    report = {}
    for name in CANDIDATES:
        margin, kept, wins, rows = 0.0, True, 0, []
        for s in DESIGN_WORLDS:
            best = min(counted[s][p]["turnaround.breach_pct"] for p in OTHERS)
            v5 = counted[s]["opslens"]["turnaround.breach_pct"]
            v6 = design[s][f"v6_{name}"]["turnaround.breach_pct"]
            margin += max(0.0, v6 - best)
            win6, win5 = v6 <= best + TIE, v5 <= best + TIE
            wins += win6
            kept = kept and (win6 or not win5)
            rows.append({"seed": s, "best_other": best, "v5": v5, "v6": v6, "v6_wins": win6})
        main_ok = main["candidates"][name]["breach_pct"] <= main["v5_breach_pct"]
        report[name] = {"loss_margin": margin, "design_wins": wins, "keeps_v5_wins": kept,
                        "main_not_above_v5": main_ok, "qualifies": bool(kept and main_ok), "worlds": rows}
        print(f"  {name}: margin {margin:.2f}  wins {wins}/{len(DESIGN_WORLDS)}  keeps v5 wins {kept}  main ok {main_ok}")
    ok = [n for n in CANDIDATES if report[n]["qualifies"]]
    chosen = min(ok, key=lambda n: report[n]["loss_margin"]) if ok else None
    out = {"chosen": chosen, "candidates": CANDIDATES, "report": report, "design_worlds": DESIGN_WORLDS}
    (parts / "design_v6.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"chosen: {chosen}")
    return 0


if __name__ == "__main__":
    if "--main" in sys.argv:
        raise SystemExit(main_world())
    raise SystemExit(choose())
