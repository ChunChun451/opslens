"""Find recurring problems in the ticket history and back each one with evidence.

What it does: scans the history (days 1-42) for groups of tickets that are clearly worse than
comparable tickets, decides the likely cause, and writes an evidence card with the numbers,
three example tickets and a recommended action. It also finds unusual days (volume spikes)
and, in the live period, raises alerts within the hour.

How it works:
1. Every ticket gets simple labels: category, language, channel, team, priority, tier, and
   "when" (weekday/weekend × night/morning/lunch/afternoon/dinner/late).
2. **Interaction scan.** For every pair of labels (e.g. language=hi × team=B) we compare the
   mean wait with BOTH "parents": Hindi tickets of other teams, and Team B tickets in other
   languages. A pair is a finding only if it is ≥ 2× worse than both, with a large z-score.
   That separates "Hindi Team-B tickets are slow" from "Team B is slow" or "Hindi is slow".
3. **Process scan.** Groups whose transfers per 100 tickets are ≥ 3× the rest.
4. **Partner scan.** Restaurant clusters whose share of one category is ≥ 2× the others'.
5. **Spike scan.** Daily count per category vs its usual level on days of the same type
   (weekday or weekend) with a robust z-score (median and MAD, CLAUDE.md section 4).
   Known sale days are explained, not alarms.
6. **Capacity scan.** For every team × time window: work arriving (handle minutes) ÷ the
   team's agent-minutes on shift. ρ ≥ 1.2 while the team is staffed = overloaded window.
7. **Cause type** by plain rules: transfers → process; restaurant cluster → partner issue;
   unusual day → volume spike; overloaded window → capacity; a time window with almost no
   capable agent on shift → capacity (coverage); language × skill with few capable agents
   → skill gap.
8. Overlapping findings about the same tickets are merged (the stronger one is kept).

Example (our history): Hindi × Team B tickets wait 302 min on average; Hindi tickets of other
teams wait 37 min and Team B tickets in other languages 50 min → ratio vs the worse parent
6.0×, z = 31 → finding, cause "skill gap" because only 3 agents speak Hindi and handle refunds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
import pandas as pd

from opslens.privacy import mask_pii

HOUR_BANDS = [(0, 6, "night"), (7, 11, "morning"), (12, 15, "lunch"), (16, 18, "afternoon"),
              (19, 22, "dinner"), (23, 23, "late")]
PAIR_DIMS = ["category", "language", "channel", "team", "priority", "tier", "when"]
MIN_PAIR_TICKETS = 150
MIN_RATIO = 2.0
MIN_Z = 6.0
TRANSFER_RATIO = 3.0
PARTNER_RATIO = 2.0
SPIKE_Z = 3.5
WEEKEND = (5, 6)


@dataclass
class Finding:
    """One problem with its evidence. Turned into an EvidenceCard for results.json."""

    title: str
    cause_type: str
    metric: str
    value: float
    comparison_value: float
    comparison_text: str
    segment: dict
    mask: np.ndarray  # which history tickets are affected
    strength: float
    not_explained_by: str = ""
    recommendation: str = ""
    examples: list[dict] = field(default_factory=list)


# ---- Labels ----------------------------------------------------------------------------------

def hour_band(hour: int) -> str:
    for low, high, name in HOUR_BANDS:
        if low <= hour <= high:
            return name
    return "night"


def label_frame(history: pd.DataFrame, team_skills: dict[str, list[str]]) -> pd.DataFrame:
    """Add the labels the scans group by.

    "team" is the team that OWNS the ticket's category (its queue), not the team that happened
    to resolve it: overflow work picked up by helpers would otherwise hide a team's problem.
    """
    df = history.copy()
    df["category"] = df["final_category"].astype(str)
    owner = {c: team for team, cats in team_skills.items() for c in cats}
    df["team"] = df["category"].map(owner).fillna("?")
    df["tier"] = df["customer_tier"].astype(str)
    band = df["hour"].map(hour_band)
    df["when"] = np.where(df["weekday"].isin(WEEKEND), "weekend ", "weekday ") + band
    return df


# ---- Statistics ------------------------------------------------------------------------------

def welch_z(a: pd.Series, b: pd.Series) -> float:
    """How many standard errors apart two means are (large = not chance)."""
    a, b = a.dropna(), b.dropna()
    if len(a) < 2 or len(b) < 2:
        return 0.0
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return float((a.mean() - b.mean()) / se) if se > 0 else 0.0


def robust_z(x: float, history: np.ndarray) -> float:
    """0.6745 × (x − median) ÷ MAD (CLAUDE.md section 4). MAD 0 → use a Poisson-like floor."""
    median = float(np.median(history))
    mad = float(np.median(np.abs(history - median)))
    mad = max(mad, np.sqrt(max(median, 1.0)) / 1.4826)
    return 0.6745 * (x - median) / mad


# ---- Scans -----------------------------------------------------------------------------------

def scan_interactions(df: pd.DataFrame, metric: str = "wait_min", dims: list[str] | None = None) -> list[Finding]:
    """Pairs of labels whose wait is ≥ 2× both parents (see module docstring, step 2).
    `metric` can be another time column (an upload without pickup times uses resolution time)."""
    findings: list[Finding] = []
    wait = df[metric]
    word = "wait" if metric == "wait_min" else "resolution time"
    for d1, d2 in combinations(dims or PAIR_DIMS, 2):
        counts = df.groupby([d1, d2], observed=True).size()
        for (v1, v2), n in counts.items():
            if n < MIN_PAIR_TICKETS:
                continue
            seg = (df[d1] == v1) & (df[d2] == v2)
            parent_a = (df[d1] == v1) & (df[d2] != v2)
            parent_b = (df[d1] != v1) & (df[d2] == v2)
            if parent_a.sum() < 50 or parent_b.sum() < 50:
                continue
            m_seg, m_a, m_b = wait[seg].mean(), wait[parent_a].mean(), wait[parent_b].mean()
            worse_parent = max(m_a, m_b)
            if worse_parent <= 0 or m_seg / worse_parent < MIN_RATIO:
                continue
            z = min(welch_z(wait[seg], wait[parent_a]), welch_z(wait[seg], wait[parent_b]))
            if z < MIN_Z:
                continue
            findings.append(Finding(
                title=f"{describe(d1, v1)} × {describe(d2, v2)} {word} {m_seg / worse_parent:.1f}× longer",
                cause_type="other", metric=f"mean {word} (min)", value=float(m_seg),
                comparison_value=float(worse_parent),
                comparison_text=(f"{describe(d1, v1)} × {describe(d2, v2)}: {m_seg:.0f} min mean {word} vs "
                                 f"{m_a:.0f} min ({describe(d1, v1)}, other {d2}) and "
                                 f"{m_b:.0f} min ({describe(d2, v2)}, other {d1})"),
                segment={d1: v1, d2: v2}, mask=seg.to_numpy(),
                strength=float(m_seg / worse_parent) * np.log10(n),
            ))
    return findings


def scan_transfers(df: pd.DataFrame) -> list[Finding]:
    """Single labels whose transfers per 100 tickets are ≥ 3× the rest (process problems)."""
    findings: list[Finding] = []
    for dim in ("channel", "category", "language", "tier"):
        for value, n in df[dim].value_counts().items():
            seg = (df[dim] == value).to_numpy()
            if n < MIN_PAIR_TICKETS or (~seg).sum() < 50:
                continue
            rate, rest = 100 * df.loc[seg, "transfers"].mean(), 100 * df.loc[~seg, "transfers"].mean()
            if rest <= 0 or rate / rest < TRANSFER_RATIO:
                continue
            findings.append(Finding(
                title=f"{describe(dim, value)} tickets are transferred {rate / rest:.1f}× more",
                cause_type="process", metric="transfers per 100 tickets", value=float(rate),
                comparison_value=float(rest),
                comparison_text=f"{rate:.1f} transfers per 100 {describe(dim, value)} tickets vs {rest:.1f} for the rest",
                segment={dim: value}, mask=seg, strength=float(rate / rest) * np.log10(n),
            ))
    return findings


def scan_partners(df: pd.DataFrame, min_tickets: int = 50) -> list[Finding]:
    """Restaurant clusters that send ≥ 2× the usual share of one category."""
    findings: list[Finding] = []
    if "restaurant_cluster_id" not in df:
        return findings
    total_by_cluster = df.groupby("restaurant_cluster_id").size()
    for category in df["category"].unique():
        is_cat = df["category"] == category
        by_cluster = df[is_cat].groupby("restaurant_cluster_id").size()
        for cluster, n_cat in by_cluster.items():
            n_cluster = total_by_cluster[cluster]
            others_cat, others_all = is_cat.sum() - n_cat, len(df) - n_cluster
            if n_cat < min_tickets or others_all == 0:
                continue
            share, share_rest = n_cat / n_cluster, others_cat / others_all
            if share_rest <= 0 or share / share_rest < PARTNER_RATIO:
                continue
            p = (n_cat + others_cat) / len(df)  # two-proportion z-test
            z = (share - share_rest) / np.sqrt(p * (1 - p) * (1 / n_cluster + 1 / others_all))
            if z < MIN_Z:
                continue
            seg = (is_cat & (df["restaurant_cluster_id"] == cluster)).to_numpy()
            findings.append(Finding(
                title=f"Restaurant cluster {cluster}: {share / share_rest:.1f}× more {nice(category)} tickets",
                cause_type="partner_issue", metric=f"share of tickets that are {nice(category)}",
                value=100 * share, comparison_value=100 * share_rest,
                comparison_text=(f"{100 * share:.1f}% of cluster {cluster}'s tickets are {nice(category)} "
                                 f"vs {100 * share_rest:.1f}% for other clusters"),
                segment={"category": category, "restaurant_cluster_id": int(cluster)}, mask=seg,
                strength=float(share / share_rest) * np.log10(n_cat),
            ))
    return findings


def scan_spikes(df: pd.DataFrame, known_event_days: set[int], dates: dict[int, str],
                window_days: int | None = None, min_usual: float = 0.0) -> tuple[list[Finding], list[dict]]:
    """Unusual days per category (robust z on daily counts). Known sale days are explained.
    `window_days`: compare only with days at most this far away (for long, uneven exports);
    `min_usual`: skip categories whose usual day has fewer tickets than this."""
    findings: list[Finding] = []
    explained: list[dict] = []
    daily = df.groupby(["category", "day"]).size().unstack(fill_value=0)
    # Compare a day only with days of the same type: weekends are busier by design.
    day_is_weekend = df.groupby("day")["weekday"].first().isin(WEEKEND)
    for category, counts in daily.iterrows():
        values = counts.to_numpy(dtype=float)
        same_type = day_is_weekend.reindex(counts.index).to_numpy()
        for day, x in counts.items():
            near = np.abs(counts.index - day) <= window_days if window_days else True
            others = values[(counts.index != day) & (same_type == day_is_weekend[day]) & near]
            if len(others) < 5 or np.median(others) < min_usual:
                continue
            z = robust_z(float(x), others)
            if z < SPIKE_Z:
                continue
            if day in known_event_days:
                explained.append({"category": category, "day": int(day), "z": round(z, 1)})
                continue
            median = float(np.median(others))
            seg = ((df["category"] == category) & (df["day"] == day)).to_numpy()
            hours = df.loc[seg, "hour"].value_counts()
            usual_hour = df[(df["category"] == category) & (df["day"] != day)].groupby(["day", "hour"]).size()
            usual_hour = usual_hour.groupby(level="hour").median()
            peak_hours = sorted(h for h, c in hours.items() if c > 2 * usual_hour.get(h, 0) + 3)
            window = f", concentrated {peak_hours[0]:02d}:00-{peak_hours[-1] + 1:02d}:00" if peak_hours else ""
            findings.append(Finding(
                title=f"{nice(category).capitalize()} spike on {dates.get(int(day), f'day {day}')}",
                cause_type="volume_spike", metric="tickets per day", value=float(x), comparison_value=median,
                comparison_text=(f"{int(x)} {nice(category)} tickets on {dates.get(int(day), f'day {day}')} vs "
                                 f"{median:.0f} on a usual day (robust z {z:.1f}){window}"),
                segment={"category": category, "day": int(day), "hour": peak_hours},
                mask=seg, strength=float(z), not_explained_by="not a known sale or event day",
            ))
    return findings, explained


def next_band(when: str) -> str:
    """'weekend dinner' → 'weekend late' (the window where a backlog spills over)."""
    day_type, band = when.split(" ", 1)
    names = [name for _, _, name in HOUR_BANDS]
    return f"{day_type} {names[(names.index(band) + 1) % len(names)]}"


def scan_capacity(df: pd.DataFrame, agents: pd.DataFrame, team_skills: dict[str, list[str]],
                  first_weekday: int, min_rho: float = 1.2, min_agents: float = 2.0) -> list[Finding]:
    """Team × time windows with more work than agent-time (rho ≥ 1.2) while the team is staffed.
    The evidence covers the window and the next one, where the backlog spills over."""
    findings: list[Finding] = []
    for team, categories in team_skills.items():
        own = df["team"] == team
        usual_wait = df.loc[own, "wait_min"].mean()
        for when in sorted(df["when"].unique()):
            rho, avg_agents = team_rho(df, agents, team, when, categories, first_weekday)
            if rho < min_rho or avg_agents < min_agents:
                continue
            spill = next_band(when)
            window = own & (df["when"] == when)
            after = own & (df["when"] == spill)
            wait_in, wait_after = df.loc[window, "wait_min"].mean(), df.loc[after, "wait_min"].mean()
            findings.append(Finding(
                title=f"Team {team} overloaded on {when} (work {rho:.2f}× agent-time)",
                cause_type="capacity", metric="work ÷ agent-time (rho)", value=rho, comparison_value=1.0,
                comparison_text=(f"Team {team} gets {rho:.2f}× more work than its agents' time on {when} "
                                 f"({avg_agents:.1f} agents on shift); its tickets wait {wait_in:.0f} min then and "
                                 f"{wait_after:.0f} min on {spill} while the backlog clears "
                                 f"(usual {usual_wait:.0f} min)"),
                segment={"team": team, "when": when}, mask=(window | after).to_numpy(), strength=10.0 * rho,
                not_explained_by=f"recurs every {when.split(' ')[0]}, not a one-off",
                recommendation=(f"Add Team {team} capacity on {when}: move agents trained on "
                                f"{', '.join(nice(c) for c in categories)} from a quieter team (see Recommendations)"),
            ))
    return findings


# ---- Cause rules -----------------------------------------------------------------------------

def capable_agents(agents: pd.DataFrame, language: str | None, categories: list[str]) -> list[str]:
    """Agents who speak `language` (if given) and are trained on any of `categories`."""
    ok = pd.Series(True, index=agents.index)
    if language:
        ok &= agents["languages"].str.split("|").map(lambda langs: language in langs)
    if categories:  # no category given = any skill will do
        ok &= agents["skills"].str.split("|").map(lambda skills: any(c in skills for c in categories))
    return agents.loc[ok, "agent_id"].tolist()


def team_rho(df: pd.DataFrame, agents: pd.DataFrame, team: str, when: str, team_categories: list[str],
             first_weekday_of_day1: int) -> tuple[float, float]:
    """Work arriving for a team's categories in a time window ÷ the team's minutes on shift then.
    Also returns how many of the team's own agents are on shift on average in that window."""
    in_window = df["when"] == when
    work = df.loc[in_window & df["category"].isin(team_categories), "handled_min"].sum()
    weekend = when.startswith("weekend")
    band = when.split(" ", 1)[1]
    low, high = next((lo, hi) for lo, hi, name in HOUR_BANDS if name == band)
    hours = set(range(low, high + 1))
    capacity = 0.0
    days = sorted(df["day"].unique())
    slot_hours = sum(len(hours) for day in days
                     if (((first_weekday_of_day1 + day - 1) % 7) in WEEKEND) == weekend)
    for _, a in agents[agents["team"] == team].iterrows():
        off = {int(d) for d in str(a["days_off"]).split("|") if d != ""}
        start, length = int(a["shift_start_hour"]), int(a["shift_hours"])
        for day in days:
            weekday = (first_weekday_of_day1 + day - 1) % 7
            if (weekday in WEEKEND) != weekend:
                continue
            for h in hours:  # is the agent on shift during hour h of this day?
                on_today = weekday not in off and start <= h < start + length
                yesterday = (weekday - 1) % 7
                on_from_yesterday = yesterday not in off and h < start + length - 24
                if on_today or on_from_yesterday:
                    capacity += 60.0 * 0.95  # 5% absence on average
    rho = float(work / capacity) if capacity else float("inf")
    avg_agents = capacity / (60.0 * 0.95 * slot_hours) if slot_hours else 0.0
    return rho, avg_agents


