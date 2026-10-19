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

Example: world 7001 might draw volume x1.12, Hindi share 9%, skill mismatch x1.85, P1 SLA 47 min,
2 chats per agent at slowdown .25 (so volume is also x1.6 to keep the load: see load_factor).
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
WORLD_SEEDS = list(range(7001, 7031))
SKIP = {".git", ".venv", ".venv-challengers", ".claude", "data/generated", "data/public/uci_incidents",
        "cache", ".pytest_tmp", ".pytest_cache", "__pycache__", "eval/parts/worlds", "eval/challengers"}
CATEGORIES = ["late_delivery", "missing_item", "wrong_item", "refund", "payment_failure", "app_bug",
              "account", "restaurant_partner"]
OTHERS = ["baseline_a", "baseline_b", "baseline_c", "baseline_d", "least_slack"]
TIE_POINTS = 0.05


# ---- 1. Sampling a world ----------------------------------------------------------------------

def sample_world(seed: int) -> dict:
    """The world's parameters, drawn from the ranges in docs/PLAN_V4.md (W1). Same seed, same world."""
    rng = np.random.default_rng(seed)
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
                   "partner_cluster": int(rng.integers(1, 41)), "partner_mult": float(rng.uniform(2, 4)),
                   "ivr_wrong_prob": float(rng.uniform(0.15, 0.35)), "team_c_lift": float(rng.uniform(1.2, 1.5))},
        "roster_seed": int(rng.integers(0, 2**31 - 1)),
    }


def load_factor(world: dict) -> float:
    """Ticket volume multiplier. With k chats per agent each agent does k / (1 + s(k-1)) times the
    work, so the volume is raised by that much too: the same load, a different way of working
    (the W2 amendment). Example: load 1.1, k = 2, s = .25 → 1.1 x 1.6 = 1.76."""
    k, s = world["chats_per_agent"], world["chat_slowdown"]
    return world["load"] * k / (1.0 + s * (k - 1))


# ---- 2. Writing it into a copy of the repo ----------------------------------------------------

def apply_world(dest: Path, world: dict) -> None:
    """Edit the copy's generator, roster and SLA configs (comments are lost; it is a throwaway copy)."""
    gen_path, roster_path, sla_path = (dest / "config" / n for n in ("generator.yaml", "roster.yaml", "sla.yaml"))
    gen = yaml.safe_load(gen_path.read_text(encoding="utf-8"))
    gen["seed"] = world["seed"]
    gen["tickets_per_weekday"] = int(round(gen["tickets_per_weekday"] * load_factor(world)))
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

    roster = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
    roster["max_concurrent"] = world["chats_per_agent"]
    roster["agents"] = resize_teams(roster["agents"], world["team_delta"], world["roster_seed"])
    roster_path.write_text(yaml.safe_dump(roster, sort_keys=False), encoding="utf-8")

    sla = yaml.safe_load(sla_path.read_text(encoding="utf-8"))
    sla["sla_minutes"] = world["sla_minutes"]
    sla_path.write_text(yaml.safe_dump(sla, sort_keys=False), encoding="utf-8")


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
    subprocess.run([sys.executable, *args], cwd=dest, check=True, stdout=log, stderr=subprocess.STDOUT)
    log.write(f"\n== {' '.join(args)} done in {time.perf_counter() - started:.0f}s\n".encode())


def run_world(seed: int, workers: int) -> dict:
    """The whole pipeline for one world; returns (and saves) its result."""
    out_path = OUT_DIR / f"{seed}.json"
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    world = sample_world(seed)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"opslens_world_{seed}_") as tmp:
        dest = Path(tmp) / "repo"
        copy_repo(dest)
        apply_world(dest, world)
        with open(OUT_DIR / f"{seed}.log", "wb") as log:
            run_step(dest, log, "data/generate_ops.py")
            run_step(dest, log, "eval/run_classification.py", "--no-llm")
            run_step(dest, log, "eval/run_risk.py")
            run_step(dest, log, "eval/run_forecast.py")
            run_step(dest, log, "eval/run_world_compare.py", "--workers", str(workers))
        parts = dest / "eval" / "parts"
        compare = json.loads((parts / "world_compare.json").read_text(encoding="utf-8"))
        risk = json.loads((parts / "risk.json").read_text(encoding="utf-8"))
    result = {"seed": seed, "params": world, "volume_factor": load_factor(world), "compare": compare,
              "risk_auc": (risk.get("test") or {}).get("auc"), "minutes": round((time.perf_counter() - started) / 60, 1)}
    out_path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    breach = {p: v["turnaround.breach_pct"] for p, v in compare["mean"].items()}
    print(f"world {seed}: " + "  ".join(f"{p} {b:.2f}%" for p, b in breach.items()) + f"  ({result['minutes']} min)", flush=True)
    return result


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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seeds = WORLD_SEEDS
    if "--only" in sys.argv:
        seeds = [int(x) for x in sys.argv[sys.argv.index("--only") + 1:] if x.isdigit()]
    if "--summary" not in sys.argv:
        parallel = 3 if len(seeds) > 1 else 1
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            list(pool.map(lambda s: run_world(s, workers=4), seeds))
    # Only the 30 pre-registered worlds count: the code-check world 7000 is never part of the result.
    done = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(OUT_DIR.glob("*.json"))
            if p.stem.isdigit() and int(p.stem) in WORLD_SEEDS]
    summary = summarize(done)
    (ROOT / "eval" / "parts" / "worlds.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"{summary['n_worlds']} worlds: OpsLens lowest (within {TIE_POINTS} pts) in {summary['wins']}; "
          f"median OpsLens - D {summary['median_opslens_minus_d']:+.2f} pts, CI {summary['median_ci']}; "
          f"rule {'PASSED' if summary['rule_passed'] else 'not passed (or not all worlds done)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
