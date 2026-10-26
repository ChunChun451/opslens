"""OpsLens on your file: what OpsLens would have changed, on any relevant CSV of work items.

What it does: a judge (or any company) uploads an export with one row per work item (a support
ticket, an incident, a delivery order). OpsLens guesses which column is which (start, end or
duration, what a miss is, priority, team, category) and says in plain words what it will do; the
person can change any guess. Then it:
  1. checks the file is relevant: start times, an end or a duration, a way to tell a miss, and
     enough items and days to learn from (otherwise it says exactly what is missing, and the fix);
  2. learns on the first 70% of items (by start time) and scores the last 30% once;
  3. reports early warning (the chance each item misses, known the moment it opens, with reasons)
     against the file's own priority field and a rule of thumb; "shadow mode" on the busiest
     later day, item by item so the screen can replay it; problem cards found on the first 70%,
     each checked again on the last 30%; and a week-ahead workload forecast per team. Anything
     that needs a column the file lacks says which one (`needs`) instead of staying blank.

Why it is built this way: a log records what happened under ONE way of working. It cannot be
replayed under another policy without the work times, rosters and skills it does not contain
(our real-desk twin failed its gate for exactly that reason). So this module answers the honest
questions a log CAN answer: which items OpsLens would have warned about in time, where the
recurring problems are, and how much work each team gets a week ahead, scored on items and days
it never learned from.

No leakage: a feature for an item may only use what was known when it opened. Three guards:
column-name rules (resolved, closed, sla, duration... are never features), the person mapping
the file can untick any column, and a screen that drops any column which alone predicts the
outcome almost perfectly on the learning items (AUC above 0.97: it was written after the fact).
The forecast for a day only reads counts from a week or more before that day.

Example (UCI ServiceNow log, one row per incident, 24,918 rows): learn on 17,442, score 7,476;
early-warning AUC 0.796 against 0.575 for the priority field; on the busiest later day (Thu 5 May
2016, 403 incidents) OpsLens's 81 flags catch 50 of the 111 real misses, the priority field's 22.
"""

from __future__ import annotations

import re
import time
from typing import Callable

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from opslens.forecast import wape

MIN_ROWS = 500
MIN_DAYS = 7
MIN_MISSES = 30
LEARN_SHARE = 0.70
FLAG_SHARE = 0.20
LEAK_AUC = 0.97
TIMELINE_MAX = 3000  # a shadow day with more items is summarised, not replayed item by item
FORECAST_DAYS = 56  # 8 weeks: the forecast reads 1 to 4 weeks back and needs days left to learn and to score
FORECAST_TEAMS = 8
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# Column names that describe what happened AFTER an item opened; never used as features.
# A word in the name that starts with one of these marks the column (so "end" catches "ended_at"
# but not "vendor"; "sla" catches "sla_met" but not "slab").
AFTER_WORDS = ("resolv", "close", "reopen", "transfer", "reassign", "sla", "made", "breach", "duration",
               "taken", "wait", "handled", "resolution", "events", "updated", "mod", "status", "state",
               "outcome", "deliver", "pickup", "picked", "response", "responded", "assigned", "end", "ended",
               "finish", "rating", "satisf", "csat", "feedback", "solved", "escalat", "knowledge", "confirm")
# What the person sees when a needed column is missing: one sentence and one fix.
NO_START = "OpsLens cannot tell when each item started: pick the column, or try another file."
NO_END = "This file has no time an item ended or took: tell OpsLens which column it is, or try another file."
NO_MISS = ("OpsLens does not know what a miss is in this file: type a promised time in minutes, or pick the "
           "column that says if an item was on time.")
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
    # A time has digits AND a date or clock separator: "T00042" (a ticket id) parses as ISO, but is not a time.
    if sample.str.contains(r"\d").mean() >= 0.9 and sample.str.contains(r"[-/:.\s]").mean() >= 0.9 \
            and parse_times(sample).notna().mean() >= 0.9:
        return "time"
    unique_share = values.nunique(dropna=True) / max(1, values.notna().sum())
    if sample.str.len().mean() > 40:
        return "text"
    if unique_share > 0.5 and values.nunique() > 200:
        return "id"
    return "category"


def name_words(name: str) -> list[str]:
    """The words of a column name, lower case: "Time_taken (min)" -> ["time", "taken", "min"]."""
    return [w for w in re.split(r"[^a-z0-9]+", str(name).lower()) if w]


