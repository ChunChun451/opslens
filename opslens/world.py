"""Build a simulation `World` from a tickets table, the roster and a seed.

Why this file exists: the generator (to make history), the evaluation (to compare policies)
and the What-if panel all need the same thing — tickets + agents + one seed's luck draws.

Common random numbers: every luck draw is looked up by the ticket's *number* (T000812 → 812),
not by its row position. If a stress test adds extra tickets, the original tickets still
get exactly the same handle times and reopen draws.

Example: ticket T000812, refund via chat, seed 3. Its three handle-time draws are
    12 min (median) × 1.0 (chat) × exp(0.5 × z) with z = the 812th row of seed 3's normals,
so with z = 0.4 → 12 × e^0.2 ≈ 14.7 minutes for the first attempt — for every policy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from opslens.config import load_config
from opslens.simulate import MINUTES_PER_DAY, Agent, World

ALL_CATEGORIES = [
    "late_delivery", "missing_item", "wrong_item", "refund",
    "payment_failure", "app_bug", "account", "restaurant_partner",
]

# Separate random streams so adding one kind of draw never shifts another.
STREAM_HANDLE, STREAM_REOPEN, STREAM_REOPEN_DELAY, STREAM_ABSENCE = 1, 2, 3, 4


def load_agents(roster: dict[str, Any] | None = None) -> list[Agent]:
    """Agents from config/roster.yaml (team skills + extra skills)."""
    roster = roster or load_config("roster")
    teams = roster["teams"]
    agents: list[Agent] = []
    for row in roster["agents"]:
        team_skills = frozenset(teams[row["team"]]["skills"])
        extra = row.get("extra_skills", [])
        extra_set = frozenset(ALL_CATEGORIES) if extra == "all" else frozenset(extra)
        agents.append(
            Agent(
                agent_id=row["id"],
                name=row["name"],
                team=row["team"],
                team_skills=team_skills,
                skills=team_skills | extra_set,
                languages=frozenset(row["langs"]),
                shift_start_min=int(row["start"]) * 60,
                shift_minutes=int(roster["shift_hours"]) * 60,
                days_off=frozenset(row["days_off"]),
                max_concurrent=int(row.get("max_concurrent", roster.get("max_concurrent", 1))),
            )
        )
    return agents


def agents_table(agents: list[Agent]) -> pd.DataFrame:
    """Agents as a table (for data/generated/agents.csv and the dashboard)."""
    return pd.DataFrame([
        {
            "agent_id": a.agent_id, "name": a.name, "team": a.team,
            "skills": "|".join(sorted(a.skills)), "team_skills": "|".join(sorted(a.team_skills)),
            "languages": "|".join(sorted(a.languages)), "shift_start_hour": a.shift_start_min // 60,
            "shift_hours": a.shift_minutes // 60, "days_off": "|".join(str(d) for d in sorted(a.days_off)),
            "max_concurrent": a.max_concurrent,
        }
        for a in agents
    ])


def ticket_numbers(ticket_ids: pd.Series) -> np.ndarray:
    """'T000812' → 812."""
    return ticket_ids.str.slice(1).astype(int).to_numpy()


def build_world(
    tickets: pd.DataFrame,
    seed: int,
    agents: list[Agent] | None = None,
    gen_cfg: dict[str, Any] | None = None,
    sla_cfg: dict[str, Any] | None = None,
    n_days: int | None = None,
) -> World:
    """World for `tickets` (needs columns ticket_id, created_min, category, selected_category,
    channel, priority, language, customer_tier, order_value_inr) and one seed's luck."""
    gen_cfg = gen_cfg or load_config("generator")
    sla_cfg = sla_cfg or load_config("sla")
    agents = agents or load_agents()
    tickets = tickets.sort_values("created_min", kind="stable").reset_index(drop=True)
    nums = ticket_numbers(tickets["ticket_id"])
    max_num = int(nums.max()) + 1 if len(nums) else 1
    n_days = n_days or int(gen_cfg["days"]) + 7  # a week of slack for the drain period

    # Luck draws, indexed by ticket number (common random numbers).
    z = np.random.default_rng([seed, STREAM_HANDLE]).standard_normal((max_num, 3))[nums]
    reopen_u = np.random.default_rng([seed, STREAM_REOPEN]).random(max_num)[nums]
    lo, hi = gen_cfg["reopen_delay_min"]
    reopen_delay = np.random.default_rng([seed, STREAM_REOPEN_DELAY]).uniform(lo, hi, max_num)[nums]
    absent = np.random.default_rng([seed, STREAM_ABSENCE]).random((len(agents), n_days)) < float(
        gen_cfg["absent_prob"]
    )

    medians = tickets["category"].map(gen_cfg["handle_median_min"]).to_numpy(dtype=float)
    channel_factor = tickets["channel"].map(gen_cfg["channel_handle_factor"]).to_numpy(dtype=float)
    base_handle = (medians * channel_factor)[:, None] * np.exp(float(gen_cfg["handle_sigma"]) * z)

    sla_minutes = tickets["priority"].map(sla_cfg["sla_minutes"]).to_numpy(dtype=float)
    first_weekday = pd.Timestamp(gen_cfg["start_date"]).weekday()

    return World(
        ticket_ids=tickets["ticket_id"].tolist(),
        created_min=tickets["created_min"].to_numpy(dtype=float),
        true_category=tickets["category"].tolist(),
        selected_category=tickets["selected_category"].tolist(),
        channel=tickets["channel"].tolist(),
        priority=tickets["priority"].tolist(),
        language=tickets["language"].tolist(),
        tier=tickets["customer_tier"].tolist(),
        order_value=tickets["order_value_inr"].to_numpy(dtype=float),
        sla_min=sla_minutes,
        base_handle_min=base_handle,
        reopen_u=reopen_u,
        reopen_delay_min=reopen_delay,
        agents=agents,
        absent=absent,
        first_weekday=first_weekday,
        mismatch_factor=float(gen_cfg["skill_mismatch_factor"]),
        reopen_prob_matched=float(gen_cfg["reopen_prob"]["matched"]),
        reopen_prob_mismatch=float(gen_cfg["reopen_prob"]["mismatch"]),
        reopen_handle_factor=float(gen_cfg["reopen_handle_factor"]),
        transfer_discovery_min=float(gen_cfg["transfer_discovery_min"]),
    )


def day_bounds(first_day: int, last_day: int) -> tuple[float, float]:
    """Minutes [start, end) covering calendar days first_day..last_day (day 1 = minute 0)."""
    return (first_day - 1) * MINUTES_PER_DAY, last_day * MINUTES_PER_DAY


def load_world_tickets(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)
