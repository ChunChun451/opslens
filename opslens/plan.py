"""Your plan: the recommendations a manager accepts, and what they would change.

What it does: OpsLens recommends two kinds of big decisions that a person must approve:
- **staffing moves** (staffing.py): one agent, one week, a new shift start or day off;
- **fix-at-source playbooks** (playbooks.py): an action for a team outside support.
Each one becomes a *plan item* with a stable id ("staff_43_C02", "pb_F2"). `apply_items`
changes the roster and the tickets the way the accepted items would. eval/run_plan_items.py
measures every item alone on the 14 test days (5 seeds); the live endpoint POST /api/plan/impact
replays one day with ALL accepted items together. Both use `apply_items`, so the precomputed and
the live numbers come from one code path.

Why this design:
- Small decisions (who takes ticket 812) run automatically; the manager approves only the big
  ones and sees their effect first (docs/PLAN_V3.md, decision 3).
- "Without" is always OpsLens dispatch on today's published roster with nothing accepted.
  "With" is the same days, same tickets, same luck (common random numbers) plus the plan, so
  the difference is the plan's effect and nothing else.
- Items are applied in catalogue order, whatever order the manager clicked, so the same plan
  always gives the same answer.
- Results are grouped under the problem statement's three words: turnaround, productivity,
  service quality.

Example: "staff_43_C02" = Deepak W. (C02, Team C) starts at 07:00 instead of 08:00 on days
43-49. `apply_staffing_move` gives C02 one override (days 43-49, start minute 420, same days
off); the other 39 agents are untouched. Measured alone on the test days (5 seeds), customers
who miss their SLA go from 379.8 to 378.6: -1.2, 95% CI [-5.45, +3.05], no clear effect. The
playbook "pb_F2" (cross-train A09 and D11) alone: -26.8 [-39.01, -14.59] (eval/parts/plan_items.json).
"""

from __future__ import annotations

import dataclasses

import pandas as pd

from opslens.impact import mean_std, paired_ci
from opslens.playbooks import apply_scenario
from opslens.simulate import Agent

# (KPI key, heading, plain words, unit, which direction is better). Keys have no dots, so the
# dashboard can use them in evidence paths ("planimpact.delta.breaches").
PLAN_KPIS = [
    ("breaches", "turnaround", "customers who missed the SLA", "tickets", "lower"),
    ("breach_pct", "turnaround", "SLA breach rate", "%", "lower"),
    ("mean_resolution_min", "turnaround", "mean resolution time", "min", "lower"),
    ("p90_resolution_min", "turnaround", "P90 resolution time", "min", "lower"),
    ("tickets", "productivity", "tickets that reach an agent", "tickets", "lower"),
    ("busy_agent_hours", "productivity", "agent-hours of work", "h", "lower"),
    # Falls when a playbook prevents tickets: agents are less busy, not slower. So no direction.
    ("tickets_per_agent_hour", "productivity", "tickets resolved per agent-hour", "tickets/h", None),
    ("transfers", "productivity", "transfers between teams", "tickets", "lower"),
    ("reopen_rate_pct", "quality", "reopen rate", "%", "lower"),
    ("late_minutes_per_100", "quality", "minutes past SLA per 100 tickets", "min", "lower"),
]
HEADINGS = ["turnaround", "productivity", "quality"]
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---- The catalogue of plan items --------------------------------------------------------------

def staffing_items(plans: list[dict], agents: list[Agent]) -> list[dict]:
    """One item per staffing move in data/generated/staffing_plan.json.

    A weekly plan lists every agent's shift; a move changes exactly one agent (staffing.py
    allows one change per person per week), so the item keeps only that agent's new shift.
    """
    by_id = {a.agent_id: a for a in agents}
    items = []
    for plan in plans:
        shifts = {s["agent_id"]: s for s in plan["shifts"]}
        for move in plan["moves"]:
            agent = by_id[move["agent_id"]]
            new = shifts[move["agent_id"]]
            items.append({
                "id": f"staff_{plan['first_day']}_{agent.agent_id}",
                "kind": "staffing",
                "title": f"{agent.name} ({agent.agent_id}, Team {agent.team}): {move['change']}",
                "owner": "Team lead / workforce planning",
                "first_day": plan["first_day"], "last_day": plan["last_day"],
                "when": f"days {plan['first_day']}-{plan['last_day']}",
                "change": {"agent_id": agent.agent_id, "start_hour": int(new["start_hour"]),
                           "days_off": sorted(int(d) for d in new["days_off"])},
                "assumptions": ["same person, same hours per week: only the start time or a day off moves"],
            })
    return items


def playbook_items(playbooks: list[dict], test_days: tuple[int, int]) -> list[dict]:
    """One item per fix-at-source playbook (entries of eval/parts/playbooks.json)."""
    return [{
        "id": pb["id"],
        "kind": "playbook",
        "title": pb["title"],
        "owner": pb["owner"],
        "first_day": test_days[0], "last_day": test_days[1],
        "when": f"days {test_days[0]}-{test_days[1]}",
        "action": pb["action"],
        "scenario": pb["scenario"],
        "assumptions": pb.get("assumptions", []),
        "card_id": pb.get("card_id"),
    } for pb in playbooks]