def mean_capable_on_shift(agents: pd.DataFrame, when: str, language: str | None, categories: list[str],
                          first_weekday: int, days: list[int]) -> float:
    """Average number of agents on shift per hour of the window who could serve the segment."""
    capable = agents[agents["agent_id"].isin(capable_agents(agents, language, categories))]
    weekend = when.startswith("weekend")
    band = when.split(" ", 1)[1]
    low, high = next((lo, hi) for lo, hi, name in HOUR_BANDS if name == band)
    agent_hours, slot_hours = 0.0, 0
    for day in days:
        weekday = (first_weekday + day - 1) % 7
        if (weekday in WEEKEND) != weekend:
            continue
        for h in range(low, high + 1):
            slot_hours += 1
            for _, a in capable.iterrows():
                off = {int(d) for d in str(a["days_off"]).split("|") if d != ""}
                start, length = int(a["shift_start_hour"]), int(a["shift_hours"])
                on_today = weekday not in off and start <= h < start + length
                on_from_yesterday = (weekday - 1) % 7 not in off and h < start + length - 24
                if on_today or on_from_yesterday:
                    agent_hours += 0.95
    return agent_hours / slot_hours if slot_hours else 0.0


def classify_cause(f: Finding, df: pd.DataFrame, agents: pd.DataFrame, team_skills: dict[str, list[str]],
                   first_weekday: int) -> None:
    """Fill cause_type, the 'why' line and a recommendation for interaction findings."""
    seg = f.segment
    if f.cause_type != "other":
        return
    team = seg.get("team")
    language = seg.get("language")
    categories = [seg["category"]] if "category" in seg else team_skills.get(team or "", [])
    if "when" in seg and (language not in (None, "en") or categories):
        on_shift = mean_capable_on_shift(agents, seg["when"], language if language != "en" else None,
                                         categories, first_weekday, sorted(df["day"].unique()))
        if on_shift < 1.5:
            who = " and ".join(x for x in [
                f"speak {describe('language', language)}" if language not in (None, "en") else "",
                f"handle {', '.join(nice(c) for c in categories)}" if categories else ""] if x)
            f.cause_type = "capacity"
            f.not_explained_by = f"on average only {on_shift:.1f} agents who {who} are on shift on {seg['when']}"
            f.recommendation = f"Put at least one agent who can {who.replace('speak', 'speak').strip()} on shift on {seg['when']}"
            return
    if language and language != "en" and categories:
        agents_ok = capable_agents(agents, language, categories)
        if len(agents_ok) <= 4:
            f.cause_type = "skill_gap"
            f.not_explained_by = (f"only {len(agents_ok)} agents ({', '.join(agents_ok)}) speak {language} "
                                  f"and handle {', '.join(nice(c) for c in categories)}")
            f.recommendation = (f"Cross-train {language}-speaking agents on {', '.join(nice(c) for c in categories)}; "
                                f"meanwhile route these tickets to the {len(agents_ok)} capable agents first")


