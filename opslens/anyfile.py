"""OpsLens on your file: what OpsLens would have changed, on any relevant CSV of work items.

What it does: a judge (or any company) uploads an export with one row per work item (a support
ticket, an incident, a delivery order) and says which column is which. OpsLens then:
  1. checks the file is relevant: start times, an end or a duration, a way to tell a miss, and
     enough items and days to learn from (otherwise it says exactly what is missing);
  2. learns on the first 70% of items (by start time) and scores the last 30% once;
  3. reports early warning (the chance each item misses, known the moment it opens, with reasons)
     against the file's own priority field and a rule of thumb; "shadow mode" on the busiest
     later day (how many real misses each one flagged, same number of flags); and problem cards
     found on the first 70%, each checked again on the last 30%.

Why it is built this way: a log records what happened under ONE way of working. It cannot be
replayed under another policy without the work times, rosters and skills it does not contain
(our real-desk twin failed its gate for exactly that reason). So this module answers the honest
question a log CAN answer: which items OpsLens would have warned about in time, and where the
recurring problems are, scored on items it never learned from.

No leakage: a feature for an item may only use what was known when it opened. Three guards:
column-name rules (resolved, closed, sla, duration... are never features), the person mapping
the file can untick any column, and a screen that drops any column which alone predicts the
outcome almost perfectly on the learning items (AUC above 0.97: it was written after the fact).

Example (UCI ServiceNow log, one row per incident, 24,918 rows): learn on 17,442, score 7,476;
early-warning AUC well above the priority field's; on the busiest later day OpsLens's top 20%
catch more of the real misses than the priority field's top 20%.
"""

from __future__ import annotations

import re
import time
from typing import Callable

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

MIN_ROWS = 500
MIN_DAYS = 7
MIN_MISSES = 30
LEARN_SHARE = 0.70
FLAG_SHARE = 0.20
LEAK_AUC = 0.97
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# Column names that describe what happened AFTER an item opened; never used as features.
# A word in the name that starts with one of these marks the column (so "end" catches "ended_at"
# but not "vendor"; "sla" catches "sla_met" but not "slab").
AFTER_WORDS = ("resolv", "close", "reopen", "transfer", "reassign", "sla", "made", "breach", "duration",
               "taken", "wait", "handled", "resolution", "events", "updated", "mod", "status", "state",
               "outcome", "deliver", "pickup", "picked", "response", "responded", "assigned", "end", "ended",
               "finish", "rating", "satisf", "csat", "feedback", "solved", "escalat", "knowledge", "confirm")
Progress = Callable[[str], None]


# ---- 1. Reading and mapping the file -----------------------------------------------------------

COMMON_FORMATS = ["%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",
                  "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S"]


def parse_times(values: pd.Series) -> pd.Series:
    """ISO first; then the common day-first and month-first layouts, tried on a sample so the whole
    column is parsed with one fast format; finally pandas' slow "mixed" parser (day first).

    Example: "12-02-2022 21:55" -> 12 Feb 2022 21:55 ("%d-%m-%Y %H:%M"); "29/2/2016 01:16" -> 29 Feb 2016.
    """
    text = values.astype(str).str.strip()
    sample = text[values.notna() & ~text.str.lower().str.contains("nan|nat|none", regex=True)].head(500)
    # Every layout is tried on 500 values first: on a non-ISO column, pandas' ISO attempt falls back to
    # a slow row-by-row parser (seconds on 45k rows).
    if len(sample) and pd.to_datetime(sample, errors="coerce", format="ISO8601").notna().mean() >= 0.9:
        return pd.to_datetime(values, errors="coerce", format="ISO8601")
    for fmt in COMMON_FORMATS:
        if len(sample) and pd.to_datetime(sample, errors="coerce", format=fmt).notna().mean() >= 0.8:
            parsed = pd.to_datetime(text, errors="coerce", format=fmt)
            rest = parsed.isna() & values.notna()  # the few odd rows get the slow parser, not all of them
            if rest.any():
                parsed[rest] = pd.to_datetime(values[rest], errors="coerce", dayfirst=True, format="mixed")
            return parsed
    return pd.to_datetime(values, errors="coerce", dayfirst=True, format="mixed")


