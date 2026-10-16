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
    with tempfile.TemporaryDirectory(prefix="opslens_sealed_") as tmp:
        dest = Path(tmp) / "repo"
        copy_repo(dest)
        set_seed(dest, seed)
        print(f"sealed world: seed {seed} in {dest}", flush=True)
        run(dest, "data/generate_ops.py")
        run(dest, "eval/run_classification.py", *no_llm)
        run(dest, "eval/run_risk.py")
        run(dest, "eval/run_forecast.py")
        run(dest, "eval/run_baseline_c.py", "--test-only")
        out = json.loads((dest / "eval" / "parts" / "baseline_c.json").read_text(encoding="utf-8"))
        risk = json.loads((dest / "eval" / "parts" / "risk.json").read_text(encoding="utf-8"))
    out = {"data_seed": seed, "classifier": "local only" if no_llm else "cascade (local + LLM)",
           "note": "New world generated after the policy freeze; weights unchanged; run once.",
           "risk_auc": (risk.get("test") or {}).get("auc"), **out}
    (ROOT / "eval" / "parts" / "sealed_world.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print("wrote eval/parts/sealed_world.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