# ---- Merging, examples, cards ----------------------------------------------------------------

def merge_overlapping(findings: list[Finding], overlap: float = 0.5) -> list[Finding]:
    """Keep the strongest finding of each group that covers mostly the same tickets."""
    kept: list[Finding] = []
    for f in sorted(findings, key=lambda x: x.strength, reverse=True):
        same_story = False
        for k in kept:
            inter = np.logical_and(f.mask, k.mask).sum()
            smaller = min(f.mask.sum(), k.mask.sum())
            if smaller and inter / smaller >= overlap:
                same_story = True
                break
        if not same_story:
            kept.append(f)
    return kept


def add_examples(f: Finding, df: pd.DataFrame, n: int = 3) -> None:
    """Three affected tickets, worst first, with masked text."""
    rows = df[f.mask]
    sort_col = {"mean wait (min)": "wait_min", "mean resolution time (min)": "resolution_min"}.get(f.metric, "transfers")
    if sort_col not in df:
        sort_col = "created_at"
    rows = rows.sort_values([sort_col, "created_at"], ascending=[False, True]).head(n)
    f.examples = []
    for r in rows.itertuples():
        wait = getattr(r, "wait_min", None)  # an uploaded export may have no pickup times
        f.examples.append({"ticket_id": str(r.ticket_id), "created_at": str(r.created_at)[:16],
                           "text": mask_pii(str(r.text)).text,
                           "wait_min": None if wait is None or pd.isna(wait) else round(float(wait), 1),
                           "breached": bool(r.breached)})