def check_ids(ids, catalogue: list[dict]) -> list[dict]:
    """The accepted items in catalogue order. Unknown or repeated ids raise ValueError."""
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ValueError("items must be a list of plan item ids (strings)")
    known = {item["id"] for item in catalogue}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ValueError(f"unknown plan item ids: {', '.join(unknown)}")
    wanted = set(ids)
    if len(wanted) != len(ids):
        raise ValueError("an item id appears twice")
    return [item for item in catalogue if item["id"] in wanted]


# ---- Applying items ---------------------------------------------------------------------------

def apply_staffing_move(agents: list[Agent], item: dict) -> list[Agent]:
    """The roster with ONE move in place: that agent gets a week-specific shift, nobody else changes."""
    change = item["change"]
    override = (item["first_day"], item["last_day"], change["start_hour"] * 60, frozenset(change["days_off"]))
    return [dataclasses.replace(a, overrides=a.overrides + (override,)) if a.agent_id == change["agent_id"] else a
            for a in agents]


def apply_items(tickets: pd.DataFrame, preds: pd.DataFrame, agents: list[Agent], items: list[dict],
                first_day: int, last_day: int, first_weekday: int, alerts: list[dict] | None = None
                ) -> tuple[pd.DataFrame, pd.DataFrame, list[Agent], dict[str, dict]]:
    """Changed copies of (tickets, predictions, agents) with every item in place, and what each changed.

    Staffing moves carry their own week; playbooks touch only tickets of days first_day..last_day
    (the warm-up day stays as it was, as in eval/run_playbooks.py). `items` must be in catalogue
    order (check_ids returns them that way).
    """
    changed: dict[str, dict] = {}
    for item in items:
        if item["kind"] == "staffing":
            agents = apply_staffing_move(agents, item)
            changed[item["id"]] = {"kind": "staffing", "removed": 0, "changed": 1}
        else:
            tickets, preds, agents, info = apply_scenario(tickets, preds, agents, item["scenario"],
                                                          first_day, last_day, first_weekday, alerts=alerts)
            changed[item["id"]] = info
    return tickets, preds, agents, changed


def shift_on(agent: Agent, day: int, first_weekday: int) -> tuple[int, int] | None:
    """(start, end) minute of the agent's shift that starts on calendar day `day`, or None if off."""
    start_min, days_off = agent.schedule_on(day - 1)
    if (first_weekday + day - 1) % 7 in days_off:
        return None
    return start_min, start_min + agent.shift_minutes


def item_changes(item: dict, info: dict, agents_before: list[Agent], agents_after: list[Agent],
                 days: list[int], first_weekday: int) -> dict:
    """What the item changes on these days, in plain counts. A staffing move is only in effect if
    the agent's shift is different on one of the days; a playbook only if it removed or fixed a
    ticket, or trained someone."""
    kind = item["kind"] if item["kind"] == "staffing" else item["scenario"]["kind"]
    out = {"tickets_removed": int(info.get("removed", 0)),
           "tickets_rerouted": int(info.get("changed", 0)) if kind == "fix_menu" else 0,
           "agents_changed": 0}
    if kind == "staffing":
        agent_id = item["change"]["agent_id"]
        before = next(a for a in agents_before if a.agent_id == agent_id)
        after = next(a for a in agents_after if a.agent_id == agent_id)
        out["agents_changed"] = int(any(shift_on(before, d, first_weekday) != shift_on(after, d, first_weekday)
                                        for d in days))
    elif kind == "cross_train":
        out["agents_changed"] = len(item["scenario"]["agents"])
    out["in_effect"] = any(v > 0 for v in out.values())
    return out


# ---- KPIs under the three headings ------------------------------------------------------------

def plan_kpis(k: dict[str, float]) -> dict[str, float]:
    """The plan's KPIs for one run, from impact.summarize. Counts are made from the percentages:
    2% of 1,500 tickets = 30 customers who missed the SLA."""
    n = k["tickets"]
    return {
        "breaches": k["turnaround.breach_pct"] * n / 100.0,
        "breach_pct": k["turnaround.breach_pct"],
        "mean_resolution_min": k["turnaround.mean_resolution_min"],
        "p90_resolution_min": k["turnaround.p90_resolution_min"],
        "tickets": float(n),
        "busy_agent_hours": k["productivity.busy_agent_hours"],
        "tickets_per_agent_hour": k["productivity.tickets_per_agent_hour"],
        "transfers": k["productivity.transfers_per_100"] * n / 100.0,
        "reopen_rate_pct": k["quality.reopen_rate_pct"],
        "late_minutes_per_100": k["quality.late_minutes_per_100"],
    }


