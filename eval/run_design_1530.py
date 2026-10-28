from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import GENERATED, published_rule
from opslens import risk
from opslens.config import load_config
from opslens.impact import mean_std, paired_ci, summarize
from opslens.policies import (OpsLensPolicy, OpsLensSettings, baseline_d, cross_estimates, handle_lognormal,
                              reopen_estimates)
from opslens.simulate import simulate
from opslens.world import apply_staffing_plan, build_world, day_bounds, load_agents

OUT = ROOT / "eval" / "parts" / "food_1530"
ESTIMATES = OUT / "estimates_1530.json"
FIRST, LAST = 36, 42
DESIGN_SEEDS = list(range(1, 11))
CONFIRM_SEEDS = list(range(101, 121))
TEST_FIRST, TEST_LAST = 43, 56
TEST_SEEDS = [1, 2, 3, 4, 5]
PILOT_SEED = 0
PILOT_WEEKS = [(1, 7), (8, 14), (15, 21), (22, 28), (29, 35)]
BLEND_GRID = [0.25, 0.5, 0.75]
TIE = 0.05
RESCUE_THRESHOLD = 10
GATES = {"lost_lane": True, "clock_cross_gate": True}
CANDIDATES = {
    "S1": {"settings": GATES, "weights": {}},
    **{f"S2 w={w}": {"settings": {**GATES, "use_live_risk": True, "queue_clock": True},
                     "weights": {"live_clock_weight": w}} for w in BLEND_GRID},
}
KPIS = ["turnaround.breach_pct", "segment.p1_breach_pct", "quality.p99_wait_min", "quality.late_minutes_per_100",
        "segment.hindi_breach_pct", "quality.reopen_rate_pct"]


def s3_spec(weight: float) -> dict:
    return {"settings": {**GATES, "use_live_risk": True, "queue_clock": True, "p1_guard": True},
            "weights": {"live_clock_weight": weight}}


def history_frame() -> pd.DataFrame:
    return pd.read_csv(GENERATED / "history.csv", usecols=["created_at", "final_category", "channel", "handled_min",
                                                           "reopens", "resolution_min", "transfers"])


def world_for(seed: int, staffing: bool = False):
    tickets = pd.read_csv(GENERATED / "world_tickets.csv")
    preds = pd.read_csv(GENERATED / "predictions.csv", usecols=["ticket_id", "pred_final"])
    agents = load_agents()
    if staffing:
        agents = apply_staffing_plan(agents, json.loads((GENERATED / "staffing_plan.json").read_text(encoding="utf-8")))
    world = build_world(tickets, seed=seed, agents=agents, gen_cfg=load_config("generator"))
    return world, dict(zip(preds.ticket_id, preds.pred_final))


def opslens_policy(world, predicted, spec: dict, estimates: dict | None):
    start = load_config("calendar")["start_date"]
    dist = handle_lognormal(history_frame(), start, last_day=35)
    weights = {**load_config("optimizer"), **spec.get("weights", {})}
    settings = OpsLensSettings(**spec.get("settings", {}))
    needs = settings.use_live_risk or settings.lost_lane or settings.clock_cross_gate
    return OpsLensPolicy(world, predicted, risk.load(GENERATED / "models"), weights, settings,
                         handle_dist=dist if needs else None, estimates=estimates)


def run_job(job: dict) -> dict:
    started = time.perf_counter()
    world, predicted = world_for(job["seed"], job.get("staffing", False))
    first, last = job.get("days", (FIRST, LAST))
    if job["key"] == "baseline_d":
        policy = baseline_d(world, predicted)
    elif job["key"] == "least_slack_rescue":
        policy = published_rule({"policy": "least_slack_rescue", "params": {"threshold_min": RESCUE_THRESHOLD}},
                                world, predicted)
    else:
        policy = opslens_policy(world, predicted, job.get("spec", {}), job.get("estimates"))
    warm, _ = day_bounds(first - 1, first - 1)
    start, end = day_bounds(first, last)
    result = simulate(world, policy, warm, end, metric_start_min=start, seed_label=str(job["seed"]))
    return {"key": job.get("tag", job["key"]), "seed": job["seed"], "kpis": summarize(result),
            "seconds": round(time.perf_counter() - started, 1)}


class CrossRecorder:
    def __init__(self, inner):
        self.inner, self.name = inner, inner.name
        self.first: dict[int, tuple[float, bool]] = {}

    def decide(self, state, now):
        out = self.inner.decide(state, now)
        for a in out:
            if a.ticket_idx not in self.first:
                self.first[a.ticket_idx] = (now, bool(a.deliberate_cross_skill))
        return out


