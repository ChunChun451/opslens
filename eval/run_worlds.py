"""Plan v4 W1: does OpsLens win on 30 food-delivery worlds we did not design?

Run:  .venv/Scripts/python.exe eval/run_worlds.py                  (all 30 worlds, seeds 7001-7030)
      .venv/Scripts/python.exe eval/run_worlds.py --only 7001 7002  (a pilot)
      .venv/Scripts/python.exe eval/run_worlds.py --summary          (only re-read finished worlds)

Why: the headline (2.05% vs 5.51% missed SLAs) comes from ONE world we built, with problems we
planted, a simulator we wrote and a policy tuned in it. A judge can fairly say "of course it wins
there". So we draw 30 worlds at random from wide ranges fixed in docs/PLAN_V4.md BEFORE any run,
retrain the product the routine way on each, and compare every policy on each world's test days.
Nothing is tuned per world: config/optimizer.yaml (OpsLens's weights) is copied unchanged.

Each world, in its own copy of the repo (the main data/generated/ is never touched):
1. sample its parameters from the world seed (sample_world): volume, peak heights, category mix,
   Hindi share, handle times, skill-mismatch slowdown, absences, team sizes, SLA targets, chats per
   agent, and the size/day of each planted problem;
2. write them into the copy's config files (apply_world);
3. routine pipeline: data/generate_ops.py → eval/run_classification.py --no-llm (local classifier:
   30 worlds would exhaust the free LLM quota; the LLM moves accuracy by ~0.1 point) →
   eval/run_risk.py → eval/run_forecast.py (forecast + staffing plan);
4. eval/run_world_compare.py: A, B, C, D, least slack and OpsLens, seeds 1-3, test days 43-56;
5. keep the result in eval/parts/worlds/<seed>.json (so a crash loses one world, not thirty).

Rule (pre-registered): "robust" only if OpsLens has the lowest missed-SLA rate (or is within 0.05
points of the lowest) in at least 27 of 30 worlds, AND the median over worlds of (OpsLens − industry
standard) has a 95% bootstrap CI below 0. Every world is reported, with the worst three.

Example: world 7001 draws load x1.22, Hindi share 17%, skill mismatch x1.81, P1 SLA 60 min, 3 chats
per agent at slowdown .5 and 45 agents; load_factor turns that into the ticket volume that makes the
floor exactly 1.22 times as busy as today.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "eval" / "parts" / "worlds"
DIAG_DIR = ROOT / "eval" / "parts" / "worlds_diag"  # the overload diagnosis (23 Oct); never counted
WORLD_SEEDS = list(range(7001, 7031))
SKIP = {".git", ".venv", ".venv-challengers", ".claude", "data/generated",
        "cache", ".pytest_tmp", ".pytest_cache", "__pycache__", "eval/parts/worlds", "eval/parts/worlds_diag",
        "eval/challengers"}
CATEGORIES = ["late_delivery", "missing_item", "wrong_item", "refund", "payment_failure", "app_bug",
              "account", "restaurant_partner"]
OTHERS = ["baseline_a", "baseline_b", "baseline_c", "baseline_d", "least_slack"]
TIE_POINTS = 0.05


# ---- 1. Sampling a world ----------------------------------------------------------------------

def sample_world(seed: int) -> dict:
    """The world's parameters, drawn from the ranges in docs/PLAN_V4.md (W1). Same seed, same world."""
    rng = np.random.default_rng(seed)
    # Restaurant clusters are numbered 0-39; the partner draw is 1-40, so 40 maps to 0 (fix 19 Oct,
    # found when world 7005 crashed; every draw stays the same, so finished worlds are unchanged).
    k = int(rng.integers(1, 4))  # chats per agent: 1, 2 or 3
    s = float(rng.choice([0.25, 0.5])) if k > 1 else 0.0
    return {
        "seed": seed,
        "load": float(rng.uniform(0.7, 1.4)),          # volume x0.7-1.4 of today's load
        "peak_scale": float(rng.uniform(0.7, 1.3)),    # lunch/dinner peaks ±30%
        "category_scale": {c: float(rng.uniform(0.6, 1.4)) for c in CATEGORIES},  # mix ±40%
        "hindi_share": float(rng.uniform(0.05, 0.25)),
        "handle_scale": float(rng.uniform(0.7, 1.3)),
        "mismatch_factor": float(rng.uniform(1.2, 2.0)),
        "absent_prob": float(rng.uniform(0.02, 0.10)),
        "team_delta": {t: int(rng.integers(-2, 3)) for t in "ABCD"},  # ±2 agents per team
        "sla_minutes": {"P1": int(rng.uniform(30, 90)), "P2": int(rng.uniform(120, 360)),
                        "P3": int(rng.uniform(720, 2160))},
        "chats_per_agent": k, "chat_slowdown": s,
        "plants": {"payment_spike_day": int(rng.integers(12, 31)), "payment_spike_mult": float(rng.uniform(3, 5)),
                   "app_bug_day": int(rng.integers(44, 56)), "app_bug_mult": float(rng.uniform(3, 6)),
                   "partner_cluster": int(rng.integers(1, 41)) % 40, "partner_mult": float(rng.uniform(2, 4)),
                   "ivr_wrong_prob": float(rng.uniform(0.15, 0.35)), "team_c_lift": float(rng.uniform(1.2, 1.5))},
        "roster_seed": int(rng.integers(0, 2**31 - 1)),
    }


