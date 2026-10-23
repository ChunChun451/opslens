"""The real public service desk: OpsLens on the UCI ServiceNow incident log (CC BY 4.0).

What it does: the same five questions as on the food-delivery floor, answered on a real company's
IT service desk (24,918 incidents, 72 teams, 220 agents, a real SLA flag):
- What is happening?   summary of the desk;
- Why does it go wrong? evidence cards on the causes of delay, measured from the event log;
- What will go wrong?  incidents likely to miss their SLA (scored 1 h after opening) and next
                        week's workload per team;
- What should we do?    actions with their evidence;
- Does it work?         each prediction against what the desk itself used, on later months.

Why this design: deliverable 1 asks for "a working prototype using a provided or publicly available
dataset". Nothing here is generated. Every model learns on the first 70% of incidents (by opening
time) and is scored only on the last 30%; every choice (thresholds, stopping) uses the last 20% of
the learning period. We report what OpsLens does NOT do better, too: picking the final team at
opening time is worse than the real desk overall, so OpsLens only suggests a team when it is sure.

Plan v4 adds proof on the same split: replicate_cards (each card re-measured on the test months),
forecast_candidates (three forecasts, the check weeks pick one) and bottleneck_alerts (overload
alerts scored on test team-days). The fast-track benchmark is in realdesk_fasttrack.py, the daily
detectors in realdesk_watch.py. Exact JSON shapes: docs/explain/realdesk.md.

Example (from the 19 Oct check): incidents that wait on the user, a vendor or a problem record miss
their SLA 71% of the time, against 26% for incidents that never wait.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from opslens import forecast as F
from opslens import risk
from opslens.adapters.uci_incidents import risk_features
from opslens.realdesk_fasttrack import N_BOOT, week_totals

RISK_CATS = ["priority_raw", "impact", "urgency", "category", "channel", "first_team", "team_now", "state_now"]
RISK_NUMS = ["reassignments_now", "updates_now", "knowledge", "hour", "weekday", "open_in_team"]
ROUTE_COLS = ["category", "subcategory", "u_symptom", "location", "contact_type", "impact", "urgency", "priority",
              "opened_by", "cmdb_ci"]
STATE_GROUP = {"New": "waiting to be picked up", "Active": "being worked on", "Awaiting User Info": "waiting for the user",
               "Awaiting Vendor": "waiting for a vendor", "Awaiting Problem": "waiting for another fix",
               "Awaiting Evidence": "waiting for the user"}


def masks(incidents: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """learn (first 80% of the training period), check (last 20% of it, for every choice), test."""
    train = (incidents["split"] == "train").to_numpy()
    cut = incidents.loc[train, "created_at"].quantile(0.8)
    learn = train & (incidents["created_at"] <= cut).to_numpy()
    return learn, train & ~learn, (incidents["split"] == "test").to_numpy()


# ---- Why does it go wrong? -------------------------------------------------------------------

def time_in_states(events: pd.DataFrame) -> pd.DataFrame:
    """Hours each incident spent in each state group before it was resolved (from the event log).
    Example: New 2 h → Active 5 h → Awaiting User Info 20 h → Resolved: waiting for the user 20 h."""
    ev = events[["number", "incident_state", "sys_updated_at"]].copy()
    ev["hours"] = (ev.groupby("number")["sys_updated_at"].shift(-1) - ev["sys_updated_at"]).dt.total_seconds() / 3600
    ev["group"] = ev["incident_state"].map(STATE_GROUP)
    ev = ev.dropna(subset=["group", "hours"])
    return ev.pivot_table(index="number", columns="group", values="hours", aggfunc="sum", fill_value=0.0)


def problem_cards(incidents: pd.DataFrame, states: pd.DataFrame, history: np.ndarray) -> list[dict]:
    """Evidence cards on the history (learning period only), in the same shape as the food world's."""
    h = incidents[history].set_index("ticket_id")
    st = states.reindex(h.index).fillna(0.0)
    cards = []
    total = st.sum()
    share = (total / total.sum() * 100).round(1)
    waited = (st.get("waiting for the user", 0) + st.get("waiting for a vendor", 0) + st.get("waiting for another fix", 0)) > 0
    miss_w, miss_n = h.loc[waited, "breached"].mean() * 100, h.loc[~waited, "breached"].mean() * 100
    cards.append(card("R1", f"Incidents that wait on someone outside the team miss their SLA {miss_w / miss_n:.1f}× as often",
                      "process", "SLA missed (%)", miss_w, miss_n, "incidents that never waited", int(waited.sum()), len(h),
                      {"waits": "user, vendor or another fix"},
                      f"Waiting for the user is {share.get('waiting for the user', 0):.0f}% of all open time. "
                      "Remind the user automatically and close or pause stale waits.", h[waited & h["breached"]].head(3)))
    new_share = float(share.get("waiting to be picked up", 0))
    picked_late = st.get("waiting to be picked up", 0) > 8
    cards.append(card("R2", f"{new_share:.0f}% of all open time is spent waiting for someone to pick the incident up",
                      "capacity", "SLA missed (%)", h.loc[picked_late, "breached"].mean() * 100,
                      h.loc[~picked_late, "breached"].mean() * 100, "incidents picked up within 8 h",
                      int(picked_late.sum()), len(h), {"waited_to_be_picked_up_h": ">8"},
                      "Staff the teams where incidents queue longest at the hours they arrive (see next week's forecast).",
                      h[picked_late & h["breached"]].head(3)))
    by = h.groupby("final_category").agg(n=("breached", "size"), miss=("breached", "mean"), bounced=("transfers", lambda s: (s > 0).mean()))
    by = by[by["n"] >= 200]
    worst = (by["n"] * by["miss"] * by["bounced"]).sort_values(ascending=False).index[0]
    seg = h["final_category"] == worst
    bounced = seg & (h["transfers"] > 0)
    cards.append(card("R3", f"{worst}: {by.loc[worst, 'bounced'] * 100:.0f}% of incidents are passed between teams",
                      "process", "SLA missed (%)", h.loc[bounced, "breached"].mean() * 100,
                      h.loc[seg & ~bounced, "breached"].mean() * 100, f"{worst} incidents that stayed with one team",
                      int(seg.sum()), len(h), {"category": worst},
                      f"Agree a single owning team for {worst}, or route it there directly when OpsLens is sure.",
                      h[bounced & h["breached"]].head(3)))
    return cards