def has_word(name: str, hints: tuple[str, ...]) -> bool:
    """True when a word of the name starts with a hint; hints under 4 letters must match a whole word.

    Example: ("Date Created", ("creat",)) -> True; ("vendor", ("end",)) -> False.
    """
    return any(w == h or (len(h) >= 4 and w.startswith(h)) for w in name_words(name) for h in hints)


def known_at_open(name: str) -> bool:
    """False for column names that describe what happened after an item opened.

    Example: "reassignment_count" -> False, "Time_taken(min)" -> False, "vendor" -> True.
    """
    return not has_word(name, AFTER_WORDS)


def peek(raw: pd.DataFrame) -> dict:
    """What the upload card needs before anything is learned: each column's kind and a few values,
    the suggested mapping (with the columns it would learn from), a 3-row preview, a question for
    each needed column it could not guess, and what will happen with the suggestion (check_mapping).

    Example: a UCI one-row export -> created_at = created_at, resolved_at = resolved_at,
    priority = priority, team = first_team, sla_met = made_sla; nothing to ask; plan: 24,918 items,
    a miss is the file's own made_sla column, learn on the first 17,442.
    """
    columns = []
    for name in raw.columns:
        kind = column_kind(raw[name])
        columns.append({"name": str(name), "kind": kind, "unique": int(raw[name].nunique()),
                        "examples": [str(v) for v in raw[name].dropna().astype(str).unique()[:3]],
                        "feature": kind in ("number", "category") and known_at_open(str(name))})
    suggested = suggest_mapping(raw, columns)
    suggested["features"] = [c["name"] for c in columns if c["feature"] and c["name"] not in suggested.values()]
    ask = questions(columns, suggested)
    return {"rows": int(len(raw)), "columns": columns, "suggested": suggested, "preview": preview_rows(raw),
            "ask": ask, "plan": None if ask else check_mapping(raw, suggested)}


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
# For a role still empty after the known names: the first column of this kind whose name has one
# of these words. Start, priority, team and category never take a name that sounds after the fact.
WORD_HINTS = {
    "id": (("id",), ("ticket", "case", "incident", "order", "number", "key", "ref")),
    "created_at": (("time",), ("creat", "open", "start", "submit", "report", "logged", "receiv", "raised", "arriv",
                               "placed", "order")),
    "resolved_at": (("time",), ("resolv", "close", "end", "finish", "complet", "deliver", "done", "solved", "fixed")),
    "duration_min": (("number",), ("duration", "minutes", "mins", "taken", "tat", "turnaround")),
    "due_at": (("time",), ("due", "deadline", "promised", "expected")),
    "priority": (("category", "number"), ("priorit", "severity", "urgency", "sev")),
    "team": (("category",), ("team", "group", "queue", "department", "desk")),
    "category": (("category",), ("categor", "type", "issue", "topic", "reason", "product", "service")),
}
ONE_END = {"resolved_at": "duration_min", "duration_min": "resolved_at"}  # either end is enough


def suggest_mapping(raw: pd.DataFrame, columns: list[dict]) -> dict[str, str]:
    """Known names first ("opened_at", "Time_taken(min)"...), compared without case, spaces or
    underscores; then, for a role still empty, a column of the right kind with a telling word in
    its name ("Date Created" is a start, "Closed On" an end, "SLA Breached" says it missed).

    Example: the Kaggle delivery export -> created_at Order_Date + created_time Time_Orderd,
    duration_min "Time_taken (min)", team City, category Type_of_order.
    """
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
    for key, (kinds, hints) in WORD_HINTS.items():
        if out.get(key) or out.get(ONE_END.get(key, "")) or (key == "due_at" and out.get("sla_met")):
            continue
        after_ok = key in ("resolved_at", "duration_min", "due_at")
        for c in columns:
            if c["kind"] in kinds and c["name"] not in out.values() and has_word(c["name"], hints) \
                    and (after_ok or known_at_open(c["name"])) and not (key == "duration_min" and in_hours(c["name"])):
                out[key] = c["name"]
                break
    guess_on_time(columns, out)
    return out


def in_hours(name: str) -> bool:
    """A duration in hours, days or seconds is not a duration in minutes ("Resolution time (hrs)")."""
    return has_word(name, ("hour", "hours", "hrs", "hr", "h", "day", "days", "sec", "secs", "seconds"))