def clock_text(values: pd.Series) -> pd.Series:
    """A time-of-day column as "HH:MM" text. Spreadsheet exports sometimes store it as a fraction of a
    day: 0.458333333 -> "11:00", 0.958333333 -> "23:00"; "21:55" stays "21:55"."""
    text = values.astype(str).str.strip()
    number = pd.to_numeric(text, errors="coerce")
    fraction = number.notna() & (number >= 0) & (number < 1)
    if fraction.any():
        minutes = (number[fraction] * 1440).round().astype(int)
        text[fraction] = [f"{m // 60:02d}:{m % 60:02d}" for m in minutes]
    return text.where(values.notna(), None)


def column_kind(values: pd.Series) -> str:
    """time / number / category / id / text, from a sample of the column."""
    sample = values.dropna().astype(str).str.strip()
    sample = sample[sample != ""].head(300)
    if sample.empty:
        return "empty"
    if pd.to_numeric(sample, errors="coerce").notna().mean() >= 0.95:
        return "number"
    if sample.str.contains(r"\d").mean() >= 0.9 and parse_times(sample).notna().mean() >= 0.9:
        return "time"
    unique_share = values.nunique(dropna=True) / max(1, values.notna().sum())
    if sample.str.len().mean() > 40:
        return "text"
    if unique_share > 0.5 and values.nunique() > 200:
        return "id"
    return "category"


def known_at_open(name: str) -> bool:
    """False for column names that describe what happened after an item opened.

    Example: "reassignment_count" -> False, "Time_taken(min)" -> False, "vendor" -> True.
    """
    words = [w for w in re.split(r"[^a-z0-9]+", name.lower()) if w]
    return not any(w == a or (len(a) >= 4 and w.startswith(a)) for w in words for a in AFTER_WORDS)


def peek(raw: pd.DataFrame) -> dict:
    """What the mapping form needs: each column's kind, a few values, and a suggested mapping.

    Example: a UCI one-row export -> created_at = opened_at, resolved_at = resolved_at,
    priority = priority, team = assignment_group, sla_met = made_sla; features = category, ...
    """
    columns = []
    for name in raw.columns:
        kind = column_kind(raw[name])
        columns.append({"name": str(name), "kind": kind, "unique": int(raw[name].nunique()),
                        "examples": [str(v) for v in raw[name].dropna().astype(str).unique()[:3]],
                        "feature": kind in ("number", "category") and known_at_open(str(name))})
    return {"rows": int(len(raw)), "columns": columns, "suggested": suggest_mapping(raw, columns)}


GUESSES = {
    "id": ["ticket_id", "id", "number", "case_id", "incident_id", "order_id", "id_"],
    "created_at": ["created_at", "opened_at", "created", "open_time", "order_date", "start", "sys_created_at"],
    "created_time": ["time_orderd", "time_ordered", "created_time", "open_hour"],
    "resolved_at": ["resolved_at", "closed_at", "resolved", "close_time", "end_time", "delivered_at"],
    "duration_min": ["time_taken(min)", "time_taken", "duration_min", "duration", "resolution_min"],
    "sla_met": ["made_sla", "sla_met", "within_sla", "on_time"],
    "due_at": ["due_at", "due", "deadline", "sla_due"],
    "priority": ["priority", "severity", "urgency"],
    "team": ["assignment_group", "team", "queue", "group", "first_team", "city"],  # never a "resolved by" column
    "category": ["category", "type", "issue_type", "type_of_order", "final_category"],
}


def suggest_mapping(raw: pd.DataFrame, columns: list[dict]) -> dict[str, str]:
    # Compare names without case, spaces or underscores: "Time_taken (min)" matches "time_taken(min)".
    squash = lambda name: re.sub(r"[\s_]+", "", str(name).lower())  # noqa: E731
    lower = {squash(c): c for c in raw.columns}
    out = {}
    for key, names in GUESSES.items():
        for guess in names:
            guess = squash(guess)
            if guess in lower:
                out[key] = lower[guess]
                break
    return out


