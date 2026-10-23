"""W5: CP-SAT weekly roster vs today's greedy moves. Design (pre-registered): docs/explain/roster_opt.md.

Run:  python eval/run_roster_opt.py design     (validation week 36-42, seeds 1-5, N chosen)
      python eval/run_roster_opt.py confirm    (same week, 20 fresh seeds 26-45, N fixed)
      python eval/run_roster_opt.py test       (test days 43-56 once, seeds 1-5)
Each stage adds its block to eval/parts/roster_opt.json; rosters go to data/generated/roster_opt/.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GENERATED = ROOT / "data" / "generated"
ROSTERS = GENERATED / "roster_opt"
OUT = ROOT / "eval" / "parts" / "roster_opt.json"
N_CHOICES = [1, 2, 3, 4]
DESIGN_SEEDS = [1, 2, 3, 4, 5]
CONFIRM_SEEDS = list(range(26, 46))
TEST_SEEDS = [1, 2, 3, 4, 5]
KPIS = {"breach_pct": "turnaround.breach_pct", "late_minutes_per_100": "quality.late_minutes_per_100",
        "p90_resolution_min": "turnaround.p90_resolution_min"}


# ---- Inputs: need and load per team-hour for a planning week ------------------------------------

def week_inputs(first_days: list[int], fit_last_day: int, stop_last_day: int) -> dict:
    """Forecast need/load for each planning week, from a model fitted on days 8..fit_last_day and
    early-stopped/conformal-fitted on fit_last_day+1..stop_last_day (never the planned days)."""
    from eval.run_forecast import TEAMS, event_uplift, predict_normal_day, team_workload
    from opslens import forecast as F
    from opslens import staffing as S
    from opslens.classify import CATEGORIES
    from opslens.config import load_config
    from opslens.ingest import load_history

    cal = load_config("calendar")
    first_weekday = pd.Timestamp(cal["start_date"]).weekday()
    events = {e["day"] for e in cal["known_events"]}
    h = load_history()
    preds = pd.read_csv(GENERATED / "predictions.csv", usecols=["ticket_id", "pred_final"])
    h = h.merge(preds, on="ticket_id")
    aht = h[h["day"] <= stop_last_day].groupby("final_category")["handled_min"].mean().to_dict()
    rows = F.add_features(F.hourly_counts(h, "pred_final", cal["days"], CATEGORIES), first_weekday, events)
    train = rows[(rows["day"] >= 8) & (rows["day"] <= fit_last_day)]
    valid = rows[(rows["day"] > fit_last_day) & (rows["day"] <= stop_last_day)]
    model = F.train(train[~train["day"].isin(events)], valid[~valid["day"].isin(events)])
    uplift = event_uplift(model, train, events)
    fc = lambda part: np.where(part["day"].isin(events), predict_normal_day(model, part) * uplift,  # noqa: E731
                               predict_normal_day(model, part))
    wf, wy = team_workload(valid, fc(valid), aht), team_workload(valid, valid["count"].to_numpy(), aht)
    q80_team = F.conformal_q(wy["arrivals"].to_numpy(), wf["arrivals"].to_numpy(), 0.8)
    shifts = S.shifts_from_agents(pd.read_csv(GENERATED / "agents.csv"))
    weeks = []
    for first_day in first_days:
        part = rows[rows["day"].isin(range(first_day, first_day + 7))]
        wl = team_workload(part, fc(part), aht)
        wl["arrivals"] = F.interval(wl["arrivals"].to_numpy(), q80_team)[1]
        wl["hour_index"] = wl["hour_index"] - (first_day - 1) * 24
        weeks.append({"first_day": first_day, "need": S.needed_per_hour(wl)[TEAMS], "load": S.load_per_hour(wl)[TEAMS]})
    return {"weeks": weeks, "shifts": shifts, "first_weekday": first_weekday, "q80_team": q80_team}


def build_rosters(inputs: dict, planners: dict) -> dict:
    """{name: (plan list for apply_staffing_plan, per-week info)} for each planner."""
    from opslens import staffing as S
    from opslens.roster_opt import plan_roster, weighted_shortage

    out = {}
    for name, how in planners.items():
        plans, info = [], []
        for w in inputs["weeks"]:
            args = (inputs["shifts"], w["need"], w["first_day"], 7, inputs["first_weekday"])
            if how == "published":
                new, changes, extra = list(inputs["shifts"]), [], {}
            elif how == "greedy":
                new, changes = S.plan_moves(*args, load=w["load"])
                extra = {}
            else:
                new, changes, extra = plan_roster(*args, load=w["load"], max_changes_per_team=how)
            score = weighted_shortage(new, w["need"], w["first_day"], 7, inputs["first_weekday"], w["load"])
            plans.append({"first_day": w["first_day"], "last_day": w["first_day"] + 6,
                          "shifts": [{"agent_id": s.agent_id, "start_hour": s.start_hour, "days_off": sorted(s.days_off)}
                                     for s in new]})
            info.append({"first_day": w["first_day"], "weighted_shortage": round(score, 2), "changes": changes, **extra})
            print(f"  {name:10s} week {w['first_day']}: weighted shortage {score:7.1f}, {len(changes)} changes "
                  f"{extra.get('status', '')}", flush=True)
        out[name] = (plans, info)
    return out


# ---- Simulation --------------------------------------------------------------------------------

def run_with_plan(job: dict) -> dict:
    """Worker: one OpsLens simulation with the roster file named in the job (none = published)."""
    import eval.run_opslens as R
    from opslens.world import apply_staffing_plan

    plan_file = job.get("plan_file")
    R.apply_staffing_plan = (lambda agents, plans: apply_staffing_plan(
        agents, json.loads(Path(plan_file).read_text(encoding="utf-8"))))
    try:
        return R.run_one({**job, "staffing": bool(plan_file)})
    finally:
        R.apply_staffing_plan = apply_staffing_plan


def simulate_rosters(names: list[str], seeds: list[int], first: int, last: int, prefix: str) -> dict:
    from concurrent.futures import ProcessPoolExecutor

    import eval.run_roster_opt as me
    jobs = [{"policy": "opslens", "seed": s, "first_day": first, "last_day": last, "tag": n,
             "plan_file": None if n == "published" else str(ROSTERS / f"{prefix}_{n}.json")}
            for n in names for s in seeds]
    with ProcessPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(me.run_with_plan, jobs))
    out = {}
    for n in names:
        rs = sorted([r for r in results if r["job"]["tag"] == n], key=lambda r: r["job"]["seed"])
        out[n] = {k: [r["kpis"][v] for r in rs] for k, v in KPIS.items()}
    return out


def compare(kpis: dict, a: str, b: str) -> dict:
    from opslens.impact import paired_ci
    res = {}
    for k in KPIS:
        ci = paired_ci(kpis[a][k], kpis[b][k])
        res[k] = {"mean_diff": ci["mean_diff"], "ci95": [ci["ci_low"], ci["ci_high"]]}
    return res


def summary(kpis: dict) -> dict:
    return {n: {k: round(float(np.mean(v)), 4) for k, v in d.items()} for n, d in kpis.items()}


def save_rosters(rosters: dict, prefix: str) -> None:
    ROSTERS.mkdir(parents=True, exist_ok=True)
    for name, (plans, _) in rosters.items():
        (ROSTERS / f"{prefix}_{name}.json").write_text(json.dumps(plans, indent=1), encoding="utf-8")


def load_out() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}


def main() -> int:
    stage = sys.argv[1] if len(sys.argv) > 1 else "design"
    started = time.perf_counter()
    out = load_out()
    if stage == "design":
        inputs = week_inputs([36], fit_last_day=28, stop_last_day=35)
        planners = {"published": "published", "greedy": "greedy", **{f"cpsat_n{n}": n for n in N_CHOICES}}
        rosters = build_rosters(inputs, planners)
        save_rosters(rosters, "val")
        kpis = simulate_rosters(list(planners), DESIGN_SEEDS, 36, 42, "val")
        best = min((n for n in planners if n.startswith("cpsat")), key=lambda n: np.mean(kpis[n]["breach_pct"]))
        out["design"] = {"days": [36, 42], "seeds": DESIGN_SEEDS, "forecast": "fit days 8-28, stop/conformal 29-35",
                         "rosters": {n: info for n, (_, info) in rosters.items()}, "means": summary(kpis),
                         "per_seed": kpis, "chosen": best, "chosen_minus_greedy": compare(kpis, best, "greedy"),
                         "greedy_minus_published": compare(kpis, "greedy", "published")}
        for n in planners:
            print(f"  {n:10s} breach {np.mean(kpis[n]['breach_pct']):.3f}%  late/100 {np.mean(kpis[n]['late_minutes_per_100']):.1f}")
        print(f"chosen {best}: vs greedy {out['design']['chosen_minus_greedy']['breach_pct']}")
    elif stage == "confirm":
        best = out["design"]["chosen"]
        kpis = simulate_rosters(["greedy", best], CONFIRM_SEEDS, 36, 42, "val")
        diff = compare(kpis, best, "greedy")
        design_ok = out["design"]["chosen_minus_greedy"]["breach_pct"]["ci95"][1] < 0
        out["confirm"] = {"seeds": CONFIRM_SEEDS, "candidate": best, "means": summary(kpis), "per_seed": kpis,
                          "candidate_minus_greedy": diff,
                          "adopted": bool(design_ok and diff["breach_pct"]["ci95"][1] < 0)}
        print(f"confirm {best} - greedy: {diff['breach_pct']}; adopted: {out['confirm']['adopted']}")
    elif stage == "test":
        best = out["design"]["chosen"]
        n = int(best.removeprefix("cpsat_n"))
        inputs = week_inputs([43, 50], fit_last_day=35, stop_last_day=42)  # the product's own forecast
        rosters = build_rosters(inputs, {"published": "published", "greedy": "greedy", best: n})
        save_rosters(rosters, "test")
        product = json.loads((GENERATED / "staffing_plan.json").read_text(encoding="utf-8"))
        same = [p["shifts"] for p in product] == [p["shifts"] for p in rosters["greedy"][0]]
        kpis = simulate_rosters(["published", "greedy", best], TEST_SEEDS, 43, 56, "test")
        out["test"] = {"days": [43, 56], "seeds": TEST_SEEDS, "greedy_equals_product_plan": same,
                       "rosters": {k: info for k, (_, info) in rosters.items()}, "means": summary(kpis), "per_seed": kpis,
                       "candidate_minus_greedy": compare(kpis, best, "greedy"),
                       "greedy_minus_published": compare(kpis, "greedy", "published"),
                       "candidate_minus_published": compare(kpis, best, "published")}
        print(f"test: greedy plan identical to the product's: {same}")
        for k in ("published", "greedy", best):
            print(f"  {k:10s} breach {np.mean(kpis[k]['breach_pct']):.3f}%")
        print(f"  {best} - greedy {out['test']['candidate_minus_greedy']['breach_pct']}")
    out.setdefault("seconds", {})[stage] = round(time.perf_counter() - started, 1)
    OUT.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
