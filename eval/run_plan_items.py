from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens import risk
from opslens.config import load_config
from opslens.impact import mean_std, summarize
from opslens.plan import apply_items, effect_by_kpi, kpi_info, plan_kpis, playbook_items, staffing_items
from opslens.policies import OpsLensPolicy, OpsLensSettings
from opslens.simulate import simulate
from opslens.world import build_world, day_bounds, load_agents

GENERATED = ROOT / "data" / "generated"
PARTS = ROOT / "eval" / "parts"
FIRST, LAST = 43, 56
SEEDS = [1, 2, 3, 4, 5]


def run_job(job: dict) -> dict:
    tickets = pd.read_csv(GENERATED / "world_tickets.csv")
    preds = pd.read_csv(GENERATED / "predictions.csv", usecols=["ticket_id", "pred_final"])
    weekday = pd.Timestamp(load_config("calendar")["start_date"]).weekday()
    tickets, preds, agents, _ = apply_items(tickets, preds, load_agents(), job["items"], FIRST, LAST, weekday,
                                            alerts=job["alerts"])
    world = build_world(tickets, seed=job["seed"], agents=agents, gen_cfg=load_config("generator"))
    policy = OpsLensPolicy(world, dict(zip(preds.ticket_id, preds.pred_final)), risk.load(GENERATED / "models"),
                           load_config("optimizer"), OpsLensSettings())
    warm, _ = day_bounds(FIRST - 1, FIRST - 1)
    start, end = day_bounds(FIRST, LAST)
    result = simulate(world, policy, warm, end, metric_start_min=start, seed_label=str(job["seed"]))
    return {"tag": job["tag"], "seed": job["seed"], "kpis": plan_kpis(summarize(result))}


def catalogue() -> tuple[list[dict], list[dict]]:
    plans = json.loads((GENERATED / "staffing_plan.json").read_text(encoding="utf-8"))
    books = json.loads((PARTS / "playbooks.json").read_text(encoding="utf-8"))
    items = staffing_items(plans, load_agents()) + playbook_items(books["playbooks"], (FIRST, LAST))
    return items, books["alerts_used"]


def main() -> int:
    started = time.perf_counter()
    items, alerts = catalogue()
    for item in items:
        print(f"{item['id']:14s} {item['title']}")
    jobs = [{"tag": "none", "seed": s, "items": [], "alerts": alerts} for s in SEEDS]
    jobs += [{"tag": item["id"], "seed": s, "items": [item], "alerts": alerts} for item in items for s in SEEDS]
    jobs += [{"tag": "all", "seed": s, "items": items, "alerts": alerts} for s in SEEDS]
    print(f"{len(jobs)} runs ...", flush=True)
    with ProcessPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run_job, jobs))
    runs: dict[str, list[dict]] = {}
    for r in sorted(results, key=lambda r: r["seed"]):
        runs.setdefault(r["tag"], []).append(r["kpis"])
    base = runs["none"]

    for item in items:
        item["effect"] = effect_by_kpi(base, runs[item["id"]])
        d = item["effect"]["breaches"]
        print(f"{item['id']:14s} breaches {d['diff']:+7.1f} [{d['ci_low']:+.1f}, {d['ci_high']:+.1f}]")
    together = {"ids": [item["id"] for item in items], "effect": effect_by_kpi(base, runs["all"])}
    d = together["effect"]["breaches"]
    print(f"{'all items':14s} breaches {d['diff']:+7.1f} [{d['ci_low']:+.1f}, {d['ci_high']:+.1f}]")
    base_kpis = {k: dict(zip(("mean", "std"), mean_std([r[k] for r in base]))) for k in base[0]}
    print(f"without (nothing accepted): breach {base_kpis['breach_pct']['mean']:.2f}%")

    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "plan_items.json").write_text(json.dumps({
        "test_days": [FIRST, LAST], "warmup_day": FIRST - 1, "seeds": SEEDS, "policy": "opslens",
        "without": "OpsLens dispatch on the published roster, nothing accepted (no staffing moves, no playbooks)",
        **kpi_info(), "alerts_used": alerts, "base_kpis": base_kpis,
        "items": items, "all_items": together,
    }, indent=1), encoding="utf-8")
    print(f"wrote eval/parts/plan_items.json ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
