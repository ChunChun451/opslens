from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from opslens import agents, store
from opslens.llm.client import LLMClient
from opslens.llm.mock import MockProvider

pytestmark = pytest.mark.skipif(not store.available(), reason="Postgres is not running")


def scripted(*replies) -> LLMClient:
    return LLMClient([MockProvider(replies=[json.dumps(r) for r in replies])])


def fresh_run(agent: str, ticket_id: str | None = None) -> agents.Run:
    return agents.Run(agents.create_run(agent, "test", ticket_id), agent)


def steps(run: agents.Run) -> list[tuple[str, str | None]]:
    return [(s["kind"], s["tool"]) for s in agents.q("select kind, tool from agent_steps where run_id = %s order by n", (run.id,))]


@pytest.fixture(scope="module", autouse=True)
def floor_tickets():
    from opslens.seed import seed

    store.migrate()
    store.ensure_partitions(date.today().replace(day=1), months=2)
    now = datetime.now().astimezone()
    with store.connection() as conn:
        seed(conn)
        for tid, team, category, language, status, assignee, minutes, risk in [
            ("TEST-G1", "A", "late_delivery", "hi", "open", None, -20, 0.9),
            ("TEST-G2", "B", "refund", "en", "open", None, 12, 0.7),
            ("TEST-G3", "A", "missing_item", "en", "in_progress", "A02", 25, 0.2),
        ]:
            conn.execute("insert into tickets (id, day, created_at, priority, category, language, body, status, assignee, team, "
                         "sla_due_at, risk, order_value_inr) values (%s, 48, %s, 'P1', %s, %s, 'test message', %s, %s, %s, %s, %s, 450) "
                         "on conflict (id) do update set status = excluded.status, assignee = excluded.assignee, "
                         "sla_due_at = excluded.sla_due_at, risk = excluded.risk, category = excluded.category",
                         (tid, now, category, language, status, assignee, team, now + timedelta(minutes=minutes), risk))
    yield
    with store.connection() as conn:
        conn.execute("delete from proposals where ticket_id like 'TEST-%' or title like '%TEST-%'")
        conn.execute("delete from agent_runs where trigger = 'test' or ticket_id like 'TEST-%'")
        conn.execute("delete from tickets where id like 'TEST-%'")


def test_the_loop_calls_a_tool_reads_its_result_and_answers():
    seen = []
    tool = agents.Tool("lookup", "look something up.", {"what": "the thing"}, lambda what: seen.append(what) or {"found": 7})
    client = scripted({"tool": "lookup", "args": {"what": "x"}}, {"answer": {"text": "there are 7"}})
    run = fresh_run("ask")
    answer = agents.think(client, run, "a tester.", '{"text": "..."}', "How many?", [tool])
    assert answer == {"text": "there are 7"} and seen == ["x"]
    assert steps(run) == [("tool_call", "lookup"), ("tool_result", "lookup"), ("answer", None)]
    assert '"found": 7' in client.providers[0].sent[1][1]["content"]


def test_the_loop_refuses_unknown_tools_missing_args_and_repeats_then_stops_at_the_limit():
    calls = []
    tool = agents.Tool("lookup", "look something up.", {"what": "the thing"}, lambda what: calls.append(what) or {"ok": True})
    client = scripted({"tool": "drop_tables", "args": {}}, {"tool": "lookup", "args": {}},
                      {"tool": "lookup", "args": {"what": "a", "sql": "delete"}}, {"tool": "lookup", "args": {"what": "a"}},
                      {"answer": {"text": "done"}})
    run = fresh_run("ask")
    answer = agents.think(client, run, "a tester.", '{"text": "..."}', "Go.", [tool], max_steps=4)
    assert calls == ["a"]
    assert ("error", "drop_tables") in steps(run) and ("error", "lookup") in steps(run)
    assert answer == {"text": "done"}
    last_prompt = client.providers[0].sent[-1][1]["content"]
    assert "no tool calls left" in last_prompt and "already have this result" in last_prompt


def test_reassigning_is_only_offered_when_the_agent_is_free_and_can_do_the_ticket():
    free = lambda: [{"id": "A01", "status": "idle"}, {"id": "A03", "status": "busy"}]
    assert agents.check_reassign("TEST-G1", "A01", free) is None
    assert "not free" in agents.check_reassign("TEST-G1", "A03", free)
    assert "does not speak" in agents.check_reassign("TEST-G1", "A02", free)
    assert "does not handle" in agents.check_reassign("TEST-G2", "A01", free)
    assert "not waiting" in agents.check_reassign("TEST-G3", "A01", free)


