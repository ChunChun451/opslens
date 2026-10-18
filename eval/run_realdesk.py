"""The real public service desk (UCI ServiceNow log): every screen's numbers for the real-data world.

Run:  .venv/Scripts/python.exe eval/run_realdesk.py   -> eval/parts/realdesk.json
Learning: first 70% of incidents by opening time (choices on its last 20%); test: the last 30%.
See opslens/realdesk.py for what each part does and why.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens import realdesk as R  # noqa: E402
from opslens.adapters.uci_incidents import load_uci  # noqa: E402

PARTS = ROOT / "eval" / "parts"


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
    out = {"summary": summary, "cards": R.problem_cards(incidents, states, history),
           "early_warning": R.early_warning(incidents, events), "forecast": R.team_forecast(incidents),
           "routing": R.routing_hints(incidents, events), "seconds": time.perf_counter() - started}
    ew, rt, fc = out["early_warning"], out["routing"]["test"], out["forecast"]
    print(f"cards: {[c['title'] for c in out['cards']]}")
    print(f"early warning: AUC {ew['auc_opslens']:.3f} vs priority {ew['auc_priority']:.3f}; missed SLAs caught in top 20%: "
          f"{ew['caught_top20_opslens_pct']:.1f}% vs {ew['caught_top20_priority_pct']:.1f}%")
    print(f"forecast: check weeks chose {fc['chosen_on_check_weeks']}; test WAPE learned {fc['wape_learned']:.3f} vs same day last week {fc['wape_same_day_last_week']:.3f}; "
          f"{len(fc['bottlenecks'])} bottleneck team-days next week")
    print(f"routing (sure >= {out['routing']['threshold']}): desk right {rt['desk_right_pct']:.1f}%, OpsLens all {rt['opslens_all_right_pct']:.1f}%; "
          f"sure on {rt['sure_share_pct']:.0f}%: OpsLens {rt['opslens_sure_right_pct']:.1f}% vs desk {rt['desk_on_same_right_pct']:.1f}%, "
          f"net +{rt['net_first_time_right']} ({rt['fixed']} fixed, {rt['made_wrong']} made wrong)")
    (PARTS / "realdesk.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"wrote eval/parts/realdesk.json ({out['seconds']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
