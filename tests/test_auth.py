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
    assert admin.post("/api/v2/login", json={"email": "admin@opslens.demo", "password": password}).json()["home"] == "/admin/"


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
    assert client.get("/agent/").status_code == 200
    assert client.get("/admin/").status_code == 200
    assert client.get("/desk/desk.js").status_code == 200
    assert client.get("/app/").status_code == 200


def test_admin_signs_in_by_username_and_agent_picks_who_they_are(app_client):
    client, password = app_client
    client.cookies.clear()
    assert client.post("/api/v2/login", json={"username": "admin", "password": password}).json()["home"] == "/admin/"
    client.cookies.clear()
    assert client.get("/api/v2/login/agents").status_code == 401
    assert client.post("/api/v2/login/pick", json={"agent": "A01"}).status_code == 401
    first = client.post("/api/v2/login", json={"username": "agent", "password": password})
    assert first.json() == {"pick": True} and client.get("/api/v2/me").status_code == 401
    listed = client.get("/api/v2/login/agents").json()["agents"]
    assert listed and all(a["status"] != "off" for a in listed)
    assert client.post("/api/v2/login/pick", json={"agent": "nobody"}).status_code == 400
    chosen = client.post("/api/v2/login/pick", json={"agent": listed[0]["agent_code"]})
    assert chosen.json()["home"] == "/agent/"
    assert client.get("/api/v2/me").json()["user"]["agent_code"] == listed[0]["agent_code"]
    assert client.post("/api/v2/login/pick", json={"agent": "A02"}).status_code == 401


def test_the_agent_username_still_needs_the_right_password(app_client):
    client, _ = app_client
    client.cookies.clear()
    assert client.post("/api/v2/login", json={"username": "agent", "password": "nope"}).status_code == 401
    assert client.get("/api/v2/login/agents").status_code == 401