# ---- 2. Building the work items ---------------------------------------------------------------

def truthy(values: pd.Series) -> pd.Series:
    return values.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y", "met", "on time"})


def priority_rank(values: pd.Series) -> pd.Series:
    """0 = most urgent. P1/P2/P3, "1 - Critical", "high/medium/low" all work.

    Example: ["3 - Moderate", "1 - Critical", "4 - Low"] -> [1, 0, 2].
    """
    labels = values.astype(str).str.strip()
    words = {"critical": 0, "urgent": 0, "high": 1, "medium": 2, "normal": 2, "moderate": 2, "low": 3}
    lowered = labels.str.lower()
    if lowered.isin(words).mean() >= 0.9:
        ranks = lowered.map(words)
    else:
        levels = sorted(labels.unique(), key=lambda v: (pd.to_numeric("".join(ch for ch in v if ch.isdigit())[:2] or "nan", errors="coerce"), v))
        ranks = labels.map({v: i for i, v in enumerate(levels)})
    return pd.to_numeric(ranks, errors="coerce")


def build_items(raw: pd.DataFrame, m: dict, target_min: float | None) -> tuple[pd.DataFrame, list[str]]:
    """One row per work item: start, end, missed, and the columns the person mapped.

    The miss comes from (in this order) an "SLA met" column, a due time, or a promised time in
    minutes typed in the form (the same for every item, or per priority if a priority column exists).
    """
    notes: list[str] = []
    created = raw[m["created_at"]].astype(str)
    if m.get("created_time"):
        created = created + " " + clock_text(raw[m["created_time"]])
    items = pd.DataFrame({"created_at": parse_times(created)})
    items["id"] = raw[m["id"]].astype(str) if m.get("id") else [f"row {i + 1}" for i in range(len(raw))]
    if m.get("resolved_at"):
        items["end_at"] = parse_times(raw[m["resolved_at"]])
    elif m.get("duration_min"):
        minutes = pd.to_numeric(raw[m["duration_min"]].astype(str).str.extract(r"([\d.]+)")[0], errors="coerce")
        items["end_at"] = items["created_at"] + pd.to_timedelta(minutes, unit="min")
    else:
        raise ValueError("map either an end time (resolved / closed) or a duration in minutes")
    items["duration_min"] = (items["end_at"] - items["created_at"]).dt.total_seconds() / 60.0
    if m.get("priority"):
        items["priority"] = raw[m["priority"]].astype(str)
        items["priority_rank"] = priority_rank(raw[m["priority"]])
    for key in ("team", "category"):
        if m.get(key):
            items[key] = raw[m[key]].astype(str).fillna("(blank)")
    if m.get("sla_met"):
        items["missed"] = ~truthy(raw[m["sla_met"]])
        notes.append(f"A miss is the file's own \"{m['sla_met']}\" column.")
    elif m.get("due_at"):
        due = parse_times(raw[m["due_at"]])
        items["missed"] = items["end_at"] > due
        notes.append(f"A miss is finishing after \"{m['due_at']}\".")
    elif target_min:
        items["missed"] = items["duration_min"] > float(target_min)
        notes.append(f"A miss is taking longer than the promised {float(target_min):g} minutes you entered.")
    else:
        raise ValueError("tell OpsLens what a miss is: an SLA-met column, a due time, or a promised time in minutes")
    if m.get("sla_met"):
        # The file says whether each item missed, so an item without an end is still known: it
        # counts as open until the last moment in the file (for the "open when it arrived" counts).
        last = items["end_at"].max()
        unended = items["end_at"].isna() & items["created_at"].notna()
        if unended.any():
            items.loc[unended, "end_at"] = max(last, items["created_at"].max())
            notes.append(f"{int(unended.sum())} items have no end in the file; they count as still open at its end.")
        items["duration_min"] = (items["end_at"] - items["created_at"]).dt.total_seconds() / 60.0
    items = add_features(items, raw, m)
    before = len(items)
    items = items.dropna(subset=["created_at", "end_at"]).sort_values("created_at").reset_index(drop=True)
    if len(items) < before:
        notes.append(f"{before - len(items)} rows without a readable start or end were left out.")
    return items, notes


