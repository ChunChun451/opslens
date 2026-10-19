"""Your plan (opslens/plan.py, POST /api/plan/impact): hand-checkable cases.

The calendar: day 1 = Monday 31 Aug 2026, so day 43 is a Monday, day 45 a Wednesday, day 47 a
Friday. Roster: C02 (Deepak W., Team C) starts 08:00, off Mon+Tue; B02 (Arjun N., Team B) starts
14:00, off Fri+Sat.
"""

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from opslens.plan import (HEADINGS, apply_items, apply_staffing_move, check_ids, effect_by_heading,
                          item_changes, plan_kpis, staffing_items)
from opslens.world import load_agents

MONDAY = 0  # weekday of day 1
GENERATED = Path(__file__).resolve().parent.parent / "data" / "generated"


def week_plan() -> list[dict]:
    """A staffing plan for days 43-49 with two moves, in the format of staffing_plan.json."""
    return [{"first_day": 43, "last_day": 49, "moves": [
        {"agent_id": "C02", "team": "C", "change": "start 07:00 instead of 08:00"},
        {"agent_id": "B02", "team": "B", "change": "day off on Mon instead of Fri"}],
        "shifts": [{"agent_id": "C02", "start_hour": 7, "days_off": [0, 1]},
                   {"agent_id": "B02", "start_hour": 14, "days_off": [0, 5]}]}]


def test_staffing_items_have_stable_ids_and_one_agent_each() -> None:
    items = staffing_items(week_plan(), load_agents())
    assert [i["id"] for i in items] == ["staff_43_C02", "staff_43_B02"]
    assert items[0]["change"] == {"agent_id": "C02", "start_hour": 7, "days_off": [0, 1]}
    assert items[0]["title"] == "Deepak W. (C02, Team C): start 07:00 instead of 08:00"


def test_applying_a_move_changes_exactly_that_agent() -> None:
    agents = load_agents()
    item = staffing_items(week_plan(), agents)[0]  # C02 starts 07:00 on days 43-49
    after = apply_staffing_move(agents, item)
    changed = [a.agent_id for a, b in zip(agents, after) if a != b]
    assert changed == ["C02"]
    c02 = next(a for a in after if a.agent_id == "C02")
    assert c02.schedule_on(43 - 1) == (7 * 60, frozenset({0, 1}))   # day 43: the new start
    assert c02.schedule_on(49 - 1) == (7 * 60, frozenset({0, 1}))   # day 49: still that week
    assert c02.schedule_on(50 - 1) == (8 * 60, frozenset({0, 1}))   # day 50: back to the roster


def test_unknown_or_repeated_ids_are_refused_and_order_is_the_catalogue_order() -> None:
    items = staffing_items(week_plan(), load_agents())
    assert [i["id"] for i in check_ids(["staff_43_B02", "staff_43_C02"], items)] == ["staff_43_C02", "staff_43_B02"]
    with pytest.raises(ValueError, match="unknown"):
        check_ids(["staff_43_C02", "pb_F99"], items)
    with pytest.raises(ValueError, match="twice"):
        check_ids(["staff_43_C02", "staff_43_C02"], items)
    with pytest.raises(ValueError):
        check_ids("staff_43_C02", items)


def test_a_day_off_move_is_only_in_effect_on_the_days_it_touches() -> None:
    agents = load_agents()
    item = staffing_items(week_plan(), agents)[1]  # B02: off Mon instead of Fri, days 43-49
    _, _, after, info = apply_items(pd.DataFrame(), pd.DataFrame(), agents, [item], 45, 45, MONDAY)
    wednesday = item_changes(item, info[item["id"]], agents, after, [44, 45, 46], MONDAY)
    friday = item_changes(item, info[item["id"]], agents, after, [46, 47, 48], MONDAY)
    assert not wednesday["in_effect"] and wednesday["agents_changed"] == 0
    assert friday["in_effect"] and friday["agents_changed"] == 1


def test_counts_from_percentages() -> None:
    # 2% of 1,500 tickets missed the SLA = 30 customers; 10 transfers per 100 = 150 transfers.
    k = {"tickets": 1500.0, "turnaround.breach_pct": 2.0, "productivity.transfers_per_100": 10.0,
         "turnaround.mean_resolution_min": 50.0}
    out = plan_kpis(k)
    assert out["breaches"] == pytest.approx(30.0) and out["transfers"] == pytest.approx(150.0)
    assert out["turnaround.mean_resolution_min"] == 50.0