def card(cid, title, cause, metric, value, comparison, comparison_text, affected, n, segment, recommendation, examples):
    return {"id": cid, "title": title, "cause_type": cause, "metric": metric, "value": round(float(value), 1),
            "comparison_value": round(float(comparison), 1), "comparison_text": comparison_text,
            "segment": segment, "affected_tickets": int(affected), "affected_share_pct": round(100.0 * affected / n, 1),
            "recommendation": recommendation, "not_explained_by": "measured on the real event log (learning period)",
            "examples": [{"ticket_id": t, "category": r["final_category"], "team": r["resolved_by_team"],
                          "priority": r["priority_raw"], "missed_sla": bool(r["breached"]),
                          "resolution_h": round(float(r["resolution_min"]) / 60, 1) if pd.notna(r["resolution_min"]) else None}
                         for t, r in examples.iterrows()]}


def card_groups(h: pd.DataFrame, st: pd.DataFrame, r3_category: str) -> dict[str, tuple[pd.Series, pd.Series]]:
    """For each card R1-R3: (incidents in the finding, incidents it is compared with). The same
    definitions as problem_cards; R3's category is the one problem_cards found on the learning months."""
    waited = (st.get("waiting for the user", 0) + st.get("waiting for a vendor", 0) + st.get("waiting for another fix", 0)) > 0
    picked_late = st.get("waiting to be picked up", 0) > 8
    seg = h["final_category"] == r3_category
    bounced = seg & (h["transfers"] > 0)
    return {"R1": (waited, ~waited), "R2": (picked_late, ~picked_late), "R3": (bounced, seg & ~bounced)}


def bootstrap_gap(weeks: np.ndarray, missed: np.ndarray, group: np.ndarray, other: np.ndarray, seed: int = 0) -> tuple[float, float]:
    """95% CI of (miss % in group − miss % in other) with whole weeks resampled.
    Example: one week with group 6 of 10 missed and other 2 of 10 → gap 40 points."""
    totals = week_totals(weeks, {"n_g": group, "m_g": missed & group, "n_o": other, "m_o": missed & other})
    n_weeks = len(totals["n_g"])
    draws = np.random.default_rng(seed).integers(0, n_weeks, size=(N_BOOT, n_weeks))
    pick = {name: v[draws].sum(axis=1) for name, v in totals.items()}
    gap = 100.0 * (pick["m_g"] / np.maximum(pick["n_g"], 1) - pick["m_o"] / np.maximum(pick["n_o"], 1))
    return float(np.percentile(gap, 2.5)), float(np.percentile(gap, 97.5))


