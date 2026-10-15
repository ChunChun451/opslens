"""Write eval/fixture_results.json (invented numbers, same shape as results.json) and
eval/results.schema.json (the JSON Schema of results.json).

Why: the dashboard is built in parallel with the engine. It needs data of the right shape
before the real numbers exist. Every number here is INVENTED; the file says so in
`meta.fixture = true`, the UI shows a red FIXTURE banner, and `make demo` refuses it.
Example tickets are real rows from data/generated/history.csv (texts masked).

Run:  .venv/Scripts/python.exe eval/make_fixture.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens.privacy import mask_pii  # noqa: E402
from opslens.results_schema import Results  # noqa: E402

KPI_NAMES = [
    "turnaround.breach_pct", "turnaround.mean_resolution_min", "turnaround.p90_resolution_min",
    "turnaround.mean_wait_min", "turnaround.max_backlog", "productivity.tickets_per_agent_hour",
    "productivity.transfers_per_100", "productivity.busy_agent_hours", "quality.reopen_rate_pct",
    "quality.p99_wait_min", "quality.mean_utilisation", "quality.load_fairness_std",
]
FAKE_KPIS = {
    "baseline_a": [13.0, 80.0, 185.0, 64.0, 227.0, 5.3, 4.7, 3100.0, 3.9, 816.0, 0.87, 0.12],
    "baseline_b": [6.8, 85.0, 198.0, 68.0, 234.0, 5.3, 4.6, 3100.0, 3.9, 1007.0, 0.87, 0.12],
    "opslens":    [4.1, 61.0, 140.0, 47.0, 160.0, 5.6, 1.9, 2950.0, 3.6, 420.0, 0.83, 0.08],
}
LABELS = {"baseline_a": "Baseline A (FIFO)", "baseline_b": "Baseline B (priority)", "opslens": "OpsLens"}


def examples(history: pd.DataFrame, mask: pd.Series, n: int = 3) -> list[dict]:
    rows = history[mask].head(n)
    return [
        {"ticket_id": r.ticket_id, "created_at": str(r.created_at)[:16], "text": mask_pii(str(r.text)).text,
         "wait_min": round(float(r.wait_min), 1), "breached": bool(r.breached)}
        for r in rows.itertuples()
    ]


def build(history: pd.DataFrame) -> dict:
    rng = np.random.default_rng(0)
    policies = {}
    for key, values in FAKE_KPIS.items():
        kpis = {name: {"mean": v, "std": round(abs(v) * 0.08, 3)} for name, v in zip(KPI_NAMES, values)}
        per_seed = [{name: round(v * (1 + rng.normal(0, 0.05)), 3) for name, v in zip(KPI_NAMES, values)} for _ in range(5)]
        policies[key] = {"key": key, "label": LABELS[key], "kpis": kpis, "per_seed": per_seed}
    comparisons = [
        {"policy": "opslens", "baseline": base, "kpi": kpi, "mean_diff": d, "ci_low": d - 0.8, "ci_high": d + 0.8, "n": 5}
        for base, kpi, d in [("baseline_a", "turnaround.breach_pct", -8.9), ("baseline_b", "turnaround.breach_pct", -2.7),
                             ("baseline_a", "turnaround.p90_resolution_min", -45.0), ("baseline_b", "turnaround.p90_resolution_min", -58.0)]
    ]
    steps = 24  # 18:00-23:45 every 15 min
    times = [f"{18 + i // 4:02d}:{(i % 4) * 15:02d}" for i in range(steps)]
    curve = np.sin(np.linspace(0, np.pi, steps))
    replay = {
        "title": "Saturday 17 Oct, 18:00-23:59 (FIXTURE)", "day": 48, "start_minute": 47 * 1440 + 18 * 60,
        "step_min": 15.0, "times": times,
        "series": {
            "baseline_a": {"waiting": [int(40 + 140 * c) for c in curve], "breached_cum": [int(3 * i * 1.6) for i in range(steps)]},
            "baseline_b": {"waiting": [int(40 + 130 * c) for c in curve], "breached_cum": [int(3 * i * 0.9) for i in range(steps)]},
            "opslens": {"waiting": [int(30 + 80 * c) for c in curve], "breached_cum": [int(3 * i * 0.45) for i in range(steps)]},
        },
    }
    h = history
    cards = [
        {"id": "C1", "title": "Hindi payments & refunds wait 6x longer", "cause_type": "skill_gap",
         "metric": "mean wait (min)", "value": 302.0, "comparison_value": 47.0,
         "comparison_text": "Hindi refund/payment tickets wait 302 min vs 47 min for English ones (FIXTURE)",
         "segment": {"language": "hi", "category": ["refund", "payment_failure"]}, "affected_tickets": 3900,
         "affected_share_pct": 5.5, "strength": 9.1, "not_explained_by": "volume is normal; only 3 agents have both skills",
         "examples": examples(h, (h.language == "hi") & (h.final_category == "refund") & (h.wait_min > 200)),
         "recommendation": "Cross-train 2 Hindi-speaking agents on refunds; route Hindi refunds to them first"},
        {"id": "C2", "title": "Team C overloaded at weekend dinner", "cause_type": "capacity",
         "metric": "utilisation (rho)", "value": 1.4, "comparison_value": 0.8,
         "comparison_text": "Sat/Sun 19-23h: rho 1.40 vs 0.80 on weekdays (FIXTURE)",
         "segment": {"team": "C", "weekday": [5, 6], "hour": [19, 20, 21, 22]}, "affected_tickets": 1500,
         "affected_share_pct": 2.1, "strength": 6.2, "not_explained_by": "every weekend, not a one-off",
         "examples": examples(h, (h.final_category == "missing_item") & (h.wait_min > 120)),
         "recommendation": "Move 3 cross-trained Team D agents to Team C queue, Sat-Sun 19:00-23:00"},
        {"id": "C3", "title": "Payment-failure spike on 17 Sep", "cause_type": "volume_spike",
         "metric": "tickets per hour", "value": 96.0, "comparison_value": 22.0,
         "comparison_text": "96 payment-failure tickets/h vs 22 usual (robust z 8.4) (FIXTURE)",
         "segment": {"category": "payment_failure", "day": 18}, "affected_tickets": 420, "affected_share_pct": 0.6,
         "strength": 8.4, "not_explained_by": "not a known sale day",
         "examples": examples(h, (h.final_category == "payment_failure")), "recommendation": "Check the app release of 17 Sep"},
        {"id": "C4", "title": "Wrong items from restaurant cluster 17", "cause_type": "partner_issue",
         "metric": "share of wrong-item tickets", "value": 5.1, "comparison_value": 2.0,
         "comparison_text": "Cluster 17 sends 5.1% of wrong-item tickets but only 2.0% of all tickets (FIXTURE)",
         "segment": {"category": "wrong_item", "restaurant_cluster_id": 17}, "affected_tickets": 380,
         "affected_share_pct": 0.5, "strength": 5.0,
         "examples": examples(h, (h.final_category == "wrong_item") & (h.restaurant_cluster_id == 17)),
         "recommendation": "Raise with the partner team: packing checks at cluster 17 kitchens"},
        {"id": "C5", "title": "Phone (IVR) tickets are transferred 5x more", "cause_type": "process",
         "metric": "transfers per 100 tickets", "value": 12.8, "comparison_value": 2.6,
         "comparison_text": "12.8 transfers per 100 call tickets vs 2.6 for chat (FIXTURE)",
         "segment": {"channel": "call"}, "affected_tickets": 14000, "affected_share_pct": 20.0, "strength": 7.7,
         "examples": examples(h, (h.channel == "call") & (h.transfers > 0)),
         "recommendation": "Route call tickets by text classification, not the IVR menu choice"},
    ]
    start = datetime(2026, 10, 26, 0, 0)
    horizon = []
    for hour in range(48):
        for team, scale in (("A", 1.0), ("B", 1.3), ("C", 1.0), ("D", 1.25)):
            hod = hour % 24
            demand = scale * (0.3 + 4.0 * np.exp(-((hod - 20.5) ** 2) / 6) + 3.0 * np.exp(-((hod - 13) ** 2) / 4))
            cap = 4.5 * scale if 9 <= hod <= 23 else 1.2
            horizon.append({"time": (start + timedelta(hours=hour)).isoformat(timespec="minutes"), "team": team,
                            "demand_hours": round(demand, 2), "lo80": round(demand * 0.8, 2), "hi80": round(demand * 1.2, 2),
                            "capacity_hours": cap})
    at_risk = []
    for i, r in enumerate(h[h.breached & (h.priority == "P1")].head(10).itertuples()):
        at_risk.append({
            "ticket_id": r.ticket_id, "created_at": str(r.created_at)[:16], "category": r.final_category,
            "priority": r.priority, "language": r.language, "text": mask_pii(str(r.text)).text,
            "probability": round(0.92 - 0.04 * i, 2), "minutes_to_sla": float(12 + 4 * i),
            "reasons": [{"feature": "queue_length_skilled", "contribution": 0.21, "text": "18 tickets ahead in queue (+0.21)"},
                        {"feature": "language", "contribution": 0.12, "text": f"language {r.language} (+0.12)"},
                        {"feature": "hour", "contribution": 0.07, "text": "dinner peak (+0.07)"}],
            "action": "assign to a free skilled agent now", "probability_after_action": round(0.35 - 0.02 * i, 2),
        })
    return {
        "meta": {"fixture": True, "generated_at": datetime.now().isoformat(timespec="seconds"), "git_commit": "",
                 "data_seed": 2026, "n_tickets": int(len(h)), "start_date": "2026-08-31", "days": 56,
                 "train_days": [1, 35], "validation_days": [36, 42], "test_days": [43, 56], "run_seconds": 0.0},
        "sim": {"seeds": [1, 2, 3, 4, 5], "test_days": [43, 56], "policies": policies, "comparisons": comparisons, "replay": replay},
        "patterns": {"cards": cards,
                     "recall": {"planted": 6, "found": 6, "false_alarms": 1, "details": [{"id": c["id"], "found": True} for c in cards]},
                     "blind_recall": {"sets": 20, "found_pct": 90.0, "false_alarms_mean": 0.4},
                     "live_detection_latency_min": 45.0,
                     "delay_decomposition": {t: {"waiting": w, "handling": 9.0, "transfer": tr, "reopen": 2.0}
                                             for t, w, tr in (("A", 55.0, 3.0), ("B", 95.0, 2.0), ("C", 48.0, 4.0), ("D", 30.0, 2.5))}},
        "classification": {"accuracy_local": 0.91, "accuracy_cascade": 0.94, "accuracy_llm_sample": 0.95, "pct_sent_to_llm": 8.0,
                           "cost_per_million_tickets_usd": 0.0, "transfers_avoided_per_100": 2.8, "confusion": {},
                           "clusters": [{"category": "refund", "name": "Refund promised but not received (FIXTURE)",
                                         "root_cause": "refund stuck after cancellation", "size": 1200,
                                         "examples": ["refund not received yet", "cancelled but money not returned"]}]},
        "forecast": {"wape_model": 0.14, "wape_naive": 0.22, "coverage_80": 0.81, "coverage_90": 0.9, "horizon": horizon,
                     "bottlenecks": [{"team": "C", "start": "2026-10-31T19:00", "end": "2026-10-31T23:00", "peak_rho": 1.4,
                                      "text": "Team C short by ~2 agents, Sat 19:00-23:00 (FIXTURE)"}]},
        "risk": {"auc": 0.86, "pr_auc": 0.52, "top10_precision": 0.61, "brier": 0.07, "base_rate": 0.13,
                 "calibration": [{"predicted": p, "observed": round(p * 0.95, 3), "n": 1000} for p in (0.05, 0.15, 0.3, 0.5, 0.7, 0.9)],
                 "at_risk": at_risk, "realdata_auc": 0.78, "realdata_n": 24918},
        "recommendations": {
            "assignments": [{"ticket_id": t["ticket_id"], "agent_id": "B01", "agent_name": "Kavita D.",
                             "reason": "Hindi refund, 91% breach risk, Kavita is one of 3 agents with both skills (FIXTURE)",
                             "value": 2.4} for t in at_risk[:5]],
            "staffing_moves": [{"text": "Move Chetan G., Esha P., Gita K. (Team D, trained on missing/wrong items) to the Team C queue, Sat-Sun 19:00-23:00 (FIXTURE)",
                                "team_from": "D", "team_to": "C", "agents": ["D06", "D07", "D09"], "when": "Sat-Sun 19:00-23:00",
                                "expected_effect": {"turnaround.breach_pct": -1.2}}],
        },
        "ablations": [{"key": k, "label": lbl, "breach_pct": {"mean": v, "std": 0.3}, "p90_resolution_min": {"mean": 150.0, "std": 8.0},
                       "delta_breach_vs_full": round(v - 4.1, 2)}
                      for k, lbl, v in (("full", "OpsLens (full)", 4.1), ("no_staffing", "without staffing", 4.9),
                                        ("no_risk", "without risk scores", 5.8), ("no_optimizer", "risk-sorted greedy", 5.2),
                                        ("no_classifier", "without classifier", 5.5), ("no_scarcity", "without scarcity cost", 4.7))],
        "sensitivity": [{"gold_weight": w, "breach_pct": b, "gold_breach_pct": g} for w, b, g in ((1.0, 4.0, 4.3), (1.5, 4.1, 3.2), (2.0, 4.4, 2.5))],
        "stress": [{"scenario": s, "baseline_a": a, "baseline_b": b, "opslens": o}
                   for s, a, b, o in (("+25% volume", 31.0, 19.0, 11.0), ("10% absent", 18.0, 9.5, 6.0), ("surprise spike day 47", 22.0, 12.0, 7.0))],
        "speed": {"pipeline_seconds": 210.0, "optimizer_ms_median": 3.1, "optimizer_ms_max": 48.0,
                  "scale_test": {"tickets": 5000, "agents": 500, "seconds": 0.9}},
        "brief": {"text": "FIXTURE brief: breaches would fall from 13.0% to 4.1% on the test days.", "source": "template",
                  "numbers_used": ["sim.policies.baseline_a.kpis.turnaround.breach_pct.mean"]},
    }


def main() -> int:
    history = pd.read_csv(ROOT / "data" / "generated" / "history.csv")
    data = build(history)
    Results.model_validate(data)  # fails loudly if the fixture drifts from the schema
    (ROOT / "eval" / "fixture_results.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    schema = Results.model_json_schema()
    (ROOT / "eval" / "results.schema.json").write_text(json.dumps(schema, indent=1), encoding="utf-8")
    print("wrote eval/fixture_results.json and eval/results.schema.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