def guess_on_time(columns: list[dict], out: dict) -> None:
    """A two-valued column whose name says late ("SLA Breached", "is_late") or on time ("SLA Met")."""
    if out.get("sla_met") or out.get("due_at"):
        return
    for c in columns:
        if c["unique"] != 2 or c["name"] in out.values():
            continue
        if has_word(c["name"], ("breach", "violat", "overdue", "missed")) or "late" in name_words(c["name"]):
            out["breached"] = c["name"]
            return
        if has_word(c["name"], ("sla", "ontime", "within", "met")):
            out["sla_met"] = c["name"]
            return


def questions(columns: list[dict], m: dict) -> list[dict]:
    """Ask only what cannot be guessed: the start, and the end or duration. Each question offers the
    columns of the right kind as answers (each answer says which role it fills).

    Example: two time columns "opened" and "logged", no known names -> one question,
    "Which column is when each item started?" with the answers opened and logged.
    """
    used = set(v for v in m.values() if isinstance(v, str))
    times = [c["name"] for c in columns if c["kind"] == "time" and c["name"] not in used]
    asks = []
    if not m.get("created_at"):
        asks.append({"role": "created_at", "text": "Which column is when each item started?",
                     "options": [{"column": n, "role": "created_at"} for n in times[:4]]})
    if not m.get("resolved_at") and not m.get("duration_min"):
        numbers = [c["name"] for c in columns if c["kind"] == "number" and c["name"] not in used]
        options = [{"column": n, "role": "resolved_at"} for n in times[:4]] + \
                  [{"column": n, "role": "duration_min"} for n in numbers[:3]]
        asks.append({"role": "end", "text": "Which column is when each item ended, or how many minutes it took?",
                     "options": options})
    return asks


def preview_rows(raw: pd.DataFrame, n: int = 3) -> list[dict[str, str]]:
    """The first rows as short text, for the preview on the upload card (values cut at 32 letters)."""
    return [{str(k): "" if pd.isna(v) else str(v)[:32] for k, v in row.items()} for _, row in raw.head(n).iterrows()]


# ---- 2. Building the work items ---------------------------------------------------------------

def truthy(values: pd.Series) -> pd.Series:
    return values.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y", "met", "on time", "within sla",
                                                            "achieved", "in time", "ontime", "on-time"})


def said_missed(values: pd.Series) -> pd.Series:
    """For a "breached" column: True, yes, 1, breached, violated, missed or late mean the item missed."""
    return values.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y", "breached", "violated", "missed",
                                                            "late", "overdue", "sla violated", "failed"})


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


def miss_rule(m: dict, target_min: float | None) -> dict:
    """Which rule says an item missed, in the order build_items uses them: the file's own "SLA met"
    column, a "breached" column, a due time, or a promised time in minutes (rule None: no way yet).

    Example: {"duration_min": "Time_taken(min)"} with 30 -> {"rule": "promise", "column": None, "target_min": 30.0}.
    """
    for rule in ("sla_met", "breached", "due_at"):
        if m.get(rule):
            return {"rule": rule, "column": m[rule], "target_min": None}
    if target_min:
        return {"rule": "promise", "column": None, "target_min": float(target_min)}
    return {"rule": None, "column": None, "target_min": None}


def item_times(raw: pd.DataFrame, m: dict) -> tuple[pd.Series, pd.Series]:
    """Start and end of every row (NaT where unreadable). The end is an end time, or the start plus a
    duration in minutes ("(min) 24" reads as 24 minutes)."""
    for key, name in m.items():
        if key != "features" and name and name not in raw.columns:
            raise ValueError(f'There is no column "{name}" in this file: pick another one.')
    if not m.get("created_at"):
        raise ValueError(NO_START)
    created = raw[m["created_at"]].astype(str)
    if m.get("created_time"):
        created = created + " " + clock_text(raw[m["created_time"]])
    start = parse_times(created)
    if m.get("resolved_at"):
        return start, parse_times(raw[m["resolved_at"]])
    if m.get("duration_min"):
        minutes = pd.to_numeric(raw[m["duration_min"]].astype(str).str.extract(r"([\d.]+)")[0], errors="coerce")
        return start, start + pd.to_timedelta(minutes, unit="min")
    raise ValueError(NO_END)