def load_factor(world: dict, gen: dict, n_agents_before: int, n_agents_after: int) -> float:
    """Ticket volume multiplier that makes the floor exactly `world["load"]` times as busy as today
    (the W1 amendment: "x0.7-1.4 of today's LOAD"). Load = work / capacity, so the volume is
    - raised by k / (1 + s(k-1)) when agents hold k chats (each agent does that much more work),
    - raised by agents_after / agents_before when teams grow (more people),
    - lowered by the handle-time scale and by the category mix's effect on the average handle time
      (longer tickets = more work per ticket).
    Example: load 1.10, 2 chats at s = .25 (x1.6), 42 agents instead of 40 (x1.05), handle x1.2 and
    a mix whose average handle time is 3% longer → 1.10 x 1.6 x 1.05 / (1.2 x 1.03) = 1.50."""
    k, s = world["chats_per_agent"], world["chat_slowdown"]
    medians = gen["handle_median_min"]
    old_mix = sum(gen["categories"][c] * medians[c] for c in CATEGORIES)
    shares = {c: gen["categories"][c] * world["category_scale"][c] for c in CATEGORIES}
    new_mix = sum(shares[c] / sum(shares.values()) * medians[c] for c in CATEGORIES)
    capacity = k / (1.0 + s * (k - 1)) * n_agents_after / n_agents_before
    work_per_ticket = world["handle_scale"] * new_mix / old_mix
    return world["load"] * capacity / work_per_ticket


# ---- 2. Writing it into a copy of the repo ----------------------------------------------------

def apply_world(dest: Path, world: dict) -> float:
    """Edit the copy's generator, roster and SLA configs (comments are lost; it is a throwaway copy).
    Returns the ticket volume multiplier used."""
    gen_path, roster_path, sla_path = (dest / "config" / n for n in ("generator.yaml", "roster.yaml", "sla.yaml"))
    gen = yaml.safe_load(gen_path.read_text(encoding="utf-8"))
    roster = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
    resized = resize_teams(roster["agents"], world["team_delta"], world["roster_seed"])
    volume = load_factor(world, gen, len(roster["agents"]), len(resized))  # before gen is edited below
    gen["seed"] = world["seed"]
    gen["tickets_per_weekday"] = int(round(gen["tickets_per_weekday"] * volume))
    profile = np.asarray(gen["hourly_profile"], dtype=float)
    gen["hourly_profile"] = [float(max(0.1, profile.mean() + (v - profile.mean()) * world["peak_scale"])) for v in profile]
    shares = {c: gen["categories"][c] * world["category_scale"][c] for c in CATEGORIES}
    gen["categories"] = {c: v / sum(shares.values()) for c, v in shares.items()}
    other = gen["languages"]["other"]
    gen["languages"] = {"en": 1.0 - other - world["hindi_share"], "hi": world["hindi_share"], "other": other}
    gen["handle_median_min"] = {c: float(v) * world["handle_scale"] for c, v in gen["handle_median_min"].items()}
    gen["skill_mismatch_factor"] = world["mismatch_factor"]
    gen["absent_prob"] = world["absent_prob"]
    gen["concurrency_slowdown"] = world["chat_slowdown"]
    p, planted = world["plants"], gen["planted"]
    planted["payment_spike"].update(day=p["payment_spike_day"], multiplier=p["payment_spike_mult"])
    planted["app_bug_surge"].update(day=p["app_bug_day"], multiplier=p["app_bug_mult"])
    planted["partner_cluster"].update(cluster_id=p["partner_cluster"], multiplier=p["partner_mult"])
    planted["ivr_misrouting"]["wrong_selection_prob"] = p["ivr_wrong_prob"]
    planted["team_c_weekend_dinner"]["weekend_lift"] = {"missing_item": p["team_c_lift"], "wrong_item": p["team_c_lift"]}
    gen_path.write_text(yaml.safe_dump(gen, sort_keys=False), encoding="utf-8")

    roster["max_concurrent"] = world["chats_per_agent"]
    roster["agents"] = resized
    roster_path.write_text(yaml.safe_dump(roster, sort_keys=False), encoding="utf-8")

    sla = yaml.safe_load(sla_path.read_text(encoding="utf-8"))
    sla["sla_minutes"] = world["sla_minutes"]
    sla_path.write_text(yaml.safe_dump(sla, sort_keys=False), encoding="utf-8")
    return volume


