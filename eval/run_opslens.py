"""M7: choose OpsLens weights on validation days, then compare OpsLens with both baselines on
the held-out test days.

Run:  .venv/Scripts/python.exe eval/run_opslens.py --tune     (validation days 36-42, seeds 1-3)
      .venv/Scripts/python.exe eval/run_opslens.py            (test days 43-56, seeds 1-5)

Tuning (decision-focused: weights are judged by the breaches they cause, not by a model score):
one weight at a time, try a few values, keep the best mean breach % over 3 seeds, provided the
slowest customers (P99 wait) are not worse than under Baseline B. Writes eval/parts/tuning.json;
the chosen values are then copied into config/optimizer.yaml by hand (so the choice is visible).

Comparison: every policy sees the same tickets and the same luck per seed (common random
numbers); day 42 is a warm-up day. OpsLens uses the weekly staffing plans made on days 42 and
49 (M6) — same people, same hours. Writes eval/parts/sim.json with KPIs per seed, paired
95% CIs, the Saturday-evening replay series, and example assignments with reasons.
Seeds run in parallel processes.
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

from opslens import risk  # noqa: E402
from opslens.config import load_config  # noqa: E402
from opslens.impact import mean_std, paired_ci, summarize  # noqa: E402
from opslens.playbooks import apply_scenario  # noqa: E402
from opslens.policies import OpsLensPolicy, OpsLensSettings, baseline_a, baseline_b, baseline_c, baseline_d  # noqa: E402
from opslens.policies import (ClairvoyantSlackPolicy, GeneralizedCMuPolicy, LeastSlackPolicy,  # noqa: E402
                              LeastSlackRescuePolicy, expected_handle_minutes)
from opslens.simulate import MINUTES_PER_DAY, simulate  # noqa: E402
from opslens.world import apply_staffing_plan, build_world, day_bounds, load_agents  # noqa: E402

GENERATED = ROOT / "data" / "generated"
PARTS = ROOT / "eval" / "parts"
TUNE_GRID = {
    "aging_per_hour": [0.25, 0.5, 1.0, 2.0],
    "cross_skill_min_rescue": [0.5, 0.7, 99.0],  # 99 = never cross-skill
    "mismatch_penalty": [1.0, 2.0, 3.0],
    "scarcity_weight": [0.0, 0.3, 1.0],
    "rescue_floor": [0.05, 0.2],
}
REPLAY_DAY, REPLAY_FROM_H, REPLAY_TO_H = 48, 18, 24  # Saturday 17 Oct, 18:00-24:00
KPIS = [
    "turnaround.breach_pct", "turnaround.mean_resolution_min", "turnaround.p90_resolution_min",
    "turnaround.mean_wait_min", "turnaround.max_backlog", "productivity.tickets_per_agent_hour",
    "productivity.transfers_per_100", "productivity.busy_agent_hours", "quality.reopen_rate_pct",
    "quality.p99_wait_min", "quality.mean_utilisation", "quality.load_fairness_std",
    "segment.p1_breach_pct", "segment.gold_breach_pct", "segment.hindi_breach_pct",
]


def run_one(job: dict) -> dict:
    """One simulation (runs in a worker process). Returns KPIs and small extras."""
    tickets = pd.read_csv(GENERATED / "world_tickets.csv")
    preds = pd.read_csv(GENERATED / "predictions.csv", usecols=["ticket_id", "pred_final"])
    if job.get("volume_boost"):
        tickets, preds = boost_volume(tickets, preds, job["volume_boost"], job["first_day"] - 1, job["last_day"])
    agents = load_agents()
    if job.get("staffing"):
        agents = apply_staffing_plan(agents, json.loads((GENERATED / "staffing_plan.json").read_text(encoding="utf-8")))
    weekday = pd.Timestamp(load_config("calendar")["start_date"]).weekday()
    for spec in job.get("scenarios", []):  # fix-at-source playbooks (eval/run_playbooks.py)
        tickets, preds, agents, _ = apply_scenario(tickets, preds, agents, spec, job["first_day"], job["last_day"],
                                                   weekday, alerts=job.get("alerts"))
    gen_cfg = load_config("generator")
    if job.get("absent_prob") is not None:
        gen_cfg = {**gen_cfg, "absent_prob": job["absent_prob"]}
    if job.get("max_concurrent"):  # Plan v4 W2: every agent may hold several chats at once
        agents = [dataclasses.replace(a, max_concurrent=int(job["max_concurrent"])) for a in agents]
    world = build_world(tickets, seed=job["seed"], agents=agents, gen_cfg=gen_cfg)
    if "concurrency_slowdown" in job:  # else the world's own setting (generator.yaml, default 0)
        world.concurrency_slowdown = float(job["concurrency_slowdown"])
    warm, _ = day_bounds(job["first_day"] - 1, job["first_day"] - 1)
    start, end = day_bounds(job["first_day"], job["last_day"])
    if job["policy"] == "baseline_a":
        policy = baseline_a()
    elif job["policy"] == "baseline_b":
        policy = baseline_b()
    elif job["policy"] == "baseline_c":
        policy = baseline_c()
    elif job["policy"] == "baseline_d":
        policy = baseline_d(world, dict(zip(preds.ticket_id, preds.pred_final)))
    elif job["policy"] in PUBLISHED_RULES:  # eval/run_best_baselines.py
        policy = published_rule(job, world, dict(zip(preds.ticket_id, preds.pred_final)))
    else:
        weights = {**load_config("optimizer"), **job.get("weights", {})}
        log_window = None
        if job.get("log"):
            day0 = (REPLAY_DAY - 1) * MINUTES_PER_DAY
            log_window = (day0 + 20 * 60 + 30, day0 + 20 * 60 + 45)
        handle = None
        if weights.get("overload"):  # v6 candidate: expected minutes of work, history days 1-35 only
            history = pd.read_csv(GENERATED / "history.csv", usecols=["created_at", "final_category", "channel",
                                                                     "handled_min", "reopens", "resolution_min"])
            handle = expected_handle_minutes(history, load_config("calendar")["start_date"], last_day=35)
        policy = OpsLensPolicy(world, dict(zip(preds.ticket_id, preds.pred_final)), risk.load(GENERATED / "models"),
                               weights, OpsLensSettings(**job.get("settings", {})), log_window=log_window,
                               handle=handle)
    started = time.perf_counter()
    day0 = (REPLAY_DAY - 1) * MINUTES_PER_DAY
    floor_window = (day0 + REPLAY_FROM_H * 60, day0 + REPLAY_TO_H * 60) if job.get("log") else None
    result = simulate(world, policy, warm, end, metric_start_min=start, seed_label=str(job["seed"]),
                      floor_window=floor_window)
    out = {"job": job, "kpis": summarize(result), "seconds": time.perf_counter() - started}
    if job.get("log"):
        out["replay"] = replay_series(result, world)
        out["floor"] = floor_frames(result.floor, world, day0=(REPLAY_DAY - 1) * MINUTES_PER_DAY)
        out["decisions"] = [{**d, "ticket_id": world.ticket_ids[d["ticket_idx"]]} for d in getattr(policy, "decision_log", [])]
    if hasattr(policy, "stats"):
        ms = policy.stats.solve_ms or [0.0]
        out["solver"] = {"solves": policy.stats.solves, "fallbacks": policy.stats.fallbacks,
                         "median_ms": float(np.median(ms)), "max_ms": float(np.max(ms))}
    if job.get("daily"):  # performance tracking (eval/run_tracking.py): the same run, day by day
        out["daily"] = daily_breakdown(result.tickets)
    if hasattr(policy, "overload_minutes") and policy.handle:  # OpsLens v6 candidates only
        out["overload_minutes"] = policy.overload_minutes
    return out


def daily_breakdown(tickets: pd.DataFrame) -> list[dict]:
    """One row per day (the day a ticket was created) and per team (the team its true category belongs
    to): tickets, missed SLAs, minutes past SLA and the mean wait. Sums, so seeds and days add up exactly."""
    from opslens.classify import TEAM_OF
    t = tickets.assign(day=(tickets["created_min"] // MINUTES_PER_DAY).astype(int) + 1,
                       team=tickets["category"].map(TEAM_OF).fillna("?"),
                       late=(tickets["resolution_min"] - tickets["sla_min"]).clip(lower=0).fillna(0.0))
    rows = []
    for (day, team), g in t.groupby(["day", "team"]):
        rows.append({"day": int(day), "team": str(team), "tickets": int(len(g)), "missed": int(g["breached"].sum()),
                     "late_minutes": float(g.loc[g["breached"], "late"].sum()), "wait_sum": float(g["wait_min"].fillna(0).sum())})
    return rows


PUBLISHED_RULES = {"least_slack", "least_slack_rescue", "gen_cmu", "clairvoyant"}


def published_rule(job: dict, world, predicted: dict[str, str]):
    """The rules from the scheduling literature (opslens/policies.py, added 18 Oct). Expected
    handle times come from this world's history, days 1-35 only."""
    history = pd.read_csv(GENERATED / "history.csv",
                          usecols=["created_at", "final_category", "channel", "handled_min", "reopens", "resolution_min"])
    handle = expected_handle_minutes(history, load_config("calendar")["start_date"], last_day=35)
    if job["policy"] == "least_slack":
        return LeastSlackPolicy(world, predicted, handle)
    if job["policy"] == "least_slack_rescue":  # the same freedom as OpsLens: cross-skill rescues
        return LeastSlackRescuePolicy(world, predicted, handle, threshold_min=job["params"]["threshold_min"])
    if job["policy"] == "gen_cmu":
        params = job["params"]
        return GeneralizedCMuPolicy(world, predicted, handle, tau=params["tau"], beta=params["beta"])
    return ClairvoyantSlackPolicy(world)


