from __future__ import annotations

import dataclasses

import pandas as pd

from opslens.impact import mean_std, paired_ci
from opslens.playbooks import apply_scenario
from opslens.simulate import Agent

PLAN_KPIS = [
    ("breaches", "turnaround", "customers who missed the SLA", "tickets", "lower"),
    ("breach_pct", "turnaround", "SLA breach rate", "%", "lower"),
    ("mean_resolution_min", "turnaround", "mean resolution time", "min", "lower"),
    ("p90_resolution_min", "turnaround", "P90 resolution time", "min", "lower"),
    ("tickets", "productivity", "tickets that reach an agent", "tickets", "lower"),
    ("busy_agent_hours", "productivity", "agent-hours of work", "h", "lower"),
    ("tickets_per_agent_hour", "productivity", "tickets resolved per agent-hour", "tickets/h", None),
    ("transfers", "productivity", "transfers between teams", "tickets", "lower"),
    ("reopen_rate_pct", "quality", "reopen rate", "%", "lower"),
    ("late_minutes_per_100", "quality", "minutes past SLA per 100 tickets", "min", "lower"),
]
HEADINGS = ["turnaround", "productivity", "quality"]
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def staffing_items(plans: list[dict], agents: list[Agent]) -> list[dict]:
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


def apply_staffing_move(agents: list[Agent], item: dict) -> list[Agent]:
    change = item["change"]
    override = (item["first_day"], item["last_day"], change["start_hour"] * 60, frozenset(change["days_off"]))
    return [dataclasses.replace(a, overrides=a.overrides + (override,)) if a.agent_id == change["agent_id"] else a
            for a in agents]


def apply_items(tickets: pd.DataFrame, preds: pd.DataFrame, agents: list[Agent], items: list[dict],
                first_day: int, last_day: int, first_weekday: int, alerts: list[dict] | None = None
                ) -> tuple[pd.DataFrame, pd.DataFrame, list[Agent], dict[str, dict]]:
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
    start_min, days_off = agent.schedule_on(day - 1)
    if (first_weekday + day - 1) % 7 in days_off:
        return None
    return start_min, start_min + agent.shift_minutes


def item_changes(item: dict, info: dict, agents_before: list[Agent], agents_after: list[Agent],
                 days: list[int], first_weekday: int) -> dict:
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


def plan_kpis(k: dict[str, float]) -> dict[str, float]:
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
    return {
        "headings": {h: [key for key, heading, _, _, _ in PLAN_KPIS if heading == h] for h in HEADINGS},
        "labels": {key: label for key, _, label, _, _ in PLAN_KPIS},
        "units": {key: unit for key, _, _, unit, _ in PLAN_KPIS},
        "better": {key: better for key, _, _, _, better in PLAN_KPIS},
    }


def effect_by_kpi(without: list[dict], with_plan: list[dict]) -> dict[str, dict]:
    out = {}
    for key, _, _, _, _ in PLAN_KPIS:
        a, b = [r[key] for r in without], [r[key] for r in with_plan]
        ci = paired_ci(b, a)
        out[key] = {"without": mean_std(a)[0], "with": mean_std(b)[0], "diff": ci["mean_diff"],
                    "ci_low": ci["ci_low"], "ci_high": ci["ci_high"], "n": ci["n"]}
    return out


def live_delta(without: list[dict], with_plan: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {"without": {}, "with": {}, "delta": {}, "delta_by_seed": {}}
    for key, _, _, _, _ in PLAN_KPIS:
        a, b = [r[key] for r in without], [r[key] for r in with_plan]
        out["without"][key] = round(sum(a) / len(a), 3)
        out["with"][key] = round(sum(b) / len(b), 3)
        out["delta"][key] = round((sum(b) - sum(a)) / len(a), 3)
        out["delta_by_seed"][key] = [round(y - x, 3) for x, y in zip(a, b)]
    return out


def run_plan_day(inputs: dict, job: dict) -> dict:
    from opslens.whatif import simulate_day

    day, items = job["day"], job["items"]
    tickets, agents, preds = inputs["tickets"], inputs["agents"], inputs["preds"]
    changes = {}
    if items:
        preds_df = pd.DataFrame({"ticket_id": list(preds), "pred_final": list(preds.values())})
        tickets, preds_df, plan_agents, info = apply_items(tickets, preds_df, agents, items, day, day,
                                                           job["first_weekday"], job["alerts"])
        sim_days = [day - 1, day, day + 1]
        changes = {item["id"]: item_changes(item, info[item["id"]], agents, plan_agents, sim_days,
                                            job["first_weekday"]) for item in items}
        agents, preds = plan_agents, dict(zip(preds_df["ticket_id"], preds_df["pred_final"]))
    kpis = simulate_day(tickets, agents, preds, inputs["model"], inputs["weights"], day, job["seed"])
    return {"kpis": plan_kpis(kpis), "changes": changes}


def plan_jobs(items: list[dict], day: int, seeds: list[int], alerts: list[dict], first_weekday: int
              ) -> tuple[list[dict], list[dict]]:
    base = {"day": day, "alerts": alerts, "first_weekday": first_weekday}
    plan = [{k: v for k, v in item.items() if k != "effect"} for item in items]
    without = [{**base, "seed": s, "items": []} for s in seeds]
    with_plan = [{**base, "seed": s, "items": plan} for s in seeds]
    return without, with_plan


def impact_answer(items: list[dict], day: int, seeds: list[int], first_weekday: int,
                  without: list[dict], with_plan: list[dict], seconds: float) -> dict:
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