def replicate_cards(incidents: pd.DataFrame, states: pd.DataFrame, cards: list[dict], history: np.ndarray,
                    test: np.ndarray) -> dict:
    """Out-of-time replication: each card was found on the learning months; is it still true on
    the test months? 'Replicates' only if the gap (miss % in the finding − miss % in its comparison)
    keeps its sign on the test months with a 95% CI (whole test weeks resampled) excluding 0."""
    r3 = cards[2]["segment"]["category"]
    out = []
    for c in cards:
        row = {"id": c["id"], "title": c["title"], "comparison_text": c["comparison_text"]}
        for part, mask in (("learning", history), ("test", test)):
            h = incidents[mask].set_index("ticket_id")
            st = states.reindex(h.index).fillna(0.0)
            group, other = card_groups(h, st, r3)[c["id"]]
            y = h["breached"].to_numpy().astype(bool)
            g, o = group.to_numpy(), other.to_numpy()
            value, comparison = float(y[g].mean() * 100), float(y[o].mean() * 100)
            row[part] = {"value": value, "comparison": comparison, "gap": value - comparison,
                         "ratio": value / comparison if comparison > 0 else None,
                         "n_group": int(g.sum()), "n_comparison": int(o.sum())}
            if part == "test":
                weeks = h["created_at"].dt.to_period("W").astype(str).to_numpy()
                row[part]["ci_low"], row[part]["ci_high"] = bootstrap_gap(weeks, y, g, o)
        sign = np.sign(row["learning"]["gap"])
        t = row["test"]
        row["replicates"] = bool(np.sign(t["gap"]) == sign and np.sign(t["ci_low"]) == sign and np.sign(t["ci_high"]) == sign)
        out.append(row)
    return {"cards": out, "replicated": sum(r["replicates"] for r in out), "of": len(out),
            "rule": "Found on the learning months; replicates only if the gap keeps its sign on the test months "
                    "with a 95% CI (whole test weeks resampled) excluding 0."}


# ---- What will go wrong? ---------------------------------------------------------------------

def train_early_warning(incidents: pd.DataFrame, events: pd.DataFrame) -> dict:
    """The early-warning model: LightGBM on the as-of-1-hour features, learned on `learn`, stopped
    on `check`. Returned with its features so the fast-track benchmark scores the same model."""
    feats = risk_features(incidents, events)
    X = feats[RISK_CATS + RISK_NUMS].copy()
    for c in RISK_CATS:
        X[c] = X[c].astype("category")
    learn, check, test = masks(incidents)  # feats rows are in the same order as incidents
    y = feats["breached"].to_numpy()
    booster = lgb.train({**risk.PARAMS, "num_threads": 4}, lgb.Dataset(X[learn], y[learn], categorical_feature=RISK_CATS), 2000,
                        valid_sets=[lgb.Dataset(X[check], y[check], categorical_feature=RISK_CATS)],
                        callbacks=[lgb.early_stopping(50, verbose=False)])
    return {"feats": feats, "X": X, "y": y, "booster": booster, "learn": learn, "check": check, "test": test,
            "cats": RISK_CATS}


def early_warning(incidents: pd.DataFrame, events: pd.DataFrame, model: dict | None = None) -> dict:
    """SLA-miss risk scored 1 h after opening; compared with the desk's own priority field.
    'Caught in the top 20%': of all incidents that missed their SLA, how many the score had put in
    its riskiest 20% (the desk can only look closely at a few)."""
    model = model or train_early_warning(incidents, events)
    feats, X, y, booster, test = model["feats"], model["X"], model["y"], model["booster"], model["test"]
    p = booster.predict(X[test])
    prio = -feats.loc[test, "priority_raw"].str[0].astype(float).to_numpy()  # 1 - Critical = most urgent
    yt = y[test]
    k = int(0.2 * len(yt))
    caught = lambda score: float(yt[np.argsort(-score, kind="stable")[:k]].sum() / max(1, yt.sum()))  # noqa: E731
    rng = np.random.default_rng(0)
    prio_tiebreak = prio + rng.uniform(0, 1e-6, len(prio))  # the field has 4 levels: break ties at random
    out = {"n_test": int(test.sum()), "missed_pct": float(yt.mean() * 100),
           "auc_opslens": float(roc_auc_score(yt, p)), "auc_priority": float(roc_auc_score(yt, prio)),
           "caught_top20_opslens_pct": caught(p) * 100, "caught_top20_priority_pct": caught(prio_tiebreak) * 100}
    out["at_risk"] = at_risk_examples(booster, X[test], feats[test], p)
    return out