def boost_volume(tickets: pd.DataFrame, preds: pd.DataFrame, share: float, first_day: int,
                 last_day: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stress test: copy `share` of the tickets in the window as extra tickets, 0-30 min later.
    New ticket numbers (900000+) get their own luck; copies keep the original's text and
    predicted category, so every policy faces the same extra work."""
    rng = np.random.default_rng(99)
    lo, hi = (first_day - 1) * MINUTES_PER_DAY, last_day * MINUTES_PER_DAY
    window = tickets[(tickets["created_min"] >= lo) & (tickets["created_min"] < hi)]
    extra = window.sample(frac=share, random_state=99).copy()
    extra["created_min"] = np.minimum(extra["created_min"] + rng.uniform(0, 30, len(extra)), hi - 1)
    new_ids = [f"T{900000 + k}" for k in range(len(extra))]
    pred_of = dict(zip(preds["ticket_id"], preds["pred_final"]))
    extra_preds = pd.DataFrame({"ticket_id": new_ids, "pred_final": [pred_of.get(t) for t in extra["ticket_id"]]})
    extra["ticket_id"] = new_ids
    return pd.concat([tickets, extra], ignore_index=True), pd.concat([preds, extra_preds], ignore_index=True)


def replay_series(result, world) -> dict:
    """Waiting tickets and cumulative breaches every 15 minutes on the replay evening."""
    day0 = (REPLAY_DAY - 1) * MINUTES_PER_DAY
    times = np.arange(day0 + REPLAY_FROM_H * 60, day0 + REPLAY_TO_H * 60 + 1, 15.0)
    snaps = result.snapshots.set_index("minute")["waiting"]
    t = result.tickets
    deadline = t["created_min"] + t["idx"].map(lambda i: world.sla_min[i])
    breach_at = deadline[t["breached"]].to_numpy()  # a breach "happens" when the deadline passes
    since = day0 + REPLAY_FROM_H * 60
    return {
        "times": [f"{int((m - day0) // 60) % 24:02d}:{int(m % 60):02d}" for m in times],
        "waiting": [int(snaps.get(m, 0)) for m in times],
        "breached_cum": [int(((breach_at >= since) & (breach_at <= m)).sum()) for m in times],
    }


def floor_frames(frames: list[dict], world, day0: float) -> dict:
    """Floor map for the replay, compact for the dashboard: agents once, then per 5-min frame a
    status letter per agent (o off, i idle, b busy, x cross-skill, w wrong queue) and each
    team's queue as [can still make SLA, already late]."""
    letter = {"off": "o", "idle": "i", "busy": "b", "cross": "x", "wrong": "w"}
    agents = [{"id": a.agent_id, "team": a.team, "languages": sorted(a.languages)} for a in world.agents]
    return {
        "agents": agents,
        "times": [f"{int((f['minute'] - day0) // 60) % 24:02d}:{int(f['minute'] % 60):02d}" for f in frames],
        "status": ["".join(letter[f["agents"][a["id"]]] for a in agents) for f in frames],
        "queues": [f["queues"] for f in frames],
    }


def run_jobs(jobs: list[dict], workers: int = 6) -> list[dict]:
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run_one, jobs))


