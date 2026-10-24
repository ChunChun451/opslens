"""Shadow mode on a real day: what OpsLens would have said, hour by hour, next to what really happened.

What it does: for real days of the UCI test months, every incident with what the desk knew at its
1-hour mark (OpsLens risk and its top 3 reasons, the priority field, still unassigned?) and what
happened later (pickup, resolution, the company's SLA flag, our deadline rule). Per day: how many
misses each warning caught in time, how many of its flags were real, and how many misses each
fast-track picker would have saved (the W3 assumption). This is how a company would try OpsLens
in week 1: watching, not acting.

Why this design: nothing is retrained. The models, the deadline rule and the pickers are the ones
of the W3 benchmark (realdesk_fasttrack), so the day pages add up to the benchmark (a test checks
the picks are the same). The UCI log has no free text (only codes such as "Category 26",
"Group 70"), so nothing needs PII masking; if a text column is ever added, mask it with
privacy.mask_pii before it is written here.

Days: every test-month day with at least 50 new incidents. Showcase: the busiest test weekday (the
day with the most new incidents: the floor at its hardest, and the day with the most to show). Four
more: the busiest weekday of each other busy test week (weeks with at least 100 incidents), so a
judge can see the result is not one lucky day.

Example (results.realdesk.shadow, showcase Thu 5 May 2016): 403 new incidents, 111 missed; OpsLens's top 20%
at the 1-hour mark caught 53 of the 102 benchmark misses (precision 67.1%), the priority field 16 (20.3%).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from opslens.realdesk import REASON, RISK_CATS, RISK_NUMS
from opslens.realdesk_fasttrack import (ASSUMPTION, RULE_BUDGET, SCORED_PRIORITIES, missed_by_rule, pick_daily,
                                        picker_scores, pickup_wait_after)

MIN_DAY_INCIDENTS = 50
MIN_BUSY_WEEK = 100
SHADOW_PICKERS = ["opslens", "priority", "unassigned"]


def minute_of_day(times: pd.Series, day: pd.Timestamp) -> list[int | None]:
    """Minutes since the day's midnight (more than 1440 for a later day); None when unknown.
    Example: opened Mon 2 May 13:24, resolved Fri 6 May 14:18 → 804 and 6618."""
    out = []
    for t in times:
        out.append(None if pd.isna(t) else int((t - day).total_seconds() // 60))
    return out


def top_reasons(booster, X: pd.DataFrame, feats: pd.DataFrame) -> list[list[dict]]:
    """The 3 features that push each incident's risk up most (TreeSHAP), worded as at_risk_examples."""
    contrib = booster.predict(X, pred_contrib=True)[:, :-1]
    names = list(X.columns)
    out = []
    for row in range(len(X)):
        pos = np.clip(contrib[row], 0, None)
        total = pos.sum() or 1.0
        out.append([{"text": REASON[names[j]](feats.iloc[row][names[j]]), "share": round(float(pos[j] / total), 2)}
                    for j in np.argsort(-contrib[row])[:3] if contrib[row, j] > 0])
    return out


def choose_days(daily: pd.DataFrame) -> list[pd.Timestamp]:
    """Showcase first (busiest weekday), then the busiest weekday of every other busy week."""
    weekdays = daily[daily["weekday"] < 5]
    showcase = weekdays["opened"].idxmax()
    busy = daily.groupby("week")["opened"].sum()
    others = []
    for week in sorted(busy[busy >= MIN_BUSY_WEEK].index):
        if week == daily.loc[showcase, "week"]:
            continue
        in_week = weekdays[weekdays["week"] == week]
        if len(in_week):
            others.append(in_week["opened"].idxmax())
    return [showcase] + others[:4]


def day_summary(rows: pd.DataFrame) -> dict:
    """Misses caught in time and flag precision (company flag, benchmark incidents), fast-track saved."""
    pool = rows[rows["in_benchmark"]]
    missed = pool["missed_flag"].to_numpy()
    out = {"incidents": int(len(rows)), "benchmark_incidents": int(len(pool)),
           "actual_misses": int(rows["missed_flag"].sum()), "actual_misses_benchmark": int(missed.sum())}
    for p in ("opslens", "priority"):
        flagged = pool[f"top20_{p}"].to_numpy()
        hits = int((flagged & missed).sum())
        out[p] = {"flagged": int(flagged.sum()), "caught": hits,
                  "recall_pct": 100.0 * hits / max(int(missed.sum()), 1),
                  "precision_pct": 100.0 * hits / max(int(flagged.sum()), 1)}
    out["fast_track_saved"] = {p: int(pool[f"saved_{p}"].sum()) for p in SHADOW_PICKERS}
    return out


