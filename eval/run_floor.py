from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import GENERATED, PARTS
from opslens.config import load_config
from opslens.floor import unavoidable
from opslens.impact import mean_std
from opslens.world import apply_staffing_plan, build_world, day_bounds, load_agents

FIRST, LAST = 43, 56
SEEDS = [1, 2, 3, 4, 5]


def floor_pct(seed: int, tickets: pd.DataFrame) -> tuple[float, int]:
    plan = json.loads((GENERATED / "staffing_plan.json").read_text(encoding="utf-8"))
    warm, _ = day_bounds(FIRST - 1, FIRST - 1)
    start, end = day_bounds(FIRST, LAST)
    sets = []
    for agents in (load_agents(), apply_staffing_plan(load_agents(), plan)):
        world = build_world(tickets, seed=seed, agents=agents, gen_cfg=load_config("generator"))
        sets.append(unavoidable(world, warm, start, end))
    n = int(((world.created_min >= start) & (world.created_min < end)).sum())
    return 100.0 * len(sets[0] & sets[1]) / n, n


def main() -> int:
    started = time.perf_counter()
    tickets = pd.read_csv(GENERATED / "world_tickets.csv")
    per_seed = [floor_pct(s, tickets)[0] for s in SEEDS]
    bc = json.loads((PARTS / "baseline_c.json").read_text(encoding="utf-8"))["test"]["per_seed"]
    breach = {p: [k["turnaround.breach_pct"] for k in bc[p]] for p in ("baseline_d", "opslens")}
    captured = [100.0 * (d - o) / (d - f) for d, o, f in zip(breach["baseline_d"], breach["opslens"], per_seed)]
    out = {"test_days": [FIRST, LAST], "seeds": SEEDS, "floor_breach_pct": per_seed,
           "floor_breach_pct_mean": mean_std(per_seed)[0], "captured_pct": captured,
           "captured_pct_mean": mean_std(captured)[0], "captured_pct_std": mean_std(captured)[1],
           "opslens_above_floor_points": float(np.mean(breach["opslens"]) - np.mean(per_seed)),
           "definition": "unavoidable = R*(i) > SLA under both rosters (opslens/floor.py, exact per ticket); "
                         "captured = (D - OpsLens) / (D - floor) per seed"}
    print(f"floor {out['floor_breach_pct_mean']:.2f}% | OpsLens {np.mean(breach['opslens']):.2f}% | "
          f"industry standard {np.mean(breach['baseline_d']):.2f}% | captured {out['captured_pct_mean']:.0f}% "
          f"± {out['captured_pct_std']:.0f} ({time.perf_counter() - started:.0f}s)")
    (PARTS / "floor.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
