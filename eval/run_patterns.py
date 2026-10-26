from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.recall import score
from opslens.config import load_config
from opslens.ingest import load_history
from opslens.patterns import find_patterns, label_frame, live_alerts, team_rho

PARTS = ROOT / "eval" / "parts"


def replicates(card: dict, test: pd.DataFrame, agents: pd.DataFrame, team_skills: dict, first_weekday: int) -> tuple[bool, str]:
    seg, df = card["segment"], test
    if card["cause_type"] == "volume_spike":
        return False, "one-off spike (not expected to repeat)"
    if card["metric"].startswith("work"):
        rho, _ = team_rho(df, agents, seg["team"], seg["when"], team_skills[seg["team"]], first_weekday)
        return rho >= 1.1, f"rho {rho:.2f} on test days"
    mask = pd.Series(True, index=df.index)
    for key, value in seg.items():
        if key in ("hour", "day"):
            continue
        mask &= df[key] == value
    if mask.sum() < 30:
        return False, f"only {int(mask.sum())} tickets on test days"
    if card["metric"].startswith("transfers"):
        ratio = df.loc[mask, "transfers"].mean() / max(df.loc[~mask, "transfers"].mean(), 1e-9)
        return ratio >= 1.5, f"transfers {ratio:.1f}x on test days"
    if card["metric"].startswith("share"):
        cat = seg["category"]
        in_cluster = df["restaurant_cluster_id"] == seg["restaurant_cluster_id"]
        share = (df.loc[in_cluster, "category"] == cat).mean()
        rest = (df.loc[~in_cluster, "category"] == cat).mean()
        return share / rest >= 1.5, f"share {share / rest:.1f}x on test days"
    keys = [k for k in seg if k not in ("hour", "day")]
    worst_parent = 0.0
    for k in keys:
        parent = pd.Series(True, index=df.index)
        for k2 in keys:
            parent &= (df[k2] == seg[k2]) if k2 == k else (df[k2] != seg[k2])
        if parent.sum() >= 30:
            worst_parent = max(worst_parent, df.loc[parent, "wait_min"].mean())
    ratio = df.loc[mask, "wait_min"].mean() / max(worst_parent, 1e-9)
    return ratio >= 1.5, f"wait {ratio:.1f}x the worse parent on test days"


def main() -> int:
    started = time.perf_counter()
    calendar = load_config("calendar")
    splits = calendar["splits"]
    first_weekday = pd.Timestamp(calendar["start_date"]).weekday()
    known = {e["day"] for e in calendar["known_events"]}
    roster = load_config("roster")
    team_skills = {t: v["skills"] for t, v in roster["teams"].items()}
    agents = pd.read_csv(ROOT / "data" / "generated" / "agents.csv")
    planted = json.loads((ROOT / "data" / "planted.json").read_text(encoding="utf-8"))

    h = load_history()
    history = h[h["day"] <= splits["validation_last_day"]]
    test = label_frame(h[h["day"] > splits["validation_last_day"]], team_skills).reset_index(drop=True)
    out = find_patterns(history, agents, team_skills, known, first_weekday)
    cards = out["cards"]

    history_problems = [p for p in planted["problems"] if p.get("period") != "test"]
    result = score(cards, history_problems, team_skills)
    print(f"{len(cards)} evidence cards from {out['candidates']} candidates; "
          f"planted found {result['found']}/{result['planted']}, diagnosed {result['diagnosed']}/{result['planted']}")
    for d in result["details"]:
        print(f"  {d['id']:4s} {'FOUND' if d['found'] else 'missed':6s} {'diagnosed' if d['diagnosed'] else '':9s} {d['card']:4s} {d['name']}")
    unmatched = []
    for card in result["unmatched"]:
        ok, why = replicates(card, test, agents, team_skills, first_weekday)
        unmatched.append({"id": card["id"], "title": card["title"], "replicated": ok, "why": why})
        print(f"  unplanted {card['id']}: {card['title']} -> {'REPLICATES' if ok else 'does not replicate'} ({why})")

    category_col = "selected_category"
    pred_path = ROOT / "data" / "generated" / "predictions.csv"
    if pred_path.exists():
        preds = pd.read_csv(pred_path, usecols=["ticket_id", "pred_final"])
        h = h.merge(preds, on="ticket_id", how="left")
        category_col = "pred_final"
    alerts = live_alerts(h, category_col, splits["validation_last_day"] + 1, splits["test_last_day"], known)
    surge = next(p for p in planted["problems"] if p.get("period") == "test")
    seg = surge["segment"]
    start_min = (seg["day"] - 1) * 1440 + min(seg["hour"]) * 60
    hits = alerts[(alerts["category"] == seg["category"]) & (alerts["day"] == seg["day"]) & ~alerts["explained"]]
    latency = float(hits["minute"].min() - start_min) if len(hits) else None
    false_alerts = alerts[~alerts["explained"] & ~((alerts["category"] == seg["category"]) & (alerts["day"] == seg["day"]))]
    test_weeks = (splits["test_last_day"] - splits["validation_last_day"]) / 7
    print(f"live detection ({category_col}): day-{seg['day']} {seg['category']} surge flagged after "
          f"{latency} min; false alerts {len(false_alerts)} in {test_weeks:.0f} weeks; "
          f"{int(alerts['explained'].sum())} alerts on known sale days (explained)")

    PARTS.mkdir(parents=True, exist_ok=True)
    part = {
        "cards": cards,
        "recall": {"planted": result["planted"], "found": result["found"], "false_alarms":
                   sum(not u["replicated"] for u in unmatched),
                   "details": [{k: v for k, v in d.items()} for d in result["details"]]},
        "diagnosed": result["diagnosed"],
        "unplanted_findings": unmatched,
        "explained_anomalies": out["explained_anomalies"],
        "live_detection_latency_min": latency,
        "live_false_alerts_per_week": len(false_alerts) / test_weeks,
        "live_alerts": alerts.replace({np.nan: None}).to_dict("records"),
    }
    (PARTS / "patterns.json").write_text(json.dumps(part, indent=1, default=str), encoding="utf-8")
    print(f"wrote eval/parts/patterns.json ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
