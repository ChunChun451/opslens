from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import PARTS, run_jobs
from opslens.impact import mean_std, paired_ci

SETTINGS = [(2, 0.25), (2, 0.5), (3, 0.25), (3, 0.5)]
POLICIES = ["baseline_a", "baseline_b", "baseline_c", "baseline_d", "opslens"]
KPIS = ["turnaround.breach_pct", "turnaround.p90_resolution_min", "quality.late_minutes_per_100",
        "quality.p99_wait_min", "quality.reopen_rate_pct"]
ABLATION_SETTING = (3, 0.25)


def equal_load_boost(k: int, s: float) -> float:
    return k / (1.0 + s * (k - 1)) - 1.0


def jobs_for(first: int, last: int, seeds: list[int], settings: list[tuple[int, float]],
             policies: list[str], ablation: bool) -> list[dict]:
    jobs = []
    for k, s in settings:
        for load in ("equal_load", "today"):
            boost = equal_load_boost(k, s) if load == "equal_load" else 0.0
            for policy in policies:
                for seed in seeds:
                    jobs.append({"policy": policy, "seed": seed, "first_day": first, "last_day": last,
                                 "staffing": policy == "opslens", "max_concurrent": k, "concurrency_slowdown": s,
                                 "volume_boost": boost, "tag": f"{k}|{s}|{load}|{policy}"})
    if ablation:
        k, s = ABLATION_SETTING
        for seed in seeds:
            jobs.append({"policy": "opslens", "seed": seed, "first_day": first, "last_day": last, "staffing": True,
                         "max_concurrent": k, "concurrency_slowdown": s, "volume_boost": equal_load_boost(k, s),
                         "settings": {"use_optimizer": False, "label": "no_optimizer"},
                         "tag": f"{k}|{s}|equal_load|opslens_no_optimizer"})
    return jobs


def series(rows: list[dict], kpi: str) -> list[float]:
    return [r["kpis"][kpi] for r in sorted(rows, key=lambda r: r["job"]["seed"])]


def summarise(by_tag: dict[str, list[dict]], k: int, s: float, load: str, policies: list[str]) -> dict:
    out = {"k": k, "s": s, "load": load, "volume_factor": 1.0 + (equal_load_boost(k, s) if load == "equal_load" else 0.0),
           "policies": {}, "opslens_vs": {}}
    for policy in policies:
        rows = by_tag[f"{k}|{s}|{load}|{policy}"]
        out["policies"][policy] = {kpi: dict(zip(("mean", "std"), mean_std(series(rows, kpi)))) for kpi in KPIS}
    ops = by_tag[f"{k}|{s}|{load}|opslens"]
    for base in [p for p in policies if p != "opslens"]:
        rows = by_tag[f"{k}|{s}|{load}|{base}"]
        out["opslens_vs"][base] = {kpi: paired_ci(series(ops, kpi), series(rows, kpi)) for kpi in
                                   ("turnaround.breach_pct", "quality.late_minutes_per_100")}
    return out


def main() -> int:
    smoke = "--smoke" in sys.argv
    started = time.perf_counter()
    if smoke:
        first, last, seeds, settings, policies = 37, 38, [1], [(2, 0.25)], ["baseline_d", "opslens"]
    else:
        first, last, seeds, settings, policies = 43, 56, [1, 2, 3, 4, 5], SETTINGS, POLICIES
    jobs = jobs_for(first, last, seeds, settings, policies, ablation=not smoke)
    print(f"{len(jobs)} runs, days {first}-{last}, seeds {seeds}")
    results = run_jobs(jobs, workers=12)
    by_tag: dict[str, list[dict]] = {}
    for r in results:
        by_tag.setdefault(r["job"]["tag"], []).append(r)

    rows = []
    for k, s in settings:
        for load in ("equal_load", "today"):
            row = summarise(by_tag, k, s, load, policies)
            rows.append(row)
            p = row["policies"]
            d = row["opslens_vs"]["baseline_d"]["turnaround.breach_pct"]
            print(f"  k={k} s={s:.2f} {load:10s} x{row['volume_factor']:.2f}: " +
                  "  ".join(f"{name} {p[name]['turnaround.breach_pct']['mean']:5.2f}%" for name in policies) +
                  f"  | OpsLens - D {d['mean_diff']:+.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}]")
    out = {"first_day": first, "last_day": last, "seeds": seeds, "settings": rows, "smoke": smoke,
           "assumption": "slowdown s per extra open chat is an assumption; fixed when a chat starts"}
    if not smoke:
        equal = [r for r in rows if r["load"] == "equal_load"]
        out["rule_passed"] = all(r["opslens_vs"]["baseline_d"]["turnaround.breach_pct"]["ci_high"] < 0 for r in equal)
        k, s = ABLATION_SETTING
        full = series(by_tag[f"{k}|{s}|equal_load|opslens"], "turnaround.breach_pct")
        greedy = series(by_tag[f"{k}|{s}|equal_load|opslens_no_optimizer"], "turnaround.breach_pct")
        out["optimizer_ablation"] = {"k": k, "s": s, "greedy_breach_pct": dict(zip(("mean", "std"), mean_std(greedy))),
                                     "full_breach_pct": dict(zip(("mean", "std"), mean_std(full))),
                                     "greedy_minus_full": paired_ci(greedy, full)}
        g = out["optimizer_ablation"]["greedy_minus_full"]
        print(f"  rule (OpsLens beats D in all equal-load settings): {'PASSED' if out['rule_passed'] else 'FAILED'}")
        print(f"  optimiser ablation at k={k}, s={s}: greedy - full {g['mean_diff']:+.2f} [{g['ci_low']:+.2f}, {g['ci_high']:+.2f}]")
    name = "concurrency_smoke.json" if smoke else "concurrency.json"
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / name).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote eval/parts/{name} ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