def default_recommendation(f: Finding) -> str:
    if f.recommendation:
        return f.recommendation
    return {
        "process": "Route these tickets by the text classifier instead of the menu choice",
        "partner_issue": "Raise with the partner team: check packing and order accuracy at these restaurants",
        "volume_spike": "Check what changed that day (app release, payment gateway, outage)",
    }.get(f.cause_type, "Review this group with the team lead")


def to_card(f: Finding, number: int, total: int) -> dict:
    return {
        "id": f"F{number}", "title": f.title, "cause_type": f.cause_type, "metric": f.metric,
        "value": round(f.value, 2), "comparison_value": round(f.comparison_value, 2),
        "comparison_text": f.comparison_text,
        "segment": {k: (v if not isinstance(v, (np.integer,)) else int(v)) for k, v in f.segment.items()},
        "affected_tickets": int(f.mask.sum()), "affected_share_pct": round(100 * f.mask.sum() / total, 2),
        "strength": round(f.strength, 2), "not_explained_by": f.not_explained_by,
        "examples": f.examples, "recommendation": default_recommendation(f),
    }


# ---- Entry point -----------------------------------------------------------------------------

def find_patterns(history: pd.DataFrame, agents: pd.DataFrame, team_skills: dict[str, list[str]],
                  known_event_days: set[int], first_weekday: int, max_cards: int = 12) -> dict:
    """All scans → merged, typed, ranked evidence cards (as dicts) + explained anomalies."""
    df = label_frame(history, team_skills).reset_index(drop=True)
    dates = {int(d): pd.Timestamp(t).strftime("%a %d %b") for d, t in
             df.groupby("day")["created_at"].min().items()}
    spikes, explained = scan_spikes(df, known_event_days, dates)
    findings = (scan_capacity(df, agents, team_skills, first_weekday) + scan_interactions(df)
                + scan_transfers(df) + scan_partners(df) + spikes)
    for f in findings:
        classify_cause(f, df, agents, team_skills, first_weekday)
    kept = merge_overlapping(findings)[:max_cards]
    for f in kept:
        add_examples(f, df)
    cards = [to_card(f, i + 1, len(df)) for i, f in enumerate(kept)]
    return {"cards": cards, "explained_anomalies": explained, "candidates": len(findings)}


