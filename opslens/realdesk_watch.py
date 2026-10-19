"""Watch the real service desk day by day: spikes, slow teams and bouncing categories (UCI log).

What it does: every day, three detectors look at what the desk knows by the end of that day and
raise an alert when today is clearly unusual for one category or one team:
- spike     a category's new incidents today vs its usual day;
- slowdown  a team's incidents opened yesterday that were still open 24 h later (share);
- bounce    a category's incidents opened yesterday that were passed to another team within
            24 h of opening (share).
It is the food world's spike scan (patterns.scan_spikes, robust z, CLAUDE.md section 4) carried
over to the real log's columns, plus two share detectors for things a log shows and a ticket
count does not. The food world's code is not changed.

Why this design: the detectors must work on a real company's export without knowing anything
about the problems planted into it (only eval/realdesk_plants.py knows those). So the rules are
fixed and plain, and were committed before the blind test ran:
- "usual" = the median of the same kind of day (weekday or weekend) in the 28 days before;
- alert when the robust z-score is at least 3.5 (the food world's threshold) AND the excess is
  big enough to matter (spike: 5 incidents above usual; share: 3 incidents above what the usual
  share predicts, on a day with at least 8 incidents);
- for a share, the spread is never taken as smaller than chance alone (binomial) for today's
  count, so a small team cannot raise an alert on two unlucky incidents.
Only information known at the end of the alert day is used: a share is known one day after the
incidents opened (their 24 hours must have passed).

Example: Category 26, Tue 10 May 2016: 52 incidents are usual on a weekday (MAD 6). A day with
80 → robust z = 0.6745 × (80 − 52) ÷ 6 = 3.1 → no alert; a day with 90 → z = 4.3 and 38 above
usual → "spike" alert at the end of that day.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from opslens.patterns import robust_z

Z = 3.5                   # alert threshold (same as the food world's spike scan)
WINDOW_DAYS = 28          # "usual" = days of the same kind in the 4 weeks before
MIN_HISTORY_DAYS = 5      # need at least this many comparable days to judge
MIN_USUAL_COUNT = 3.0     # spike: skip categories whose usual day has fewer incidents
MIN_EXCESS_COUNT = 5      # spike: at least this many incidents above usual
MIN_DAY_COUNT = 8         # share: today's share needs at least this many incidents
MIN_HISTORY_COUNT = 3     # share: a past day counts as comparable with at least this many incidents
MIN_EXCESS_SHARE = 3      # share: at least this many incidents above what the usual share predicts
MIN_SHARE_FLOOR = 0.02    # share: chance spread uses p at least 2% (p = 0 would give no spread)


def as_of_table(incidents: pd.DataFrame, events: pd.DataFrame, hours: float = 24.0) -> pd.DataFrame:
    """One row per incident with what the desk knows `hours` after it opened.

    category = the category at opening (first event), team = the first team it was sent to,
    open_24h = still not resolved 24 h after opening (never resolved counts as open),
    bounced_24h = passed to another team at least once within 24 h of opening.
    Example: INC0000047 opened 04:40, reassigned at 05:10, resolved 2 days later →
    open_24h True, bounced_24h True.
    """
    snap = incidents.set_index("ticket_id")["created_at"] + pd.Timedelta(hours=hours)
    ev = events[["number", "sys_updated_at", "reassignment_count"]].merge(snap.rename("snap"), left_on="number", right_index=True)
    known = ev[ev["sys_updated_at"] <= ev["snap"]]
    reassigned = known.groupby("number")["reassignment_count"].max()
    first = events.groupby("number").head(1).set_index("number")
    inc = incidents.set_index("ticket_id")
    out = pd.DataFrame(index=inc.index)
    out["created_at"] = inc["created_at"]
    out["date"] = inc["created_at"].dt.normalize()
    out["category"] = first["category"].reindex(out.index)
    out["team"] = inc["first_team"]
    out["resolution_h"] = inc["resolution_min"] / 60.0
    out["open_24h"] = ~(out["resolution_h"] <= hours)  # NaN (never resolved) → still open
    out["bounced_24h"] = reassigned.reindex(out.index).fillna(0).to_numpy() >= 1
    return out.reset_index().rename(columns={"index": "ticket_id"})


def share_z(k: int, n: int, past_shares: np.ndarray) -> float:
    """Robust z of today's share k/n against past daily shares, with a chance floor.

    Example: usual share 0.30 (MAD 0.05), today 9 of 12 = 0.75. Chance spread for 12 incidents:
    sqrt(0.3 × 0.7 / 12) = 0.13 → MAD floor 0.6745 × 0.13 = 0.089 → z = 0.6745 × 0.45 ÷ 0.089 = 3.4.
    """
    p = float(np.median(past_shares))
    mad = float(np.median(np.abs(past_shares - p)))
    q = max(p, MIN_SHARE_FLOOR)
    chance = np.sqrt(q * (1 - q) / n)
    return 0.6745 * (k / n - p) / max(mad, 0.6745 * chance)


def comparable_days(dates: pd.DatetimeIndex, day: pd.Timestamp) -> np.ndarray:
    """Positions of the days of the same kind (weekday / weekend) in the 28 days before `day`."""
    weekend = day.weekday() >= 5
    lo = day - pd.Timedelta(days=WINDOW_DAYS)
    ok = (dates >= lo) & (dates < day) & ((dates.weekday >= 5) == weekend)
    return np.flatnonzero(ok)


def spike_alerts(table: pd.DataFrame, days: pd.DatetimeIndex) -> list[dict]:
    """Spike detector: a category's new incidents on a day vs its usual day (known that evening)."""
    counts = table.groupby(["category", "date"]).size().unstack(fill_value=0)
    all_dates = pd.date_range(days[0] - pd.Timedelta(days=WINDOW_DAYS), days[-1])
    counts = counts.reindex(columns=all_dates, fill_value=0)
    values = counts.to_numpy(dtype=float)
    alerts = []
    for day in days:
        past = comparable_days(all_dates, day)
        if len(past) < MIN_HISTORY_DAYS:
            continue
        col = all_dates.get_loc(day)
        for row, category in enumerate(counts.index):
            usual = values[row, past]
            median = float(np.median(usual))
            x = values[row, col]
            if median < MIN_USUAL_COUNT or x - median < MIN_EXCESS_COUNT:
                continue
            z = robust_z(x, usual)
            if z >= Z:
                alerts.append({"type": "spike", "segment": str(category), "day": day, "known_on": day,
                               "value": int(x), "usual": median, "z": round(float(z), 1)})
    return alerts