def add_features(items: pd.DataFrame, raw: pd.DataFrame, m: dict) -> pd.DataFrame:
    """The columns the person ticked as known when an item opens (never the mapped outcome ones)."""
    outcome = {m.get(k) for k in ("resolved_at", "duration_min", "sla_met", "due_at", "id", "created_at", "created_time")}
    for name in m.get("features", []):
        if name in outcome or name not in raw.columns:
            continue
        values = raw[name]
        if column_kind(values) == "number":
            items[f"f:{name}"] = pd.to_numeric(values.astype(str).str.extract(r"(-?[\d.]+)")[0], errors="coerce")
        else:
            top = values.astype(str).value_counts().index[:40]
            items[f"f:{name}"] = values.astype(str).where(values.astype(str).isin(top), "(other)")
    return items


def relevance_problems(items: pd.DataFrame) -> list[str]:
    """Why a file cannot be learned from, in plain words (an empty list means it can)."""
    problems = []
    if len(items) < MIN_ROWS:
        problems.append(f"only {len(items)} usable rows; OpsLens needs at least {MIN_ROWS} to learn from")
    days = items["created_at"].dt.normalize().nunique() if len(items) else 0
    if days < MIN_DAYS:
        problems.append(f"the items cover {days} days; OpsLens needs at least {MIN_DAYS} to learn and then test")
    if len(items) and (items["duration_min"] < 0).mean() > 0.1:
        problems.append("more than 1 in 10 items end before they start: check the start and end columns")
    misses = int(items["missed"].sum()) if len(items) else 0
    if misses < MIN_MISSES or len(items) - misses < MIN_MISSES:
        problems.append(f"{misses} misses out of {len(items)} items; OpsLens needs at least {MIN_MISSES} misses and {MIN_MISSES} in time")
    return problems


# ---- 3. Features known at the moment an item opens --------------------------------------------

def open_counts(created: np.ndarray, ended: np.ndarray) -> np.ndarray:
    """For each item, how many items were open at the moment it opened (opened before, not ended).

    Uses only the past: an item counts as open at t if it started before t and its end is after t,
    which is known at t (it has not ended yet). Example: starts [0, 1, 2], ends [5, 1.5, 9] -> [0, 1, 1].
    """
    starts = np.sort(created)
    ends = np.sort(ended)
    opened_before = np.searchsorted(starts, created, side="left")
    ended_before = np.searchsorted(ends, created, side="right")
    return np.maximum(opened_before - ended_before, 0)


def feature_frame(items: pd.DataFrame) -> pd.DataFrame:
    """Model inputs: time of day, weekday, load when it opened, urgency, and the ticked columns."""
    t = items["created_at"].astype("int64").to_numpy() / 6e10  # minutes
    e = items["end_at"].astype("int64").to_numpy() / 6e10
    X = pd.DataFrame(index=items.index)
    X["opened at hour"] = items["created_at"].dt.hour
    X["weekday"] = items["created_at"].dt.weekday
    X["open when it arrived"] = open_counts(t, e)
    X["arrived in the hour before"] = np.arange(len(t)) - np.searchsorted(t, t - 60, side="left")
    if "team" in items:
        X["open in its team"] = 0
        for _, idx in items.groupby("team").groups.items():
            rows = np.asarray(idx)
            X.loc[rows, "open in its team"] = open_counts(t[rows], e[rows])
    if "priority_rank" in items:
        X["priority"] = items["priority_rank"]
    for key in ("team", "category"):
        if key in items:
            X[key] = items[key].astype("category")
    for col in [c for c in items.columns if c.startswith("f:")]:
        values = items[col]
        X[col[2:]] = values if pd.api.types.is_numeric_dtype(values) else values.astype("category")
    return X


