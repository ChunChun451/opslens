"""Fix-at-source playbooks, measured: replay the held-out test days with each playbook in place.

Run:  .venv/Scripts/python.exe eval/run_playbooks.py

- The playbooks come from the evidence cards found on HISTORY days (eval/parts/patterns.json)
  and the roster; the status banner reacts to the live spike alerts OpsLens raised on the test
  days (the same alerts reported in M4, false alerts included). Nothing reads data/planted.json.
- Each playbook is applied alone, then all together, on test days 43-56 with day 42 as warm-up,
  under Baseline B (today's practice) and OpsLens, seeds 1-5, same tickets and luck as M7.
  Removed tickets are the same for every policy and seed, so differences stay paired.
- Main measures: breaches (count of customers who missed the SLA), tickets prevented, transfers,
  agent-hours of work; paired 95% CI against the same policy without the playbook.
- Every ASSUMPTION in config/playbooks.yaml is re-run at its low and high value (3 seeds).
Writes eval/parts/playbooks.json.

Example: "kitchen order-check for cluster 17" removes 67 wrong-item tickets on the test days;
the run shows how many breaches and agent-hours that saves under each policy.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from opslens.config import load_config  # noqa: E402
from opslens.impact import mean_std, paired_ci  # noqa: E402
from opslens.playbooks import draft_message, playbooks_from_cards  # noqa: E402
from opslens.world import load_agents  # noqa: E402
from run_opslens import run_jobs  # noqa: E402

FIRST, LAST = 43, 56
SEEDS = [1, 2, 3, 4, 5]
SENS_SEEDS = [1, 2, 3]
POLICIES = ["baseline_b", "opslens"]
ASSUMPTION_KEY = {"partner_fix": "fix_share", "status_banner": "deflect_share", "self_serve": "uptake"}


def counts(k: dict) -> dict:
    """Per-run totals from the KPI percentages."""
    n = k["tickets"]
    return {"tickets": n, "breaches": k["turnaround.breach_pct"] * n / 100.0,
            "transfers": k["productivity.transfers_per_100"] * n / 100.0,
            "agent_hours": k["productivity.busy_agent_hours"], "breach_pct": k["turnaround.breach_pct"],
            "p90_resolution_min": k["turnaround.p90_resolution_min"]}


def job(policy: str, seed: int, scenarios: list[dict], alerts: list[dict], tag: str) -> dict:
    return {"policy": policy, "seed": seed, "first_day": FIRST, "last_day": LAST, "staffing": policy == "opslens",
            "scenarios": scenarios, "alerts": alerts, "tag": tag}


def summarise(runs: list[dict], base: dict[tuple, dict]) -> dict:
    """Mean ± std of totals, and paired differences vs the same policy without playbooks."""
    out = {}
    for policy in POLICIES:
        rs = sorted([r for r in runs if r["job"]["policy"] == policy], key=lambda r: r["job"]["seed"])
        if not rs:
            continue
        c = [counts(r["kpis"]) for r in rs]
        b = [counts(base[(policy, r["job"]["seed"])]) for r in rs]
        out[policy] = {
            "totals": {k: dict(zip(("mean", "std"), mean_std([x[k] for x in c]))) for k in c[0]},
            "vs_without": {k: paired_ci([x[k] for x in c], [y[k] for y in b]) for k in c[0]},
            "seeds": [r["job"]["seed"] for r in rs],
        }
    return out


def llm_client():
    try:
        from opslens.llm.client import build_client
        return build_client()
    except Exception:  # no keys / no network: the template text is always there
        return None


def redraft_messages() -> int:
    """`--messages`: re-write only the LLM messages (no simulation), e.g. after a prompt change."""
    path = ROOT / "eval" / "parts" / "playbooks.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    books, _ = make_playbooks()
    client = llm_client()
    by_id = {pb.id: pb for pb in books}
    for entry in data["playbooks"]:
        entry["message"] = draft_message(by_id[entry["id"]], client)
        print(f"{entry['id']:8s} {entry['message']['source']:8s} {entry['message']['text']}")
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return 0


def make_playbooks() -> tuple[list, list[dict]]:
    patterns = json.loads((ROOT / "eval" / "parts" / "patterns.json").read_text(encoding="utf-8"))
    alerts = [{"minute": a["minute"], "category": a["category"]} for a in patterns["live_alerts"] if not a["explained"]]
    roster = load_config("roster")
    team_skills = {team: t["skills"] for team, t in roster["teams"].items()}
    return playbooks_from_cards(patterns["cards"], load_agents(), team_skills, load_config("playbooks")), alerts


def main() -> int:
    if "--messages" in sys.argv:
        return redraft_messages()
    started = time.perf_counter()
    patterns = json.loads((ROOT / "eval" / "parts" / "patterns.json").read_text(encoding="utf-8"))
    alerts = [{"minute": a["minute"], "category": a["category"]} for a in patterns["live_alerts"] if not a["explained"]]
    roster = load_config("roster")
    team_skills = {team: t["skills"] for team, t in roster["teams"].items()}
    cfg = load_config("playbooks")
    books = playbooks_from_cards(patterns["cards"], load_agents(), team_skills, cfg)
    for pb in books:
        print(f"{pb.id:10s} {pb.title}  ->  {pb.scenario}")

    jobs = [job(p, s, [], alerts, "base") for p in POLICIES for s in SEEDS]
    for pb in books:
        jobs += [job(p, s, [pb.scenario], alerts, pb.id) for p in POLICIES for s in SEEDS]
    jobs += [job(p, s, [pb.scenario for pb in books], alerts, "all") for p in POLICIES for s in SEEDS]
    sens_cfg = cfg.get("sensitivity", {})
    for pb in books:
        key = ASSUMPTION_KEY.get(pb.scenario["kind"])
        cfg_key = {"fix_share": "partner_fix_share", "deflect_share": "banner_deflect_share", "uptake": "self_serve_uptake"}.get(key)
        for value in sens_cfg.get(cfg_key, []):
            spec = {**pb.scenario, key: value}
            jobs += [job(p, s, [spec], alerts, f"{pb.id}@{value}") for p in POLICIES for s in SENS_SEEDS]
    print(f"{len(jobs)} runs ...", flush=True)
    results = run_jobs(jobs, workers=8)
    by_tag: dict[str, list[dict]] = {}
    for r in results:
        by_tag.setdefault(r["job"]["tag"], []).append(r)
    base = {(r["job"]["policy"], r["job"]["seed"]): r["kpis"] for r in by_tag["base"]}

    client = llm_client()
    out_books = []
    for pb in books:
        entry = {k: v for k, v in dataclasses.asdict(pb).items() if k != "facts"}
        entry["message"] = draft_message(pb, client)
        entry["effect"] = summarise(by_tag[pb.id], base)
        entry["sensitivity"] = {tag.split("@")[1]: summarise(rs, base) for tag, rs in by_tag.items()
                                if tag.startswith(pb.id + "@")}
        out_books.append(entry)
        for p in POLICIES:
            d = entry["effect"][p]["vs_without"]
            print(f"{pb.id:10s} {p:11s} tickets {d['tickets']['mean_diff']:+7.0f}  breaches {d['breaches']['mean_diff']:+7.1f} "
                  f"[{d['breaches']['ci_low']:+.1f}, {d['breaches']['ci_high']:+.1f}]  transfers {d['transfers']['mean_diff']:+6.0f}  "
                  f"agent-hours {d['agent_hours']['mean_diff']:+6.1f}")
    combined = summarise(by_tag["all"], base)
    # Today's floor (Baseline B, no playbooks) vs OpsLens with every playbook.
    ops_all = sorted(by_tag["all"], key=lambda r: r["job"]["seed"])
    ops_all = [counts(r["kpis"]) for r in ops_all if r["job"]["policy"] == "opslens"]
    b_today = [counts(base[("baseline_b", s)]) for s in SEEDS]
    headline = {k: paired_ci([x[k] for x in ops_all], [y[k] for y in b_today]) for k in ops_all[0]}
    base_totals = {p: {k: dict(zip(("mean", "std"), mean_std([counts(base[(p, s)])[k] for s in SEEDS])))
                       for k in counts(base[(p, SEEDS[0])])} for p in POLICIES}
    for p in POLICIES:
        d = combined[p]["vs_without"]["breaches"]
        print(f"all playbooks {p:11s} breaches {d['mean_diff']:+.1f} [{d['ci_low']:+.1f}, {d['ci_high']:+.1f}]")
    h = headline["breaches"]
    print(f"OpsLens + all playbooks vs Baseline B today: breaches {h['mean_diff']:+.1f} [{h['ci_low']:+.1f}, {h['ci_high']:+.1f}]")
    (ROOT / "eval" / "parts" / "playbooks.json").write_text(json.dumps({
        "test_days": [FIRST, LAST], "seeds": SEEDS, "sensitivity_seeds": SENS_SEEDS, "alerts_used": alerts,
        "config": cfg, "base": base_totals, "playbooks": out_books, "all": combined,
        "opslens_all_vs_baseline_b": headline,
    }, indent=1), encoding="utf-8")
    print(f"wrote eval/parts/playbooks.json ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
