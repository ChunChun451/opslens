"""Does OpsLens beat the strongest PUBLISHED rules, not only helpdesk defaults? (added 18 Oct)

"Industry standard" (Baseline D) is our own reading of what helpdesks ship. This step adds the
rules the scheduling literature says are best (opslens/policies.py):
- least slack first, hopeless tickets last (deadline + job size; Conway et al. 1967, Niyama 2025),
- generalized c-mu with a smooth "minutes past SLA" cost (Van Mieghem 1995; Mandelbaum &
  Stolyar 2004), two shape parameters chosen on validation days,
- clairvoyant least slack (NOT implementable): least slack first with the true category and the
  true handle time, without and with OpsLens's staffing plan. It shows what perfect information
  buys the best simple rule; it is not an upper bound on what is possible.

Order of work, so the test days cannot influence any choice:
1. validation days 36-42, seeds 1-3: every rule, the c-mu grid, D and OpsLens. The c-mu shape
   with the lowest breach % is kept (ties: fewer late minutes). Nothing else has a parameter.
2. gate: if an implementable rule has a lower validation breach % than OpsLens, stop (the
   owner decides what happens next). Clairvoyant least slack is not part of the gate.
3. test days 43-56, seeds 1-5, every policy on the same tickets and luck. Paired 95% CI vs OpsLens.

Least slack + cross-skill rescue (added 18 Oct, `--rescue`): the published rules may not make
deliberate cross-skill jobs, OpsLens may. This stage gives least slack the same freedom by a plain
rule (opslens/policies.py, LeastSlackRescuePolicy) and repeats 1-3 for it alone:
1. validation days 36-42, seeds 1-3: one run per slack threshold in RESCUE_GRID; the lowest
   breach % is kept (ties: fewer late minutes). Plain least slack is run again as a check that
   the stored numbers reproduce.
2. gate: stop before the test run if its validation breach % is at or below OpsLens's (stored).
3. test days 43-56, seeds 1-5, chosen threshold, with OpsLens and plain least slack run again
   beside it (same tickets, same luck); both must reproduce the stored test numbers exactly.

Run:  .venv/Scripts/python.exe eval/run_best_baselines.py                    (1, 2, then 3)
      ... run_best_baselines.py --rescue        (only the rescue stage; needs the stages above)
      ... run_best_baselines.py --rescue --test-only   (rescue test days only, stored threshold)
      ... run_best_baselines.py --validation-only
      ... run_best_baselines.py --test-only   (3 only, with the c-mu shape already chosen in
                                               eval/parts/best_baselines.json; the sealed world)
Writes eval/parts/best_baselines.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import PARTS, run_jobs  # noqa: E402
from opslens.impact import mean_std, paired_ci  # noqa: E402

RESCUE_GRID = [10, 20, 30, 60, 120, 240]  # slack threshold in minutes (240 = the P2 SLA)
CMU_GRID = [{"tau": tau, "beta": beta} for beta in (0.0, 1.0) for tau in (0.1, 0.25, 0.5, 1.0)]
NEW_RULES = ["least_slack", "gen_cmu"]  # implementable: these are in the gate
CLAIRVOYANT = ["clairvoyant", "clairvoyant_staffed"]
TEST_POLICIES = ["baseline_a", "baseline_b", "baseline_c", "baseline_d", "opslens", *NEW_RULES, *CLAIRVOYANT]
SHOW = ["turnaround.breach_pct", "segment.p1_breach_pct", "quality.mean_minutes_late",
        "quality.late_minutes_per_100", "quality.p99_wait_min", "turnaround.p90_resolution_min",
        "productivity.transfers_per_100", "quality.reopen_rate_pct"]


def job(key: str, seed: int, first: int, last: int, params: dict | None = None) -> dict:
    """One simulation job. `key` is how the result is labelled; `policy` is what run_one builds."""
    policy = "clairvoyant" if key == "clairvoyant_staffed" else key
    out = {"key": key, "policy": policy, "seed": seed, "first_day": first, "last_day": last,
           "staffing": key in ("opslens", "clairvoyant_staffed")}
    if params:
        out["params"] = params
    return out


def by_key(results: list[dict]) -> dict[str, list[dict]]:
    """{key: [kpis of seed 1, seed 2, ...]}."""
    out: dict[str, list[dict]] = {}
    for r in sorted(results, key=lambda r: r["job"]["seed"]):
        out.setdefault(r["job"]["key"], []).append(r["kpis"])
    return out


def mean(per: dict, key: str, kpi: str = "turnaround.breach_pct") -> float:
    return mean_std([r[kpi] for r in per[key]])[0]


def print_table(per: dict, keys: list[str]) -> None:
    print(f"{'KPI':32s}" + "".join(f"{k:>14s}" for k in keys))
    for kpi in SHOW:
        print(f"{kpi:32s}" + "".join(f"{mean(per, k, kpi):14.2f}" for k in keys))


def validation() -> dict:
    first, last, seeds = 36, 42, [1, 2, 3]
    jobs = [job(k, s, first, last) for k in ("baseline_d", "opslens", "least_slack", *CLAIRVOYANT) for s in seeds]
    jobs += [job(f"gen_cmu tau={p['tau']} beta={p['beta']}", s, first, last, p) | {"policy": "gen_cmu"}
             for p in CMU_GRID for s in seeds]
    per = by_key(run_jobs(jobs, workers=min(len(jobs), 14)))
    grid = []
    for p in CMU_GRID:
        k = f"gen_cmu tau={p['tau']} beta={p['beta']}"
        grid.append({**p, "breach_pct": mean(per, k), "late_minutes_per_100": mean(per, k, "quality.late_minutes_per_100")})
        print(f"  c-mu tau={p['tau']:<5} beta={p['beta']:<4} breach {grid[-1]['breach_pct']:6.2f}%  "
              f"late min/100 {grid[-1]['late_minutes_per_100']:8.1f}")
    best = min(grid, key=lambda g: (g["breach_pct"], g["late_minutes_per_100"]))
    chosen = {"tau": best["tau"], "beta": best["beta"]}
    per["gen_cmu"] = per[f"gen_cmu tau={chosen['tau']} beta={chosen['beta']}"]
    keys = ["baseline_d", "opslens", *NEW_RULES, *CLAIRVOYANT]
    print(f"\nvalidation days {first}-{last}, seeds {seeds}; c-mu chosen: {chosen}")
    print_table(per, keys)
    ops = mean(per, "opslens")
    beaten_by = [k for k in NEW_RULES if mean(per, k) <= ops]
    return {"days": [first, last], "seeds": seeds, "cmu_grid": grid, "cmu_chosen": chosen,
            "cmu_rule": "lowest validation breach %, ties broken by fewer late minutes per 100",
            "per_seed": {k: per[k] for k in keys},
            "gate": {"opslens_breach_pct": ops, "beaten_by": beaten_by, "passed": not beaten_by,
                     "rule": "stop before the test run if an implementable rule has a validation breach % "
                             "at or below OpsLens (clairvoyant least slack is not in the gate)"}}


def test(chosen: dict) -> dict:
    first, last, seeds = 43, 56, [1, 2, 3, 4, 5]
    jobs = [job(k, s, first, last, chosen if k == "gen_cmu" else None) for k in TEST_POLICIES for s in seeds]
    per = by_key(run_jobs(jobs, workers=min(len(jobs), 14)))
    print(f"\ntest days {first}-{last}, seeds {seeds}")
    print_table(per, TEST_POLICIES)
    out = {"days": [first, last], "seeds": seeds, "cmu_params": chosen, "per_seed": per, "opslens_minus": {}}
    for base in TEST_POLICIES:
        if base == "opslens":
            continue
        diffs = {kpi: paired_ci([r[kpi] for r in per["opslens"]], [r[kpi] for r in per[base]]) for kpi in SHOW}
        out["opslens_minus"][base] = diffs
        d = diffs["turnaround.breach_pct"]
        late = diffs["quality.late_minutes_per_100"]
        print(f"OpsLens - {base:20s} breach {d['mean_diff']:+6.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}]   "
              f"late min/100 {late['mean_diff']:+8.1f} [{late['ci_low']:+.1f}, {late['ci_high']:+.1f}]")
    return out


def rescue_validation(stored: dict) -> dict:
    """Stage 1-2 for least slack + cross-skill rescue. `stored` = the validation block above."""
    first, last, seeds = stored["days"][0], stored["days"][1], stored["seeds"]
    jobs = [job(f"rescue {th}", s, first, last, {"threshold_min": th}) | {"policy": "least_slack_rescue"}
            for th in RESCUE_GRID for s in seeds]
    jobs += [job("least_slack", s, first, last) for s in seeds]
    per = by_key(run_jobs(jobs, workers=min(len(jobs), 14)))
    grid = []
    for th in RESCUE_GRID:
        k = f"rescue {th}"
        grid.append({"threshold_min": th, "breach_pct": mean(per, k),
                     "late_minutes_per_100": mean(per, k, "quality.late_minutes_per_100"),
                     "reopen_rate_pct": mean(per, k, "quality.reopen_rate_pct")})
        print(f"  rescue threshold {th:4d} min: breach {grid[-1]['breach_pct']:6.2f}%  late min/100 "
              f"{grid[-1]['late_minutes_per_100']:8.1f}  reopen {grid[-1]['reopen_rate_pct']:5.2f}%")
    best = min(grid, key=lambda g: (g["breach_pct"], g["late_minutes_per_100"]))
    chosen = best["threshold_min"]
    per["least_slack_rescue"] = per[f"rescue {chosen}"]
    per["opslens"] = stored["per_seed"]["opslens"]
    reproduced = per["least_slack"] == stored["per_seed"]["least_slack"]
    print(f"\nvalidation days {first}-{last}, seeds {seeds}; threshold chosen: {chosen} min; "
          f"plain least slack reproduced: {reproduced}")
    print_table(per, ["opslens", "least_slack", "least_slack_rescue"])
    ops = mean(per, "opslens")
    passed = mean(per, "least_slack_rescue") > ops
    return {"days": [first, last], "seeds": seeds, "grid": grid, "threshold_chosen": chosen,
            "rule": "lowest validation breach %, ties broken by fewer late minutes per 100",
            "least_slack_reproduced": reproduced,
            "per_seed": {k: per[k] for k in ("least_slack", "least_slack_rescue")},
            "gate": {"opslens_breach_pct": ops, "passed": passed,
                     "rule": "stop before the test run if least slack + rescue has a validation breach % at or "
                             "below OpsLens"}}


def rescue_test(threshold: float, stored: dict | None) -> dict:
    """Stage 3: test days 43-56 once, chosen threshold, with OpsLens and plain least slack run again
    beside it (same tickets, same luck). `stored` = the test block above, if this world has one:
    then the re-runs are checked against it (they must reproduce exactly)."""
    first, last, seeds = 43, 56, [1, 2, 3, 4, 5]
    jobs = [job("least_slack_rescue", s, first, last, {"threshold_min": threshold}) for s in seeds]
    jobs += [job(k, s, first, last) for k in ("opslens", "least_slack") for s in seeds]
    per = by_key(run_jobs(jobs, workers=min(len(jobs), 14)))
    keys = ["opslens", "least_slack", "least_slack_rescue"]
    reproduced = {k: per[k] == stored["per_seed"][k] for k in keys[:2]} if stored else {}
    print(f"\ntest days {first}-{last}, seeds {seeds}; threshold {threshold} min; reproduced: {reproduced}")
    print_table(per, keys)
    out = {"days": [first, last], "seeds": seeds, "threshold_min": threshold, "reproduced": reproduced,
           "per_seed": {k: per[k] for k in keys}, "opslens_minus": {}}
    for base in ("least_slack_rescue", "least_slack"):
        diffs = {kpi: paired_ci([r[kpi] for r in per["opslens"]], [r[kpi] for r in per[base]]) for kpi in SHOW}
        out["opslens_minus"][base] = diffs
        d, late, reo = (diffs[k] for k in ("turnaround.breach_pct", "quality.late_minutes_per_100",
                                            "quality.reopen_rate_pct"))
        print(f"OpsLens - {base:20s} breach {d['mean_diff']:+6.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}]   "
              f"late min/100 {late['mean_diff']:+8.1f} [{late['ci_low']:+.1f}, {late['ci_high']:+.1f}]   "
              f"reopen {reo['mean_diff']:+5.2f} [{reo['ci_low']:+.2f}, {reo['ci_high']:+.2f}]")
    out["rescue_minus_least_slack"] = {
        kpi: paired_ci([r[kpi] for r in per["least_slack_rescue"]], [r[kpi] for r in per["least_slack"]])
        for kpi in SHOW}
    d = out["rescue_minus_least_slack"]["turnaround.breach_pct"]
    print(f"rescue - plain least slack       breach {d['mean_diff']:+6.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}]")
    return out


def rescue_stage(out: dict, test_only: bool) -> None:
    """Least slack + rescue: validation → gate → test once; `test_only` reuses the stored threshold
    (the sealed world). Writes into out["rescue"]."""
    if test_only:
        if not out["rescue"]["validation"]["gate"]["passed"]:
            raise SystemExit("the rescue validation gate failed: the owner decides before any test run")
        out["rescue"]["test"] = rescue_test(out["rescue"]["validation"]["threshold_chosen"], None)
        return
    out["rescue"] = {"validation": rescue_validation(out["validation"])}
    if not out["rescue"]["validation"]["gate"]["passed"]:
        print("\nSTOP: least slack + rescue matched or beat OpsLens on validation days. Test days NOT run.")
    elif "--validation-only" not in sys.argv:
        out["rescue"]["test"] = rescue_test(out["rescue"]["validation"]["threshold_chosen"], out.get("test"))


def main() -> int:
    path = PARTS / "best_baselines.json"
    PARTS.mkdir(parents=True, exist_ok=True)
    test_only = "--test-only" in sys.argv
    if "--rescue" in sys.argv:  # only the rescue stage
        out = json.loads(path.read_text(encoding="utf-8"))
        rescue_stage(out, test_only)
    elif test_only:
        out = json.loads(path.read_text(encoding="utf-8"))
        if not out["validation"]["gate"]["passed"]:
            raise SystemExit("the validation gate failed: the owner decides before any test run")
        out["test"] = test(out["validation"]["cmu_chosen"])
        if "rescue" in out:
            rescue_stage(out, test_only=True)
    else:
        out = {"validation": validation()}
        gate = out["validation"]["gate"]
        if not gate["passed"]:
            print(f"\nSTOP: {gate['beaten_by']} beat OpsLens on validation days. Test days NOT run.")
        elif "--validation-only" not in sys.argv:
            out["test"] = test(out["validation"]["cmu_chosen"])
            rescue_stage(out, test_only=False)
    path.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print("wrote eval/parts/best_baselines.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
