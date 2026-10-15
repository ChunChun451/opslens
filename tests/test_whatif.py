"""What-if changes: volume and agents (no simulation needed)."""

import pandas as pd

from opslens.whatif import change_agents, change_volume
from opslens.world import load_agents


def day_tickets() -> pd.DataFrame:
    return pd.DataFrame({"ticket_id": [f"T{i:06d}" for i in range(1, 101)],
                         "created_min": [1440 + 10 * i for i in range(100)]})  # all on day 2


def test_volume_up_copies_with_new_ids() -> None:
    t, preds = change_volume(day_tickets(), {"T000001": "refund"}, day=2, factor=1.2)
    assert len(t) == 120 and t["ticket_id"].is_unique
    assert t["created_min"].max() < 2 * 1440  # copies stay inside the day


def test_volume_down_drops_tickets() -> None:
    t, _ = change_volume(day_tickets(), {}, day=2, factor=0.8)
    assert len(t) == 80


def test_agents_added_and_removed_per_team() -> None:
    agents = load_agents()
    changed = change_agents(agents, {"C": 2, "D": -2})
    assert sum(a.team == "C" for a in changed) == sum(a.team == "C" for a in agents) + 2
    assert sum(a.team == "D" for a in changed) == sum(a.team == "D" for a in agents) - 2
    assert len({a.agent_id for a in changed}) == len(changed)