def build_items(raw: pd.DataFrame, m: dict, target_min: float | None,
                target_assumed: bool = False) -> tuple[pd.DataFrame, list[str]]:
    """One row per work item: start, end, missed, and the columns the person mapped.

    The miss comes from (in this order) an "SLA met" column, a "breached" column, a due time, or a
    promised time in minutes (typed in the form, or OpsLens's assumption from the file's median).
    """
    notes: list[str] = []
    start, end = item_times(raw, m)
    items = pd.DataFrame({"created_at": start})
    items["id"] = raw[m["id"]].astype(str) if m.get("id") else [f"row {i + 1}" for i in range(len(raw))]
    items["end_at"] = end
    items["duration_min"] = (items["end_at"] - items["created_at"]).dt.total_seconds() / 60.0
    if m.get("priority"):
        items["priority"] = raw[m["priority"]].astype(str)
        items["priority_rank"] = priority_rank(raw[m["priority"]])
    for key in ("team", "category"):
        if m.get(key):
            items[key] = raw[m[key]].astype(str).fillna("(blank)")
    rule = miss_rule(m, target_min)
    if rule["rule"] == "sla_met":
        items["missed"] = ~truthy(raw[m["sla_met"]])
        notes.append(f"A miss is the file's own \"{m['sla_met']}\" column.")
    elif rule["rule"] == "breached":
        items["missed"] = said_missed(raw[m["breached"]])
        notes.append(f"A miss is the file's own \"{m['breached']}\" column.")
    elif rule["rule"] == "due_at":
        items["missed"] = items["end_at"] > parse_times(raw[m["due_at"]])
        notes.append(f"A miss is finishing after \"{m['due_at']}\".")
    elif rule["rule"] == "promise" and target_assumed:
        median = float(items["duration_min"][items["duration_min"] >= 0].median())
        items["missed"] = items["duration_min"] > float(target_min)
        notes.append(f"A miss is taking longer than {float(target_min):g} minutes. This is an assumption: the file has no "
                     f"on-time column, so OpsLens took its median time ({median:.1f} min) rounded up.")
    elif rule["rule"] == "promise":
        items["missed"] = items["duration_min"] > float(target_min)
        notes.append(f"A miss is taking longer than the promised {float(target_min):g} minutes you entered.")
    else:
        raise ValueError(NO_MISS)
    if rule["rule"] in ("sla_met", "breached"):
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


OUTCOME_ROLES = ("resolved_at", "duration_min", "sla_met", "breached", "due_at", "id", "created_at", "created_time")


def add_features(items: pd.DataFrame, raw: pd.DataFrame, m: dict) -> pd.DataFrame:
    """The columns the person ticked as known when an item opens (never the mapped outcome ones)."""
    outcome = {m.get(k) for k in OUTCOME_ROLES}
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


def relevance_problems(items: pd.DataFrame) -> list[tuple[str, str]]:
    """Why a file cannot be learned from, each with the one thing to try (an empty list means it can).

    Example: 120 rows -> [("only 120 usable rows; OpsLens needs at least 500 to learn from",
    "Try a longer export, a few months of items.")]
    """
    problems = []
    if len(items) < MIN_ROWS:
        problems.append((f"only {len(items)} usable rows; OpsLens needs at least {MIN_ROWS} to learn from",
                         "Try a longer export, a few months of items."))
    days = items["created_at"].dt.normalize().nunique() if len(items) else 0
    if days < MIN_DAYS:
        problems.append((f"the items cover {days} days; OpsLens needs at least {MIN_DAYS} to learn and then test",
                         "Try an export that covers at least a week."))
    if len(items) and (items["duration_min"] < 0).mean() > 0.1:
        problems.append(("more than 1 in 10 items end before they start", "Check which column is the start and which is the end."))
    misses = int(items["missed"].sum()) if len(items) else 0
    if misses < MIN_MISSES or len(items) - misses < MIN_MISSES:
        problems.append((f"{misses} misses out of {len(items)} items; OpsLens needs at least {MIN_MISSES} misses and {MIN_MISSES} in time",
                         "Change what counts as a miss, or try a longer export."))
    return problems


def refusal(problems: list[tuple[str, str]]) -> str:
    """One readable refusal: every reason, then the first fix to try."""
    return "This file cannot be analysed: " + "; ".join(reason for reason, _ in problems) + ". " + problems[0][1]


