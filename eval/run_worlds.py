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
sys.path.insert(0, str(ROOT))
OUT_DIR = ROOT / "eval" / "parts" / "worlds"
DIAG_DIR = ROOT / "eval" / "parts" / "worlds_diag"
WORLD_SEEDS = list(range(7001, 7031))
SKIP = {".git", ".venv", ".venv-challengers", "data/generated",
        "cache", ".pytest_tmp", ".pytest_cache", "__pycache__", "eval/parts/worlds", "eval/parts/worlds_diag",
        "eval/parts/worlds_v6design", "eval/parts/worlds_v6design2", "eval/parts/worlds_v6confirm",
        "eval/challengers"}
CATEGORIES = ["late_delivery", "missing_item", "wrong_item", "refund", "payment_failure", "app_bug",
              "account", "restaurant_partner"]
OTHERS = ["baseline_a", "baseline_b", "baseline_c", "baseline_d", "least_slack"]
TIE_POINTS = 0.05


def sample_world(seed: int) -> dict:
    rng = np.random.default_rng(seed)
    k = int(rng.integers(1, 4))
    s = float(rng.choice([0.25, 0.5])) if k > 1 else 0.0
    return {
        "seed": seed,
        "load": float(rng.uniform(0.7, 1.4)),
        "peak_scale": float(rng.uniform(0.7, 1.3)),
        "category_scale": {c: float(rng.uniform(0.6, 1.4)) for c in CATEGORIES},
        "hindi_share": float(rng.uniform(0.05, 0.25)),
        "handle_scale": float(rng.uniform(0.7, 1.3)),
        "mismatch_factor": float(rng.uniform(1.2, 2.0)),
        "absent_prob": float(rng.uniform(0.02, 0.10)),
        "team_delta": {t: int(rng.integers(-2, 3)) for t in "ABCD"},
        "sla_minutes": {"P1": int(rng.uniform(10, 20)), "P2": int(rng.uniform(40, 80)),
                        "P3": int(rng.uniform(160, 320))},
        "chats_per_agent": k, "chat_slowdown": s,
        "plants": {"payment_spike_day": int(rng.integers(12, 31)), "payment_spike_mult": float(rng.uniform(3, 5)),
                   "app_bug_day": int(rng.integers(44, 56)), "app_bug_mult": float(rng.uniform(3, 6)),
                   "partner_cluster": int(rng.integers(1, 41)) % 40, "partner_mult": float(rng.uniform(2, 4)),
                   "ivr_wrong_prob": float(rng.uniform(0.15, 0.35)), "team_c_lift": float(rng.uniform(1.2, 1.5))},
        "roster_seed": int(rng.integers(0, 2**31 - 1)),
    }


def load_factor(world: dict, gen: dict, n_agents_before: int, n_agents_after: int) -> float:
    k, s = world["chats_per_agent"], world["chat_slowdown"]
    medians = gen["handle_median_min"]
    old_mix = sum(gen["categories"][c] * medians[c] for c in CATEGORIES)
    shares = {c: gen["categories"][c] * world["category_scale"][c] for c in CATEGORIES}
    new_mix = sum(shares[c] / sum(shares.values()) * medians[c] for c in CATEGORIES)
    capacity = k / (1.0 + s * (k - 1)) * n_agents_after / n_agents_before
    work_per_ticket = world["handle_scale"] * new_mix / old_mix
    return world["load"] * capacity / work_per_ticket


def apply_world(dest: Path, world: dict) -> float:
    gen_path, roster_path, sla_path = (dest / "config" / n for n in ("generator.yaml", "roster.yaml", "sla.yaml"))
    gen = yaml.safe_load(gen_path.read_text(encoding="utf-8"))
    roster = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
    resized = resize_teams(roster["agents"], world["team_delta"], world["roster_seed"])
    volume = load_factor(world, gen, len(roster["agents"]), len(resized))
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


def copy_repo(dest: Path) -> None:
    def ignore(folder: str, names: list[str]) -> list[str]:
        rel = Path(folder).relative_to(ROOT).as_posix()
        return [n for n in names if n in SKIP or f"{rel}/{n}".lstrip("./") in SKIP]
    shutil.copytree(ROOT, dest, ignore=ignore)


def run_step(dest: Path, log, *args: str) -> None:
    started = time.perf_counter()
    subprocess.run([sys.executable, "-u", *args], cwd=dest, check=True, stdout=log, stderr=subprocess.STDOUT)
    log.write(f"\n== {' '.join(args)} done in {time.perf_counter() - started:.0f}s\n".encode())