def pilot_week(week: tuple[int, int]) -> list[dict]:
    world, predicted = world_for(PILOT_SEED)
    rec = CrossRecorder(opslens_policy(world, predicted, {}, None))
    first, last = week
    start, end = day_bounds(first, last)
    warm = day_bounds(first - 1, first - 1)[0] if first > 1 else start
    result = simulate(world, rec, warm, end, metric_start_min=start, seed_label="pilot")
    t = result.tickets
    rows = []
    for r in t.itertuples():
        got = rec.first.get(int(r.idx))
        if got is None or not got[1] or np.isnan(r.resolved_min):
            continue
        rows.append({"category": r.category, "channel": world.channel[int(r.idx)], "transfers": int(r.transfers),
                     "reopens": int(r.reopens), "reopened": bool(r.reopens > 0),
                     "minutes": float(r.handled_min) if r.reopens == 0 else float("nan")})
    return rows


def estimates() -> int:
    started = time.perf_counter()
    start = load_config("calendar")["start_date"]
    hist = history_frame()
    reopen = reopen_estimates(hist, start, last_day=35)
    with ProcessPoolExecutor(max_workers=len(PILOT_WEEKS)) as pool:
        jobs = pd.DataFrame([row for rows in pool.map(pilot_week, PILOT_WEEKS) for row in rows])
    cross = cross_estimates(jobs, handle_lognormal(hist, start, last_day=35))
    gen = load_config("generator")
    est = {"cross_factor": cross["cross_factor"], "reopen_trained": reopen["reopen_trained"],
           "reopen_cross": cross["reopen_cross"], "reopen_handle_factor": reopen["reopen_handle_factor"]}
    truth = {"cross_factor": gen["skill_mismatch_factor"], "reopen_trained": gen["reopen_prob"]["matched"],
             "reopen_cross": gen["reopen_prob"]["mismatch"], "reopen_handle_factor": gen["reopen_handle_factor"]}
    out = {"estimates": est, "true_values_for_reporting_only": truth,
           "sources": {"reopen_trained, reopen_handle_factor": f"history.csv days 1-35 ({reopen['n_tickets']:,} "
                                                               f"tickets, {reopen['n_reopened']:,} reopened)",
                       "cross_factor, reopen_cross": (f"training-days pilot: OpsLens today, days 1-35, seed "
                                                      f"{PILOT_SEED}, {cross['n_cross_jobs']:,} cross-skill first "
                                                      f"services ({cross['n_clean_jobs']:,} without reopen or "
                                                      f"transfer used for the slowdown)")},
           "seconds": round(time.perf_counter() - started, 1)}
    OUT.mkdir(parents=True, exist_ok=True)
    ESTIMATES.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for k in est:
        print(f"{k:22s} estimate {est[k]:.4f}   true {truth[k]}")
    print(out["sources"])
    return 0


def run_all(jobs: list[dict]) -> dict[str, list[dict]]:
    with ProcessPoolExecutor(max_workers=15) as pool:
        results = list(pool.map(run_job, sorted(jobs, key=lambda j: j["key"] in ("baseline_d", "least_slack_rescue"))))
    per: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(results, key=lambda r: r["seed"]):
        per[r["key"]].append(r["kpis"])
    return per


def means(per: dict, key: str) -> dict:
    return {k: mean_std([r[k] for r in per[key]])[0] for k in KPIS}


def verdict(per: dict, key: str) -> dict:
    b = paired_ci([r["turnaround.breach_pct"] for r in per[key]], [r["turnaround.breach_pct"] for r in per["opslens"]])
    p = paired_ci([r["segment.p1_breach_pct"] for r in per[key]], [r["segment.p1_breach_pct"] for r in per["opslens"]])
    m, d = means(per, key), means(per, "baseline_d")
    checks = {"breach_ci_below_0": b["ci_high"] < 0, "p1_not_up": p["mean_diff"] <= 0,
              "p99_wait_not_above_industry": m["quality.p99_wait_min"] <= d["quality.p99_wait_min"],
              "late_min_per_100_below_industry": m["quality.late_minutes_per_100"] < d["quality.late_minutes_per_100"]}
    return {"vs_opslens_breach": b, "vs_opslens_p1": p, "checks": checks, "passed": all(checks.values())}


def comparisons(per: dict, keys: list[str]) -> dict:
    out = {}
    for k in keys:
        for base in ("baseline_d", "least_slack_rescue"):
            out[f"{k} - {base}"] = {kpi: paired_ci([r[kpi] for r in per[k]], [r[kpi] for r in per[base]])
                                    for kpi in ("turnaround.breach_pct", "segment.p1_breach_pct")}
    return out


def load_estimates() -> dict:
    return json.loads(ESTIMATES.read_text(encoding="utf-8"))["estimates"]