ROUND_MINUTES = (5, 10, 15, 20, 25, 30, 45, 60, 90, 120, 180, 240, 360, 480, 720, 1440, 2880, 4320, 7200, 10080)


def round_promise(median_min: float) -> float:
    """The file's median time rounded up to the next round number of minutes: OpsLens's assumed
    promise when the file has no on-time column. Strictly above the median, so fewer than half the
    items count as misses even when the median is itself round. Example: 21.4 -> 25, 20 -> 25,
    26 -> 30, 50 -> 60, 700 -> 720 (12 hours), 2000 -> 2880 (2 days); beyond a week, whole weeks."""
    for minutes in ROUND_MINUTES:
        if median_min < minutes:
            return float(minutes)
    return float((np.floor(median_min / 10080) + 1) * 10080)


def learned_columns(raw: pd.DataFrame, m: dict) -> list[str]:
    """The file's own columns the model learns from: team, category, priority and the ticked ones."""
    outcome = {m.get(k) for k in OUTCOME_ROLES}
    chosen = {m.get(k) for k in ("team", "category", "priority")} | set(m.get("features", []))
    return [str(c) for c in raw.columns if c in chosen and c not in outcome]


def check_mapping(raw: pd.DataFrame, m: dict, target_min: float | None = None) -> dict:
    """What will happen with this mapping, before anything is learned: how many items are usable,
    how long they take, what counts as a miss (OpsLens assumes a promise when the file has no
    on-time column) and how many misses that makes, and how the items split into the first 70% and
    the rest. `problem` is one sentence and one fix when the file cannot be analysed this way.

    Example (generated delivery orders): 3,000 items over 30 days, median 21.1 min; no on-time
    column, so a miss is taking longer than 25 minutes (assumed); learn on 2,100, test on 900.
    """
    try:
        start, end = item_times(raw, m)
        minutes = ((end - start).dt.total_seconds() / 60.0).dropna()
        median = float(minutes[minutes >= 0].median()) if (minutes >= 0).any() else None
        assumed = miss_rule(m, target_min)["rule"] is None and median is not None
        if assumed:
            target_min = round_promise(median)
        items, _ = build_items(raw, m, target_min, assumed)
    except ValueError as exc:
        return {"problem": str(exc)}
    learn = int(len(items) * LEARN_SHARE)
    problems = relevance_problems(items)
    learns_from = learned_columns(raw, m)
    return {"problem": refusal(problems) if problems else None, "items": int(len(items)), "rows": int(len(raw)),
            "from": str(items["created_at"].min())[:10], "to": str(items["created_at"].max())[:10],
            "days": int(items["created_at"].dt.normalize().nunique()), "median_min": round(median, 1) if median else None,
            "miss": {**miss_rule(m, target_min), "assumed": assumed},
            "missed_pct": round(100 * float(items["missed"].mean()), 1) if len(items) else None,
            "learn_items": learn, "test_items": int(len(items)) - learn, "learns_from": learns_from,
            "learns_from_count": len(learns_from)}


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
    if len(rows) == 0:
        return []
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
    of the misses that really happened? Nothing is changed: the outcomes are the file's own.
    `timeline` lists the day item by item, so the screen can replay it minute by minute."""
    opened_day = items["created_at"].dt.normalize()
    busiest = opened_day[test].value_counts().idxmax()
    rows = np.flatnonzero(test & (opened_day == busiest).to_numpy())
    same_day = np.zeros(len(rows))
    result = {"date": str(busiest)[:10], "weekday": WEEKDAYS[busiest.weekday()], "items": int(len(rows)),
              "misses": int(y[rows].sum()), "flags": max(1, int(round(FLAG_SHARE * len(rows)))), "caught": {}}
    flagged = {}
    for name, score in scores.items():
        flagged[name] = flags_by_day(same_day, score[rows])
        result["caught"][name] = int((flagged[name] & (y[rows] == 1)).sum())
    order = rows[np.argsort(-scores["opslens"][rows])[:6]]
    why = reasons(booster, X, items, order)
    result["examples"] = [{"id": str(items.at[r, "id"]), "opened": str(items.at[r, "created_at"])[11:16],
                           "risk": round(float(scores["opslens"][r]), 3), "missed": bool(y[r]), "reasons": why[i]}
                          for i, r in enumerate(order)]
    if len(rows) <= TIMELINE_MAX:
        result["timeline"] = day_timeline(items, X, y, rows, flagged, scores, booster, busiest)
    else:
        result["timeline_note"] = f"This day has {len(rows):,} items, too many to replay one by one, so only its totals are shown."
    return result


def day_timeline(items: pd.DataFrame, X: pd.DataFrame, y: np.ndarray, rows: np.ndarray, flagged: dict[str, np.ndarray],
                 scores: dict[str, np.ndarray], booster: lgb.Booster, day: pd.Timestamp) -> list[dict]:
    """The shadow day item by item, in opening order: the minute it opened and ended (minutes after
    that day's midnight, so an end on a later day is above 1440), whether it really missed, which
    pickers flagged it the moment it opened, OpsLens's risk, and its reasons when OpsLens flagged it.

    Example: {"id": "0x0b2c", "opened_min": 754.2, "ended_min": 791.0, "missed": True,
              "flagged": ["opslens", "rule"], "risk": 0.71, "reasons": [{"text": "Road_traffic_density: Jam ", ...}]}
    """
    opened = ((items["created_at"].iloc[rows] - day).dt.total_seconds() / 60.0).to_numpy()
    ended = ((items["end_at"].iloc[rows] - day).dt.total_seconds() / 60.0).to_numpy()
    ours = np.flatnonzero(flagged["opslens"])
    why = dict(zip(ours.tolist(), reasons(booster, X, items, rows[ours])))
    out = []
    for k, r in enumerate(rows):
        line = {"id": str(items.at[r, "id"]), "opened_min": round(float(opened[k]), 1), "ended_min": round(float(ended[k]), 1),
                "missed": bool(y[r]), "flagged": [name for name in flagged if flagged[name][k]],
                "risk": round(float(scores["opslens"][r]), 3)}
        if "priority" in items:
            line["priority"] = str(items.at[r, "priority"])
        if k in why:
            line["reasons"] = why[k]
        out.append(line)
    return out


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
    `test_misses` counts the real misses in the group on the last 30% (the Actions screen shows it).

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
                      "examples": items.loc[t_in & (y == 1), "id"].astype(str).head(3).tolist(),
                      "test_misses": int(y[t_in].sum())})
    return cards


# ---- 7. Workload a week ahead, per team --------------------------------------------------------

FORECAST_LAGS = (7, 14, 21, 28)
BLANKS = ("nan", "None", "(blank)", "")  # an empty team is not a team to forecast
FORECAST_INPUTS = ["team", "weekday", "lag_7", "lag_14", "lag_21", "lag_28", "mean_4w"]
FORECAST_PARAMS = {"objective": "poisson", "learning_rate": 0.05, "num_leaves": 15, "min_child_samples": 10,
                   "feature_fraction": 0.9, "verbose": -1, "seed": 7, "deterministic": True, "num_threads": 1}


def daily_team_counts(items: pd.DataFrame, teams: list[str], first: pd.Timestamp, days: int) -> pd.DataFrame:
    """New items per team and calendar day (day 0 = the file's first day), zeros included."""
    day = (items["created_at"].dt.normalize() - first).dt.days
    counts = items.groupby([items["team"].astype(str), day]).size()
    counts.index = counts.index.set_names(["team", "day"])
    grid = pd.MultiIndex.from_product([teams, range(days)], names=["team", "day"])
    return counts.reindex(grid, fill_value=0).rename("count").reset_index()


def lag_features(counts: pd.DataFrame, first_weekday: int) -> pd.DataFrame:
    """Weekday and the same weekday 1 to 4 weeks earlier, per team. Only the past: the row of day d
    reads days d-7, d-14, d-21 and d-28 (empty before the file starts), never day d or later.

    Example: 40, 38, 45 and 41 items on the four Mondays before -> lag_7 = 41, mean_4w = 41.0.
    """
    df = counts.sort_values(["team", "day"]).reset_index(drop=True)
    df["weekday"] = (first_weekday + df["day"]) % 7
    grouped = df.groupby("team")["count"]
    for lag in FORECAST_LAGS:
        df[f"lag_{lag}"] = grouped.shift(lag)
    df["mean_4w"] = df[[f"lag_{lag}" for lag in FORECAST_LAGS]].mean(axis=1)
    df["team"] = df["team"].astype("category")
    return df


def usual_ends(items: pd.DataFrame, teams: list[str], start: pd.Timestamp) -> pd.Series:
    """What each team usually finishes in a day: the median over the 28 days before `start` (days
    with none count as 0). Only ends before `start`, so it is known when the forecast is made."""
    since = start - pd.Timedelta(days=28)
    done = items[(items["end_at"] >= since) & (items["end_at"] < start) & items["team"].astype(str).isin(teams)]
    if done.empty:
        return pd.Series(0.0, index=teams)
    per_day = done.groupby([done["team"].astype(str), (done["end_at"].dt.normalize() - since).dt.days]).size()
    return per_day.unstack(fill_value=0).reindex(index=teams, columns=range(28), fill_value=0).median(axis=1)


def team_forecast(items: pd.DataFrame, test: np.ndarray) -> dict:
    """New items per team and day, a week ahead, on the first 4 weeks of the later 30%: learned
    (LightGBM, Poisson, fixed settings) on the days before vs "same weekday last week". The last
    fifth of the learning days (at least a week) picks which of the two to trust; the later days
    only report. Four weeks, because a forecast is a near-term tool and the end of an export is
    often a thin tail of stragglers. The file's last day is never scored (often cut short).
    Needs a team column and 8 weeks of items; otherwise `needs` says what is missing.

    Example (a 90-day file of generated delivery orders, 3 cities): learned WAPE 0.12 vs 0.18 for
    same weekday last week; the check days had chosen the learned one (0.11 vs 0.15).
    """
    if "team" not in items:
        return {"needs": "a team column"}
    first = items["created_at"].min().normalize()
    span = int((items["created_at"].max().normalize() - first).days) + 1
    if span < FORECAST_DAYS:
        return {"needs": f"at least 8 weeks of items; this file covers {span} days"}
    test_day = int((items.loc[test, "created_at"].min().normalize() - first).days)
    check_from = test_day - max(7, int(round(0.2 * (test_day - 7))))
    last_scored = min(test_day + 28, span - 1)
    if check_from - 7 < 14 or last_scored - test_day < 7:
        return {"needs": "3 weeks of items before the later 30% begins and a week after it"}
    names = items.loc[~test, "team"].astype(str)
    teams = [str(t) for t in names[~names.isin(BLANKS)].value_counts().index[:FORECAST_TEAMS]]
    rows = lag_features(daily_team_counts(items[items["team"].astype(str).isin(teams)], teams, first, span), first.weekday())
    fit = rows[(rows["day"] >= 7) & (rows["day"] < check_from)]
    check = rows[(rows["day"] >= check_from) & (rows["day"] < test_day)]
    scored = rows[(rows["day"] >= test_day) & (rows["day"] < last_scored)].copy()
    train = lgb.Dataset(fit[FORECAST_INPUTS], fit["count"])
    booster = lgb.train(FORECAST_PARAMS, train, 300, valid_sets=[lgb.Dataset(check[FORECAST_INPUTS], check["count"], reference=train)],
                        callbacks=[lgb.early_stopping(20, verbose=False)])
    on_check = {"learned": wape(check["count"].to_numpy(), booster.predict(check[FORECAST_INPUTS])),
                "same_weekday_last_week": wape(check["count"].to_numpy(), check["lag_7"].to_numpy())}
    chosen = min(on_check, key=on_check.get)
    scored["learned"] = booster.predict(scored[FORECAST_INPUTS])
    scored["forecast"] = scored["learned"] if chosen == "learned" else scored["lag_7"]
    scored["usual_ends"] = scored["team"].astype(str).map(usual_ends(items, teams, first + pd.Timedelta(days=test_day)))
    scored["date"] = (first + pd.to_timedelta(scored["day"], unit="D")).dt.strftime("%a %d %b")
    return {"teams": teams, "chosen_on_check": chosen, "wape_check": {k: round(v, 3) for k, v in on_check.items()},
            "wape_learned": round(wape(scored["count"].to_numpy(), scored["learned"].to_numpy()), 3),
            "wape_same_weekday_last_week": round(wape(scored["count"].to_numpy(), scored["lag_7"].to_numpy()), 3),
            "learned_days": [str((first + pd.Timedelta(days=7)).date()), str((first + pd.Timedelta(days=test_day - 1)).date())],
            "scored_days": [str((first + pd.Timedelta(days=test_day)).date()), str((first + pd.Timedelta(days=last_scored - 1)).date())],
            "team_days": int(len(scored)), "items_scored": int(scored["count"].sum()),
            "first_week": forecast_rows(scored[scored["day"] < test_day + 7]), "by_team": forecast_by_team(scored, teams)}


def forecast_rows(week: pd.DataFrame) -> list[dict]:
    """One row per team and day: the forecast it used, same weekday last week, what came, and what
    the team usually finishes in a day."""
    return [{"team": str(r["team"]), "date": r["date"], "forecast": round(float(r["forecast"]), 1),
             "same_weekday_last_week": int(r["lag_7"]), "actual": int(r["count"]), "usual_ends": round(float(r["usual_ends"]), 1)}
            for r in week.sort_values(["day", "team"]).to_dict("records")]


def forecast_by_team(scored: pd.DataFrame, teams: list[str]) -> list[dict]:
    """WAPE of both forecasts per team over the scored days (teams with under 7 items are left out)."""
    out = []
    for team in teams:
        rows = scored[scored["team"].astype(str) == team]
        if rows["count"].sum() < 7:
            continue
        out.append({"team": team, "items": int(rows["count"].sum()),
                    "wape_learned": round(wape(rows["count"].to_numpy(), rows["learned"].to_numpy()), 3),
                    "wape_same_weekday_last_week": round(wape(rows["count"].to_numpy(), rows["lag_7"].to_numpy()), 3)})
    return out


# ---- 8. The whole report ----------------------------------------------------------------------

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


def missing_columns(items: pd.DataFrame, scores: dict, forecast: dict) -> dict[str, str]:
    """What the file lacks, for each part of the report that would use it, as the thing to add.

    Example: a delivery file without priority or category -> {"priority": "a priority column",
    "category": "a category column", "forecast": "at least 8 weeks of items; this file covers 30 days"}.
    """
    needs = {}
    if "priority" not in scores:
        needs["priority"] = "a priority column filled in for most items" if "priority_rank" in items else "a priority column"
    for key in ("team", "category"):
        if key not in items:
            needs[key] = f"a {key} column"
    if forecast.get("needs"):
        needs["forecast"] = forecast["needs"]
    return needs


CANNOT = [
    "Replay your floor under OpsLens's dispatch: that needs how long each item was actually worked on, "
    "who was on shift and who can handle what. A log records one way of working, not those.",
    "Say what would have happened to an item OpsLens flagged: every outcome shown is your file's own.",
]


def analyse(raw: pd.DataFrame, mapping: dict, target_min: float | None = None, progress: Progress | None = None,
            target_assumed: bool = False) -> dict:
    """Run the whole report on one file. `progress(step)` is called as each step starts.
    `target_assumed` says the promised time is OpsLens's assumption, not typed by the person."""
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
    items, notes = build_items(raw, mapping, target_min, target_assumed)
    step("Checking the file can be learned from")
    problems = relevance_problems(items)
    if problems:
        raise ValueError(refusal(problems))
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
    step("Forecasting each team's workload a week ahead")
    forecast = team_forecast(items, test)
    steps[-1]["seconds"] = round(time.perf_counter() - steps[-1].pop("_t"), 1)
    rule = miss_rule(mapping, target_min)
    return {
        "summary": floor_summary(items), "notes": notes, "dropped_after_the_fact": dropped,
        "features": list(X.columns), "rule_column": rule_col,
        "learn": {"items": int(learn.sum()), "from": str(items.loc[learn, "created_at"].min())[:10],
                  "to": str(items.loc[learn, "created_at"].max())[:10]},
        "test": {"items": int(test.sum()), "from": str(items.loc[test, "created_at"].min())[:10],
                 "to": str(items.loc[test, "created_at"].max())[:10]},
        "warning": warning, "shadow": shadow, "cards": cards, "flag_share_pct": int(100 * FLAG_SHARE),
        "steps": steps, "seconds": round(time.perf_counter() - started, 1), "cannot": CANNOT,
        "miss": {**rule, "assumed": bool(target_assumed) and rule["rule"] == "promise"}, "forecast": forecast,
        "needs": missing_columns(items, scores, forecast),
    }
