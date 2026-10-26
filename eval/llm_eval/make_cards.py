from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from data.plant import apply_plants, clean_config, clean_roster, random_plant_set
from eval.recall import score
from eval.run_blind import DAYS, SEED_BASE, run_set
from opslens.config import load_config

OUT = ROOT / "eval" / "llm_eval" / "cards.json"


def main() -> int:
    started = time.perf_counter()
    published = json.loads((ROOT / "eval" / "parts" / "blind.json").read_text(encoding="utf-8"))["sets"]
    calendar = load_config("calendar")
    base_cfg = clean_config({**load_config("generator"), **calendar})
    base_roster = clean_roster(load_config("roster"))
    sla = load_config("sla")
    team_skills = {t: v["skills"] for t, v in base_roster["teams"].items()}
    rng = np.random.default_rng(SEED_BASE)

    run_set(base_cfg, base_roster, sla, calendar, SEED_BASE)
    sets = []
    for k in range(len(published)):
        plants = random_plant_set(rng, base_roster, base_cfg, days=DAYS)
        cfg, roster, records = apply_plants(base_cfg, base_roster, plants)
        cards = run_set(cfg, roster, sla, calendar, SEED_BASE + k + 1)
        result = score(cards, records, team_skills)
        same = (result["found"], result["diagnosed"]) == (published[k]["found"], published[k]["diagnosed"])
        print(f"set {k + 1:2d}: found {result['found']} diagnosed {result['diagnosed']} "
              f"{'= published' if same else 'DIFFERS from blind.json'}", flush=True)
        if not same:
            raise SystemExit("blind set does not reproduce; refusing to write cards")
        sets.append({"set": k + 1, "plants": records, "details": result["details"], "cards": cards})

    results = json.loads((ROOT / "eval" / "results.json").read_text(encoding="utf-8"))
    main_world = {"cards": results["patterns"]["cards"],
                  "plants": json.loads((ROOT / "data" / "planted.json").read_text(encoding="utf-8"))["problems"]}
    OUT.write_text(json.dumps({"main": main_world, "blind": sets}, indent=1, default=str), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
