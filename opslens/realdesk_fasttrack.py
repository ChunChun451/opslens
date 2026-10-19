"""Fast-track benchmark on the real service desk: whose pick saves more missed deadlines?

What it does: a real log cannot be replayed, so we ask one fair, stated question. If the desk can
fast-track 10%, 20% or 30% of each day's new incidents at their 1-hour mark, which way of picking
them saves the most missed deadlines? Fast-track = the incident's wait to be picked up after the
1-hour mark becomes zero; everything else happens as it really did (an ASSUMPTION, shown on screen).
Five pickers, all scored with what the desk knows 1 hour after opening (risk_features):
the desk's priority field; "still unassigned at 1 hour"; oldest first; logistic regression on the
same features as OpsLens; OpsLens (the LightGBM early warning). Plus the ceiling: every incident
picked up the moment its first hour ends.

How it works:
1. Deadline rule. The log has the company's own SLA flag but not its clock, so we learn, per
   priority, the resolution-time limit (whole hours) that best matches the flag on the learning
   part (first 80% of the learning period). Two candidate clocks: plain resolution time, or with
   waits on others (user, vendor, another fix) paused; the check part (last 20%) picks one.
   Critical and High are flagged missed ~98% whatever their time: no rule can score them, so they
   are left out of the benchmark (a desk fast-tracks them anyway) and reported separately.
2. Pickup wait after 1 h, from the event log: the first event in a state other than New is the
   pickup. When an incident goes from New straight to Resolved, no pickup was recorded and its New
   time includes the fix itself, so we count NO wait for it (conservative: understates savings).
3. Each day, a picker fast-tracks round(k × that day's incidents) of them, highest score first,
   ties oldest first. Incidents that never got a resolution time use budget but save nothing.
4. Saved = missed under the rule as it happened, met once its pickup wait after 1 h is removed.
5. 95% CIs: whole test weeks resampled (2,000 times), totals scaled to the test size. Most test
   incidents fall in 5 busy weeks (2 May - 5 Jun 2016), so we also show each busy week alone.

Pre-registered rule (docs/PLAN_V4.md, W3): we say OpsLens's pick is better only if it saves more
misses than the BEST other picker (best on the test months, the hardest comparison) at the 20%
budget with a CI excluding 0. Every picker and budget is shown either way.

Example: INC0000045-like case — a "3 - Moderate" incident resolved after 100 h misses the 91 h
limit; it sat 12 h in New after its first hour; fast-tracked it resolves after 88 h → saved.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

SCORED_PRIORITIES = ["3 - Moderate", "4 - Low"]
LEFT_OUT_PRIORITIES = ["1 - Critical", "2 - High"]
LIMIT_GRID_H = np.arange(1.0, 2001.0)      # candidate limits: 1 h .. 2,000 h in whole hours
BUDGETS = [10, 20, 30]                      # % of each day's new incidents
RULE_BUDGET = 20
PICKERS = ["priority", "unassigned", "oldest", "logistic", "opslens"]
PICKER_LABELS = {
    "priority": "The desk's priority field (then oldest)",
    "unassigned": "Still unassigned at 1 hour (then oldest)",
    "oldest": "Oldest first",
    "logistic": "Logistic regression, same features as OpsLens",
    "opslens": "OpsLens early warning (LightGBM)",
}
LOGISTIC_C = [0.01, 0.1, 1.0, 10.0]
N_BOOT = 2000
ASSUMPTION = ("A log cannot be replayed. We assume a fast-tracked incident is picked up the moment its "
              "first hour ends and that everything after the pickup happens exactly as it really did.")


# ---- 1. The deadline rule ---------------------------------------------------------------------

def learn_limits(hours: np.ndarray, priority: np.ndarray, missed_flag: np.ndarray, mask: np.ndarray) -> dict[str, float]:
    """Per priority, the limit L (whole hours) for which "took longer than L" best matches the flag.
    Example: 3 Moderate incidents of 10 h, 50 h, 120 h flagged made, made, missed → any L in
    50..119 matches all three; the smallest, 50, is kept."""
    limits = {}
    for prio in SCORED_PRIORITIES:
        m = mask & (priority == prio) & ~np.isnan(hours)
        h, y = hours[m], missed_flag[m]
        agree = [np.mean((h > limit) == y) for limit in LIMIT_GRID_H]
        limits[prio] = float(LIMIT_GRID_H[int(np.argmax(agree))])
    return limits


def missed_by_rule(hours: np.ndarray, priority: np.ndarray, limits: dict[str, float]) -> np.ndarray:
    """True where the incident took longer than its priority's limit (NaN hours → False)."""
    limit = np.array([limits.get(p, np.nan) for p in priority])
    with np.errstate(invalid="ignore"):
        return hours > limit


