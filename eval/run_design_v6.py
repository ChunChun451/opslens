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
    "D1": {"threshold": 1.5, "horizon_min": 240, "switch_to": "least_slack"},
    "D2": {"threshold": 2.0, "horizon_min": 240, "switch_to": "least_slack"},
}
ROUND2 = ["D1", "D2"]
DESIGN_WORLDS = [7001, 7005, 7006, 7007, 7008, 7011, 7014, 7019, 7023, 7025, 7026,
                 7029, 7018, 7002, 7013, 7012, 7015,
                 7022, 7004, 7009]
OTHERS = ["baseline_a", "baseline_b", "baseline_c", "baseline_d", "least_slack"]
TIE = 0.05


def candidate_jobs(first: int, last: int, seeds: list[int], with_v5: bool, names: list[str] | None = None) -> list[dict]:
    names = names or [n for n in CANDIDATES if n not in ROUND2]
    jobs = [{"policy": "opslens", "seed": s, "first_day": first, "last_day": last, "staffing": True,
             "weights": {"overload": CANDIDATES[name]}, "tag": f"v6_{name}"} for name in names for s in seeds]
    if with_v5:
        jobs += [{"policy": "opslens", "seed": s, "first_day": first, "last_day": last, "staffing": True,
                  "tag": "v5"} for s in seeds]
    return jobs


def main_world(round2: bool = False) -> int:
    from eval.run_opslens import PARTS, run_jobs
    from opslens.impact import paired_ci
    started = time.perf_counter()
    names = ROUND2 if round2 else None
    results = run_jobs(candidate_jobs(36, 42, [1, 2, 3, 4, 5], with_v5=True, names=names), workers=8)
    by: dict[str, list] = {}
    for r in sorted(results, key=lambda r: r["job"]["seed"]):
        by.setdefault(r["job"]["tag"], []).append(r)
    v5 = [r["kpis"]["turnaround.breach_pct"] for r in by["v5"]]
    out = {"days": [36, 42], "seeds": [1, 2, 3, 4, 5], "v5_breach_pct": float(np.mean(v5)), "candidates": {}}
    for name in (ROUND2 if round2 else [n for n in CANDIDATES if n not in ROUND2]):
        b = [r["kpis"]["turnaround.breach_pct"] for r in by[f"v6_{name}"]]
        ci = paired_ci(b, v5)
        on = float(np.mean([r.get("overload_minutes", 0.0) for r in by[f"v6_{name}"]]))
        out["candidates"][name] = {"breach_pct": float(np.mean(b)), "vs_v5": ci, "overload_minutes": on}
        print(f"  {name}: {np.mean(b):.3f}% vs v5 {np.mean(v5):.3f}%  diff {ci['mean_diff']:+.3f} "
              f"[{ci['ci_low']:+.3f}, {ci['ci_high']:+.3f}]  mode on {on:.0f} min")
    name = "design_v6_main2.json" if round2 else "design_v6_main.json"
    (PARTS / name).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote eval/parts/{name} ({time.perf_counter() - started:.0f}s)")
    return 0


def choose() -> int:
    parts = ROOT / "eval" / "parts"
    main = json.loads((parts / "design_v6_main.json").read_text(encoding="utf-8"))
    if (parts / "design_v6_main2.json").exists():
        main["candidates"].update(json.loads((parts / "design_v6_main2.json").read_text(encoding="utf-8"))["candidates"])
    counted = {s: json.loads((parts / "worlds" / f"{s}.json").read_text(encoding="utf-8"))["compare"]["mean"]
               for s in DESIGN_WORLDS}
    design = {s: json.loads((parts / "worlds_v6design" / f"{s}.json").read_text(encoding="utf-8"))["compare"]["mean"]
              for s in DESIGN_WORLDS}
    if (parts / "worlds_v6design2").exists():
        for s in DESIGN_WORLDS:
            design[s].update(json.loads((parts / "worlds_v6design2" / f"{s}.json").read_text(encoding="utf-8"))["compare"]["mean"])
    names = [n for n in CANDIDATES if all(f"v6_{n}" in design[s] for s in DESIGN_WORLDS) and n in main["candidates"]]
    report = {}
    for name in names:
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
    ok = [n for n in names if report[n]["qualifies"]]
    chosen = min(ok, key=lambda n: report[n]["loss_margin"]) if ok else None
    out = {"chosen": chosen, "candidates": CANDIDATES, "report": report, "design_worlds": DESIGN_WORLDS}
    (parts / "design_v6.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"chosen: {chosen}")
    return 0


def confirm_main(name: str) -> int:
    from eval.run_opslens import PARTS, run_jobs
    from opslens.impact import paired_ci
    seeds = list(range(26, 46))
    jobs = candidate_jobs(36, 42, seeds, with_v5=True, names=[name])
    results = run_jobs(jobs, workers=10)
    by: dict[str, list] = {}
    for r in sorted(results, key=lambda r: r["job"]["seed"]):
        by.setdefault(r["job"]["tag"], []).append(r["kpis"]["turnaround.breach_pct"])
    ci = paired_ci(by[f"v6_{name}"], by["v5"])
    out = {"candidate": name, "config": CANDIDATES[name], "seeds": seeds, "v5_breach_pct": float(np.mean(by["v5"])),
           "v6_breach_pct": float(np.mean(by[f"v6_{name}"])), "v6_minus_v5": ci, "passed": bool(ci["ci_high"] < 0.05)}
    (PARTS / "confirm_v6_main.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"v6 {name} - v5: {ci['mean_diff']:+.3f} [{ci['ci_low']:+.3f}, {ci['ci_high']:+.3f}]  passed: {out['passed']}")
    return 0


if __name__ == "__main__":
    if "--confirm-main" in sys.argv:
        raise SystemExit(confirm_main(sys.argv[sys.argv.index("--confirm-main") + 1]))
    if "--main" in sys.argv:
        raise SystemExit(main_world(round2="--round2" in sys.argv))
    raise SystemExit(choose())