REASON = {"team_now": lambda v: f"now held by {v}", "first_team": lambda v: f"first sent to {v}",
          "state_now": lambda v: f"state after 1 h: {v}", "reassignments_now": lambda v: f"passed between teams {int(v)}× in its first hour",
          "updates_now": lambda v: f"{int(v)} updates in its first hour", "open_in_team": lambda v: f"{int(v)} other incidents open in its team",
          "category": lambda v: f"{v}", "priority_raw": lambda v: f"priority {v}", "impact": lambda v: f"impact {v}",
          "urgency": lambda v: f"urgency {v}", "channel": lambda v: f"came in by {v}", "knowledge": lambda v: "a knowledge article was used" if v else "no knowledge article",
          "hour": lambda v: f"opened at {int(v):02d}:00", "weekday": lambda v: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(v)]}


def at_risk_examples(booster, X: pd.DataFrame, feats: pd.DataFrame, p: np.ndarray, k: int = 8) -> list[dict]:
    """The riskiest test incidents with their top reasons (TreeSHAP, as share of the upward push)."""
    top = np.argsort(-p)[:k]
    contrib = booster.predict(X.iloc[top], pred_contrib=True)[:, :-1]
    names = list(X.columns)
    out = []
    for row, i in enumerate(top):
        pos = np.clip(contrib[row], 0, None)
        reasons = [{"text": REASON[names[j]](feats.iloc[i][names[j]]), "share": round(float(pos[j] / pos.sum()), 2)}
                   for j in np.argsort(-contrib[row])[:3] if contrib[row, j] > 0]
        out.append({"ticket_id": str(feats.iloc[i]["ticket_id"]), "risk": round(float(p[i]), 3), "missed_sla": bool(feats.iloc[i]["breached"]),
                    "priority": str(feats.iloc[i]["priority_raw"]), "team_now": str(feats.iloc[i]["team_now"]), "reasons": reasons})
    return out