def resize_teams(agents: list[dict], delta: dict[str, int], seed: int) -> list[dict]:
    """Drop random agents from a team, or add copies of random team members (same shift and skills,
    a new id): the floor changes size without anyone designing who goes where."""
    rng = np.random.default_rng(seed)
    out: list[dict] = []
    for team in "ABCD":
        members = [a for a in agents if a["team"] == team]
        d = delta[team]
        if d < 0:
            drop = set(rng.choice(len(members), size=min(-d, len(members) - 2), replace=False).tolist())
            members = [a for i, a in enumerate(members) if i not in drop]
        for j in range(max(0, d)):
            copy = dict(members[int(rng.integers(0, len(members)))])
            copy["id"], copy["name"] = f"{team}{90 + j}", f"Extra {team}{90 + j}"
            members.append(copy)
        out.extend(members)
    return out


# ---- 3-5. Running one world ----------------------------------------------------------------------

def copy_repo(dest: Path) -> None:
    def ignore(folder: str, names: list[str]) -> list[str]:
        rel = Path(folder).relative_to(ROOT).as_posix()
        return [n for n in names if n in SKIP or f"{rel}/{n}".lstrip("./") in SKIP]
    shutil.copytree(ROOT, dest, ignore=ignore)


def run_step(dest: Path, log, *args: str) -> None:
    started = time.perf_counter()
    subprocess.run([sys.executable, "-u", *args], cwd=dest, check=True, stdout=log, stderr=subprocess.STDOUT)
    log.write(f"\n== {' '.join(args)} done in {time.perf_counter() - started:.0f}s\n".encode())


def run_world(seed: int, workers: int, diagnose: bool = False) -> dict:
    """The whole pipeline for one world; returns (and saves) its result. With diagnose=True (added
    23 Oct, after the result): the same world rebuilt, only industry standard, least slack and
    OpsLens, with misses by priority / tier / language recorded, saved apart in worlds_diag/."""
    out_path = (DIAG_DIR if diagnose else OUT_DIR) / f"{seed}.json"
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    world = sample_world(seed)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"opslens_world_{seed}_") as tmp:
        dest = Path(tmp) / "repo"
        copy_repo(dest)
        volume = apply_world(dest, world)
        with open((DIAG_DIR if diagnose else OUT_DIR) / f"{seed}.log", "wb") as log:
            run_step(dest, log, "data/generate_ops.py")
            run_step(dest, log, "eval/run_classification.py", "--no-llm")
            run_step(dest, log, "eval/run_risk.py")
            run_step(dest, log, "eval/run_forecast.py")
            run_step(dest, log, "eval/run_world_compare.py", "--workers", str(workers),
                     *(["--diagnose"] if diagnose else []))
        parts = dest / "eval" / "parts"
        compare = json.loads((parts / "world_compare.json").read_text(encoding="utf-8"))
        risk = json.loads((parts / "risk.json").read_text(encoding="utf-8"))
    result = {"seed": seed, "params": world, "volume_factor": volume, "compare": compare,
              "risk_auc": (risk.get("test") or {}).get("auc"), "minutes": round((time.perf_counter() - started) / 60, 1)}
    out_path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    breach = {p: v["turnaround.breach_pct"] for p, v in compare["mean"].items()}
    print(f"world {seed}: " + "  ".join(f"{p} {b:.2f}%" for p, b in breach.items()) + f"  ({result['minutes']} min)", flush=True)
    return result


def run_world_safe(seed: int, workers: int) -> dict | None:
    """run_world, but one broken world is logged instead of stopping the other 29. A failed world
    is never dropped from the rule: the rule needs all 30, so a failure must be fixed and re-run."""
    try:
        return run_world(seed, workers)
    except Exception as exc:  # noqa: BLE001 — recorded in the world's log and on screen
        print(f"world {seed} FAILED: {exc!r} (see eval/parts/worlds/{seed}.log)", flush=True)
        return None


# ---- Summary and the pre-registered rule ---------------------------------------------------------

