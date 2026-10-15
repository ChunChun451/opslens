"""Blind recall test: 20 fresh datasets, each with 3 problems of random type, place and size.

Run:  .venv/Scripts/python.exe eval/run_blind.py [n_sets]

For each set: clean floor + random plants (data/plant.py) → 42 days of tickets (new seed, no
text) → Baseline A history → the SAME pattern finder as on the main data → scored with the
SAME matcher (eval/recall.py). Also one CLEAN set with no plants: every card there is a false
alarm (or a real roster gap). Writes eval/parts/blind.json.

Why: 5/5 on problems we designed ourselves could be tuning. Problems drawn at random after
the finder was frozen cannot be.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.generate_ops import make_history, make_tickets  # noqa: E402
from data.plant import apply_plants, clean_config, clean_roster, random_plant_set  # noqa: E402
from eval.recall import score  # noqa: E402
from opslens.config import load_config  # noqa: E402
from opslens.ingest import add_calendar, add_timing, clean  # noqa: E402
from opslens.patterns import find_patterns  # noqa: E402
from opslens.policies import baseline_a  # noqa: E402
from opslens.simulate import MINUTES_PER_DAY, simulate  # noqa: E402
from opslens.world import agents_table, build_world, load_agents  # noqa: E402

DAYS = 42
SEED_BASE = 5000


def run_set(cfg: dict, roster: dict, sla: dict, calendar: dict, seed: int, days: int = DAYS) -> list[dict]:
    """Generate, simulate, ingest and run the pattern finder for one dataset. Returns cards."""
    cfg = {**cfg, "seed": seed, "days": days}
    tickets = make_tickets(cfg, bank=None)
    agents = load_agents(roster)
    agents_df = agents_table(agents)
    world = build_world(tickets, seed=seed, agents=agents, gen_cfg=cfg, sla_cfg=sla)
    result = simulate(world, baseline_a(), 0, days * MINUTES_PER_DAY)
    hist = make_history(tickets, result.tickets, agents_df, pd.Timestamp(calendar["start_date"]), sla)
    hist = add_calendar(add_timing(clean(hist), sla["sla_minutes"]), calendar["start_date"], calendar["splits"])
    team_skills = {t: v["skills"] for t, v in roster["teams"].items()}
    known = {e["day"] for e in calendar["known_events"]}
    first_weekday = pd.Timestamp(calendar["start_date"]).weekday()
    return find_patterns(hist, agents_df, team_skills, known, first_weekday)["cards"]


def main() -> int:
    n_sets = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    started = time.perf_counter()
    calendar = load_config("calendar")
    base_cfg = clean_config({**load_config("generator"), **calendar})
    base_roster = clean_roster(load_config("roster"))
    sla = load_config("sla")
    team_skills = {t: v["skills"] for t, v in base_roster["teams"].items()}
    rng = np.random.default_rng(SEED_BASE)

    clean_cards = run_set(base_cfg, base_roster, sla, calendar, SEED_BASE)
    print(f"clean set (no plants): {len(clean_cards)} cards: " + "; ".join(c["title"] for c in clean_cards))

    sets, by_type = [], {}
    for k in range(n_sets):
        plants = random_plant_set(rng, base_roster, base_cfg, days=DAYS)
        cfg, roster, records = apply_plants(base_cfg, base_roster, plants)
        cards = run_set(cfg, roster, sla, calendar, SEED_BASE + k + 1)
        result = score(cards, records, team_skills)
        for d, rec in zip(result["details"], records):
            stats = by_type.setdefault(rec["cause_type"], {"planted": 0, "found": 0, "diagnosed": 0})
            stats["planted"] += 1
            stats["found"] += int(d["found"])
            stats["diagnosed"] += int(d["diagnosed"])
        sets.append({"set": k + 1, "plants": records, "found": result["found"], "diagnosed": result["diagnosed"],
                     "unmatched": [c["title"] for c in result["unmatched"]], "details": result["details"]})
        missed = [r["name"] for r, d in zip(records, result["details"]) if not d["found"]]
        print(f"set {k + 1:2d}: found {result['found']}/3 diagnosed {result['diagnosed']}/3, "
              f"unplanted cards {len(result['unmatched'])}" + (f"  missed: {missed}" if missed else ""), flush=True)

    planted = sum(s["planted"] for s in by_type.values())
    found = sum(s["found"] for s in by_type.values())
    diagnosed = sum(s["diagnosed"] for s in by_type.values())
    summary = {
        "sets": n_sets, "planted": planted, "found": found, "diagnosed": diagnosed,
        "found_pct": 100.0 * found / planted, "diagnosed_pct": 100.0 * diagnosed / planted,
        "unplanted_cards_per_set": float(np.mean([len(s["unmatched"]) for s in sets])),
        "clean_set_cards": len(clean_cards), "by_type": by_type,
    }
    print(json.dumps({k: v for k, v in summary.items() if k != "by_type"}))
    print("by type:", by_type)
    out = ROOT / "eval" / "parts"
    out.mkdir(parents=True, exist_ok=True)
    (out / "blind.json").write_text(json.dumps({"summary": summary, "sets": sets,
                                                "clean_set_cards": [c["title"] for c in clean_cards]},
                                               indent=1, default=str), encoding="utf-8")
    print(f"wrote eval/parts/blind.json ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
