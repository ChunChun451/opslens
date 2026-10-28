from __future__ import annotations

import time

from fastapi.testclient import TestClient

from server.app import app
from tests.test_anyfile import delivery_file

client = TestClient(app)


def poll(job: str, seconds: float = 120) -> dict:
    deadline = time.time() + seconds
    while time.time() < deadline:
        state = client.get(f"/api/anyfile/job/{job}").json()
        if state["status"] in ("done", "error"):
            return state
        time.sleep(0.2)
    raise AssertionError("the report did not finish in time")


def test_peek_run_and_poll_a_delivery_file():
    csv = delivery_file().to_csv(index=False).encode()
    peek = client.post("/api/anyfile/peek", files={"file": ("orders.csv", csv, "text/csv")}).json()
    assert peek["rows"] == 3000 and peek["suggested"]["duration_min"] == "Time_taken(min)"
    mapping = dict(peek["suggested"])
    mapping["features"] = [c["name"] for c in peek["columns"] if c["feature"] and c["name"] not in mapping.values()]
    job = client.post("/api/anyfile/run", json={"token": peek["token"], "mapping": mapping, "target_min": 30}).json()["job"]
    state = poll(job)
    assert state["status"] == "done", state.get("error")
    assert state["result"]["warning"]["auc"]["opslens"] > 0.75
    assert "Learning on the first 70% of items" in state["steps"]


def test_a_mapping_without_a_miss_rule_is_a_readable_error():
    csv = delivery_file(n=800).to_csv(index=False).encode()
    peek = client.post("/api/anyfile/peek", files={"file": ("orders.csv", csv, "text/csv")}).json()
    job = client.post("/api/anyfile/run", json={"token": peek["token"], "mapping": peek["suggested"]}).json()["job"]
    state = poll(job)
    assert state["status"] == "error" and "what a miss is" in state["error"]


def test_a_non_csv_is_refused():
    reply = client.post("/api/anyfile/peek", files={"file": ("photo.csv", b"\x89PNG\r\n\x1a\n\x00\x00", "text/csv")})
    assert reply.status_code == 400


def test_the_report_carries_the_file_name_the_replay_and_the_forecast():
    csv = delivery_file(n=9000, days=90).to_csv(index=False).encode()
    peek = client.post("/api/anyfile/peek", files={"file": ("orders.csv", csv, "text/csv")}).json()
    plan = peek["plan"]
    assert peek["ask"] == [] and plan["miss"]["assumed"] and len(peek["preview"]) == 3
    job = client.post("/api/anyfile/run", json={"token": peek["token"], "mapping": peek["suggested"],
                                                 "target_min": plan["miss"]["target_min"], "target_assumed": True}).json()["job"]
    state = poll(job)
    assert state["status"] == "done", state.get("error")
    r = state["result"]
    assert r["file"] == "orders.csv" and state["file"] == "orders.csv" and r["rows"] == 9000
    assert r["miss"] == {"rule": "promise", "column": None, "target_min": plan["miss"]["target_min"], "assumed": True}
    assert len(r["shadow"]["timeline"]) == r["shadow"]["items"]
    assert r["forecast"]["wape_learned"] > 0 and "forecast" not in r["needs"]
    assert client.get(f"/api/anyfile/job/{job}").json()["result"] == r


def test_check_says_what_a_changed_promise_does_before_anything_is_learned():
    csv = delivery_file().to_csv(index=False).encode()
    peek = client.post("/api/anyfile/peek", files={"file": ("orders.csv", csv, "text/csv")}).json()
    tight = client.post("/api/anyfile/check", json={"token": peek["token"], "mapping": peek["suggested"], "target_min": 20}).json()
    loose = client.post("/api/anyfile/check", json={"token": peek["token"], "mapping": peek["suggested"], "target_min": 30}).json()
    assert tight["missed_pct"] > loose["missed_pct"] and not loose["miss"]["assumed"]
    gone = client.post("/api/anyfile/check", json={"token": "nope", "mapping": {}})
    assert gone.status_code == 400 and "upload has expired" in gone.json()["error"]


def test_a_junk_file_is_refused_in_one_plain_sentence():
    junk = "name,favourite_colour\n" + "\n".join(f"person {i},{'red' if i % 2 else 'blue'}" for i in range(800))
    peek = client.post("/api/anyfile/peek", files={"file": ("people.csv", junk.encode(), "text/csv")}).json()
    assert [q["role"] for q in peek["ask"]] == ["created_at", "end"] and peek["ask"][0]["options"] == []
    job = client.post("/api/anyfile/run", json={"token": peek["token"], "mapping": {"created_at": "name"}, "target_min": 30}).json()["job"]
    state = poll(job)
    assert state["status"] == "error" and "result" not in state
    assert state["error"].endswith("or try another file.") and "Traceback" not in state["error"] and "{" not in state["error"]
    unknown = client.get("/api/anyfile/job/nothing:here")
    assert unknown.status_code == 404 and unknown.json()["error"].startswith("This report is gone")


def test_the_effect_of_a_plan_comes_from_the_server_and_refuses_what_it_cannot_measure():
    csv = delivery_file().to_csv(index=False).encode()
    peek = client.post("/api/anyfile/peek", files={"file": ("orders.csv", csv, "text/csv")}).json()
    mapping = dict(peek["suggested"])
    mapping["features"] = [c["name"] for c in peek["columns"] if c["feature"] and c["name"] not in mapping.values()]
    job = client.post("/api/anyfile/run", json={"token": peek["token"], "mapping": mapping, "target_min": 30}).json()["job"]
    result = poll(job)["result"]
    assert result["cards"]
    out = client.post("/api/anyfile/effect", json={"job": job, "groups": [0], "warn": True, "save": 0.75}).json()
    assert out["plan"]["fewer"] == out["plan"]["from_fixes"] + out["plan"]["from_warning"]
    assert out["warn"]["save"] == 0.75 and len(out["cards"]) == len(result["cards"])
    assert out["plan"]["after"] < out["plan"]["before"]
    assert client.post("/api/anyfile/effect", json={"job": job, "groups": [0], "save": 0.6}).status_code == 400
    assert client.post("/api/anyfile/effect", json={"job": job, "groups": [99], "save": 0.5}).status_code == 400
    assert client.post("/api/anyfile/effect", json={"job": "gone:0", "groups": [], "save": 0.5}).status_code == 400