def leak_screen(X: pd.DataFrame, y: np.ndarray, learn: np.ndarray) -> tuple[pd.DataFrame, list[str]]:
    """Drop any column that alone predicts the miss almost perfectly on the learning items."""
    dropped = []
    target = y[learn]
    for col in list(X.columns):
        values = X.loc[learn, col]
        if hasattr(values, "cat"):  # a category: how well its past miss rates sort the items
            score = pd.Series(target).groupby(values.astype(str).to_numpy()).transform("mean").to_numpy()
        else:                       # a number: how well the number itself sorts them (either way round)
            score = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
        ok = ~np.isnan(score)
        if ok.sum() < 50 or len(np.unique(target[ok])) < 2:
            continue
        auc = roc_auc_score(target[ok], score[ok])
        if max(auc, 1 - auc) > LEAK_AUC:
            dropped.append(col)
    return X.drop(columns=dropped), dropped


# ---- 4. Learn on the first 70%, score the last 30% ---------------------------------------------

def split_masks(n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """learn = first 70% by start time (its last fifth is the check part), test = the rest."""
    cut = int(n * LEARN_SHARE)
    check_cut = int(cut * 0.8)
    idx = np.arange(n)
    return idx < check_cut, (idx >= check_cut) & (idx < cut), idx >= cut


PARAMS = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 40,
          "feature_fraction": 0.9, "bagging_fraction": 0.9, "bagging_freq": 1, "verbose": -1, "seed": 7}


def train_model(X: pd.DataFrame, y: np.ndarray, fit: np.ndarray, check: np.ndarray) -> lgb.Booster:
    """LightGBM with fixed settings (no search, so it is fast and nothing is tuned on the test part)."""
    train = lgb.Dataset(X[fit], y[fit])
    valid = lgb.Dataset(X[check], y[check], reference=train)
    return lgb.train(PARAMS, train, num_boost_round=400, valid_sets=[valid],
                     callbacks=[lgb.early_stopping(30, verbose=False)])


def rule_of_thumb(items: pd.DataFrame, X: pd.DataFrame, y: np.ndarray, learn: np.ndarray) -> tuple[str, np.ndarray]:
    """The simplest honest rival: 'this kind of item was late X% of the time before', using the one
    column (chosen on the learning items) whose past miss rates rank the learning items best."""
    best, best_auc, best_scores = "", 0.0, np.full(len(items), y[learn].mean())
    for col in X.columns:
        if not hasattr(X[col], "cat"):
            continue
        rates = pd.Series(y[learn]).groupby(X.loc[learn, col].astype(str).to_numpy()).mean()
        scores = X[col].astype(str).map(rates).fillna(y[learn].mean()).to_numpy()
        auc = roc_auc_score(y[learn], scores[learn])
        if auc > best_auc:
            best, best_auc, best_scores = col, auc, scores
    return best, best_scores


# ---- 5. Early warning: flag 1 item in 5 as it opens; how many real misses does each one catch? --

def flags_by_day(day: np.ndarray, score: np.ndarray, share: float = FLAG_SHARE) -> np.ndarray:
    """Each day, flag the top `share` of that day's items by score (the same budget for every picker).

    Ties break by position, so a constant score (no information) flags the day's first items.
    Example: one day of 10 items, share 0.2 -> the 2 highest scores are flagged.
    """
    flagged = np.zeros(len(score), dtype=bool)
    for d in np.unique(day):
        rows = np.flatnonzero(day == d)
        k = max(1, int(round(share * len(rows))))
        order = rows[np.argsort(-score[rows], kind="stable")]
        flagged[order[:k]] = True
    return flagged


