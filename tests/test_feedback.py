from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from opslens import feedback, store
from opslens.config import load_config
from tests.helpers import database_ready

pytestmark = pytest.mark.skipif(not store.available(), reason="Postgres is not running")
MARK = "TEST-FB"


@pytest.fixture(scope="module")
def client():
    from server import feedback_api
    from server.app import app

    assert database_ready()
    refresh, feedback_api.refresh_rag = feedback_api.refresh_rag, lambda: None
    yield TestClient(app)
    feedback_api.refresh_rag = refresh
    with store.connection() as conn:
        conn.execute("delete from feedback where body like %s", (f"%{MARK}%",))


def as_admin(client: TestClient) -> TestClient:
    from opslens.seed import demo_password

    client.cookies.clear()
    assert client.post("/api/v2/login", json={"username": "admin", "password": demo_password()}).status_code == 200
    return client


def as_agent(client: TestClient, name: str, team: str) -> TestClient:
    from opslens.seed import demo_password

    client.cookies.clear()
    assert client.post("/api/v2/login", json={"role": "agent", "name": name, "team": team, "password": demo_password()}).status_code == 200
    return client


def test_the_hand_written_feedback_is_seeded_once_and_names_real_agents():
    book = load_config("feedback")
    with store.connection() as conn:
        agents = {r["agent_code"] for r in conn.execute("select agent_code from agent_profiles")}
        assert {e["agent"] for e in book["customer"] + book["admin"]} <= agents
        assert all(e["category"] in feedback.CATEGORIES and 1 <= e["rating"] <= 5 for e in book["customer"])
        before = conn.execute("select count(*) as n from feedback where seed_key is not null").fetchone()["n"]
        feedback.seed_feedback(conn)
        after = conn.execute("select count(*) as n from feedback where seed_key is not null").fetchone()["n"]
    assert before == after == len(book["customer"]) + len(book["admin"])


def test_nothing_about_feedback_opens_without_a_sign_in(client):
    client.cookies.clear()
    assert client.get("/api/v2/feedback").status_code == 401
    assert client.post("/api/v2/feedback", json={}).status_code == 401
    assert client.get("/api/v2/me/feedback").status_code == 401
    assert client.get("/api/v2/feedback/agent/A01").status_code == 401


def test_the_admin_adds_customer_feedback_with_private_details_hidden(client):
    as_admin(client)
    r = client.post("/api/v2/feedback", json={"source": "customer", "agent": "c07", "rating": 4, "category": "missing_item",
                                             "body": f"{MARK} call me on 9876543210, the fries were missing"})
    assert r.status_code == 200, r.text
    item = r.json()["item"]
    assert item["agent_code"] == "C07" and item["team"] == "C" and item["author_name"] == feedback.CUSTOMER_AUTHOR
    assert "9876543210" not in item["body"] and "[PHONE]" in item["body"]


def test_bad_feedback_is_refused_with_a_reason(client):
    as_admin(client)
    cases = [{"source": "customer", "agent": "A01", "body": f"{MARK} no rating"},
             {"source": "customer", "agent": "A01", "rating": 9, "body": f"{MARK} too high"},
             {"source": "customer", "agent": "A01", "rating": "five", "body": f"{MARK} not a number"},
             {"source": "customer", "agent": "ZZ9", "rating": 3, "body": f"{MARK} nobody"},
             {"source": "customer", "agent": "A01", "rating": 3, "body": "   "},
             {"source": "customer", "agent": "A01", "rating": 3, "category": "weather", "body": f"{MARK} odd"},
             {"source": "robot", "agent": "A01", "rating": 3, "body": f"{MARK} who"}]
    for case in cases:
        r = client.post("/api/v2/feedback", json=case)
        assert r.status_code == 400 and r.json()["error"], case


def test_admin_notes_are_marked_and_never_count_in_the_customer_rating(client):
    as_admin(client)
    before = client.get("/api/v2/feedback").json()
    r = client.post("/api/v2/feedback", json={"source": "admin", "agent": "B02", "body": f"{MARK} take the Hindi refunds first"})
    assert r.status_code == 200 and r.json()["item"]["rating"] is None and r.json()["item"]["author_name"] == "Ops admin"
    after = client.get("/api/v2/feedback").json()
    assert after["customer"] == before["customer"] and after["admin_notes"] == before["admin_notes"] + 1
    assert after["items"][0]["source"] == "admin"


def test_an_agent_sees_only_their_own_feedback_and_marks_it_read(client):
    as_admin(client)
    client.post("/api/v2/feedback", json={"source": "admin", "agent": "C01", "body": f"{MARK} well done today"})
    agent = as_agent(client, "Anjali", "A")
    mine = agent.get("/api/v2/me/feedback").json()
    assert mine["items"] and {f["agent_code"] for f in mine["items"]} == {"C01"} and mine["unseen"] >= 1
    assert agent.get("/api/v2/feedback").status_code == 403
    assert agent.get("/api/v2/feedback/agent/B02").status_code == 403
    assert agent.post("/api/v2/feedback", json={"source": "customer", "agent": "C01", "rating": 5, "body": f"{MARK} me"}).status_code == 403
    assert agent.post("/api/v2/me/feedback/seen").json()["marked"] >= 1
    assert agent.get("/api/v2/me/feedback").json()["unseen"] == 0
    as_admin(client)
    assert client.get("/api/v2/me/feedback").status_code == 403


def test_customer_feedback_goes_into_the_rag_library_with_a_summary():
    with store.connection() as conn:
        chunks = feedback.chunks(conn)
        rated = conn.execute("select count(*) as n from feedback where source = 'customer'").fetchone()["n"]
    summary = next(c for c in chunks if c["ref"] == "feedback:summary")
    assert len(chunks) == rated + 1 and all(c["source"] == "feedback" and c["link"] == "#feedback" for c in chunks)
    assert f"{rated} reviews" in summary["body"] and "entered by hand" in summary["body"]
    assert not any("From the admin" in c["body"] or c["ref"].startswith("feedback:admin") for c in chunks)
