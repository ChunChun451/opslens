from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from opslens import store

pytestmark = pytest.mark.skipif(not store.available(), reason="Postgres is not running")


@pytest.fixture(scope="module")
def app_client():
    from opslens.seed import demo_password, seed
    from server.app import app

    store.migrate()
    store.ensure_partitions(date.today().replace(day=1), months=2)
    with store.connection() as conn:
        seed(conn)
        now = datetime.now().astimezone()
        rows = [("TEST-A1", "A", "A01", "in_progress"), ("TEST-A2", "A", None, "open"),
                ("TEST-A3", "A", "A02", "in_progress"), ("TEST-B1", "B", None, "open")]
        for tid, team, assignee, status in rows:
            conn.execute("insert into tickets (id, day, created_at, priority, body, status, assignee, team, sla_due_at) "
                         "values (%s, 48, %s, 'P2', 'test', %s, %s, %s, %s) on conflict (id) do update set "
                         "assignee = excluded.assignee, status = excluded.status, team = excluded.team",
                         (tid, now, status, assignee, team, now + timedelta(minutes=30)))
    yield TestClient(app), demo_password()
    with store.connection() as conn:
        conn.execute("delete from tickets where id like 'TEST-%'")


def logged_in(client: TestClient, email: str, password: str) -> TestClient:
    client.cookies.clear()
    r = client.post("/api/v2/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return client


def ids(client: TestClient) -> set[str]:
    r = client.get("/api/v2/tickets", params={"view": "open", "limit": 500})
    assert r.status_code == 200, r.text
    return {t["id"] for t in r.json()["tickets"] if t["id"].startswith("TEST-")}


def test_nothing_opens_without_logging_in(app_client):
    client, _ = app_client
    client.cookies.clear()
    assert client.get("/api/v2/tickets").status_code == 401
    assert client.get("/api/v2/me").status_code == 401


def test_a_wrong_password_is_refused_and_says_nothing_about_the_email(app_client):
    client, _ = app_client
    client.cookies.clear()
    wrong = client.post("/api/v2/login", json={"email": "a01@opslens.demo", "password": "nope"})
    unknown = client.post("/api/v2/login", json={"email": "nobody@opslens.demo", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()


def test_an_agent_sees_their_own_tickets_and_their_teams_unassigned_queue_only(app_client):
    client, password = app_client
    c = logged_in(client, "a01@opslens.demo", password)
    assert c.get("/api/v2/me").json()["user"]["role"] == "agent"
    assert ids(c) == {"TEST-A1", "TEST-A2"}
    assert c.get("/api/v2/tickets/TEST-A3").status_code == 404
    assert c.get("/api/v2/summary").status_code == 403


def test_there_are_only_admins_and_agents_and_an_admin_sees_everything(app_client):
    client, password = app_client
    client.cookies.clear()
    assert client.post("/api/v2/login", json={"email": "lead.a@opslens.demo", "password": password}).status_code == 401
    admin = logged_in(client, "admin@opslens.demo", password)
    assert ids(admin) == {"TEST-A1", "TEST-A2", "TEST-A3", "TEST-B1"}
    assert admin.post("/api/v2/login", json={"email": "admin@opslens.demo", "password": password}).json()["home"] == "/app/"


def test_logging_out_ends_the_session(app_client):
    client, password = app_client
    c = logged_in(client, "a02@opslens.demo", password)
    assert c.get("/api/v2/me").status_code == 200
    c.post("/api/v2/logout")
    assert c.get("/api/v2/me").status_code == 401


def test_repeated_wrong_passwords_are_slowed_down(app_client):
    client, _ = app_client
    client.cookies.clear()
    codes = [client.post("/api/v2/login", json={"email": "a03@opslens.demo", "password": f"x{n}"}).status_code
             for n in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_an_agents_own_queue_and_the_role_walls_on_the_floor(app_client):
    client, password = app_client
    agent = logged_in(client, "a01@opslens.demo", password)
    mine = agent.get("/api/v2/tickets", params={"view": "mine", "limit": 500}).json()["tickets"]
    assert {t["id"] for t in mine if t["id"].startswith("TEST-")} == {"TEST-A1"}
    assert agent.get("/api/v2/floor").status_code == 403
    assert agent.post("/api/v2/actions", json={"kind": "dance"}).status_code == 400
    admin = logged_in(client, "admin@opslens.demo", password)
    assert admin.get("/api/v2/tickets", params={"view": "mine"}).status_code == 400
    assert admin.post("/api/v2/actions", json={"kind": "done"}).status_code == 403
    assert admin.get("/api/v2/floor/me").status_code == 403


def test_the_sign_in_page_and_both_screens_are_served(app_client):
    client, _ = app_client
    client.cookies.clear()
    assert "Sign in" in client.get("/").text
    for old_address, new_address in (("/agent/", "/app/#agent"), ("/admin/", "/app/")):
        moved = client.get(old_address, follow_redirects=False)
        assert moved.status_code == 307 and moved.headers["location"] == new_address
    assert client.get("/app/js/session.js").status_code == 200
    assert client.get("/app/").status_code == 200


def test_admin_signs_in_by_username(app_client):
    client, password = app_client
    client.cookies.clear()
    assert client.post("/api/v2/login", json={"username": "admin", "password": password}).json()["home"] == "/app/"
    assert client.get("/api/v2/me").json()["user"]["role"] == "admin"


def test_an_agent_signs_in_as_themself_by_name_and_team_and_nobody_else(app_client):
    client, password = app_client
    for name in ("Rohit M.", "rohit m", "Rohit", "A01"):
        client.cookies.clear()
        r = client.post("/api/v2/login", json={"role": "agent", "name": name, "team": "A", "password": password})
        assert r.status_code == 200 and r.json()["home"] == "/app/#agent", name
        assert client.get("/api/v2/me").json()["user"]["agent_code"] == "A01"
    client.cookies.clear()
    assert client.post("/api/v2/login", json={"role": "agent", "name": "Rohit", "team": "B", "password": password}).status_code == 401
    assert client.post("/api/v2/login", json={"role": "agent", "name": "Kavita", "team": "B", "password": "nope"}).status_code == 401
    assert client.post("/api/v2/login", json={"role": "agent", "name": "Kavita", "password": password}).status_code == 400
    assert client.post("/api/v2/login", json={"username": "agent", "password": password}).status_code == 401
    assert client.get("/api/v2/me").status_code == 401
    agents = client.get("/api/v2/login/agents").json()["agents"]
    assert {"code": "A01", "name": "Rohit M.", "team": "A"} in agents and all(set(a) == {"code", "name", "team"} for a in agents)
    assert {t["code"] for t in client.get("/api/v2/login/teams").json()["teams"]} == {"A", "B", "C", "D"}


def test_an_agent_cannot_act_for_another_agent_or_reset_the_day_and_a_stranger_cannot_act_at_all(app_client):
    client, password = app_client
    client.cookies.clear()
    action = {"weekday": 4, "seed": 1, "minute": 600, "kind": "break", "agent": "A01"}
    assert client.post("/api/live/action", json=action).status_code == 401
    assert client.post("/api/live/reset", json={"weekday": 4, "seed": 1}).status_code == 401
    r = client.post("/api/v2/login", json={"role": "agent", "name": "Kavita", "team": "B", "password": password})
    assert r.status_code == 200
    forbidden = client.post("/api/live/action", json=action)
    assert forbidden.status_code == 403 and "yourself" in forbidden.json()["error"]
    assert client.post("/api/live/action", json={**action, "agent": "a01"}).status_code == 403
    assert client.post("/api/live/reset", json={"weekday": 4, "seed": 1}).status_code == 403
    admin = logged_in(client, "admin@opslens.demo", password)
    watching = admin.post("/api/live/action", json=action)
    assert watching.status_code == 403 and "only the agent" in watching.json()["error"]
    assert admin.post("/api/live/reset", json={"weekday": 4, "seed": 1}).json()["ok"] is True


def test_nothing_behind_the_dashboard_opens_without_a_sign_in_and_tools_are_admin_only(app_client):
    client, password = app_client
    client.cookies.clear()
    for method, path in [("get", "/api/results"), ("get", "/api/live?weekday=4&minute=600"), ("post", "/api/bot"),
                         ("post", "/api/ask"), ("post", "/api/whatif"), ("post", "/api/plant"), ("post", "/api/upload"),
                         ("get", "/api/live/actions?weekday=4"), ("get", "/api/rag/status")]:
        assert client.request(method, path, json={} if method == "post" and path != "/api/upload" else None).status_code == 401, path
    assert client.get("/api/health").status_code == 200
    client.post("/api/v2/login", json={"role": "agent", "name": "Kavita", "team": "B", "password": password})
    assert client.get("/api/results").status_code == 200
    for method, path in [("post", "/api/bot"), ("post", "/api/ask"), ("post", "/api/whatif"), ("post", "/api/plant"),
                         ("get", "/api/live/actions?weekday=4"), ("get", "/api/rag/status")]:
        assert client.request(method, path, json={} if method == "post" else None).status_code == 403, path
    logged_in(client, "admin@opslens.demo", password)
    assert client.get("/api/rag/status").status_code == 200


def test_an_agent_gets_only_their_own_floor_data():
    from server.app import agent_view

    payload = {"ready": True, "agents": [{"id": "A01"}, {"id": "B01"}], "floor": [{"id": "A01"}, {"id": "B01"}],
               "actions": [{"agent": "A01"}, {"agent": "B01"}], "decisions": [{"agent": "A01"}, {"agent": "B01"}],
               "danger": [{"ticket_id": "T1"}], "policies": {"opslens": {"missed": 3, "status": "bioi", "queues": {"B": [1, 2]}}}}
    mine = agent_view(payload, "B01")
    assert mine["agents"] == [{"id": "B01"}] and mine["floor"] == [{"id": "B01"}]
    assert mine["actions"] == [{"agent": "B01"}] and mine["decisions"] == [{"agent": "B01"}] and mine["danger"] == []
    assert mine["policies"]["opslens"] == {"missed": 3, "status": "", "queues": {}}
