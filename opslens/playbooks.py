"""Fix-at-source playbooks: from "route this ticket faster" to "stop this ticket from existing".

What it does: every evidence card (patterns.py) names a cause. This module turns each cause
into an upstream action for a team OUTSIDE support (partner ops, product, training) plus a
scenario spec, and `apply_scenario` changes the tickets or the roster the way that action
would. eval/run_playbooks.py then replays the held-out test days with the change in place, so
each playbook comes with a measured effect: tickets prevented, breaches avoided, agent-hours freed.

Why this design: the review of 16 Oct was right that a support engine which only reshuffles
tickets treats symptoms. But a playbook claim like "saves 65 tickets a day" is a promise unless
it is measured — so every playbook is a counterfactual run in the same fair simulator, and every
business guess (how many customers read a status banner?) is a labelled ASSUMPTION in
config/playbooks.yaml with a low and high value.

Example (real card): "Restaurant cluster 17: 24.5% of its tickets are wrong items vs 9.6%
elsewhere" → partner playbook "kitchen order-check for cluster 17". On the test days the cluster
has 370 tickets, 96 of them wrong items; at the normal 9.6% it would have about 66 fewer, so
the scenario removes 66 wrong-item tickets of cluster 17 and replays the floor.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from opslens.llm.base import LLMUnavailable
from opslens.llm.client import LLMClient
from opslens.patterns import HOUR_BANDS
from opslens.simulate import MINUTES_PER_DAY, Agent

LANGUAGE_NAMES = {"hi": "Hindi", "en": "English", "other": "regional-language"}


@dataclass
class Playbook:
    id: str
    card_id: str
    cause_type: str
    title: str
    owner: str        # the team outside support that acts
    action: str       # what to do, with the card's own numbers
    scenario: dict    # what apply_scenario changes
    assumptions: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)  # key -> (value text, meaning) for the LLM message


def nice(category: str) -> str:
    return category.replace("_", " ")


# ---- From evidence cards to playbooks ---------------------------------------------------------

def playbooks_from_cards(cards: list[dict], agents: list[Agent], team_skills: dict[str, list[str]],
                         cfg: dict) -> list[Playbook]:
    """One playbook per card whose cause has an upstream fix (cards of type 'other' get none)."""
    out = []
    for card in cards:
        maker = MAKERS.get(card["cause_type"])
        pb = maker(card, agents, team_skills, cfg) if maker else None
        if pb is not None:
            pb.facts = card_facts(card)
            out.append(pb)
    return out


def card_facts(card: dict) -> dict[str, tuple[str, str]]:
    """Facts the LLM may cite, as key -> (value WITH its unit, meaning). The unit travels with the
    value, so a sentence like "phone tickets are transferred {{issue_value}}" reads correctly."""
    issue = re.sub(r"\s+", " ", re.sub(r"[\d.]+\s*×?", "", card["title"])).strip()  # title without numbers
    metric = card["metric"]
    # Any number inside the metric name goes into the value text: the LLM may not write digits.
    if "(min)" in metric:
        unit, name = " min", re.sub(r"\s*\(.*\)", "", metric)        # mean wait (min)
    elif metric.startswith("share"):
        unit, name = "%", metric
    elif "per 100" in metric:
        unit, name = " per 100 tickets", metric.split(" per 100")[0]  # transfers per 100 tickets
    elif "rho" in metric:
        unit, name = "× the agent-time on shift", "work"            # work ÷ agent-time (rho)
    else:
        unit, name = "", metric

    def show(v: float) -> str:
        return f"{v:.1f}{unit}" if abs(v) < 100 else f"{v:,.0f}{unit}"

    facts = {"issue_value": (show(card["value"]), f"{name} of the customer tickets in the problem group ({issue})"),
             "normal_value": (show(card["comparison_value"]), f"{name} for comparable tickets"),
             "affected": (f"{card['affected_tickets']:,} tickets", "size of the problem group on the history days")}
    if "restaurant_cluster_id" in card["segment"]:
        facts["cluster"] = (str(card["segment"]["restaurant_cluster_id"]), "the restaurant cluster's number")
    return facts


def process_playbook(card: dict, agents, team_skills, cfg) -> Playbook | None:
    if card["segment"].get("channel") is None or card["value"] <= 0:
        return None
    channel = card["segment"]["channel"]
    keep = min(1.0, card["comparison_value"] / card["value"])  # error rate falls to other channels' level
    return Playbook(
        id=f"pb_{card['id']}", card_id=card["id"], cause_type="process",
        title="Fix the phone menu (IVR)" if channel == "call" else f"Fix the {channel} intake form",
        owner="Product / IVR team",
        action=(f"{channel.title()} tickets are transferred {card['value']:.1f} times per 100 vs "
                f"{card['comparison_value']:.1f} for other channels: rewrite the menu choices and confirm the issue "
                f"with one spoken question before routing."),
        scenario={"kind": "fix_menu", "channel": channel, "keep_error_share": round(keep, 3)},
        assumptions=[f"the new menu is as accurate as the other channels' ({keep:.0%} of today's wrong choices remain)"],
    )


def partner_playbook(card: dict, agents, team_skills, cfg) -> Playbook | None:
    seg = card["segment"]
    if "restaurant_cluster_id" not in seg:
        return None
    cluster, category = int(seg["restaurant_cluster_id"]), seg["category"]
    share = cfg["partner_fix_share"]
    return Playbook(
        id=f"pb_{card['id']}", card_id=card["id"], cause_type="partner_issue",
        title=f"Kitchen order-check for restaurant cluster {cluster}", owner="Partner operations",
        action=(f"Cluster {cluster}: {card['value']:.1f}% of its tickets are {nice(category)} vs "
                f"{card['comparison_value']:.1f}% elsewhere. Send the partners a quality alert and switch on "
                f"order-check (packing photo before pickup) for this cluster."),
        scenario={"kind": "partner_fix", "restaurant_cluster_id": cluster, "category": category,
                  "normal_share": card["comparison_value"] / 100.0, "fix_share": share},
        assumptions=[f"ASSUMPTION: {share:.0%} of the cluster's extra {nice(category)} tickets go away"],
    )


def skill_gap_playbook(card: dict, agents: list[Agent], team_skills, cfg) -> Playbook | None:
    seg = card["segment"]
    language, team = seg.get("language"), seg.get("team")
    if language is None or team is None:
        return None
    skills = frozenset(team_skills[team])
    chosen = pick_cross_trainees(agents, language, skills, cfg["cross_train_agents"])
    if not chosen:
        return None
    lang = LANGUAGE_NAMES.get(language, language)
    cats = " and ".join(nice(c) for c in sorted(skills))
    return Playbook(
        id=f"pb_{card['id']}", card_id=card["id"], cause_type="skill_gap",
        title=f"Cross-train {len(chosen)} {lang}-speaking agents on {cats}", owner="Training / workforce",
        action=(f"{lang} {cats} tickets wait {card['value']:.0f} min vs {card['comparison_value']:.0f} min. "
                f"Train {', '.join(chosen)} on {cats}: they already speak {lang} and their shifts cover the "
                f"hours no trained {lang} speaker works today."),
        scenario={"kind": "cross_train", "agents": chosen, "skills": sorted(skills)},
        assumptions=["training is finished before the period and trained agents work at full speed"],
    )


def volume_spike_playbook(card: dict, agents, team_skills, cfg) -> Playbook | None:
    hours, share = cfg["banner_hours"], cfg["banner_deflect_share"]
    return Playbook(
        id=f"pb_{card['id']}", card_id=card["id"], cause_type="volume_spike",
        title="Status banner the moment a spike alert fires", owner="Product / customer comms",
        action=(f"Spikes like {nice(card['segment']['category'])} on day {card['segment']['day']} come from one "
                f"cause. When OpsLens raises a live spike alert, show an in-app status banner on that issue "
                f"for {hours} hours, so customers know it is being fixed."),
        scenario={"kind": "status_banner", "hours": hours, "deflect_share": share},
        assumptions=[f"ASSUMPTION: {share:.0%} of customers who see the banner do not open a ticket"],
    )


def capacity_playbook(card: dict, agents, team_skills, cfg) -> Playbook | None:
    seg = card["segment"]
    team, when = seg.get("team"), seg.get("when")
    cats = [c for c in cfg["self_serve_categories"] if c in team_skills.get(team, [])]
    if not cats or not when:
        return None
    limit, uptake = cfg["self_serve_max_order_inr"], cfg["self_serve_uptake"]
    return Playbook(
        id=f"pb_{card['id']}", card_id=card["id"], cause_type="capacity",
        title=f"Self-serve instant refund on {when} (Team {team})", owner="Product",
        action=(f"Team {team} is overloaded on {when}. Offer an in-app instant refund for "
                f"{' and '.join(nice(c) for c in cats)} claims on orders up to ₹{limit} in that window, "
                f"so these customers need no agent."),
        scenario={"kind": "self_serve", "when": when, "categories": cats, "max_order_inr": limit, "uptake": uptake},
        assumptions=[f"ASSUMPTION: {uptake:.0%} of eligible customers use self-serve",
                     f"policy choice: only orders up to ₹{limit}"],
    )


MAKERS = {"process": process_playbook, "partner_issue": partner_playbook, "skill_gap": skill_gap_playbook,
          "volume_spike": volume_spike_playbook, "capacity": capacity_playbook}


def week_hours(agent: Agent) -> set[int]:
    """Hours of the week (0 = Monday 00:00) the agent is on shift. A night shift belongs to the
    day it starts, as in the roster."""
    hours = set()
    for day in range(7):
        if day in agent.days_off:
            continue
        for minute in range(agent.shift_start_min, agent.shift_start_min + agent.shift_minutes, 60):
            hours.add((day * 24 + minute // 60) % 168)
    return hours


def pick_cross_trainees(agents: list[Agent], language: str, skills: frozenset[str], k: int) -> list[str]:
    """Agents who speak the language but lack the skills, chosen one by one for the most shift-hours
    that no capable agent (language + skills) covers yet."""
    covered: set[int] = set()
    for a in agents:
        if language in a.languages and skills <= a.skills:
            covered |= week_hours(a)
    candidates = [a for a in agents if language in a.languages and not skills <= a.skills]
    chosen = []
    for _ in range(k):
        best = max(candidates, key=lambda a: (len(week_hours(a) - covered), a.agent_id), default=None)
        if best is None or not week_hours(best) - covered:
            break
        chosen.append(best.agent_id)
        covered |= week_hours(best)
        candidates.remove(best)
    return chosen


# ---- Scenario: change the world the way the playbook would -----------------------------------

def apply_scenario(tickets: pd.DataFrame, preds: pd.DataFrame, agents: list[Agent], spec: dict,
                   first_day: int, last_day: int, first_weekday: int, alerts: list[dict] | None = None,
                   seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame, list[Agent], dict]:
    """Return changed copies of (tickets, predictions, agents) and what changed.

    Only tickets of days first_day..last_day are touched. The same tickets are removed or fixed
    for every policy and every seed (fixed `seed`), so the comparison stays paired.
    """
    rng = np.random.default_rng(seed)
    tickets, preds = tickets.copy(), preds.copy()
    window = tickets["day"].between(first_day, last_day)
    kind = spec["kind"]
    info: dict = {"kind": kind, "removed": 0, "changed": 0}
    remove = pd.Series(False, index=tickets.index)

    if kind == "fix_menu":
        wrong = window & (tickets["channel"] == spec["channel"]) & (tickets["selected_category"] != tickets["category"])
        fixed = pick(rng, wrong, 1.0 - spec["keep_error_share"])
        tickets.loc[fixed, "selected_category"] = tickets.loc[fixed, "category"]
        # A fixed menu is as trustworthy as chat's, so the classifier would follow it.
        new_pred = dict(zip(tickets.loc[fixed, "ticket_id"], tickets.loc[fixed, "category"]))
        preds["pred_final"] = preds["ticket_id"].map(new_pred).fillna(preds["pred_final"])
        info["changed"] = int(fixed.sum())
    elif kind == "partner_fix":
        cluster = window & (tickets["restaurant_cluster_id"] == spec["restaurant_cluster_id"])
        bad = cluster & (tickets["category"] == spec["category"])
        n, w, s = int(cluster.sum()), int(bad.sum()), spec["normal_share"]
        excess = max(0.0, (w - s * n) / (1.0 - s)) * spec["fix_share"]  # (w − x) / (n − x) = s
        remove = pick(rng, bad, excess / w if w else 0.0)
    elif kind == "cross_train":
        extra = frozenset(spec["skills"])
        agents = [dataclasses.replace(a, skills=a.skills | extra) if a.agent_id in spec["agents"] else a
                  for a in agents]
        info["changed"] = len(spec["agents"])
    elif kind == "status_banner":
        pred_of = dict(zip(preds["ticket_id"], preds["pred_final"]))
        category = tickets["ticket_id"].map(pred_of)
        shown = pd.Series(False, index=tickets.index)
        for alert in alerts or []:
            start = alert["minute"]
            shown |= window & (category == alert["category"]) & tickets["created_min"].between(
                start, start + spec["hours"] * 60, inclusive="left")
        remove = pick(rng, shown, spec["deflect_share"])
        info["alerts"] = len(alerts or [])
    elif kind == "self_serve":
        eligible = (window & in_window(tickets, spec["when"], first_weekday)
                    & tickets["selected_category"].isin(spec["categories"])
                    & (tickets["order_value_inr"] <= spec["max_order_inr"]))
        remove = pick(rng, eligible, spec["uptake"])
    else:
        raise ValueError(f"unknown scenario {kind!r}")

    info["removed"] = int(remove.sum())
    return tickets[~remove].reset_index(drop=True), preds, agents, info


def pick(rng: np.random.Generator, mask: pd.Series, share: float) -> pd.Series:
    """A random `share` of the rows where mask is True (rounded to whole tickets)."""
    rows = np.flatnonzero(mask.to_numpy())
    n = int(round(min(max(share, 0.0), 1.0) * len(rows)))
    chosen = rng.choice(rows, size=n, replace=False) if n else np.array([], dtype=int)
    out = np.zeros(len(mask), dtype=bool)
    out[chosen] = True
    return pd.Series(out, index=mask.index)


def in_window(tickets: pd.DataFrame, when: str, first_weekday: int) -> pd.Series:
    """Tickets created in a window like 'weekend dinner' (same labels as patterns.py)."""
    day_type, band = when.split(" ", 1)
    low, high = next((lo, hi) for lo, hi, name in HOUR_BANDS if name == band)
    minute_of_day = tickets["created_min"] % MINUTES_PER_DAY
    hour = (minute_of_day // 60).astype(int)
    weekday = (first_weekday + tickets["day"] - 1) % 7
    weekend = weekday.isin([5, 6])
    right_day = weekend if day_type == "weekend" else ~weekend
    return right_day & hour.between(low, high)


# ---- The message to the owner team (LLM, no digits) ------------------------------------------

SYSTEM = (
    "You write a short message from the head of a food-delivery support floor to another team, "
    "asking them to take one action. Use ONLY the facts given. Never write a number yourself, in "
    "digits or in words: refer to numbers as {{key}} exactly as listed. Two or three sentences, "
    'polite and concrete. Reply with JSON only: {"message": "..."}'
)


def draft_message(pb: Playbook, client: LLMClient | None) -> dict:
    """LLM-written request to the owner team; any digit or unknown key → the template action."""
    from opslens.brief import check_and_fill  # same rule as the daily brief

    facts = {k: (v, desc, "") for k, (v, desc) in pb.facts.items()}
    if client is not None:
        title = re.sub(r"\s+", " ", re.sub(r"\d+", "", pb.title)).strip()  # numbers only via keys
        prompt = (f"To: {pb.owner}\nAction: {title}\nCause type: {pb.cause_type.replace('_', ' ')}\n"
                  "Facts:\n" + "\n".join(f"- {{{{{k}}}}}: {desc}" for k, (_, desc, _) in facts.items()))
        try:
            reply = client.ask_json("playbook_message", SYSTEM, prompt)
            text = reply.data.get("message", "") if isinstance(reply.data, dict) else ""
            filled = check_and_fill(text, facts) if text else None
            if filled:
                return {"text": filled, "source": "llm"}
        except LLMUnavailable:
            pass
    return {"text": pb.action, "source": "template"}
