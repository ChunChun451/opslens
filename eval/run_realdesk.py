"""The real public service desk (UCI ServiceNow log): every screen's numbers for the real-data world.

Run:  .venv/Scripts/python.exe eval/run_realdesk.py   -> eval/parts/realdesk.json
Learning: first 70% of incidents by opening time (choices on its last 20%); test: the last 30%.
See opslens/realdesk.py for what each part does and why; Plan v4 adds (docs/explain/realdesk.md):
- fasttrack            W3: whose pick of 10/20/30% fast-tracked incidents saves more missed deadlines
- impact               W9: the problem statement's three headings, from the fast-track benchmark
- replication          W4a: cards R1-R3 found on the learning months, re-measured on the test months
- blind_plants         W4b: 20 random plant sets in the real test weeks (eval/realdesk_plants.py)
- forecast_candidates  W7c: 3 forecasts, the check weeks pick one, the test weeks report all
- alerts               W7b: "more new incidents than the team usually closes", scored on test team-days
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

from eval import realdesk_plants as P  # noqa: E402
from opslens import realdesk as R  # noqa: E402
from opslens import realdesk_fasttrack as FT  # noqa: E402
from opslens import realdesk_watch as W  # noqa: E402
from opslens.adapters.uci_incidents import load_uci  # noqa: E402

PARTS = ROOT / "eval" / "parts"


def blind_plants(incidents: pd.DataFrame, events: pd.DataFrame, check: np.ndarray) -> dict:
    """W4b: the detectors on the clean real test weeks (every alert is a false alarm, or a real
    problem of the desk we cannot tell apart), then on 20 copies with three random plants each."""
    table = W.as_of_table(incidents, events)
    clean = W.watch(table, P.FIRST_DAY, P.LAST_DAY)
    check_days = incidents.loc[check, "created_at"]
    clean_check = W.watch(table, str(check_days.min().date()), str((check_days.max() - pd.Timedelta(days=1)).date()))
    sets = []
    for seed in P.SEEDS:
        rng = np.random.default_rng(seed)
        plants = P.random_plant_set(rng, table)
        alerts = W.watch(P.apply_plants(table, plants, rng), P.FIRST_DAY, P.LAST_DAY)
        scored, unmatched = P.score_set(alerts, plants)
        sets.append({"seed": seed, "plants": scored, "alerts": int(len(alerts)), "unmatched_alerts": unmatched})
    plants = [p for s in sets for p in s["plants"]]
    days = (pd.Timestamp(P.LAST_DAY) - pd.Timestamp(P.FIRST_DAY)).days + 1
    by_type = {}
    for kind in ("spike", "slowdown", "bounce"):
        mine = [p for p in plants if p["type"] == kind]
        delays = [p["delay_days"] for p in mine if p["found"]]
        by_type[kind] = {"found": sum(p["found"] for p in mine), "of": len(mine),
                         "median_delay_days": float(np.median(delays)) if delays else None}
    delays = [p["delay_days"] for p in plants if p["found"]]
    return {
        "window": [P.FIRST_DAY, P.LAST_DAY], "days": days, "sets": len(sets), "plants": len(plants),
        "found": sum(p["found"] for p in plants), "recall_pct": 100.0 * sum(p["found"] for p in plants) / len(plants),
        "by_type": by_type, "median_delay_days": float(np.median(delays)) if delays else None,
        "clean_alerts": int(len(clean)), "false_alarms_per_30_days": 30.0 * len(clean) / days,
        "clean_alert_list": [{"type": r.type, "segment": r.segment, "known_on": str(r.known_on.date()), "z": r.z}
                             for r in clean.itertuples()],
        "clean_check_alerts": int(len(clean_check)),
        "unmatched_alerts_per_set": float(np.mean([s["unmatched_alerts"] for s in sets])),
        "ranges": {"spike_multiplier": P.SPIKE_MULTIPLIER, "slow_factor": P.SLOW_FACTOR, "bounce_share": P.BOUNCE_SHARE,
                   "window_days": P.WINDOW_DAYS, "min_weekday_median": P.MIN_WEEKDAY_MEDIAN, "seeds": [P.SEEDS[0], P.SEEDS[-1]],
                   "match_slack_days": P.MATCH_SLACK_DAYS},
        "detector": {"z": W.Z, "window_days": W.WINDOW_DAYS, "min_excess_count": W.MIN_EXCESS_COUNT,
                     "min_day_count": W.MIN_DAY_COUNT, "min_excess_share": W.MIN_EXCESS_SHARE},
        "set_list": sets,
    }


def main() -> int:
    started = time.perf_counter()
    incidents, events = load_uci()
    learn, check, test = R.masks(incidents)
    history = learn | check
    states = R.time_in_states(events)
    hist = incidents[history]
    summary = {"source": "UCI ServiceNow incident log (CC BY 4.0), a real company's IT service desk",
               "incidents": int(len(incidents)), "events": int(len(events)), "teams": int(incidents["resolved_by_team"].nunique()),
               "agents": int(events["assigned_to"].nunique()), "missed_sla_pct": float(incidents["breached"].mean() * 100),
               "passed_between_teams_pct": float((incidents["transfers"] > 0).mean() * 100),
               "median_resolution_h": float(incidents["resolution_min"].median() / 60),
               "learning_period": [str(hist["created_at"].min().date()), str(hist["created_at"].max().date())],
               "test_period": [str(incidents.loc[test, "created_at"].min().date()), str(incidents.loc[test, "created_at"].max().date())],
               "test_incidents": int(test.sum())}
    total = states.reindex(hist["ticket_id"]).fillna(0).sum()
    summary["open_time_share_pct"] = {k: float(v) for k, v in (total / total.sum() * 100).round(1).items()}
    model = R.train_early_warning(incidents, events)
    daily = R.team_daily(incidents)
    cards = R.problem_cards(incidents, states, history)
    out = {"summary": summary, "cards": cards,
           "early_warning": R.early_warning(incidents, events, model), "forecast": R.team_forecast(incidents, daily=daily),
           "routing": R.routing_hints(incidents, events)}

    # ---- Plan v4 (W3, W4, W7 real desk, W9) ----
    p_test = model["booster"].predict(model["X"][model["test"]])
    out["fasttrack"] = FT.fasttrack_benchmark(incidents, events, states, model["feats"], p_test, R.RISK_CATS, R.RISK_NUMS,
                                              learn, check, test)
    out["impact"] = FT.impact(out["fasttrack"])
    out["replication"] = R.replicate_cards(incidents, states, cards, history, test)
    for row, c in zip(out["replication"]["cards"], cards):  # same definitions as the cards themselves
        assert round(row["learning"]["value"], 1) == c["value"] and round(row["learning"]["comparison"], 1) == c["comparison_value"]
    out["forecast_candidates"] = R.forecast_candidates(daily)
    out["alerts"] = R.bottleneck_alerts(daily, out["forecast_candidates"]["chosen_on_check"])
    out["blind_plants"] = blind_plants(incidents, events, check)
    out["seconds"] = time.perf_counter() - started
    report(out)
    (PARTS / "realdesk.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"wrote eval/parts/realdesk.json ({out['seconds']:.0f}s)")
    return 0


def report(out: dict) -> None:
    """Short printed summary (never the whole JSON)."""
    ew, rt, fc = out["early_warning"], out["routing"]["test"], out["forecast"]
    print(f"cards: {[c['title'] for c in out['cards']]}")
    print(f"early warning: AUC {ew['auc_opslens']:.3f} vs priority {ew['auc_priority']:.3f}; missed SLAs caught in top 20%: "
          f"{ew['caught_top20_opslens_pct']:.1f}% vs {ew['caught_top20_priority_pct']:.1f}%")
    print(f"forecast: check weeks chose {fc['chosen_on_check_weeks']}; test WAPE learned {fc['wape_learned']:.3f} vs same day last week {fc['wape_same_day_last_week']:.3f}; "
          f"{len(fc['bottlenecks'])} bottleneck team-days next week")
    print(f"routing (sure >= {out['routing']['threshold']}): desk right {rt['desk_right_pct']:.1f}%, OpsLens all {rt['opslens_all_right_pct']:.1f}%; "
          f"sure on {rt['sure_share_pct']:.0f}%: OpsLens {rt['opslens_sure_right_pct']:.1f}% vs desk {rt['desk_on_same_right_pct']:.1f}%, "
          f"net +{rt['net_first_time_right']} ({rt['fixed']} fixed, {rt['made_wrong']} made wrong)")
    ft = out["fasttrack"]
    dr, pop = ft["deadline_rule"], ft["population"]
    print(f"fast-track: rule '{dr['chosen_on_check']}' limits {dr['limits_h']} match {dr['match_pct']}; "
          f"{pop['test_incidents']} test incidents, {pop['missed_by_rule']} missed by the rule ({pop['missed_by_rule_pct']:.1f}%)")
    print(f"  ceiling: {ft['ceiling']['saved']} saved ({ft['ceiling']['saved_pct_of_misses']:.1f}% of misses)")
    for b in FT.BUDGETS:
        row = ft["results"][str(b)]
        print(f"  {b}%: " + ", ".join(f"{p} {row[p]['saved']} [{row[p]['ci_low']:.0f}, {row[p]['ci_high']:.0f}]" for p in FT.PICKERS))
    r = ft["rule"]
    print(f"  rule at {r['budget']}%: OpsLens − {r['best_other']} = {r['diff']} [{r['ci_low']:.1f}, {r['ci_high']:.1f}] → "
          f"{'PASSED' if r['passed'] else 'NOT passed'}; busy weeks ahead {ft['busy_weeks_opslens_ahead_of_best_other']} of {pop['busy_weeks']}")
    rep = out["replication"]
    print(f"replication: {rep['replicated']} of {rep['of']}: " + "; ".join(
        f"{c['id']} gap {c['learning']['gap']:.1f} → {c['test']['gap']:.1f} [{c['test']['ci_low']:.1f}, {c['test']['ci_high']:.1f}]"
        for c in rep["cards"]))
    fcand = out["forecast_candidates"]
    print(f"forecast candidates: check {fcand['wape_check']}, chose {fcand['chosen_on_check']}; test {fcand['wape_test']}")
    al = out["alerts"]["scores"]
    print("bottleneck alerts: " + "; ".join(f"{k} P {v['precision_pct']:.0f}% R {v['recall_pct']:.0f}% ({v['alerts']} alerts)" for k, v in al.items()))
    bp = out["blind_plants"]
    print(f"blind plants: {bp['found']}/{bp['plants']} found ({bp['recall_pct']:.0f}%), by type {bp['by_type']}; "
          f"clean false alarms {bp['clean_alerts']} in {bp['days']} days ({bp['false_alarms_per_30_days']:.1f} per 30 days); "
          f"median delay {bp['median_delay_days']} days")


if __name__ == "__main__":
    raise SystemExit(main())