def summarize(results: list[dict]) -> dict:
    rows = []
    for r in sorted(results, key=lambda r: r["seed"]):
        mean = {p: v["turnaround.breach_pct"] for p, v in r["compare"]["mean"].items()}
        best_other = min(OTHERS, key=lambda p: mean[p])
        rows.append({"seed": r["seed"], "breach_pct": mean, "best_other": best_other,
                     "opslens_minus_best_other": mean["opslens"] - mean[best_other],
                     "opslens_minus_d": mean["opslens"] - mean["baseline_d"],
                     "wins": mean["opslens"] <= mean[best_other] + TIE_POINTS,
                     "late_minutes_per_100": {p: v["quality.late_minutes_per_100"] for p, v in r["compare"]["mean"].items()},
                     "baseline_a_utilisation": r["compare"]["mean"]["baseline_a"]["quality.mean_utilisation"],
                     "risk_auc": r["risk_auc"], "params": r["params"], "volume_factor": r["volume_factor"]})
    diffs = np.array([row["opslens_minus_d"] for row in rows])
    rng = np.random.default_rng(0)
    boot = np.median(rng.choice(diffs, size=(10000, len(diffs)), replace=True), axis=1) if len(diffs) else np.array([np.nan])
    wins = sum(row["wins"] for row in rows)
    need = int(np.ceil(0.9 * len(rows)))
    median_ci = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]
    return {"n_worlds": len(rows), "wins": wins, "wins_needed": need, "tie_points": TIE_POINTS,
            "median_opslens_minus_d": float(np.median(diffs)) if len(diffs) else None, "median_ci": median_ci,
            "rule_passed": bool(len(rows) == len(WORLD_SEEDS) and wins >= need and median_ci[1] < 0),
            "worst": sorted(rows, key=lambda row: -row["opslens_minus_best_other"])[:3], "worlds": rows,
            "classifier": "local only (no LLM) in every world", "seeds": [1, 2, 3], "test_days": [43, 56]}


def diagnose_losses() -> int:
    """Rebuild the worlds where OpsLens was not lowest and record who misses the deadline. Checks
    first that the rebuilt runs reproduce the counted ones exactly (same seeds, same worlds)."""
    DIAG_DIR.mkdir(parents=True, exist_ok=True)
    summary = json.loads((ROOT / "eval" / "parts" / "worlds.json").read_text(encoding="utf-8"))
    seeds = [row["seed"] for row in summary["worlds"] if not row["wins"]]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda s: run_world(s, workers=4, diagnose=True), seeds))
    rows = []
    for seed in seeds:
        counted = json.loads((OUT_DIR / f"{seed}.json").read_text(encoding="utf-8"))["compare"]["per_seed"]
        diag = json.loads((DIAG_DIR / f"{seed}.json").read_text(encoding="utf-8"))["compare"]
        same = all([r["turnaround.breach_pct"] for r in counted[p]] == [r["turnaround.breach_pct"] for r in diag["per_seed"][p]]
                   for p in diag["per_seed"])
        rows.append({"seed": seed, "reproduced": same, "mean": diag["mean"]})
    out = {"note": "Added 23 Oct after the 30-world result: the worlds OpsLens did not win, rebuilt from the same "
                   "seeds, with misses by priority, tier and language. Analysis, not a pre-registered test.",
           "worlds": rows, "all_reproduced": all(r["reproduced"] for r in rows)}
    (ROOT / "eval" / "parts" / "worlds_diagnosis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"diagnosis: {len(rows)} worlds, reproduced exactly: {out['all_reproduced']}")
    return 0


def main() -> int:
    if "--diagnose" in sys.argv:
        return diagnose_losses()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seeds = WORLD_SEEDS
    if "--only" in sys.argv:
        seeds = [int(x) for x in sys.argv[sys.argv.index("--only") + 1:] if x.isdigit()]
    if "--summary" not in sys.argv:
        parallel = 3 if len(seeds) > 1 else 1
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            list(pool.map(lambda s: run_world_safe(s, workers=4), seeds))
    # Only the 30 pre-registered worlds count: the code-check world 7000 is never part of the result.
    done = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(OUT_DIR.glob("*.json"))
            if p.stem.isdigit() and int(p.stem) in WORLD_SEEDS]
    summary = summarize(done)
    (ROOT / "eval" / "parts" / "worlds.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    if not summary["n_worlds"]:
        print("no counted world finished yet (world 7000 is a code check and never counts)")
        return 0
    print(f"{summary['n_worlds']} worlds: OpsLens lowest (within {TIE_POINTS} pts) in {summary['wins']}; "
          f"median OpsLens - D {summary['median_opslens_minus_d']:+.2f} pts, CI {summary['median_ci']}; "
          f"rule {'PASSED' if summary['rule_passed'] else 'not passed (or not all worlds done)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