def day_diff_ci(day: np.ndarray, caught_a: np.ndarray, caught_b: np.ndarray, missed: np.ndarray,
                n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% interval of (share of misses caught by A) - (by B), in points, resampling whole days."""
    days = np.unique(day)
    per_day = np.array([[caught_a[day == d].sum(), caught_b[day == d].sum(), missed[day == d].sum()] for d in days])
    rng = np.random.default_rng(seed)
    draws = per_day[rng.integers(0, len(days), size=(n_boot, len(days)))].sum(axis=1)
    gaps = 100.0 * (draws[:, 0] - draws[:, 1]) / np.maximum(draws[:, 2], 1)
    return float(np.percentile(gaps, 2.5)), float(np.percentile(gaps, 97.5))


def describe(name: str, value, item: pd.Series) -> str:
    """One model input in plain words. Example: ("open in its team", 31) -> "31 open in its team"."""
    if name == "opened at hour":
        return f"opened at {int(value):02d}:00"
    if name == "weekday":
        return f"opened on a {WEEKDAYS[int(value)]}"
    if name in ("open when it arrived", "arrived in the hour before", "open in its team"):
        return f"{int(value)} {name}"
    if name == "priority":
        return f"priority {item.get('priority', value)}"
    if isinstance(value, (int, float, np.floating, np.integer)) and not isinstance(value, bool):
        return f"{name} {float(value):g}"
    return f"{name}: {value}"


def reasons(booster: lgb.Booster, X: pd.DataFrame, items: pd.DataFrame, rows: np.ndarray) -> list[list[dict]]:
    """Top 3 pushes towards a miss per item, from LightGBM's own TreeSHAP split of the prediction."""
    contrib = booster.predict(X.iloc[rows], pred_contrib=True)[:, :-1]
    out = []
    for r, c in zip(rows, contrib):
        positive = np.clip(c, 0, None)
        total = positive.sum() or 1.0
        top = np.argsort(-c)[:3]
        out.append([{"text": describe(X.columns[j], X.iloc[r, j], items.iloc[r]), "share": round(float(positive[j] / total), 2)}
                    for j in top if c[j] > 0])
    return out


def early_warning(items: pd.DataFrame, X: pd.DataFrame, y: np.ndarray, test: np.ndarray,
                  scores: dict[str, np.ndarray], booster: lgb.Booster) -> dict:
    """AUC per picker on the later 30%, and the share of real misses each one's flags catch."""
    day = items["created_at"].dt.normalize().to_numpy()
    out = {"auc": {}, "caught_pct": {}, "misses": int(y[test].sum()), "items": int(test.sum())}
    caught = {}
    for name, score in scores.items():
        out["auc"][name] = round(float(roc_auc_score(y[test], score[test])), 3)
        flagged = flags_by_day(day[test], score[test])
        caught[name] = flagged & (y[test] == 1)
        out["caught_pct"][name] = round(100.0 * float(caught[name].sum()) / max(1, int(y[test].sum())), 1)
    rival = "priority" if "priority" in scores else "rule"
    lo, hi = day_diff_ci(day[test], caught["opslens"], caught[rival], y[test] == 1)
    out["vs"] = {"rival": rival, "gap_pts": round(float(out["caught_pct"]["opslens"] - out["caught_pct"][rival]), 1),
                 "ci": [round(lo, 1), round(hi, 1)]}
    test_rows = np.flatnonzero(test)
    top = test_rows[np.argsort(-scores["opslens"][test_rows])[:8]]
    why = reasons(booster, X, items, top)
    out["at_risk"] = [{"id": str(items.at[r, "id"]), "opened": str(items.at[r, "created_at"])[:16],
                       "risk": round(float(scores["opslens"][r]), 3), "missed": bool(y[r]), "reasons": why[i]}
                      for i, r in enumerate(top)]
    return out


def shadow_day(items: pd.DataFrame, X: pd.DataFrame, y: np.ndarray, test: np.ndarray,
               scores: dict[str, np.ndarray], booster: lgb.Booster) -> dict:
    """The busiest later day, replayed: each picker flags 1 item in 5 as they open; who caught more
    of the misses that really happened? Nothing is changed: the outcomes are the file's own."""
    opened_day = items["created_at"].dt.normalize()
    busiest = opened_day[test].value_counts().idxmax()
    rows = np.flatnonzero(test & (opened_day == busiest).to_numpy())
    same_day = np.zeros(len(rows))
    result = {"date": str(busiest)[:10], "weekday": WEEKDAYS[busiest.weekday()], "items": int(len(rows)),
              "misses": int(y[rows].sum()), "flags": max(1, int(round(FLAG_SHARE * len(rows)))), "caught": {}}
    for name, score in scores.items():
        flagged = flags_by_day(same_day, score[rows])
        result["caught"][name] = int((flagged & (y[rows] == 1)).sum())
    order = rows[np.argsort(-scores["opslens"][rows])[:6]]
    why = reasons(booster, X, items, order)
    result["examples"] = [{"id": str(items.at[r, "id"]), "opened": str(items.at[r, "created_at"])[11:16],
                           "risk": round(float(scores["opslens"][r]), 3), "missed": bool(y[r]), "reasons": why[i]}
                          for i, r in enumerate(order)]
    return result


# ---- 6. Problem cards: found on the first 70%, checked again on the last 30% -------------------

def segment_columns(items: pd.DataFrame, X: pd.DataFrame) -> dict[str, np.ndarray]:
    """Every way to group items: the category columns, priority, time of day and weekday."""
    cols = {c: X[c].astype(str).to_numpy() for c in X.columns if hasattr(X[c], "cat")}
    if "priority" in items:
        cols["priority"] = items["priority"].astype(str).to_numpy()
    hour = items["created_at"].dt.hour
    cols["time of day"] = pd.cut(hour, [-1, 5, 11, 17, 23], labels=["night", "morning", "afternoon", "evening"]).astype(str).to_numpy()
    cols["weekday"] = items["created_at"].dt.weekday.map(dict(enumerate(WEEKDAYS))).to_numpy()
    return cols


def gap_ci(day: np.ndarray, y: np.ndarray, inside: np.ndarray, rest: np.ndarray, n_boot: int = 1000, seed: int = 0) -> tuple[float, float]:
    """95% interval of (miss % inside the group) - (miss % in the rest), resampling whole days."""
    days = np.unique(day[inside | rest])
    per_day = np.array([[y[inside & (day == d)].sum(), (inside & (day == d)).sum(),
                         y[rest & (day == d)].sum(), (rest & (day == d)).sum()] for d in days], dtype=float)
    rng = np.random.default_rng(seed)
    draws = per_day[rng.integers(0, len(days), size=(n_boot, len(days)))].sum(axis=1)
    gaps = 100.0 * (draws[:, 0] / np.maximum(draws[:, 1], 1) - draws[:, 2] / np.maximum(draws[:, 3], 1))
    return float(np.percentile(gaps, 2.5)), float(np.percentile(gaps, 97.5))


def problem_cards(items: pd.DataFrame, X: pd.DataFrame, y: np.ndarray, learn: np.ndarray, test: np.ndarray,
                  limit: int = 6) -> list[dict]:
    """Groups that miss far more often than the rest on the first 70%, then the same gap measured on
    the last 30% with a 95% interval over days ("still true later" only if it stays above zero).

    Example: team = Group 70 misses 61% vs 34% for the rest; later 58% vs 33%, gap +25 [18, 31] -> still true.
    """
    min_n = max(50, int(0.01 * learn.sum()))
    day = items["created_at"].dt.normalize().to_numpy()
    segments = segment_columns(items, X)
    found = []
    for col, v in segments.items():
        for value, n in pd.Series(v[learn]).value_counts().items():
            if n < min_n or value in ("nan", "(other)", "None"):
                continue
            rate, other = y[learn & (v == value)].mean(), y[learn & (v != value)].mean()
            if rate >= 1.3 * other and rate - other >= 0.03:
                found.append((n * (rate - other), col, value, rate, other, n))
    cards = []
    for excess, col, value, rate, other, n in sorted(found, key=lambda f: -f[0])[:limit]:
        v = segments[col]
        t_in, t_rest = test & (v == value), test & (v != value)
        if t_in.sum() < 10:
            continue
        lo, hi = gap_ci(day, y, t_in, t_rest)
        cards.append({"column": col, "value": str(value), "learn_pct": round(100 * rate, 1), "learn_rest_pct": round(100 * other, 1),
                      "learn_items": int(n), "excess_misses": round(float(excess), 1),
                      "test_pct": round(100 * float(y[t_in].mean()), 1), "test_rest_pct": round(100 * float(y[t_rest].mean()), 1),
                      "test_items": int(t_in.sum()), "gap_ci": [round(lo, 1), round(hi, 1)], "still_true": bool(lo > 0),
                      "examples": items.loc[t_in & (y == 1), "id"].astype(str).head(3).tolist()})
    return cards


# ---- 7. The whole report ----------------------------------------------------------------------

def floor_summary(items: pd.DataFrame) -> dict:
    """The plain facts of the file: size, dates, miss rate, how long items take, the worst groups."""
    d = items["duration_min"].clip(lower=0)
    out = {"items": int(len(items)), "from": str(items["created_at"].min())[:10], "to": str(items["created_at"].max())[:10],
           "days": int(items["created_at"].dt.normalize().nunique()), "missed_pct": round(100 * float(items["missed"].mean()), 1),
           "median_min": round(float(d.median()), 1), "p90_min": round(float(d.quantile(0.9)), 1)}
    for key in ("team", "category", "priority"):
        if key in items:
            g = items.groupby(key)["missed"].agg(["mean", "size"])
            g = g[g["size"] >= 30].sort_values("mean", ascending=False).head(6)
            out[f"by_{key}"] = [{"name": str(k), "items": int(r["size"]), "missed_pct": round(100 * float(r["mean"]), 1)}
                                for k, r in g.iterrows()]
    return out


CANNOT = [
    "Replay your floor under OpsLens's dispatch: that needs how long each item was actually worked on, "
    "who was on shift and who can handle what. A log records one way of working, not those.",
    "Say what would have happened to an item OpsLens flagged: every outcome shown is your file's own.",
]


def analyse(raw: pd.DataFrame, mapping: dict, target_min: float | None = None, progress: Progress | None = None) -> dict:
    """Run the whole report on one file. `progress(step)` is called as each step starts."""
    steps: list[dict] = []
    started = time.perf_counter()

    def step(name: str) -> None:
        now = time.perf_counter()
        if steps:
            steps[-1]["seconds"] = round(now - steps[-1].pop("_t"), 1)
        steps.append({"name": name, "_t": now})
        if progress:
            progress(name)

    step("Reading the file and the column mapping")
    items, notes = build_items(raw, mapping, target_min)
    step("Checking the file can be learned from")
    problems = relevance_problems(items)
    if problems:
        raise ValueError("This file cannot be analysed: " + "; ".join(problems) + ".")
    step("Building what was known when each item opened")
    y = items["missed"].to_numpy().astype(int)
    fit, check, test = split_masks(len(items))
    learn = fit | check
    X, dropped = leak_screen(feature_frame(items), y, learn)
    step("Learning on the first 70% of items")
    booster = train_model(X, y, fit, check)
    step("Scoring the last 30%, which it never saw")
    scores = {"opslens": booster.predict(X)}
    rule_col, scores["rule"] = rule_of_thumb(items, X, y, learn)
    if "priority_rank" in items and items["priority_rank"].notna().mean() > 0.9:
        scores["priority"] = -items["priority_rank"].fillna(items["priority_rank"].max()).to_numpy(dtype=float)
    warning = early_warning(items, X, y, test, scores, booster)
    step("Shadow mode on the busiest later day")
    shadow = shadow_day(items, X, y, test, scores, booster)
    step("Finding recurring problems, then checking them on later items")
    cards = problem_cards(items, X, y, learn, test)
    steps[-1]["seconds"] = round(time.perf_counter() - steps[-1].pop("_t"), 1)
    return {
        "summary": floor_summary(items), "notes": notes, "dropped_after_the_fact": dropped,
        "features": list(X.columns), "rule_column": rule_col,
        "learn": {"items": int(learn.sum()), "from": str(items.loc[learn, "created_at"].min())[:10],
                  "to": str(items.loc[learn, "created_at"].max())[:10]},
        "test": {"items": int(test.sum()), "from": str(items.loc[test, "created_at"].min())[:10],
                 "to": str(items.loc[test, "created_at"].max())[:10]},
        "warning": warning, "shadow": shadow, "cards": cards, "flag_share_pct": int(100 * FLAG_SHARE),
        "steps": steps, "seconds": round(time.perf_counter() - started, 1), "cannot": CANNOT,
    }
