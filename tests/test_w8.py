"""Plan v4 W8 (c): the runner-up agent in the reason text — words only, never a different decision."""

from pathlib import Path

import pandas as pd
import pytest

from opslens import policies
from opslens.optimize import Candidate, with_runner_up

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "data" / "generated"


def cand(ticket, agent, value):
    return Candidate(ticket, agent, value, False, "refund", "P2 refund")


def test_runner_up_names_the_next_agent_and_keeps_the_picks() -> None:
    a = cand(1, "B01", 1.0)
    b = cand(2, "B03", 0.9)
    candidates = [a, b, cand(1, "B02", 0.7), cand(1, "B03", 1.2)]
    out = with_runner_up([a, b], candidates, ticket_name=lambda i: f"T{i:06d}")
    assert [(c.ticket_idx, c.agent_id, c.value) for c in out] == [(1, "B01", 1.0), (2, "B03", 0.9)]
    # B03 valued ticket 1 more, but the optimiser gave it ticket 2: the reason says so.
    assert out[0].reason == "P2 refund; B03 valued it 0.20 higher but took T000002"
    assert out[1].reason == "P2 refund; no other free agent could take it now"
    assert with_runner_up([cand(1, "B02", 0.7)], candidates)[0].reason.endswith("B03 valued it 0.50 higher "
                                                                                 "but the plan as a whole is better this way")
    assert with_runner_up([cand(1, "B03", 1.2)], candidates)[0].reason.endswith("runner-up B01, value 0.20 lower")


@pytest.mark.skipif(not (GENERATED / "models" / "risk_booster.txt").exists(), reason="needs make gen + the risk model")
def test_runner_up_text_changes_no_assignment(monkeypatch) -> None:
    """Six busy hours of a real test day, frozen risk model: identical pickups with and without the text."""
    from opslens import risk
    from opslens.config import load_config
    from opslens.simulate import MINUTES_PER_DAY, simulate
    from opslens.world import build_world, load_agents

    tickets = pd.read_csv(GENERATED / "world_tickets.csv")
    preds = pd.read_csv(GENERATED / "predictions.csv", usecols=["ticket_id", "pred_final"])
    predicted = dict(zip(preds.ticket_id, preds.pred_final))
    model = risk.load(GENERATED / "models")
    start = 47 * MINUTES_PER_DAY + 17 * 60  # Saturday 17 Oct (day 48), 17:00-23:00: the busiest stretch

    def run():
        world = build_world(tickets, seed=1, agents=load_agents(), gen_cfg=load_config("generator"))
        policy = policies.OpsLensPolicy(world, predicted, model, load_config("optimizer"))
        out = simulate(world, policy, start, start + 6 * 60, metric_start_min=start, seed_label="1").tickets
        cols = ["ticket_id", "first_pickup_min", "resolved_min", "last_agent"]
        return out[cols].sort_values("ticket_id").reset_index(drop=True)

    with_text = run()
    monkeypatch.setattr(policies, "with_runner_up", lambda chosen, candidates, ticket_name=str: chosen)
    without_text = run()
    assert len(with_text) > 500
    pd.testing.assert_frame_equal(with_text, without_text)