def team_daily(incidents: pd.DataFrame, teams: int = 8) -> dict:
    """Daily new incidents per team (the 8 busiest first teams) on the check and test weeks, with
    the learned forecast (LightGBM Poisson on hourly counts, lags of 1-4 weeks) and "same day last
    week", plus each team's usual closures per day (median of the 4 weeks before the test period).
    Every input of either forecast is at least a week old, so both are week-ahead forecasts."""
    inc = incidents[incidents["created_at"] < "2016-06-01"].copy()
    start = inc["created_at"].min().normalize()
    inc["minute_of_run"] = (inc["created_at"] - start).dt.total_seconds() / 60
    top = inc["first_team"].value_counts().index[:teams].tolist()
    inc = inc[inc["first_team"].isin(top)]
    days = int(inc["minute_of_run"].max() // 1440) + 1
    rows = F.add_features(F.hourly_counts(inc, "first_team", days, top), start.weekday(), set())
    learn, check, test = masks(incidents)
    test_start = incidents.loc[test, "created_at"].min()
    check_start = incidents.loc[check, "created_at"].min()
    day_of = lambda ts: int((ts - start).total_seconds() // 86400) + 1  # noqa: E731
    tr = rows[(rows["day"] >= 29) & (rows["day"] < day_of(check_start))]
    va = rows[(rows["day"] >= day_of(check_start)) & (rows["day"] < day_of(test_start))]
    te = rows[rows["day"] >= day_of(test_start)].copy()
    model = F.train(tr, va)
    va_daily = va.assign(forecast=model.predict(va[F.FEATURES])).groupby(["category", "day"], observed=True).agg(
        actual=("count", "sum"), forecast=("forecast", "sum"), naive=("lag_168", "sum"))
    te["model"] = model.predict(te[F.FEATURES])
    resolved = incidents.dropna(subset=["resolved_at"])
    resolved = resolved[(resolved["resolved_at"] < test_start) & (resolved["resolved_at"] >= test_start - pd.Timedelta(days=28))]
    capacity = resolved.groupby([resolved["resolved_by_team"], resolved["resolved_at"].dt.date]).size().groupby(level=0).median()
    return {"top": top, "start": start, "va_daily": va_daily, "te": te, "capacity": capacity,
            "first_test_day": day_of(test_start)}


def team_forecast(incidents: pd.DataFrame, teams: int = 8, daily: dict | None = None) -> dict:
    """Daily new incidents per team for the test weeks: OpsLens's forecaster (LightGBM Poisson on
    hourly counts, lags of 1-4 weeks) vs 'same day last week'. A team-day is a bottleneck when the
    forecast exceeds what the team usually closes in a day (median of its last 4 learning weeks)."""
    d = daily or team_daily(incidents, teams)
    top, start, va_daily, te, capacity = d["top"], d["start"], d["va_daily"], d["te"].copy(), d["capacity"]
    # Model choice on the check weeks only: the learned forecast or "same day last week"? On the
    # first run the learned one lost on the TEST weeks (0.365 vs 0.341), so we let the check weeks
    # decide between the two, honestly, and report the test result of whichever they pick.
    use_model = F.wape(va_daily["actual"].to_numpy(), va_daily["forecast"].to_numpy()) < \
        F.wape(va_daily["actual"].to_numpy(), va_daily["naive"].to_numpy())
    te["forecast"] = te["model"] if use_model else te["lag_168"]
    daily = te.groupby(["category", "day"], observed=True).agg(actual=("count", "sum"), forecast=("forecast", "sum"),
                                                              model=("model", "sum"), naive=("lag_168", "sum")).reset_index()
    daily["capacity"] = daily["category"].astype(str).map(capacity).fillna(0)
    daily["date"] = (start + pd.to_timedelta(daily["day"] - 1, unit="D")).dt.strftime("%a %d %b")
    week = daily[daily["day"] < d["first_test_day"] + 7]
    alerts = week[week["forecast"] > week["capacity"]].sort_values("forecast", ascending=False)
    return {"teams": top, "chosen_on_check_weeks": "learned (LightGBM)" if use_model else "same day last week",
            "wape_learned": F.wape(daily["actual"].to_numpy(), daily["model"].to_numpy()),
            "wape_same_day_last_week": F.wape(daily["actual"].to_numpy(), daily["naive"].to_numpy()),
            "next_week": [{"team": str(r.category), "date": r.date, "forecast": round(float(r.forecast), 1),
                           "usual_closures": float(r.capacity), "actual": int(r.actual)} for r in week.itertuples()],
            "bottlenecks": [{"team": str(r.category), "date": r.date, "forecast": round(float(r.forecast), 1),
                             "usual_closures": float(r.capacity)} for r in alerts.head(8).itertuples()]}


CANDIDATES = {"same_day_last_week": "Same day last week", "learned": "Learned (LightGBM)",
              "average": "Average of both"}


def candidate_frames(d: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Check and test team-days with the three candidate forecasts side by side."""
    va = d["va_daily"].reset_index().rename(columns={"forecast": "learned", "naive": "same_day_last_week"})
    te = d["te"].groupby(["category", "day"], observed=True).agg(actual=("count", "sum"), learned=("model", "sum"),
                                                                same_day_last_week=("lag_168", "sum")).reset_index()
    for frame in (va, te):
        frame["average"] = (frame["learned"] + frame["same_day_last_week"]) / 2
    te["capacity"] = te["category"].astype(str).map(d["capacity"]).fillna(0)
    te["weekday"] = (d["start"] + pd.to_timedelta(te["day"] - 1, unit="D")).dt.weekday
    return va, te


def forecast_candidates(d: dict) -> dict:
    """Three forecasts of each team's daily new incidents; the check weeks pick one (lowest WAPE);
    the test weeks report all three once. Example: a team-day with same day last week 240 and
    learned 218 has the average 229."""
    va, te = candidate_frames(d)
    check = {c: F.wape(va["actual"].to_numpy(), va[c].to_numpy()) for c in CANDIDATES}
    test = {c: F.wape(te["actual"].to_numpy(), te[c].to_numpy()) for c in CANDIDATES}
    chosen = min(check, key=check.get)
    best_on_test = min(test, key=test.get)
    return {"candidates": CANDIDATES, "wape_check": check, "wape_test": test, "chosen_on_check": chosen,
            "wape_test_chosen": test[chosen], "best_on_test": best_on_test,
            "team_days_check": int(len(va)), "team_days_test": int(len(te)),
            "note": "WAPE = sum of |forecast - actual| / sum of actual over team-days. Chosen on the check weeks only."}


def score_alerts(predicted: np.ndarray, actual: np.ndarray) -> dict:
    """Precision and recall of overload alerts. Example: 10 alerts, 7 of them real, 14 real
    overloads in all → precision 70%, recall 50%."""
    tp = int((predicted & actual).sum())
    return {"alerts": int(predicted.sum()), "overloaded": int(actual.sum()), "hits": tp,
            "precision_pct": 100.0 * tp / max(int(predicted.sum()), 1), "recall_pct": 100.0 * tp / max(int(actual.sum()), 1)}


def bottleneck_alerts(d: dict, chosen: str) -> dict:
    """Score 'this team will get more new incidents than it usually closes' on every test team-day,
    for each candidate forecast and for a calendar rule that alerts on every weekday."""
    _, te = candidate_frames(d)
    actual = (te["actual"] > te["capacity"]).to_numpy()
    scores = {c: score_alerts((te[c] > te["capacity"]).to_numpy(), actual) for c in CANDIDATES}
    scores["every_weekday"] = score_alerts((te["weekday"] < 5).to_numpy(), actual)
    by_team = []
    for team, rows in te.groupby("category", observed=True):
        s = score_alerts((rows[chosen] > rows["capacity"]).to_numpy(), (rows["actual"] > rows["capacity"]).to_numpy())
        by_team.append({"team": str(team), "usual_closures": float(rows["capacity"].iloc[0]), **s})
    return {"chosen_forecast": chosen, "team_days": int(len(te)), "overloaded_share_pct": float(actual.mean() * 100),
            "scores": scores, "by_team": by_team,
            "definition": "Overloaded team-day = more new incidents than the team usually closes in a day (median of "
                          "the 4 weeks before the test period). Alerts are made a week ahead.",
            "labels": {**CANDIDATES, "every_weekday": "Calendar rule: alert on every weekday"}}


# ---- What should we do? ----------------------------------------------------------------------

def routing_hints(incidents: pd.DataFrame, events: pd.DataFrame) -> dict:
    """Suggest the team that will finally resolve an incident, at the moment it opens — but only
    when OpsLens is sure. The confidence threshold is chosen on the check period (most incidents
    fixed minus incidents it would have sent wrong); everything reported is on the test months.
    Baseline: the team the real desk sent it to first."""
    first = events.groupby("number").head(1).set_index("number")
    X = first[ROUTE_COLS].reindex(incidents["ticket_id"]).reset_index(drop=True)
    for c in ROUTE_COLS:
        X[c] = X[c].astype("category")
    y = incidents["resolved_by_team"].reset_index(drop=True)
    desk = incidents["first_team"].reset_index(drop=True)
    learn, check, test = masks(incidents)
    known = y.notna().to_numpy() & desk.notna().to_numpy()
    learn, check, test = learn & known, check & known, test & known
    classes = sorted(y[learn].unique())
    code = {c: k for k, c in enumerate(classes)}
    ok_check = check & y.isin(code).to_numpy()
    params = {"objective": "multiclass", "num_class": len(classes), "learning_rate": 0.08, "num_leaves": 31,
              "min_child_samples": 20, "verbose": -1, "num_threads": 4, "seed": 7, "deterministic": True}
    booster = lgb.train(params, lgb.Dataset(X[learn], y[learn].map(code)), 600,
                        valid_sets=[lgb.Dataset(X[ok_check], y[ok_check].map(code))],
                        callbacks=[lgb.early_stopping(30, verbose=False)])

    def judge(mask: np.ndarray, threshold: float) -> dict:
        P = booster.predict(X[mask])
        pred, conf = np.array(classes)[P.argmax(1)], P.max(1)
        yt, dk = y[mask].to_numpy(), desk[mask].to_numpy()
        sure = conf >= threshold
        fixed = int(((dk != yt) & (pred == yt) & sure).sum())
        broke = int(((dk == yt) & (pred != yt) & sure).sum())
        return {"n": int(mask.sum()), "desk_right_pct": float((dk == yt).mean() * 100), "opslens_all_right_pct": float((pred == yt).mean() * 100),
                "sure_share_pct": float(sure.mean() * 100), "opslens_sure_right_pct": float((pred[sure] == yt[sure]).mean() * 100) if sure.any() else 0.0,
                "desk_on_same_right_pct": float((dk[sure] == yt[sure]).mean() * 100) if sure.any() else 0.0,
                "fixed": fixed, "made_wrong": broke, "net_first_time_right": fixed - broke}

    grid = [0.5, 0.6, 0.7, 0.8, 0.9]
    threshold = max(grid, key=lambda t: judge(check, t)["net_first_time_right"])
    return {"threshold": threshold, "test": judge(test, threshold),
            "note": "The final team is not always the 'right' one: many incidents go to the front-line desk "
                    "(Group 70) by design. OpsLens only suggests a team when it is at least this sure."}
