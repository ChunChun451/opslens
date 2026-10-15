"""Upload CSV: column mapping, priority ranking, dates, breach from an SLA flag."""

import io
import json

from fastapi.testclient import TestClient

from server.app import app
from server.upload import parse_dates, prepare, to_priority

import pandas as pd

CSV = (b"id,opened,closed,prio,grp,ok\n"
       b"A1,2026-09-01 10:00,2026-09-01 10:30,1 - Critical,G1,true\n"
       b"A2,2026-09-01 10:05,2026-09-02 10:00,3 - Moderate,G2,false\n"
       b"A3,2026-09-01 11:00,2026-09-01 12:00,4 - Low,G2,true\n")
MAPPING = {"ticket_id": "id", "created_at": "opened", "resolved_at": "closed", "priority": "prio",
           "team": "grp", "sla_met": "ok"}


def test_priorities_are_ranked() -> None:
    assert to_priority(pd.Series(["1 - Critical", "3 - Moderate", "4 - Low"])).tolist() == ["P1", "P2", "P3"]
    assert to_priority(pd.Series(["P2", "P1"])).tolist() == ["P2", "P1"]


def test_dates_iso_and_dayfirst() -> None:
    assert parse_dates(pd.Series(["2026-09-01 10:00"]))[0].month == 9
    assert parse_dates(pd.Series(["29/2/2016 01:16", "1/3/2016 02:00"]))[0].month == 2


def test_prepare_uses_the_sla_flag() -> None:
    df = prepare(pd.read_csv(io.BytesIO(CSV)), MAPPING)
    assert df["breached"].tolist() == [False, True, False]
    assert df["resolution_min"].tolist()[0] == 30.0


def test_upload_endpoint_round_trip() -> None:
    client = TestClient(app)
    answer = client.post("/api/upload", data={"mapping": json.dumps(MAPPING)},
                         files={"file": ("t.csv", CSV, "text/csv")}).json()
    assert answer["rows"] == 3 and answer["date_range"] == ["2026-09-01", "2026-09-01"]
    bad = client.post("/api/upload", data={"mapping": json.dumps({"ticket_id": "nope"})},
                      files={"file": ("t.csv", CSV, "text/csv")})
    assert bad.status_code == 400