def tune() -> int:
    first, last, seeds = 36, 42, [1, 2, 3]
    base = run_jobs([{"policy": "baseline_b", "seed": s, "first_day": first, "last_day": last} for s in seeds])
    b_p99 = np.mean([r["kpis"]["quality.p99_wait_min"] for r in base])
    b_breach = np.mean([r["kpis"]["turnaround.breach_pct"] for r in base])
    print(f"validation Baseline B: breach {b_breach:.2f}%, P99 wait {b_p99:.0f} min")
    chosen: dict = {}
    history = []
    for name, values in TUNE_GRID.items():
        jobs = [{"policy": "opslens", "seed": s, "first_day": first, "last_day": last,
                 "weights": {**chosen, name: v}} for v in values for s in seeds]
        results = run_jobs(jobs)
        scores = []
        for v in values:
            rs = [r for r in results if r["job"]["weights"][name] == v]
            breach = np.mean([r["kpis"]["turnaround.breach_pct"] for r in rs])
            p99 = np.mean([r["kpis"]["quality.p99_wait_min"] for r in rs])
            scores.append((breach, p99, v))
            history.append({"weight": name, "value": v, "breach_pct": breach, "p99_wait_min": p99})
            print(f"  {name}={v}: breach {breach:.2f}%, P99 wait {p99:.0f} min")
        allowed = [s for s in scores if s[1] <= b_p99] or scores
        best = min(allowed, key=lambda s: (s[0], s[1]))
        chosen[name] = best[2]
        print(f"-> {name} = {best[2]}")
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "tuning.json").write_text(json.dumps({"validation_days": [first, last], "seeds": seeds,
                                                   "baseline_b": {"breach_pct": b_breach, "p99_wait_min": b_p99},
                                                   "chosen": chosen, "history": history}, indent=1), encoding="utf-8")
    print("chosen weights:", chosen)
    return 0