def test_the_analyst_only_proposes_actions_code_has_checked(monkeypatch):
    floor = lambda: [{"id": "A01", "status": "idle"}]
    monkeypatch.setattr(agents, "floor_tools", lambda team, f: [
        agents.Tool("floor_summary", "", {}, lambda: {"today": {"arrived": 3, "waiting": 2, "being_worked": 1, "missed": 1},
                                                      "teams": [{"team": "A", "waiting": 1, "likely_to_miss": 0, "missed": 1}]}),
        agents.Tool("at_risk", "", {"limit": ""}, lambda limit=6: agents.q(
            "select id as ticket_id, priority, category, language, team, status, assignee, risk, "
            "round(extract(epoch from sla_due_at - now()) / 60) as minutes_left from tickets where id like 'TEST-G%%' order by id")),
        agents.Tool("people_now", "", {}, lambda: {"A": {"free": 1}}),
        agents.Tool("free_agents", "", {}, lambda: [{"agent": "A01", "team": "A", "skills": ["late_delivery"], "languages": ["en", "hi"]}]),
    ])
    client = scripted({"answer": {"picked": [{"id": "R1", "why": "overdue by 20 minutes"}, {"id": "R99", "why": "made up"}]}})
    run = fresh_run("analyst")
    out = agents.run_analyst(client, run, None, floor)
    assert [p["title"] for p in out["proposals"]] == ["Give TEST-G1 to A01"]
    assert "OVERDUE" in client.providers[0].sent[0][1]["content"]
    saved = agents.q("select kind, ticket_id, agent_code, status, why from proposals where run_id = %s", (run.id,))
    assert saved == [{"kind": "reassign", "ticket_id": "TEST-G1", "agent_code": "A01", "status": "waiting",
                      "why": "overdue by 20 minutes"}]


def test_intake_writes_what_it_read_and_flags_disagreement(monkeypatch):
    monkeypatch.setattr(agents, "ticket_vector", lambda ticket_id: [0.0])
    client = scripted({"category": "app_bug", "language": "en", "urgency": "high", "summary": "App closes on checkout"})
    out = agents.run_intake(client, fresh_run("intake", "TEST-G2"), "TEST-G2")
    assert out["agrees"] is False and out["router_category"] == "refund"
    row = agents.q("select ai_category, ai_summary, ai_urgency from tickets where id = 'TEST-G2'")[0]
    assert row == {"ai_category": "app_bug", "ai_summary": "App closes on checkout", "ai_urgency": "high"}


def test_the_copilot_states_the_policy_limit_in_code_not_by_the_model():
    note = agents.policy_note({"category": "missing_item", "order_value_inr": 450})
    assert "above the Rs 300 limit" in note and "photo" in note
    assert "within" in agents.policy_note({"category": "missing_item", "order_value_inr": 120})
    assert agents.policy_note({"category": "refund", "order_value_inr": 900}) is None


def logged_in(client: TestClient, email: str) -> TestClient:
    from opslens.seed import demo_password

    client.cookies.clear()
    assert client.post("/api/v2/login", json={"email": email, "password": demo_password()}).status_code == 200
    return client


def test_leads_decide_proposals_for_their_own_team_only():
    from server.app import app

    with store.connection() as conn:
        pid = conn.execute("insert into proposals (kind, team, ticket_id, title, why) values "
                           "('note', 'B', 'TEST-G2', 'Find someone for TEST-G2', 'test') returning id").fetchone()["id"]
    client = TestClient(app)
    assert logged_in(client, "a01@opslens.demo").post(f"/api/v2/proposals/{pid}", json={"decision": "approve"}).status_code == 403
    assert logged_in(client, "lead.a@opslens.demo").post(f"/api/v2/proposals/{pid}", json={"decision": "approve"}).status_code == 404
    lead_b = logged_in(client, "lead.b@opslens.demo")
    assert pid in [p["id"] for p in lead_b.get("/api/v2/proposals").json()["proposals"]]
    assert lead_b.post(f"/api/v2/proposals/{pid}", json={"decision": "approve"}).json()["status"] == "approved"
    assert lead_b.post(f"/api/v2/proposals/{pid}", json={"decision": "reject"}).status_code == 409


def test_an_agent_can_only_ask_the_copilot_about_tickets_they_can_see(monkeypatch):
    from server.app import app

    monkeypatch.setattr(agents, "submit", lambda *a, **k: 1)
    client = logged_in(TestClient(app), "a01@opslens.demo")
    assert client.post("/api/v2/copilot", json={"ticket_id": "TEST-G1"}).status_code == 200
    assert client.post("/api/v2/copilot", json={"ticket_id": "TEST-G2"}).status_code == 404
    assert client.post("/api/v2/ask", json={"question": "hi"}).status_code == 403


def test_ask_retries_when_the_answer_uses_numbers_that_are_not_in_the_data(monkeypatch):
    monkeypatch.setattr(agents, "floor_tools", lambda team, f: [
        agents.Tool("floor_summary", "", {}, lambda: {"today": {"arrived": 40, "waiting": 3, "being_worked": 2, "missed": 5},
                                                      "teams": [{"team": "B", "waiting": 3, "likely_to_miss": 1, "missed": 5}]}),
        agents.Tool("at_risk", "", {"limit": ""}, lambda limit=6: []),
        agents.Tool("people_now", "", {}, lambda: {}),
        agents.Tool("free_agents", "", {}, lambda: []),
        agents.Tool("category_mix", "", {"hours": ""}, lambda hours=2: []),
        agents.Tool("tickets_per_hour", "", {}, lambda: []),
    ])
    client = scripted({"answer": {"text": "Team B missed 17."}}, {"answer": {"text": "Team B missed 5 of 40."}})
    run = fresh_run("ask")
    out = agents.run_ask(client, run, "Who missed most?", None, lambda: [])
    assert out == {"text": "Team B missed 5 of 40.", "unverified": []}
    assert "not in the facts: 17" in client.providers[0].sent[1][1]["content"]
    assert ("error", "check_numbers") in steps(run)