# ---- Small text helpers ----------------------------------------------------------------------

def nice(category: str) -> str:
    return str(category).replace("_", " ")


def describe(dim: str, value) -> str:
    names = {"language": {"hi": "Hindi", "en": "English", "other": "regional-language"}}
    if dim in names:
        return names[dim].get(str(value), str(value))
    if dim == "team":
        return f"Team {value}"
    if dim == "category":
        return nice(value)
    if dim == "channel":
        return {"call": "phone (IVR)", "chat": "chat", "email": "email"}.get(str(value), str(value))
    if dim == "tier":
        return f"{value} customers"
    return str(value)


# ---- Live detection (test period) ------------------------------------------------------------

BIN_MIN = 15
BINS_PER_DAY = 1440 // BIN_MIN
BINS_PER_WEEK = 7 * BINS_PER_DAY


# Chosen on history days 15-42 (never on test days): the fastest rule with at most 2 false
# alerts per week. z >= 4.5 on two checks in a row caught the day-18 payment spike in 90 min
# with 6 false alerts in 28 days; z >= 3.5 on one check was faster (60 min) but gave 54.
LIVE_Z = 4.5
LIVE_PERSIST = 2


def live_alerts(tickets: pd.DataFrame, category_col: str, first_day: int, last_day: int,
                known_event_days: set[int], window_bins: int = 4, weeks: int = 4,
                z_threshold: float = LIVE_Z, persist: int = LIVE_PERSIST, min_excess: int = 8) -> pd.DataFrame:
    """Every 15 minutes, compare each category's tickets in the last hour with the same hour in the
    previous `weeks` weeks (robust z). An alert is raised when the z-score stays above the
    threshold for `persist` checks in a row. Uses only tickets created before the check time.

    `category_col` must be known when a ticket arrives (the classifier's prediction or the
    customer's menu choice), never the final category — that is only known after resolution.
    Returns one row per alert: time, category, count, usual, z, explained (known event day).
    """
    categories = sorted(tickets[category_col].dropna().unique())
    n_bins = last_day * BINS_PER_DAY
    counts = np.zeros((len(categories), n_bins), dtype=float)
    bins = (tickets["minute_of_run"] // BIN_MIN).astype(int).to_numpy()
    cat_index = tickets[category_col].map({c: i for i, c in enumerate(categories)}).to_numpy()
    ok = (bins >= 0) & (bins < n_bins) & ~pd.isna(cat_index)
    np.add.at(counts, (cat_index[ok].astype(int), bins[ok]), 1.0)
    # Rolling count over the last hour, ending at the end of each bin.
    kernel = np.ones(window_bins)
    rolling = np.stack([np.convolve(row, kernel)[:n_bins] for row in counts])

    alerts = []
    first_bin = (first_day - 1) * BINS_PER_DAY
    streak = np.zeros(len(categories), dtype=int)  # consecutive checks above threshold
    for b in range(first_bin, n_bins):
        past = [b - k * BINS_PER_WEEK for k in range(1, weeks + 1) if b - k * BINS_PER_WEEK >= 0]
        if len(past) < 2:
            continue
        for ci, category in enumerate(categories):
            x = rolling[ci, b]
            usual = rolling[ci, past]
            median = float(np.median(usual))
            z = robust_z(float(x), usual) if x - median >= min_excess else 0.0
            streak[ci] = streak[ci] + 1 if z >= z_threshold else 0
            if streak[ci] == persist:  # raise once per episode
                day = b // BINS_PER_DAY + 1
                alerts.append({"minute": (b + 1) * BIN_MIN, "day": day, "category": category,
                               "count_last_hour": int(x), "usual": median, "z": round(z, 1),
                               "explained": day in known_event_days})
    return pd.DataFrame(alerts, columns=["minute", "day", "category", "count_last_hour", "usual", "z", "explained"])


# ---- Any company's export (Upload CSV) -------------------------------------------------------

def find_patterns_basic(df: pd.DataFrame, max_cards: int = 8) -> dict:
    """The same scans for an uploaded export, using only the columns it has.

    Expects canonical columns from ingest (ticket_id, created_at, day, hour, weekday,
    resolution_min, breached) plus any of: final_category, resolved_by_team, priority, channel,
    transfers, wait_min, text. Without agent rosters there is no capacity or skill-gap typing:
    findings keep the cause "other", "process" (transfers) or "volume_spike".
    """
    data = df.copy().reset_index(drop=True)
    data["category"] = data["final_category"].astype(str) if "final_category" in data else "all"
    data["team"] = data["resolved_by_team"].astype(str) if "resolved_by_team" in data else "all"
    for col in ("channel", "priority"):
        if col not in data:
            data[col] = "all"
        data[col] = data[col].astype(str)
    band = data["hour"].map(hour_band)
    data["when"] = np.where(data["weekday"].isin(WEEKEND), "weekend ", "weekday ") + band
    if "text" not in data:
        data["text"] = ""
    metric = "wait_min" if "wait_min" in data and data["wait_min"].notna().mean() > 0.5 else "resolution_min"
    dims = [d for d in ("category", "team", "priority", "channel", "when") if data[d].nunique() > 1]
    findings = scan_interactions(data, metric=metric, dims=dims)  # means skip missing values
    if "transfers" in data:
        data["language"], data["tier"] = "all", "all"  # dimensions scan_transfers expects
        findings += scan_transfers(data)
    dates = {int(d): pd.Timestamp(t).strftime("%a %d %b %Y") for d, t in data.groupby("day")["created_at"].min().items()}
    spikes, _ = scan_spikes(data, set(), dates, window_days=28, min_usual=3.0)
    findings += sorted(spikes, key=lambda f: -f.strength)[:3]  # z-scores dwarf ratios; keep the top 3
    kept = merge_overlapping(findings)[:max_cards]
    for f in kept:
        add_examples(f, data)
    return {"cards": [to_card(f, i + 1, len(data)) for i, f in enumerate(kept)], "metric": metric,
            "candidates": len(findings)}