def run_world(seed: int, workers: int, diagnose: bool = False, mode: str = "") -> dict:
    folder = DIAG_DIR if diagnose else (ROOT / "eval" / "parts" / f"worlds_{mode}" if mode else OUT_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    out_path = folder / f"{seed}.json"
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    world = sample_world(seed)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"opslens_world_{seed}_") as tmp:
        dest = Path(tmp) / "repo"
        copy_repo(dest)
        volume = apply_world(dest, world)
        with open(folder / f"{seed}.log", "wb") as log:
            run_step(dest, log, "data/generate_ops.py")
            run_step(dest, log, "eval/run_classification.py", "--no-llm")
            run_step(dest, log, "eval/run_risk.py")
            run_step(dest, log, "eval/run_forecast.py")
            run_step(dest, log, "eval/run_world_compare.py", "--workers", str(workers),
                     *(["--diagnose"] if diagnose else []), *MODE_ARGS.get(mode, []))
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
    try:
        return run_world(seed, workers)
    except Exception as exc:
        print(f"world {seed} FAILED: {exc!r} (see eval/parts/worlds/{seed}.log)", flush=True)
        return None


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


MODE_ARGS: dict[str, list[str]] = {"v6design": ["--v6-design"], "v6design2": ["--v6-design", "--round2"]}
CONFIRM_SEEDS = list(range(7101, 7131))


def run_world_safe_mode(seed: int, mode: str) -> dict | None:
    try:
        return run_world(seed, workers=4, mode=mode)
    except Exception as exc:
        print(f"world {seed} FAILED: {exc!r}", flush=True)
        return None


def summarize_v6() -> int:
    parts = ROOT / "eval" / "parts"
    confirm_main = json.loads((parts / "confirm_v6_main.json").read_text(encoding="utf-8"))
    done = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((parts / "worlds_v6confirm").glob("*.json"))
            if p.stem.isdigit() and int(p.stem) in CONFIRM_SEEDS]
    rows = []
    for r in sorted(done, key=lambda r: r["seed"]):
        mean = {p: v["turnaround.breach_pct"] for p, v in r["compare"]["mean"].items()}
        best_other = min(OTHERS, key=lambda p: mean[p])
        rows.append({"seed": r["seed"], "volume_factor": r["volume_factor"], "breach_pct": mean, "best_other": best_other,
                     "v6_lowest": mean["opslens_v6"] <= mean[best_other] + TIE_POINTS,
                     "v5_lowest": mean["opslens"] <= mean[best_other] + TIE_POINTS,
                     "v6_minus_v5": mean["opslens_v6"] - mean["opslens"]})
    need = 27
    v6_wins = sum(row["v6_lowest"] for row in rows)
    diffs = [row["v6_minus_v5"] for row in rows]
    summary = {
        "candidate": confirm_main["candidate"], "config": confirm_main["config"],
        "design_choice": json.loads((parts / "design_v6.json").read_text(encoding="utf-8"))["chosen"],
        "round2_main_gate": json.loads((parts / "design_v6_main2.json").read_text(encoding="utf-8"))["candidates"],
        "confirm_main": confirm_main,
        "worlds": rows, "n_worlds": len(rows), "tie_points": TIE_POINTS, "wins_needed": need,
        "v6_lowest_in": v6_wins, "v5_lowest_in": sum(row["v5_lowest"] for row in rows),
        "v6_beats_industry_standard_in": sum(row["breach_pct"]["opslens_v6"] < row["breach_pct"]["baseline_d"] for row in rows),
        "v5_beats_industry_standard_in": sum(row["breach_pct"]["opslens"] < row["breach_pct"]["baseline_d"] for row in rows),
        "v6_minus_v5_mean": float(np.mean(diffs)) if diffs else None,
        "v6_better_than_v5_in": sum(d < -TIE_POINTS for d in diffs),
        "v6_worse_than_v5_in": sum(d > TIE_POINTS for d in diffs),
        "adopted": bool(confirm_main["passed"] and len(rows) == len(CONFIRM_SEEDS) and v6_wins >= need),
    }
    (parts / "v6_adoption.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"v6 {summary['candidate']}: main confirm passed {confirm_main['passed']}; lowest in {v6_wins} of {len(rows)} new worlds "
          f"(v5 {summary['v5_lowest_in']}; needs {need}); adopted {summary['adopted']}")
    return 0


def main() -> int:
    if "--diagnose" in sys.argv:
        return diagnose_losses()
    if "--v6-summary" in sys.argv:
        return summarize_v6()
    if "--v6-design" in sys.argv:
        from eval.run_design_v6 import DESIGN_WORLDS
        mode = "v6design2" if "--round2" in sys.argv else "v6design"
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda s: run_world_safe_mode(s, mode), DESIGN_WORLDS))
        return 0
    if "--v6-confirm" in sys.argv:
        MODE_ARGS["v6confirm"] = ["--v6", sys.argv[sys.argv.index("--v6-confirm") + 1]]
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda s: run_world_safe_mode(s, "v6confirm"), CONFIRM_SEEDS))
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seeds = WORLD_SEEDS
    if "--only" in sys.argv:
        seeds = [int(x) for x in sys.argv[sys.argv.index("--only") + 1:] if x.isdigit()]
    if "--summary" not in sys.argv:
        parallel = 3 if len(seeds) > 1 else 1
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            list(pool.map(lambda s: run_world_safe(s, workers=4), seeds))
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