def share_alerts(table: pd.DataFrame, days: pd.DatetimeIndex, by: str, flag: str, kind: str) -> list[dict]:
    """Share detector: incidents opened on a day with `flag` true, per `by` (known the next day).
    `days` are the days the alert can be raised on; the incidents opened the day before."""
    n = table.groupby([by, "date"]).size().unstack(fill_value=0)
    k = table[table[flag]].groupby([by, "date"]).size().unstack(fill_value=0)
    all_dates = pd.date_range(days[0] - pd.Timedelta(days=WINDOW_DAYS + 1), days[-1])
    n = n.reindex(columns=all_dates, fill_value=0)
    k = k.reindex(index=n.index, columns=all_dates, fill_value=0)
    n_val, k_val = n.to_numpy(dtype=float), k.to_numpy(dtype=float)
    alerts = []
    for known_on in days:
        opened = known_on - pd.Timedelta(days=1)
        col = all_dates.get_loc(opened)
        past = comparable_days(all_dates, opened)
        for row, segment in enumerate(n.index):
            today_n, today_k = n_val[row, col], k_val[row, col]
            if today_n < MIN_DAY_COUNT:
                continue
            usable = past[n_val[row, past] >= MIN_HISTORY_COUNT]
            if len(usable) < MIN_HISTORY_DAYS:
                continue
            shares = k_val[row, usable] / n_val[row, usable]
            if today_k - today_n * float(np.median(shares)) < MIN_EXCESS_SHARE:
                continue
            z = share_z(int(today_k), int(today_n), shares)
            if z >= Z:
                alerts.append({"type": kind, "segment": str(segment), "day": opened, "known_on": known_on,
                               "value": round(float(today_k / today_n), 3), "usual": round(float(np.median(shares)), 3),
                               "z": round(float(z), 1), "incidents": int(today_n)})
    return alerts


def watch(table: pd.DataFrame, first_day: str, last_day: str) -> pd.DataFrame:
    """All three detectors over the days first_day..last_day (alerts raised on these days)."""
    days = pd.date_range(first_day, last_day)
    alerts = spike_alerts(table, days)
    alerts += share_alerts(table, days[1:], "team", "open_24h", "slowdown")
    alerts += share_alerts(table, days[1:], "category", "bounced_24h", "bounce")
    columns = ["type", "segment", "day", "known_on", "value", "usual", "z", "incidents"]
    return pd.DataFrame(alerts, columns=columns).sort_values(["known_on", "type", "segment"], kind="stable").reset_index(drop=True)
