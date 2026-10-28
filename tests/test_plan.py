import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from opslens.plan import (HEADINGS, PLAN_KPIS, apply_items, apply_staffing_move, check_ids, effect_by_kpi,
                          item_changes, plan_kpis, staffing_items)
from opslens.world import load_agents

MONDAY = 0
GENERATED = Path(__file__).resolve().parent.parent / "data" / "generated"


def week_plan() -> list[dict]:
    return [{"first_day": 43, "last_day": 49, "moves": [
        {"agent_id": "C02", "team": "C", "change": "start 08:00 instead of 07:00"},
        {"agent_id": "B02", "team": "B", "change": "day off on Fri instead of Sun"}],
        "shifts": [{"agent_id": "C02", "start_hour": 8, "days_off": [0, 1]},
                   {"agent_id": "B02", "start_hour": 14, "days_off": [0, 4]}]}]


def test_staffing_items_have_stable_ids_and_one_agent_each() -> None:
    items = staffing_items(week_plan(), load_agents())
    assert [i["id"] for i in items] == ["staff_43_C02", "staff_43_B02"]
    assert items[0]["change"] == {"agent_id": "C02", "start_hour": 8, "days_off": [0, 1]}
    assert items[0]["title"] == "Deepak W. (C02, Team C): start 08:00 instead of 07:00"


def test_applying_a_move_changes_exactly_that_agent() -> None:
    agents = load_agents()
    item = staffing_items(week_plan(), agents)[0]
    after = apply_staffing_move(agents, item)
    changed = [a.agent_id for a, b in zip(agents, after) if a != b]
    assert changed == ["C02"]
    c02 = next(a for a in after if a.agent_id == "C02")
    assert c02.schedule_on(43 - 1) == (8 * 60, frozenset({0, 1}))
    assert c02.schedule_on(49 - 1) == (8 * 60, frozenset({0, 1}))
    assert c02.schedule_on(50 - 1) == (7 * 60, frozenset({0, 1}))


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
    item = staffing_items(week_plan(), agents)[1]
    _, _, after, info = apply_items(pd.DataFrame(), pd.DataFrame(), agents, [item], 45, 45, MONDAY)
    wednesday = item_changes(item, info[item["id"]], agents, after, [44, 45, 46], MONDAY)
    friday = item_changes(item, info[item["id"]], agents, after, [46, 47, 48], MONDAY)
    assert not wednesday["in_effect"] and wednesday["agents_changed"] == 0
    assert friday["in_effect"] and friday["agents_changed"] == 1


def test_counts_from_percentages() -> None:
    k = {"tickets": 1500.0, "turnaround.breach_pct": 2.0, "turnaround.mean_resolution_min": 50.0,
         "turnaround.p90_resolution_min": 120.0, "productivity.busy_agent_hours": 300.0,
         "productivity.tickets_per_agent_hour": 4.0, "productivity.transfers_per_100": 10.0,
         "quality.reopen_rate_pct": 4.0, "quality.late_minutes_per_100": 500.0}
    out = plan_kpis(k)
    assert out["breaches"] == pytest.approx(30.0) and out["transfers"] == pytest.approx(150.0)
    assert out["mean_resolution_min"] == 50.0 and out["breach_pct"] == 2.0
    assert set(out) == {key for key, _, _, _, _ in PLAN_KPIS}
    assert all("." not in key for key in out)


def test_paired_effect_per_kpi() -> None:
    row = {key: 0.0 for key, _, _, _, _ in PLAN_KPIS}
    without = [{**row, "breaches": b} for b in (30, 40, 50)]
    with_plan = [{**row, "breaches": b} for b in (25, 36, 44)]
    effect = effect_by_kpi(without, with_plan)
    breaches = effect["breaches"]
    assert breaches["diff"] == pytest.approx(-5.0)
    assert breaches["without"] == pytest.approx(40.0) and breaches["with"] == pytest.approx(35.0)
    assert breaches["ci_low"] < -5.0 < breaches["ci_high"]
    assert effect["transfers"]["diff"] == 0.0


@pytest.fixture(scope="module")
def small_inputs() -> dict:
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
    assert answer["delta"] and answer["without"]["tickets"] > 0
    for key, value in answer["delta"].items():
        assert value == 0.0, key
    assert answer["items"] == [] and answer["seeds"] == [1]


def test_endpoint_returns_all_three_headings_for_a_plan(small_server) -> None:
    answer = small_server.post("/api/plan/impact", json={"day": 48, "items": ["staff_43_C02"]}).json()
    assert answer["day"] == 48 and answer["weekday"] == "Sat" and answer["policy"] == "opslens"
    assert [i["id"] for i in answer["items"]] == ["staff_43_C02"] and answer["items"][0]["in_effect"]
    assert list(answer["headings"]) == HEADINGS
    assert answer["headings"]["turnaround"][:3] == ["breaches", "breach_pct", "mean_resolution_min"]
    assert {"tickets_per_agent_hour", "transfers"} <= set(answer["headings"]["productivity"])
    assert {"reopen_rate_pct", "late_minutes_per_100"} <= set(answer["headings"]["quality"])
    shown = [key for keys in answer["headings"].values() for key in keys]
    for key in shown:
        assert answer["labels"][key] and key in answer["units"] and key in answer["better"]
        assert answer["delta"][key] == pytest.approx(answer["with"][key] - answer["without"][key], abs=0.002)
        assert len(answer["delta_by_seed"][key]) == 1
    assert answer["seconds"] >= 0
