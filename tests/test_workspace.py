from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from opslens import store

pytestmark = pytest.mark.skipif(not store.available(), reason="Postgres is not running")


@pytest.fixture(scope="module")
def client():
    from opslens.seed import seed
    from server.app import app

    store.migrate()
    store.ensure_partitions(date.today().replace(day=1), months=2)
    now = datetime.now().astimezone()
    with store.connection() as conn:
        seed(conn)
        for tid, team, assignee, status, body in [("TEST-W1", "A", "A01", "in_progress", "where is my zebra order"),
                                                  ("TEST-W2", "A", None, "open", "zebra refund please"),
                                                  ("TEST-W3", "B", None, "open", "zebra payment failed")]:
            conn.execute("insert into tickets (id, day, created_at, priority, category, language, body, status, assignee, team, "
                         "sla_due_at) values (%s, 48, %s, 'P2', 'late_delivery', 'en', %s, %s, %s, %s, %s) on conflict (id) do "
                         "update set status = excluded.status, assignee = excluded.assignee, body = excluded.body",
                         (tid, now, body, status, assignee, team, now + timedelta(minutes=20)))
        conn.execute("delete from plan_choices")
    yield TestClient(app)
    with store.connection() as conn:
        conn.execute("delete from tickets where id like 'TEST-%'")
        conn.execute("delete from plan_choices")


def as_user(c: TestClient, email: str) -> TestClient:
    from opslens.seed import demo_password

    c.cookies.clear()
    assert c.post("/api/v2/login", json={"email": email, "password": demo_password()}).status_code == 200
    return c


def test_notes_and_replies_are_kept_on_the_ticket_and_only_visible_tickets_take_them(client):
    agent = as_user(client, "a01@opslens.demo")
    r = agent.post("/api/v2/tickets/TEST-W1/messages", json={"kind": "internal", "body": "checked the rider"})
    assert r.status_code == 200 and r.json()["message"]["kind"] == "internal"
    thread = agent.get("/api/v2/tickets/TEST-W1").json()["messages"]
    assert [m["body"] for m in thread] == ["checked the rider"]
    assert agent.post("/api/v2/tickets/TEST-W3/messages", json={"body": "hi"}).status_code == 404
    assert agent.post("/api/v2/tickets/TEST-W1/messages", json={"body": "  "}).status_code == 400
    assert agent.post("/api/v2/tickets/TEST-W2/messages", json={"body": "done", "solve": True}).status_code == 403


def test_marking_solved_needs_the_ticket_to_be_the_one_in_hand(client):
    agent = as_user(client, "a01@opslens.demo")
    r = agent.post("/api/v2/tickets/TEST-W1/messages", json={"body": "sorted", "solve": True})
    assert r.status_code == 409


def test_search_and_export_stay_inside_what_you_may_see(client):
    agent = as_user(client, "a01@opslens.demo")
    found = {t["id"] for t in agent.get("/api/v2/search", params={"q": "zebra"}).json()["results"]}
    assert found == {"TEST-W1", "TEST-W2"}
    admin = as_user(client, "admin@opslens.demo")
    assert {"TEST-W1", "TEST-W2", "TEST-W3"} <= {t["id"] for t in admin.get("/api/v2/search", params={"q": "zebra"}).json()["results"]}
    csv = admin.get("/api/v2/export.csv", params={"view": "unassigned"})
    assert csv.headers["content-type"].startswith("text/csv") and "TEST-W3" in csv.text


def test_admin_only_tools_refuse_agents(client):
    agent = as_user(client, "a01@opslens.demo")
    for method, path in [("get", "/api/v2/problems"), ("get", "/api/v2/analysis"), ("post", "/api/v2/tickets/TEST-W2/assign"),
                         ("post", "/api/v2/agents/A02/status"), ("post", "/api/v2/plan/pb_F1"), ("get", "/api/v2/team/A02")]:
        r = agent.request(method, path, json={} if method == "post" else None)
        assert r.status_code == 403, path


def test_problems_come_with_measured_fixes_and_the_plan_remembers_choices(client):
    admin = as_user(client, "admin@opslens.demo")
    p = admin.get("/api/v2/problems").json()
    assert len(p["cards"]) == 9 and len(p["fixes"]) == 18 and p["all"]["missed"] < 0
    f1 = next(c for c in p["cards"] if c["id"] == "F1")
    assert f1["fixes"] == ["pb_F1"] and f1["today"] is not None
    assert len(p["days"]) == 14 and p["days"][0]["weekday"]
    assert admin.post("/api/v2/plan/pb_F1", json={"chosen": True}).json()["chosen"] == ["pb_F1"]
    assert admin.post("/api/v2/plan/nope", json={"chosen": True}).status_code == 404
    assert admin.post("/api/v2/plan/pb_F1", json={"chosen": False}).json()["chosen"] == []
    assert admin.post("/api/v2/plan/simulate", json={}).status_code == 400


def test_analysis_reports_the_frozen_round_one_result(client):
    a = as_user(client, "admin@opslens.demo").get("/api/v2/analysis").json()
    ops = next(p for p in a["headline"]["policies"] if p["key"] == "S2")
    base = next(p for p in a["headline"]["policies"] if p["key"] == "baseline_d")
    assert ops["turnaround.breach_pct"] == 8.79 and base["turnaround.breach_pct"] == 20.74


def test_counts_match_the_views(client):
    agent = as_user(client, "a01@opslens.demo")
    counts = agent.get("/api/v2/counts").json()
    for view in ("mine", "unassigned"):
        assert counts[view] == agent.get("/api/v2/tickets", params={"view": view, "limit": 500}).json()["count"]