def kpi_info() -> dict:
    """How to show the KPIs: which keys go under which heading (in order), and each key's plain
    words, unit and better direction. The same block is in results.plan and in every live answer."""
    return {
        "headings": {h: [key for key, heading, _, _, _ in PLAN_KPIS if heading == h] for h in HEADINGS},
        "labels": {key: label for key, _, label, _, _ in PLAN_KPIS},
        "units": {key: unit for key, _, _, unit, _ in PLAN_KPIS},
        "better": {key: better for key, _, _, _, better in PLAN_KPIS},
    }


def effect_by_kpi(without: list[dict], with_plan: list[dict]) -> dict[str, dict]:
    """Precomputed effect over paired seeds, per KPI: mean without, mean with, mean difference and
    its 95% CI. without[i] and with_plan[i] must be the same seed."""
    out = {}
    for key, _, _, _, _ in PLAN_KPIS:
        a, b = [r[key] for r in without], [r[key] for r in with_plan]
        ci = paired_ci(b, a)
        out[key] = {"without": mean_std(a)[0], "with": mean_std(b)[0], "diff": ci["mean_diff"],
                    "ci_low": ci["ci_low"], "ci_high": ci["ci_high"], "n": ci["n"]}
    return out


def live_delta(without: list[dict], with_plan: list[dict]) -> dict[str, dict]:
    """Live answer for one day, per KPI: mean over the seeds without and with, the change, and the
    change seed by seed (so a noisy day shows as noisy)."""
    out: dict[str, dict] = {"without": {}, "with": {}, "delta": {}, "delta_by_seed": {}}
    for key, _, _, _, _ in PLAN_KPIS:
        a, b = [r[key] for r in without], [r[key] for r in with_plan]
        out["without"][key] = round(sum(a) / len(a), 3)
        out["with"][key] = round(sum(b) / len(b), 3)
        out["delta"][key] = round((sum(b) - sum(a)) / len(a), 3)
        out["delta_by_seed"][key] = [round(y - x, 3) for x, y in zip(a, b)]
    return out


# ---- Live: one day, without and with the plan -------------------------------------------------

def run_plan_day(inputs: dict, job: dict) -> dict:
    """One simulation for the live endpoint: `job` = {day, seed, items, alerts, first_weekday}.
    `inputs` = the server's tickets, predictions (dict), agents, risk model and weights.
    With no items this is the "without" run."""
    from opslens.whatif import simulate_day  # the What-if panel's one-day runner

    day, items = job["day"], job["items"]
    tickets, agents, preds = inputs["tickets"], inputs["agents"], inputs["preds"]
    changes = {}
    if items:
        preds_df = pd.DataFrame({"ticket_id": list(preds), "pred_final": list(preds.values())})
        tickets, preds_df, plan_agents, info = apply_items(tickets, preds_df, agents, items, day, day,
                                                           job["first_weekday"], job["alerts"])
        sim_days = [day - 1, day, day + 1]  # warm-up day, the day, and the drain into the next morning
        changes = {item["id"]: item_changes(item, info[item["id"]], agents, plan_agents, sim_days,
                                            job["first_weekday"]) for item in items}
        agents, preds = plan_agents, dict(zip(preds_df["ticket_id"], preds_df["pred_final"]))
    kpis = simulate_day(tickets, agents, preds, inputs["model"], inputs["weights"], day, job["seed"])
    return {"kpis": plan_kpis(kpis), "changes": changes}


def plan_jobs(items: list[dict], day: int, seeds: list[int], alerts: list[dict], first_weekday: int
              ) -> tuple[list[dict], list[dict]]:
    """The "without" and "with" jobs for one day: one pair per seed. The items travel without their
    precomputed effects (the run does not need them)."""
    base = {"day": day, "alerts": alerts, "first_weekday": first_weekday}
    plan = [{k: v for k, v in item.items() if k != "effect"} for item in items]
    without = [{**base, "seed": s, "items": []} for s in seeds]
    with_plan = [{**base, "seed": s, "items": plan} for s in seeds]
    return without, with_plan


def impact_answer(items: list[dict], day: int, seeds: list[int], first_weekday: int,
                  without: list[dict], with_plan: list[dict], seconds: float) -> dict:
    """The endpoint's answer: the items and what they change that day, then without / with /
    delta per KPI, and which KPIs go under turnaround, productivity and quality."""
    changes = with_plan[0]["changes"] if with_plan else {}
    return {
        "day": day,
        "weekday": DAY_NAMES[(first_weekday + day - 1) % 7],
        "policy": "opslens",
        "seeds": seeds,
        "items": [{"id": item["id"], "kind": item["kind"], "title": item["title"], "when": item["when"],
                   **changes.get(item["id"], {})} for item in items],
        **kpi_info(),
        **live_delta([r["kpis"] for r in without], [r["kpis"] for r in with_plan]),
        "seconds": round(seconds, 1),
        "note": (f"Simulated now: OpsLens dispatch on day {day} (day {day - 1} as warm-up), {len(seeds)} "
                 f"seed{'s' if len(seeds) > 1 else ''}; the same tickets and luck without and with the plan."),
    }
