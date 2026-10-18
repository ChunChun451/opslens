"""The physical floor: how many breaches would happen even with unlimited agents?

What it does: replays the test days with every agent able to take any number of tickets at once
(max_concurrent 1000) and routing by the TRUE category, in four variants: skilled agents only, or
"a skilled agent if one is on shift, else anyone who speaks the language, cross-skill"; each with
and without the staffing plan. A ticket counts as UNAVOIDABLE only if it breaches in all four:
its own work and reopens take longer than its SLA, or nobody on shift speaks its language.

Why: "how good is OpsLens?" needs a ceiling, not just baselines. The floor is a bound, not a
choice — nothing is tuned on it — so computing it on test days is fair. It turns the result into
"share of the possible improvement captured": (D − OpsLens) / (D − floor), per seed, where D is the
industry-standard baseline. Same tickets and the same luck (common random numbers) as every policy.

Example (validation days, seeds 1-3, from the 18 Oct diagnosis): unavoidable 1.36%, OpsLens v3
2.13%, industry standard 4.56% → v3 captured (4.56 − 2.13) / (4.56 − 1.36) = 76%.

Run:  .venv/Scripts/python.exe eval/run_floor.py   → eval/parts/floor.json  (after run_baseline_c.py)
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import GENERATED, PARTS  # noqa: E402
from opslens.config import load_config  # noqa: E402
from opslens.impact import mean_std  # noqa: E402
from opslens.policies import ClairvoyantSlackPolicy  # noqa: E402
from opslens.simulate import Assignment, simulate  # noqa: E402
from opslens.world import apply_staffing_plan, build_world, day_bounds, load_agents  # noqa: E402

FIRST, LAST = 43, 56
SEEDS = [1, 2, 3, 4, 5]


class CrossWhenNeeded:
    """Unlimited capacity, true category: a skilled agent if one is on shift, else any agent who
    speaks the language takes it at once as a cross-skill job (1.6x slower, more reopens)."""

    name = "floor: cross-skill when needed"

    def __init__(self, world) -> None:
        self.world = world

    def decide(self, state, now: float) -> list[Assignment]:
        free = state.free_agents(now)
        out = []
        for t in state.waiting_tickets():
            cat = self.world.true_category[t.idx]
            pick = next((a for a in free if t.language in a.languages and cat in a.skills), None)
            cross = pick is None
            if cross:
                pick = next((a for a in free if t.language in a.languages), None)
            if pick is not None:
                out.append(Assignment(t.idx, pick.agent_id, cat, deliberate_cross_skill=cross, reason=self.name))
        return out


def floor_run(job: tuple[str, bool, int]) -> tuple[set[str], int]:
    """Ticket ids that breach in one unlimited-capacity run, and how many tickets it scored."""
    kind, staffed, seed = job
    agents = load_agents()
    if staffed:
        agents = apply_staffing_plan(agents, json.loads((GENERATED / "staffing_plan.json").read_text(encoding="utf-8")))
    agents = [dataclasses.replace(a, max_concurrent=1000) for a in agents]
    world = build_world(pd.read_csv(GENERATED / "world_tickets.csv"), seed=seed, agents=agents,
                        gen_cfg=load_config("generator"))
    warm, _ = day_bounds(FIRST - 1, FIRST - 1)
    start, end = day_bounds(FIRST, LAST)
    policy = ClairvoyantSlackPolicy(world) if kind == "skilled" else CrossWhenNeeded(world)
    t = simulate(world, policy, warm, end, metric_start_min=start, seed_label=str(seed)).tickets
    return set(t.loc[t["breached"], "ticket_id"]), len(t)


def main() -> int:
    started = time.perf_counter()
    jobs = [(kind, staffed, s) for s in SEEDS for kind in ("skilled", "cross") for staffed in (False, True)]
    with ProcessPoolExecutor(10) as pool:
        runs = list(pool.map(floor_run, jobs))
    per_seed = []
    for s in SEEDS:
        sets = [r for j, r in zip(jobs, runs) if j[2] == s]
        unavoidable = set.intersection(*[b for b, _ in sets])
        per_seed.append(100.0 * len(unavoidable) / sets[0][1])
    bc = json.loads((PARTS / "baseline_c.json").read_text(encoding="utf-8"))["test"]["per_seed"]
    breach = {p: [k["turnaround.breach_pct"] for k in bc[p]] for p in ("baseline_d", "opslens")}
    captured = [100.0 * (d - o) / (d - f) for d, o, f in zip(breach["baseline_d"], breach["opslens"], per_seed)]
    out = {"test_days": [FIRST, LAST], "seeds": SEEDS, "floor_breach_pct": per_seed,
           "floor_breach_pct_mean": mean_std(per_seed)[0], "captured_pct": captured,
           "captured_pct_mean": mean_std(captured)[0], "captured_pct_std": mean_std(captured)[1],
           "opslens_above_floor_points": float(np.mean(breach["opslens"]) - np.mean(per_seed)),
           "definition": "unavoidable = breaches in all four unlimited-capacity runs (skilled-only / cross-skill when "
                         "needed, with / without the staffing plan); captured = (D - OpsLens) / (D - floor) per seed"}
    print(f"floor {out['floor_breach_pct_mean']:.2f}% | OpsLens {np.mean(breach['opslens']):.2f}% | "
          f"industry standard {np.mean(breach['baseline_d']):.2f}% | captured {out['captured_pct_mean']:.0f}% "
          f"± {out['captured_pct_std']:.0f} ({time.perf_counter() - started:.0f}s)")
    (PARTS / "floor.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