def rule_match_pct(hours, priority, missed_flag, mask, limits) -> float:
    """% of scored incidents in `mask` where the rule agrees with the company's flag."""
    m = mask & np.isin(priority, SCORED_PRIORITIES) & ~np.isnan(hours)
    return float(np.mean(missed_by_rule(hours[m], priority[m], limits) == missed_flag[m]) * 100)


# ---- 2. Pickup wait after the 1-hour mark -----------------------------------------------------

def pickup_wait_after(incidents: pd.DataFrame, events: pd.DataFrame, hours: float = 1.0) -> np.ndarray:
    """Hours each incident still waited to be picked up after its `hours` mark (order of incidents).
    Example: opened 08:00, New until 21:00, then Active → 12 h after the 09:00 mark. Opened 08:00,
    New until 15:00, then Resolved → 0 (no pickup recorded; the New time includes the fix)."""
    later = events[events["incident_state"] != "New"].groupby("number").head(1).set_index("number")
    pickup_at = later["sys_updated_at"].reindex(incidents["ticket_id"]).to_numpy()
    state = later["incident_state"].reindex(incidents["ticket_id"]).to_numpy()
    recorded = pd.notna(state) & ~np.isin(state.astype(str), ["Resolved", "Closed"])
    mark = (incidents["created_at"] + pd.Timedelta(hours=hours)).to_numpy()
    wait = (pickup_at - mark) / np.timedelta64(1, "h")
    wait = np.where(recorded & ~np.isnan(wait), np.clip(wait, 0, None), 0.0)
    return wait.astype(float)


# ---- 3. Pickers and the daily budget ----------------------------------------------------------

def logistic_scores(feats: pd.DataFrame, cats: list[str], nums: list[str], learn, check, test) -> tuple[np.ndarray, float, float]:
    """Logistic regression on the same as-of features; C chosen by AUC on the check part.
    Returns test probabilities, the chosen C and its check AUC."""
    X = design_matrix(feats, cats, nums, learn)
    y = feats["breached"].to_numpy()
    best = None
    for c in LOGISTIC_C:
        model = LogisticRegression(C=c, max_iter=3000).fit(X[learn], y[learn])
        auc = roc_auc_score(y[check], model.predict_proba(X[check])[:, 1])
        if best is None or auc > best[1]:
            best = (model, auc, c)
    return best[0].predict_proba(X[test])[:, 1], best[2], float(best[1])


def design_matrix(feats: pd.DataFrame, cats: list[str], nums: list[str], learn: np.ndarray) -> np.ndarray:
    """One-hot categories (values seen ≥ 20 times while learning, else "other"; missing → "missing")
    and standardised numbers (missing → the learning median). Only the learning part sets them."""
    parts = []
    for c in cats:
        col = feats[c].astype("object").where(feats[c].notna(), "missing").astype(str)
        counts = col[learn].value_counts()
        keep = set(counts[counts >= 20].index)
        col = col.where(col.isin(keep), "other")
        parts.append(pd.get_dummies(col, prefix=c, dtype=float).to_numpy())
    for c in nums:
        v = feats[c].astype(float)
        v = v.fillna(v[learn].median())
        sd = v[learn].std() or 1.0
        parts.append(((v - v[learn].mean()) / sd).to_numpy()[:, None])
    return np.hstack(parts)


def picker_scores(feats_test: pd.DataFrame, p_logistic: np.ndarray, p_opslens: np.ndarray) -> dict[str, np.ndarray]:
    """Higher score = fast-track first. Ties are broken oldest first by pick_daily."""
    level = feats_test["priority_raw"].str[0].astype(float).to_numpy()   # "3 - Moderate" → 3
    state = feats_test["state_now"]
    unassigned = (state.isna() | (state == "New")).to_numpy().astype(float)  # no event yet = nobody on it
    return {"priority": -level, "unassigned": unassigned, "oldest": np.zeros(len(feats_test)),
            "logistic": np.asarray(p_logistic, dtype=float), "opslens": np.asarray(p_opslens, dtype=float)}


