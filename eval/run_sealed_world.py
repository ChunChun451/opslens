"""Sealed second world: does the frozen policy hold on a world that did not exist when it was built?

Why: policy v1 → v2 → v3 were each designed after a test-day stress result (PROGRESS.md, M8).
Weights were always chosen on validation days, but the test fortnight was looked at three
times. Our data is generated, so we can do what real projects cannot: draw a completely new
world AFTER the policy is frozen and evaluate it once.

What it does, in a copy of the repo (so data/generated/ of the main world is untouched):
1. set a new generator seed (same config: same floor, same kinds of problems, new tickets,
   new daily noise, new luck),
2. `make gen`, then the normal training steps on the new world's days 1-35 (+ validation
   36-42): classifier, risk model, forecast + staffing plan. These are the product's routine
   retraining, not tuning: config/optimizer.yaml is copied unchanged (frozen weights),
3. A / B / C / OpsLens on the new world's test days 43-56, 5 seeds (eval/run_baseline_c.py),
4. copy that result back as eval/parts/sealed_world.json.

Run ONCE, after the freeze, and keep whatever it says:
    .venv/Scripts/python.exe eval/run_sealed_world.py --seed 4242
Add --no-llm to classify with the local model only (the LLM changes accuracy by ~0.1 point).

Re-run (18 Oct, GitHub issue #5): baselines were added after the first sealed run, so the same
world is run again with Baseline D and the published rules (eval/run_best_baselines.py):
    .venv/Scripts/python.exe eval/run_sealed_world.py --seed 4242 --rerun
It writes eval/parts/sealed_world_rerun.json and leaves the first run (sealed_world.json) as it was.

Rescue (18 Oct): least slack + cross-skill rescue was added after the re-run, so the same world is
built a third time and ONLY that rule runs, beside OpsLens and plain least slack (threshold chosen
on the main world's validation days):
    .venv/Scripts/python.exe eval/run_sealed_world.py --seed 4242 --rescue
It adds `rescue_test` to eval/parts/sealed_world_rerun.json and checks that OpsLens and plain least
slack reproduce the re-run's per-seed results; nothing else in the file changes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".git", ".venv", ".venv-challengers", "data/generated", "cache", ".pytest_tmp", ".pytest_cache", "__pycache__"}


def copy_repo(dest: Path) -> None:
    """Copy the repo without git, venvs, generated data and caches."""
    def ignore(folder: str, names: list[str]) -> list[str]:
        rel = Path(folder).relative_to(ROOT).as_posix()
        return [n for n in names if n in SKIP or f"{rel}/{n}".lstrip("./") in SKIP]
    shutil.copytree(ROOT, dest, ignore=ignore)


def set_seed(dest: Path, seed: int) -> None:
    path = dest / "config" / "generator.yaml"
    text = path.read_text(encoding="utf-8")
    new, count = re.subn(r"(?m)^seed:\s*\d+", f"seed: {seed}", text)
    if count != 1:
        raise RuntimeError("could not find the 'seed:' line in config/generator.yaml")
    path.write_text(new, encoding="utf-8")


def run(dest: Path, script: str, *args: str) -> None:
    started = time.perf_counter()
    subprocess.run([sys.executable, script, *args], cwd=dest, check=True)
    print(f"  {script} {' '.join(args)} done in {time.perf_counter() - started:.0f}s", flush=True)


def main() -> int:
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 4242
    no_llm = ["--no-llm"] if "--no-llm" in sys.argv else []
    rerun = "--rerun" in sys.argv
    rescue = "--rescue" in sys.argv
    with tempfile.TemporaryDirectory(prefix="opslens_sealed_") as tmp:
        dest = Path(tmp) / "repo"
        copy_repo(dest)
        set_seed(dest, seed)
        print(f"sealed world: seed {seed} in {dest}", flush=True)
        run(dest, "data/generate_ops.py")
        run(dest, "eval/run_classification.py", *no_llm)
        run(dest, "eval/run_risk.py")
        run(dest, "eval/run_forecast.py")
        if "--new" in sys.argv:
            run_new(dest, seed, no_llm)
            return 0
        if rescue:
            run(dest, "eval/run_best_baselines.py", "--rescue", "--test-only")
            add_rescue(json.loads((dest / "eval" / "parts" / "best_baselines.json").read_text(encoding="utf-8")))
            return 0
        run(dest, "eval/run_baseline_c.py", "--test-only")
        out = json.loads((dest / "eval" / "parts" / "baseline_c.json").read_text(encoding="utf-8"))
        risk = json.loads((dest / "eval" / "parts" / "risk.json").read_text(encoding="utf-8"))
        best = None
        if rerun:
            # The published rules, with the c-mu shape chosen on the MAIN world's validation days
            # (eval/parts/best_baselines.json is copied in): nothing is chosen on this world.
            run(dest, "eval/run_best_baselines.py", "--test-only")
            best = json.loads((dest / "eval" / "parts" / "best_baselines.json").read_text(encoding="utf-8"))["test"]
    out = {"data_seed": seed, "classifier": "local only" if no_llm else "cascade (local + LLM)",
           "note": "New world generated after the policy freeze; weights unchanged; run once.",
           "risk_auc": (risk.get("test") or {}).get("auc"), **out}
    name = "sealed_world"
    if rerun:
        name = "sealed_world_rerun"
        out["note"] = RERUN_NOTE
        out["best_baselines_test"] = best
        out["same_as_first_run"] = same_as_first_run(out)
    (ROOT / "eval" / "parts" / f"{name}.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(f"wrote eval/parts/{name}.json")
    return 0


def run_new(dest: Path, seed: int, no_llm: list[str]) -> None:
    """A NEW world (seed never used before) under the corrected simulator (18 Oct), run once: every
    baseline, the published rules, the frozen OpsLens policy, and the physical floor."""
    run(dest, "eval/run_baseline_c.py", "--test-only")
    run(dest, "eval/run_best_baselines.py", "--test-only")
    run(dest, "eval/run_floor.py")
    parts = dest / "eval" / "parts"
    load = lambda name: json.loads((parts / name).read_text(encoding="utf-8"))  # noqa: E731
    best = load("best_baselines.json")
    out = {"data_seed": seed, "classifier": "local only" if no_llm else "cascade (local + LLM)",
           "note": ("New world generated on 18 Oct, after the simulator correction (work draws no longer shifted by "
                    "transfers); OpsLens weights unchanged (v3), routine retraining; run once."),
           "risk_auc": (load("risk.json").get("test") or {}).get("auc"), "test": load("baseline_c.json")["test"],
           "best_baselines_test": best["test"], "rescue_test": (best.get("rescue") or {}).get("test"),
           "floor": load("floor.json")}
    (ROOT / "eval" / "parts" / "sealed_world_new.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print("wrote eval/parts/sealed_world_new.json")


def add_rescue(best: dict) -> None:
    """Put the sealed world's rescue test into sealed_world_rerun.json, with a reproduction check."""
    path = ROOT / "eval" / "parts" / "sealed_world_rerun.json"
    rerun = json.loads(path.read_text(encoding="utf-8"))
    test = best["rescue"]["test"]
    stored = rerun["best_baselines_test"]["per_seed"]
    test["reproduced"] = {k: test["per_seed"][k] == stored[k] for k in ("opslens", "least_slack")}
    test["note"] = ("Least slack + cross-skill rescue was added after the re-run; this world was built a third "
                    "time (same seed) and only this rule ran beside OpsLens and plain least slack. Threshold "
                    "chosen on the main world's validation days.")
    rerun["rescue_test"] = test
    path.write_text(json.dumps(rerun, indent=1, default=float), encoding="utf-8")
    print(f"added rescue_test to eval/parts/sealed_world_rerun.json; reproduced: {test['reproduced']}")


def same_as_first_run(rerun: dict) -> dict[str, bool]:
    """Per policy in both runs: are the per-seed KPIs of the re-run identical to the first run?"""
    first_path = ROOT / "eval" / "parts" / "sealed_world.json"
    if not first_path.exists():
        return {}
    first = json.loads(first_path.read_text(encoding="utf-8"))["test"]["per_seed"]
    return {p: first[p] == runs for p, runs in rerun["test"]["per_seed"].items() if p in first}


RERUN_NOTE = ("Re-run on 18 Oct 2026 because baselines were added AFTER the first sealed run: Baseline D (industry "
              "standard) and the published rules (least slack first, generalized c-mu, clairvoyant least slack). Same "
              "data seed, same frozen OpsLens weights, routine retraining as in the first run. The first run is kept "
              "unchanged in sealed_world; the LLM part of the classifier can answer differently on a re-run, so "
              "OpsLens and A/B/C can move slightly between the two runs.")


if __name__ == "__main__":
    raise SystemExit(main())
