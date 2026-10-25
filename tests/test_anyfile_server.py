"""The upload endpoints end to end: peek a file, start the report, poll until it is done.

Uses a generated delivery-order file (tests/test_anyfile.py), so no download is needed, and
checks that a broken mapping comes back as a readable error instead of a crash.
"""

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