def design() -> int:
    started = time.perf_counter()
    est = load_estimates()
    jobs = [{"key": k, "seed": s} for k in ("opslens", "baseline_d", "least_slack_rescue") for s in DESIGN_SEEDS]
    jobs += [{"key": name, "seed": s, "spec": spec, "estimates": est} for name, spec in CANDIDATES.items()
             for s in DESIGN_SEEDS]
    per = run_all(jobs)
    blend = {w: means(per, f"S2 w={w}")["turnaround.breach_pct"] for w in BLEND_GRID}
    best_w = min(BLEND_GRID, key=lambda w: (blend[w] - (TIE if w == 0.5 else 0.0), w))
    per["S2"] = per[f"S2 w={best_w}"]
    per.update(run_all([{"key": "S3", "seed": s, "spec": s3_spec(best_w), "estimates": est} for s in DESIGN_SEEDS]))
    keys = ["opslens", "baseline_d", "least_slack_rescue", "S1", *[f"S2 w={w}" for w in BLEND_GRID], "S2", "S3"]
    verdicts = {k: verdict(per, k) for k in ("S1", "S2", "S3")}
    passing = [k for k in ("S1", "S2", "S3") if verdicts[k]["passed"]]
    chosen = None
    if passing:
        low = min(means(per, k)["turnaround.breach_pct"] for k in passing)
        chosen = next(k for k in passing if means(per, k)["turnaround.breach_pct"] <= low + TIE)
    out = {"days": [FIRST, LAST], "seeds": DESIGN_SEEDS, "estimates": est, "blend_breach_pct": blend,
           "s2_weight": best_w, "means": {k: means(per, k) for k in keys}, "verdicts": verdicts,
           "passing": passing, "chosen": chosen, "vs_baselines": comparisons(per, ["opslens", "S1", "S2", "S3"]),
           "per_seed": {k: per[k] for k in keys}, "seconds": round(time.perf_counter() - started, 1),
           "note": "validation days only; pre-registered in eval/PREREG_1530.md"}
    (OUT / "design_1530.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print_table(out, keys)
    return 0


def confirm() -> int:
    started = time.perf_counter()
    design_out = json.loads((OUT / "design_1530.json").read_text(encoding="utf-8"))
    chosen = design_out["chosen"]
    if chosen is None:
        print("no candidate passed the design run; nothing to confirm")
        return 1
    w = design_out["s2_weight"]
    spec = s3_spec(w) if chosen == "S3" else CANDIDATES["S1"] if chosen == "S1" else CANDIDATES[f"S2 w={w}"]
    est = load_estimates()
    jobs = [{"key": k, "seed": s} for k in ("opslens", "baseline_d", "least_slack_rescue") for s in CONFIRM_SEEDS]
    jobs += [{"key": chosen, "seed": s, "spec": spec, "estimates": est} for s in CONFIRM_SEEDS]
    per = run_all(jobs)
    keys = ["opslens", "baseline_d", "least_slack_rescue", chosen]
    v = verdict(per, chosen)
    out = {"days": [FIRST, LAST], "seeds": CONFIRM_SEEDS, "chosen": chosen, "spec": spec, "verdict": v,
           "confirmed": v["passed"], "means": {k: means(per, k) for k in keys},
           "vs_baselines": comparisons(per, ["opslens", chosen]), "per_seed": {k: per[k] for k in keys},
           "seconds": round(time.perf_counter() - started, 1)}
    (OUT / "confirm_1530.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print_table({**out, "verdicts": {chosen: v}, "vs_baselines": out["vs_baselines"]}, keys)
    print("confirmed" if v["passed"] else "NOT confirmed")
    return 0


def ci_pair(per: dict, a: str, b: str) -> dict:
    return {kpi: paired_ci([r[kpi] for r in per[a]], [r[kpi] for r in per[b]])
            for kpi in ("turnaround.breach_pct", "segment.p1_breach_pct")}


def test_days() -> int:
    started = time.perf_counter()
    confirmed = json.loads((OUT / "confirm_1530.json").read_text(encoding="utf-8"))
    if not confirmed["confirmed"] or confirmed["chosen"] != "S2":
        print("S2 was not confirmed; this mode only runs the confirmed S2")
        return 1
    spec = confirmed["spec"]
    est = load_estimates()
    days = (TEST_FIRST, TEST_LAST)
    jobs = []
    for s in TEST_SEEDS:
        jobs += [{"key": "baseline_d", "seed": s, "days": days},
                 {"key": "least_slack_rescue", "seed": s, "days": days},
                 {"key": "opslens", "tag": "opslens", "seed": s, "days": days, "staffing": True},
                 {"key": "opslens", "tag": "opslens routing alone", "seed": s, "days": days},
                 {"key": "S2", "tag": "S2", "seed": s, "days": days, "staffing": True, "spec": spec, "estimates": est},
                 {"key": "S2", "tag": "S2 routing alone", "seed": s, "days": days, "spec": spec, "estimates": est}]
    per = run_all(jobs)
    keys = ["baseline_d", "least_slack_rescue", "opslens", "opslens routing alone", "S2", "S2 routing alone"]
    pairs = {f"{a} - {b}": ci_pair(per, a, b) for a in keys[2:] for b in ("baseline_d", "least_slack_rescue")}
    pairs["S2 - opslens"] = ci_pair(per, "S2", "opslens")
    s2_ind, s2_ls = pairs["S2 - baseline_d"], pairs["S2 - least_slack_rescue"]
    ops_ind = pairs["opslens - baseline_d"]
    step1 = {"beats_industry_overall": s2_ind["turnaround.breach_pct"]["ci_high"] < 0,
             "beats_industry_p1": s2_ind["segment.p1_breach_pct"]["ci_high"] < 0,
             "beats_least_slack_overall": s2_ls["turnaround.breach_pct"]["ci_high"] < 0,
             "least_slack_p1_not_worse": s2_ls["segment.p1_breach_pct"]["mean_diff"] <= 0}
    step2 = {"beats_industry_overall": ops_ind["turnaround.breach_pct"]["ci_high"] < 0,
             "beats_industry_p1": ops_ind["segment.p1_breach_pct"]["ci_high"] < 0}
    if all(step1.values()):
        decision = "ship S2 on the 15/30/60 floor"
    elif all(step2.values()):
        decision = "fallback: OpsLens today on the 15/30/60 floor"
    else:
        decision = "fallback: main's 1h/4h/24h floor"
    out = {"days": list(days), "seeds": TEST_SEEDS, "spec": spec, "estimates": est, "run_once": True,
           "means": {k: means(per, k) for k in keys}, "paired": pairs, "step1_ship_s2": step1,
           "step2_opslens_today": step2, "decision": decision, "per_seed": {k: per[k] for k in keys},
           "seconds": round(time.perf_counter() - started, 1),
           "note": "test days run once with code and weights frozen at the confirmation; PREREG_1530.md section 5"}
    (OUT / "test_1530.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for k in keys:
        m = out["means"][k]
        print(f"{k:24s} breach {m['turnaround.breach_pct']:6.2f}  P1 {m['segment.p1_breach_pct']:6.2f}  "
              f"P99 wait {m['quality.p99_wait_min']:6.1f}  late/100 {m['quality.late_minutes_per_100']:7.1f}  "
              f"Hindi {m['segment.hindi_breach_pct']:6.2f}")
    for k, d in pairs.items():
        b, p = d["turnaround.breach_pct"], d["segment.p1_breach_pct"]
        print(f"  {k:46s} breach {b['mean_diff']:+.2f} [{b['ci_low']:+.2f}, {b['ci_high']:+.2f}]  "
              f"P1 {p['mean_diff']:+.2f} [{p['ci_low']:+.2f}, {p['ci_high']:+.2f}]")
    print("step 1 (ship S2):", step1)
    print("step 2 (OpsLens today):", step2)
    print("decision:", decision)
    return 0


def print_table(out: dict, keys: list[str]) -> None:
    for k in keys:
        m = out["means"][k]
        print(f"{k:20s} breach {m['turnaround.breach_pct']:6.2f}  P1 {m['segment.p1_breach_pct']:6.2f}  "
              f"P99 wait {m['quality.p99_wait_min']:6.1f}  late/100 {m['quality.late_minutes_per_100']:7.1f}  "
              f"Hindi {m['segment.hindi_breach_pct']:6.2f}  reopen {m['quality.reopen_rate_pct']:5.2f}")
    for k, v in out["verdicts"].items():
        b, p = v["vs_opslens_breach"], v["vs_opslens_p1"]
        print(f"  {k} - OpsLens today: breach {b['mean_diff']:+.2f} [{b['ci_low']:+.2f}, {b['ci_high']:+.2f}]  "
              f"P1 {p['mean_diff']:+.2f} [{p['ci_low']:+.2f}, {p['ci_high']:+.2f}]  {v['checks']}  "
              f"{'PASS' if v['passed'] else 'fail'}")
    for k, d in out["vs_baselines"].items():
        b, p = d["turnaround.breach_pct"], d["segment.p1_breach_pct"]
        print(f"  {k:34s} breach {b['mean_diff']:+.2f} [{b['ci_low']:+.2f}, {b['ci_high']:+.2f}]  "
              f"P1 {p['mean_diff']:+.2f} [{p['ci_low']:+.2f}, {p['ci_high']:+.2f}]")
    if "chosen" in out:
        print("chosen:", out["chosen"])


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    raise SystemExit({"estimates": estimates, "design": design, "confirm": confirm, "test": test_days}.get(mode, lambda: 2)())