def shadow(incidents: pd.DataFrame, events: pd.DataFrame, model: dict, limits: dict[str, float], test: np.ndarray) -> dict:
    """results.realdesk.shadow (shape: docs/explain/realdesk.md section 8)."""
    feats, X, booster = model["feats"], model["X"], model["booster"]
    hours = incidents["resolution_min"].to_numpy() / 60.0
    priority = incidents["priority_raw"].astype(str).to_numpy()
    wait = pickup_wait_after(incidents, events)
    rule_miss = missed_by_rule(hours, priority, limits)
    savable = rule_miss & ~missed_by_rule(hours - wait, priority, limits)
    risk_all = booster.predict(X)
    later = events[events["incident_state"] != "New"].groupby("number").head(1).set_index("number")
    first_state = events.groupby("number").head(1).set_index("number")["incident_state"]

    inc = incidents.assign(row=np.arange(len(incidents)), date=incidents["created_at"].dt.normalize())
    t = inc[test]
    daily = t.groupby("date").agg(opened=("ticket_id", "size"), missed=("breached", "sum"))
    daily["weekday"] = daily.index.weekday
    daily["week"] = daily.index.to_period("W").astype(str)
    daily = daily[daily["opened"] >= MIN_DAY_INCIDENTS]
    days = [{"date": str(d.date()), "weekday": d.strftime("%a"), "opened": int(r.opened), "missed_flag": int(r.missed)}
            for d, r in daily.iterrows()]

    # The W3 benchmark's own picks over the whole test pool: every shown day must pick the same incidents.
    full = test & np.isin(priority, SCORED_PRIORITIES)
    full_rows = np.flatnonzero(full)
    full_scores = picker_scores(feats.iloc[full_rows].reset_index(drop=True), np.zeros(len(full_rows)), risk_all[full_rows])
    full_day = incidents.loc[full, "created_at"].dt.normalize().to_numpy().astype("int64")
    full_created = incidents.loc[full, "created_at"].to_numpy().astype("int64")
    benchmark_pick = {p: dict(zip(full_rows, pick_daily(full_day, full_created, full_scores[p], RULE_BUDGET)))
                      for p in SHADOW_PICKERS}

    out_days = []
    for day in choose_days(daily):
        d = t[t["date"] == day]
        idx = d["row"].to_numpy()
        pool = np.isin(priority[idx], SCORED_PRIORITIES)
        scores = picker_scores(feats.iloc[idx].reset_index(drop=True), np.zeros(len(idx)), risk_all[idx])
        day_code = np.zeros(int(pool.sum()), dtype="int64")
        created = d["created_at"].to_numpy().astype("int64")[pool]
        picks = {}
        for p in SHADOW_PICKERS:
            chosen = np.zeros(len(idx), dtype=bool)
            chosen[pool] = pick_daily(day_code, created, scores[p][pool], RULE_BUDGET)
            picks[p] = chosen
            assert all(chosen[i] == benchmark_pick[p][idx[i]] for i in np.flatnonzero(pool)), p   # same as W3
        ids = d["ticket_id"]
        pickup_state = later["incident_state"].reindex(ids).to_numpy()
        recorded = pd.notna(pickup_state) & ~np.isin(pickup_state.astype(str), ["Resolved", "Closed"])
        pickup_at = later["sys_updated_at"].reindex(ids).where(recorded)
        reasons = top_reasons(booster, X.iloc[idx], feats.iloc[idx])
        rows = pd.DataFrame({
            "in_benchmark": pool, "missed_flag": d["breached"].to_numpy().astype(bool),
            **{f"top20_{p}": picks[p] for p in ("opslens", "priority")},
            **{f"saved_{p}": picks[p] & savable[idx] for p in SHADOW_PICKERS}})
        incidents_out = []
        opened = minute_of_day(d["created_at"], day)
        picked = minute_of_day(pd.Series(pickup_at.to_numpy()), day)
        resolved = minute_of_day(d["resolved_at"], day)
        for i in range(len(idx)):
            r = idx[i]
            scorable = bool(pool[i] and not np.isnan(hours[r]))
            incidents_out.append({
                "ticket_id": str(ids.iloc[i]), "opened_at": opened[i], "priority": priority[r],
                "in_benchmark": bool(pool[i]), "risk": round(float(risk_all[r]), 3), "reasons": reasons[i],
                "unassigned_at_1h": bool(scores["unassigned"][i]),
                "top20_opslens": bool(picks["opslens"][i]), "top20_priority": bool(picks["priority"][i]),
                "pick_unassigned": bool(picks["unassigned"][i]),
                "picked_up_at": picked[i], "resolved_at": resolved[i],
                "picked_up_recorded": bool(recorded[i]), "first_state": str(first_state.get(ids.iloc[i])),
                "made_sla": not bool(d["breached"].iloc[i]),
                "rule_missed": bool(rule_miss[r]) if scorable else None,
                "fast_track_saved": {p: bool(picks[p][i] and savable[r]) for p in SHADOW_PICKERS}})
        out_days.append({"date": str(day.date()), "weekday": day.strftime("%a"), "summary": day_summary(rows),
                         "incidents": sorted(incidents_out, key=lambda x: x["opened_at"])})
    return {
        "assumption": ASSUMPTION,
        "how": "Frozen models (no retraining): OpsLens risk 1 hour after opening, the W3 deadline rule and pickers. "
               "Top 20% = the day's 20% of Moderate/Low incidents each picker ranks highest (Critical/High are "
               "outside the benchmark: the desk fast-tracks them anyway). 'Caught in time' uses the company's own flag.",
        "privacy": "The UCI log has no free text (codes only), so nothing needed PII masking.",
        "min_day_incidents": MIN_DAY_INCIDENTS, "days": days,
        "showcase": out_days[0]["date"],
        "showcase_why": "The busiest test weekday: the most new incidents, the floor at its hardest.",
        "others_why": "The busiest weekday of each other busy test week (at least 100 incidents).",
        "pickers": SHADOW_PICKERS, "features": RISK_CATS + RISK_NUMS,
        "shown_days": out_days,
    }