def compare(seeds: list[int]) -> int:
    first, last = 43, 56
    jobs = []
    for s in seeds:
        jobs.append({"policy": "baseline_a", "seed": s, "first_day": first, "last_day": last, "log": s == seeds[0]})
        jobs.append({"policy": "baseline_b", "seed": s, "first_day": first, "last_day": last, "log": s == seeds[0]})
        # Industry standard (added 17 Oct, Claude 2): skills-based routing with AI triage.
        jobs.append({"policy": "baseline_d", "seed": s, "first_day": first, "last_day": last, "log": s == seeds[0]})
        jobs.append({"policy": "opslens", "seed": s, "first_day": first, "last_day": last, "staffing": True,
                     "log": s == seeds[0]})
    started = time.perf_counter()
    results = run_jobs(jobs, workers=min(len(jobs), 8))
    by_policy: dict[str, list[dict]] = {}
    for r in results:
        by_policy.setdefault(r["job"]["policy"], []).append(r)
    labels = {"baseline_a": "Baseline A (FIFO)", "baseline_b": "Baseline B (priority)",
              "baseline_d": "Industry standard (skills routing)", "opslens": "OpsLens"}
    print(f"test days {first}-{last}, seeds {seeds}, {len(jobs)} runs in {time.perf_counter() - started:.0f}s")
    print(f"{'KPI':36s}" + "".join(f"{labels[p]:>24s}" for p in labels))
    policies = {}
    for key in labels:
        rs = sorted(by_policy[key], key=lambda r: r["job"]["seed"])
        kpis = {k: dict(zip(("mean", "std"), mean_std([r["kpis"][k] for r in rs]))) for k in KPIS}
        policies[key] = {"key": key, "label": labels[key], "kpis": kpis, "per_seed": [r["kpis"] for r in rs]}
    for k in KPIS:
        print(f"{k:36s}" + "".join(f"{policies[p]['kpis'][k]['mean']:16.2f} ±{policies[p]['kpis'][k]['std']:5.2f}" for p in labels))
    comparisons = []
    for base in ("baseline_a", "baseline_b", "baseline_d"):
        for k in KPIS:
            ci = paired_ci([r[k] for r in policies["opslens"]["per_seed"]], [r[k] for r in policies[base]["per_seed"]])
            comparisons.append({"policy": "opslens", "baseline": base, "kpi": k, **ci})
            if k in ("turnaround.breach_pct", "turnaround.p90_resolution_min", "quality.p99_wait_min",
                     "productivity.transfers_per_100"):
                print(f"OpsLens - {labels[base]:22s} {k:34s} {ci['mean_diff']:+8.2f} [{ci['ci_low']:+.2f}, {ci['ci_high']:+.2f}]")
    logged = {r["job"]["policy"]: r for r in results if r["job"].get("log")}
    solver = [r["solver"] for r in by_policy["opslens"]]
    print("solver: median %.2f ms, max %.1f ms, fallbacks %d" % (
        np.median([s["median_ms"] for s in solver]), max(s["max_ms"] for s in solver), sum(s["fallbacks"] for s in solver)))
    replay = {"title": "Saturday 17 Oct, 18:00-24:00", "day": REPLAY_DAY, "step_min": 15.0,
              "times": logged["opslens"]["replay"]["times"],
              "series": {k: {"waiting": logged[k]["replay"]["waiting"], "breached_cum": logged[k]["replay"]["breached_cum"]}
                         for k in labels},
              # Floor map (5-min frames): same seed-1 runs as the series above, so they agree.
              "floor": {k: logged[k]["floor"] for k in labels}}
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "sim.json").write_text(json.dumps({
        "seeds": seeds, "test_days": [first, last], "policies": policies, "comparisons": comparisons,
        "replay": replay, "decisions": logged["opslens"]["decisions"][:40], "solver": solver,
        "weights": load_config("optimizer"),
    }, indent=1), encoding="utf-8")
    print("wrote eval/parts/sim.json")
    return 0


if __name__ == "__main__":
    if "--tune" in sys.argv:
        raise SystemExit(tune())
    raise SystemExit(compare([1, 2, 3, 4, 5]))