def test_paired_effect_by_heading() -> None:
    # Breaches without [30, 40, 50], with [25, 36, 44] → differences -5, -4, -6 → mean -5.
    row = {"breaches": 0.0, "turnaround.breach_pct": 0.0, "turnaround.mean_resolution_min": 0.0,
           "turnaround.p90_resolution_min": 0.0, "tickets": 0.0, "productivity.busy_agent_hours": 0.0,
           "productivity.tickets_per_agent_hour": 0.0, "transfers": 0.0, "quality.reopen_rate_pct": 0.0,
           "quality.late_minutes_per_100": 0.0}
    without = [{**row, "breaches": b} for b in (30, 40, 50)]
    with_plan = [{**row, "breaches": b} for b in (25, 36, 44)]
    effect = effect_by_heading(without, with_plan)
    assert list(effect) == HEADINGS
    breaches = effect["turnaround"][0]
    assert breaches["key"] == "breaches" and breaches["diff"] == pytest.approx(-5.0)
    assert breaches["without"] == pytest.approx(40.0) and breaches["with"] == pytest.approx(35.0)
    assert breaches["ci_low"] < -5.0 < breaches["ci_high"]


# ---- The endpoint -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def small_inputs() -> dict:
    """A small slice of the generated data: the tickets of Saturday day 48, 18:00-21:00 (about
    300), so one simulated day takes a few seconds. Loaded once for all endpoint tests."""
    if not (GENERATED / "world_tickets.csv").exists():
        pytest.skip("run `make gen` first")
    from opslens import risk
    from opslens.config import load_config

    tickets = pd.read_csv(GENERATED / "world_tickets.csv")
    hour = (tickets["created_min"] % 1440) // 60
    tickets = tickets[(tickets["day"] == 48) & hour.between(18, 20)]
    preds = pd.read_csv(GENERATED / "predictions.csv", usecols=["ticket_id", "pred_final"])
    preds = preds[preds["ticket_id"].isin(tickets["ticket_id"])]
    return {"tickets": tickets, "preds": dict(zip(preds.ticket_id, preds.pred_final)), "agents": load_agents(),
            "model": risk.load(GENERATED / "models"), "weights": load_config("optimizer"), "test_days": (43, 56)}


@pytest.fixture
def small_server(small_inputs, tmp_path, monkeypatch):
    """The server on the small slice with one seed. Runs happen in this process, one by one (no
    memory of earlier runs), so "without" and "with" are really simulated twice."""
    from server import app as server

    results = {"meta": {"fixture": False}, "plan": {"items": staffing_items(week_plan(), load_agents()), "alerts_used": []}}
    path = tmp_path / "results.json"
    path.write_text(json.dumps(results), encoding="utf-8")
    monkeypatch.setattr(server, "results_path", lambda: path)
    monkeypatch.setattr(server, "engine_inputs", lambda: small_inputs)
    monkeypatch.setattr(server, "PLAN_SEEDS", [1])
    monkeypatch.setattr(server, "run_plan_jobs", lambda jobs: [server.plan_job(j) for j in jobs])
    return TestClient(server.app)


def test_endpoint_refuses_unknown_ids_and_non_test_days(small_server) -> None:
    assert small_server.post("/api/plan/impact", json={"day": 48, "items": ["pb_F99"]}).status_code == 400
    assert small_server.post("/api/plan/impact", json={"day": 30, "items": []}).status_code == 400


def test_endpoint_with_no_items_has_zero_delta(small_server) -> None:
    answer = small_server.post("/api/plan/impact", json={"day": 48, "items": []}).json()
    for heading in HEADINGS:
        assert answer[heading], heading
        for row in answer[heading]:
            assert row["delta"] == 0.0, row["key"]   # same tickets, same luck → identical runs
    assert answer["items"] == [] and answer["seeds"] == [1]


def test_endpoint_returns_all_three_headings_for_a_plan(small_server) -> None:
    # Day 48 is a Saturday; C02 starts an hour earlier on days 43-49, so the move is in effect.
    answer = small_server.post("/api/plan/impact", json={"day": 48, "items": ["staff_43_C02"]}).json()
    assert answer["day"] == 48 and answer["weekday"] == "Sat" and answer["policy"] == "opslens"
    assert [i["id"] for i in answer["items"]] == ["staff_43_C02"] and answer["items"][0]["in_effect"]
    keys = {row["key"] for heading in HEADINGS for row in answer[heading]}
    assert {"breaches", "turnaround.mean_resolution_min", "productivity.tickets_per_agent_hour",
            "transfers", "quality.reopen_rate_pct", "quality.late_minutes_per_100"} <= keys
    for heading in HEADINGS:
        for row in answer[heading]:
            assert row["delta"] == pytest.approx(row["with"] - row["without"], abs=0.002)
    assert answer["runtime_s"] >= 0