def pick_daily(day: np.ndarray, created: np.ndarray, score: np.ndarray, share_pct: float) -> np.ndarray:
    """Each day, pick round(share × that day's count) incidents: highest score first, ties oldest first.
    Example: a day with 7 incidents, share 30% → 2.1 → 2 picked; a day with 5 → 1.5 → 2."""
    order = np.lexsort((created, -score, day))           # last key is the main one: day, then score, then age
    day_sorted = day[order]
    starts = np.r_[0, np.flatnonzero(day_sorted[1:] != day_sorted[:-1]) + 1]
    sizes = np.diff(np.r_[starts, len(day_sorted)])
    rank = np.arange(len(day_sorted)) - np.repeat(starts, sizes)
    budget = np.floor(share_pct / 100.0 * sizes + 0.5).astype(int)   # rounded half up
    picked = np.zeros(len(day), dtype=bool)
    picked[order] = rank < np.repeat(budget, sizes)
    return picked


# ---- 5. Bootstrap over weeks -----------------------------------------------------------------

def week_totals(weeks: np.ndarray, columns: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Sum of each column per week (weeks in order of first appearance)."""
    codes, uniques = pd.factorize(weeks)
    return {name: np.bincount(codes, weights=np.asarray(v, dtype=float), minlength=len(uniques)) for name, v in columns.items()}


def bootstrap_ci(totals: dict[str, np.ndarray], plus: str, minus: str | None, scale: float, seed: int = 0) -> tuple[float, float]:
    """95% percentile interval of scale × (Σ plus − Σ minus) ÷ Σ n when whole weeks are resampled
    with replacement. The same seed draws the same weeks for every picker, so differences are paired.
    Example: 2 weeks with n = 100, 300 and saved = 10, 20: one draw (week 2, week 2) gives
    scale × 40 ÷ 600; with scale = 400 incidents that is 26.7 saved."""
    n_weeks = len(totals["n"])
    draws = np.random.default_rng(seed).integers(0, n_weeks, size=(N_BOOT, n_weeks))
    top = totals[plus][draws].sum(axis=1)
    if minus is not None:
        top = top - totals[minus][draws].sum(axis=1)
    values = scale * top / totals["n"][draws].sum(axis=1)
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


# ---- The benchmark ----------------------------------------------------------------------------

def deadline_rule(incidents: pd.DataFrame, states: pd.DataFrame, learn, check, test) -> dict:
    """Learn both candidate clocks on `learn`, pick one on `check`, report the match everywhere."""
    hours = incidents["resolution_min"].to_numpy() / 60.0
    st = states.reindex(incidents["ticket_id"]).fillna(0.0)
    waits = np.zeros(len(incidents))
    for c in ("waiting for the user", "waiting for a vendor", "waiting for another fix"):
        if c in st:
            waits = waits + st[c].to_numpy()
    priority = incidents["priority_raw"].astype(str).to_numpy()
    flag = incidents["breached"].to_numpy().astype(bool)
    candidates = {}
    for name, clock in (("resolution time", hours), ("resolution time with waits on others paused", hours - waits)):
        limits = learn_limits(clock, priority, flag, learn)
        candidates[name] = {"limits_h": limits, "match_pct": {part: rule_match_pct(clock, priority, flag, m, limits)
                                                             for part, m in (("learn", learn), ("check", check), ("test", test))}}
    chosen = max(candidates, key=lambda n: candidates[n]["match_pct"]["check"])
    left = test & np.isin(priority, LEFT_OUT_PRIORITIES)
    return {"chosen_on_check": chosen, "limits_h": candidates[chosen]["limits_h"], "match_pct": candidates[chosen]["match_pct"],
            "candidates": candidates, "hours": hours, "priority": priority, "flag": flag,
            "left_out": {"priorities": LEFT_OUT_PRIORITIES, "test_incidents": int(left.sum()),
                         "flag_missed_pct": float(flag[left].mean() * 100) if left.any() else 0.0,
                         "why": "The company flags almost every Critical or High incident as missed, however fast it was "
                                "resolved, so no deadline rule can score them. A desk fast-tracks them anyway; they are "
                                "left out of the benchmark (and of every picker's budget)."}}


def fasttrack_benchmark(incidents: pd.DataFrame, events: pd.DataFrame, states: pd.DataFrame, feats: pd.DataFrame,
                        p_opslens_test: np.ndarray, cats: list[str], nums: list[str], learn, check, test) -> dict:
    """Every picker at every budget on the test months, the ceiling, CIs, and the pre-registered rule."""
    rule = deadline_rule(incidents, states, learn, check, test)
    hours, priority, flag, limits = rule["hours"], rule["priority"], rule["flag"], rule["limits_h"]
    wait = pickup_wait_after(incidents, events)
    p_log, c_chosen, c_auc = logistic_scores(feats, cats, nums, learn, check, test)

    pool = np.isin(priority[test], SCORED_PRIORITIES)          # test incidents in the benchmark
    inc_t = incidents[test].reset_index(drop=True)[pool].reset_index(drop=True)
    feats_t = feats[test].reset_index(drop=True)[pool].reset_index(drop=True)
    h, pr, w = hours[test][pool], priority[test][pool], wait[test][pool]
    scored = ~np.isnan(h)
    base_miss = missed_by_rule(h, pr, limits)
    after_miss = missed_by_rule(h - w, pr, limits)
    savable = base_miss & ~after_miss
    scores = picker_scores(feats_t, p_log[pool], np.asarray(p_opslens_test)[pool])

    day = inc_t["created_at"].dt.normalize().to_numpy().astype("int64")
    created = inc_t["created_at"].to_numpy().astype("int64")
    weeks = inc_t["created_at"].dt.to_period("W").astype(str).to_numpy()
    n_pool, n_miss = int(len(inc_t)), int(base_miss.sum())
    picks = {(b, p): pick_daily(day, created, scores[p], b) for b in BUDGETS for p in PICKERS}

    totals = week_totals(weeks, {"n": np.ones(n_pool), **{f"{b}_{p}": savable & picks[(b, p)] for b in BUDGETS for p in PICKERS}})
    results = {}
    for b in BUDGETS:
        results[str(b)] = {}
        for p in PICKERS:
            chosen = picks[(b, p)]
            saved = int((savable & chosen).sum())
            low, high = bootstrap_ci(totals, f"{b}_{p}", None, n_pool)
            results[str(b)][p] = {"picked": int(chosen.sum()), "saved": saved, "ci_low": low, "ci_high": high,
                                  "saved_pct_of_misses": 100.0 * saved / max(n_miss, 1),
                                  "missed_pct_after": 100.0 * (n_miss - saved) / max(int(scored.sum()), 1),
                                  "pickup_hours_saved": float(w[chosen & scored].sum()),
                                  "hit_rate_pct": 100.0 * saved / max(int(chosen.sum()), 1)}
    vs = {}
    for b in BUDGETS:
        vs[str(b)] = {}
        for p in PICKERS:
            if p == "opslens":
                continue
            low, high = bootstrap_ci(totals, f"{b}_opslens", f"{b}_{p}", n_pool)
            vs[str(b)][p] = {"diff": results[str(b)]["opslens"]["saved"] - results[str(b)][p]["saved"], "ci_low": low, "ci_high": high}
    others = {p: results[str(RULE_BUDGET)][p]["saved"] for p in PICKERS if p != "opslens"}
    best_other = max(others, key=others.get)
    d = vs[str(RULE_BUDGET)][best_other]
    passed = bool(d["diff"] > 0 and d["ci_low"] > 0)

    ceiling_saved = int(savable.sum())
    busy = pd.Series(weeks).value_counts()
    busy = sorted(busy[busy >= 100].index)
    by_week = []
    for wk in busy:
        in_week = weeks == wk
        by_week.append({"week": wk, "incidents": int(in_week.sum()), "missed": int((base_miss & in_week).sum()),
                        "saved": {p: int((savable & picks[(RULE_BUDGET, p)] & in_week).sum()) for p in PICKERS}})
    wins = sum(1 for row in by_week if row["saved"]["opslens"] > row["saved"][best_other])

    return {
        "question": "If the desk can fast-track 10%, 20% or 30% of each day's new incidents at their 1-hour mark, "
                    "whose pick saves more missed deadlines?",
        "assumption": ASSUMPTION,
        "deadline_rule": {"chosen_on_check": rule["chosen_on_check"], "limits_h": limits, "match_pct": rule["match_pct"],
                          "candidates": rule["candidates"], "left_out": rule["left_out"]},
        "pickup": {"definition": "Pickup = the first event in a state other than New. New straight to Resolved: no pickup "
                                 "recorded, the New time includes the fix, so no wait is counted (understates savings).",
                   "new_to_resolved_pct": new_to_resolved_pct(incidents, events, test & np.isin(priority, SCORED_PRIORITIES)),
                   "waited_after_1h_pct": float((w[scored] > 0).mean() * 100)},
        "population": {"test_incidents": n_pool, "scored": int(scored.sum()), "no_resolution_time": int((~scored).sum()),
                       "missed_by_rule": n_miss, "missed_by_rule_pct": 100.0 * n_miss / max(int(scored.sum()), 1),
                       "missed_by_flag_pct": float(np.asarray(inc_t["breached"], dtype=float)[scored].mean() * 100),
                       "weeks": int(len(set(weeks))), "busy_weeks": len(busy)},
        "ceiling": {"saved": ceiling_saved, "saved_pct_of_misses": 100.0 * ceiling_saved / max(n_miss, 1),
                    "missed_pct_after": 100.0 * (n_miss - ceiling_saved) / max(int(scored.sum()), 1),
                    "pickup_hours_saved": float(w[scored].sum())},
        "pickers": [{"id": p, "label": PICKER_LABELS[p]} for p in PICKERS],
        "logistic": {"C": c_chosen, "check_auc": c_auc},
        "budgets": BUDGETS,
        "results": results,
        "opslens_minus": vs,
        "rule": {"text": "OpsLens's pick is better only if it saves more misses than the best other picker at the 20% "
                         "budget, with a 95% CI (whole test weeks resampled) excluding 0.",
                 "budget": RULE_BUDGET, "best_other": best_other, "diff": d["diff"], "ci_low": d["ci_low"],
                 "ci_high": d["ci_high"], "passed": passed},
        "by_week": by_week,
        "busy_weeks_opslens_ahead_of_best_other": wins,
    }


def new_to_resolved_pct(incidents: pd.DataFrame, events: pd.DataFrame, mask: np.ndarray) -> float:
    """% of incidents in `mask` that went from New straight to Resolved/Closed (no pickup recorded)."""
    later = events[events["incident_state"] != "New"].groupby("number").head(1).set_index("number")["incident_state"]
    first = events.groupby("number").head(1).set_index("number")["incident_state"]
    ids = incidents.loc[mask, "ticket_id"]
    straight = first.reindex(ids).eq("New") & later.reindex(ids).isin(["Resolved", "Closed"])
    return float(straight.mean() * 100)


def impact(ft: dict) -> dict:
    """The problem statement's three headings for the real desk, from the fast-track benchmark."""
    b = str(RULE_BUDGET)
    ops, desk = ft["results"][b]["opslens"], ft["results"][b]["priority"]
    pop = ft["population"]
    return {
        "budget_pct": RULE_BUDGET,
        "assumption": ft["assumption"],
        "turnaround": {"pickup_hours_saved_opslens": ops["pickup_hours_saved"], "pickup_hours_saved_priority": desk["pickup_hours_saved"],
                       "misses_avoided_opslens": ops["saved"], "misses_avoided_priority": desk["saved"],
                       "misses_avoided_ceiling": ft["ceiling"]["saved"],
                       "ci_opslens": [ops["ci_low"], ops["ci_high"]]},
        "productivity": {"claim": None,
                         "text": "No claim. Fast-tracking moves the same work earlier; the log cannot show whether agents "
                                 "would close more incidents per hour."},
        "service_quality": {"met_deadline_pct_as_it_happened": 100.0 - pop["missed_by_rule_pct"],
                            "met_deadline_pct_opslens": 100.0 - ops["missed_pct_after"],
                            "met_deadline_pct_priority": 100.0 - desk["missed_pct_after"],
                            "met_deadline_pct_ceiling": 100.0 - ft["ceiling"]["missed_pct_after"]},
        "money": {"shown": False, "why": "No cost per missed deadline exists for this desk (config/impact.yaml is not "
                                         "part of the project), and we do not invent one."},
    }
