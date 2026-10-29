from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from opslens import mirror, store
from opslens.live import LiveDay

START = 47 * 1440.0
TODAY = date.today()


def small_day() -> LiveDay:
    ids = ["TEST-M1", "TEST-M2", "TEST-M3"]
    world = SimpleNamespace(
        ticket_ids=ids, created_min=np.array([START + 5, START + 20, START + 2000]), sla_min=np.array([30.0, 15.0, 30.0]),
        channel=["chat", "call", "chat"], priority=["P2", "P1", "P3"], language=["en", "hi", "en"],
        tier=["normal", "gold", "normal"], order_value=np.array([300.0, 450.0, 100.0]),
        selected_category=["refund", "late_delivery", "account"])
    info = pd.DataFrame({"ticket_id": ids, "text": ["refund please, call 9876543210", "where is my order", "login"],
                         "restaurant_name": ["Pizza Point", "Momo Street", "Spice Route"]}).set_index("ticket_id")
    live = LiveDay(day=48, seed=1, start=START, agents=[{"id": "A01", "team": "A"}, {"id": "B01", "team": "B"}])
    live.work = {"B01": [{"minute": START + 10, "ticket_id": "TEST-M1", "reason": "breach risk 0.62 -> 0.20", "created": START + 5,
                          "deadline": START + 35, "resolved": START + 40, "priority": "P2", "category": "refund",
                          "language": "en", "text": "refund please"}]}
    live.risk_seen = [(START + 21, {1: 0.81})]
    live.context = {"world": world, "tickets_info": info, "index": {t: i for i, t in enumerate(ids)}}
    return live


def by_id(rows):
    return {r["id"]: r for r in rows}


def test_a_ticket_moves_from_open_to_in_progress_to_solved():
    live = small_day()
    assert "TEST-M1" not in by_id(mirror.ticket_rows(live, START + 4, TODAY)[0])
    assert by_id(mirror.ticket_rows(live, START + 7, TODAY)[0])["TEST-M1"]["status"] == "open"
    busy = by_id(mirror.ticket_rows(live, START + 15, TODAY)[0])["TEST-M1"]
    assert busy["status"] == "in_progress" and busy["assignee"] == "B01" and busy["team"] == "B"
    done = by_id(mirror.ticket_rows(live, START + 45, TODAY)[0])["TEST-M1"]
    assert done["status"] == "solved" and done["breached"] is True and done["risk"] is None


def test_an_unassigned_ticket_past_its_promise_is_breached_and_keeps_its_risk():
    rows = by_id(mirror.ticket_rows(small_day(), START + 40, TODAY)[0])
    late = rows["TEST-M2"]
    assert late["status"] == "open" and late["breached"] is True and late["risk"] == 0.81 and late["team"] == "A"
    assert "TEST-M3" not in rows


def test_ticket_text_is_masked_before_it_is_stored():
    row = by_id(mirror.ticket_rows(small_day(), START + 7, TODAY)[0])["TEST-M1"]
    assert "9876543210" not in row["body"]


@pytest.mark.skipif(not store.available(), reason="Postgres is not running")
def test_sync_writes_changes_once_and_history_only_grows():
    from opslens.seed import seed

    store.migrate()
    store.ensure_partitions(TODAY.replace(day=1), months=2)
    live = small_day()
    state = mirror.MirrorState()
    with store.connection() as conn:
        seed(conn)
        try:
            first = mirror.sync(conn, live, 15, TODAY, state)
            again = mirror.sync(conn, live, 15, TODAY, state)
            later = mirror.sync(conn, live, 45, TODAY, state)
            kinds = [r["kind"] for r in conn.execute(
                "select kind from ticket_events where ticket_id = 'TEST-M1' order by at, kind")]
            decided = conn.execute("select agent_code, rescue_value from decisions where ticket_id = 'TEST-M1'").fetchall()
        finally:
            for table in ("ticket_events", "decisions", "risk_scores", "tickets"):
                column = "id" if table == "tickets" else "ticket_id"
                conn.execute(f"delete from {table} where {column} like 'TEST-%'")
    assert first["changed"] == 1 and again["changed"] == 0 and again["events"] == 0 and later["changed"] == 2
    assert kinds == ["created", "assigned", "breached", "solved"]
    assert [(d["agent_code"], float(d["rescue_value"])) for d in decided] == [("B01", 0.62)]
