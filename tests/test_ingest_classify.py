import json

import numpy as np
import pandas as pd
import pytest

from opslens.adapters.uci_incidents import PRIORITY_MAP, to_incidents
from opslens.classify import (
    LLMLabel, _parse_batch, cascade, choose_threshold, classify_with_llm, misrouted_per_100,
)
from opslens.clusters import fit_category, name_clusters
from opslens.ingest import add_timing, apply_mapping, ingest, validate_rows
from opslens.kpis import kpi_table
from opslens.llm.base import ProviderConfig
from opslens.llm.client import LLMClient
from opslens.llm.mock import MockProvider

SLA = {"P1": 60, "P2": 240, "P3": 1440}


def test_timing_is_recomputed_from_timestamps() -> None:
    df = pd.DataFrame({
        "ticket_id": ["T1", "T2"], "priority": ["P1", "P2"],
        "created_at": pd.to_datetime(["2026-09-14 20:05", "2026-09-14 20:05"]),
        "first_pickup_at": pd.to_datetime(["2026-09-14 20:41", "2026-09-14 20:10"]),
        "resolved_at": pd.to_datetime(["2026-09-14 21:19", None]),
    })
    out = add_timing(df, SLA)
    assert out["wait_min"].tolist() == [36.0, 5.0]
    assert out["resolution_min"].iloc[0] == 74.0
    assert out["breached"].tolist() == [True, True]


def test_column_mapping_and_validation(tmp_path) -> None:
    path = tmp_path / "export.csv"
    pd.DataFrame({"id": ["A1"], "opened": ["2026-09-01 10:00"], "prio": ["P2"],
                  "closed": ["2026-09-01 11:00"]}).to_csv(path, index=False)
    df = ingest(path, mapping={"ticket_id": "id", "created_at": "opened", "priority": "prio",
                               "resolved_at": "closed"}, sla_minutes=SLA, start_date="2026-08-31")
    assert df.loc[0, "resolution_min"] == 60.0 and not df.loc[0, "breached"]
    assert df.loc[0, "day"] == 2 and df.loc[0, "split"] == "train"


def test_bad_priority_is_reported() -> None:
    bad = pd.DataFrame({"ticket_id": ["X"], "created_at": ["2026-09-01 10:00"], "priority": ["urgent"]})
    errors = validate_rows(bad)
    assert errors and "priority" in errors[0]


def test_mapping_to_missing_column_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        apply_mapping(pd.DataFrame({"a": [1]}), {"ticket_id": "nope"})


def test_uci_events_collapse_to_final_state() -> None:
    t = pd.to_datetime
    events = pd.DataFrame({
        "number": ["INC1", "INC1", "INC2"],
        "opened_at": t(["2016-03-01 10:00"] * 2 + ["2016-03-02 09:00"]),
        "resolved_at": [pd.NaT, t("2016-03-01 12:00"), pd.NaT],
        "sys_updated_at": t(["2016-03-01 10:05", "2016-03-01 12:00", "2016-03-02 09:01"]),
        "sys_mod_count": [0, 3, 0],
        "contact_type": ["Phone"] * 3, "priority": ["3 - Moderate", "3 - Moderate", "1 - Critical"],
        "impact": ["2 - Medium"] * 3, "urgency": ["2 - Medium"] * 3, "category": ["Category 5"] * 3,
        "subcategory": ["S1"] * 3, "location": ["L1"] * 3,
        "assignment_group": ["Group 1", "Group 2", "Group 3"], "reassignment_count": [0, 1, 0],
        "reopen_count": [0, 0, 0], "knowledge": [False, True, False], "u_priority_confirmation": [False] * 3,
        "made_sla": [True, True, False],
    })
    inc = to_incidents(events).set_index("ticket_id")
    assert inc.loc["INC1", "resolved_by_team"] == "Group 2" and inc.loc["INC1", "first_team"] == "Group 1"
    assert inc.loc["INC1", "transfers"] == 1 and inc.loc["INC1", "resolution_min"] == 120.0
    assert not inc.loc["INC1", "breached"] and inc.loc["INC2", "breached"]
    assert inc.loc["INC2", "priority"] == PRIORITY_MAP["1 - Critical"] == "P1"


def test_kpi_table_groups_and_shares() -> None:
    df = pd.DataFrame({
        "language": ["hi", "hi", "en", "en"], "breached": [True, False, False, False],
        "wait_min": [100.0, 50.0, 10.0, 20.0], "resolution_min": [120.0, 60.0, 20.0, 30.0],
        "transfers": [1, 0, 0, 0], "reopens": [0, 0, 1, 0],
    })
    table = kpi_table(df, ["language"])
    assert table.loc["hi", "breach_pct"] == 50.0 and table.loc["hi", "mean_wait_min"] == 75.0
    assert table.loc["en", "reopen_pct"] == 50.0 and table.loc["hi", "share_pct"] == 50.0


def test_parse_batch_keeps_only_valid_items() -> None:
    data = {"results": [
        {"id": 1, "category": "refund", "root_cause": "refund after 7 days"},
        {"id": 2, "category": "pizza"},
        {"id": 9, "category": "refund"},
        "garbage",
    ]}
    found = _parse_batch(data, {1, 2})
    assert list(found) == [1]
    assert found[1].category == "refund" and "7" not in found[1].root_cause


def test_cascade_uses_llm_only_below_threshold() -> None:
    local = pd.DataFrame({"ticket_id": ["a", "b", "c"], "pred_local": ["refund", "app_bug", "account"],
                          "conf_local": [0.99, 0.40, 0.30]})
    labels = {"b": LLMLabel("payment_failure", "double charge"), "a": LLMLabel("account", "x")}
    out = cascade(local, labels, threshold=0.8).set_index("ticket_id")
    assert out.loc["a", "pred_final"] == "refund" and out.loc["a", "source"] == "local"
    assert out.loc["b", "pred_final"] == "payment_failure" and out.loc["b", "source"] == "llm"
    assert out.loc["c", "pred_final"] == "account" and out.loc["c", "source"] == "local_fallback"


def test_choose_threshold_respects_budget() -> None:
    local = pd.DataFrame({"ticket_id": list("abcd"), "pred_local": ["refund", "x", "x", "x"],
                          "conf_local": [0.99, 0.6, 0.6, 0.85]})
    truth = pd.Series(["refund", "account", "account", "account"])
    labels = {t: LLMLabel("account", "") for t in "bcd"}
    best, table = choose_threshold(local, truth, labels, [0.5, 0.7, 0.9], max_escalated_pct=60)
    assert best == 0.7
    assert table.set_index("threshold").loc[0.7, "accuracy"] == 0.75


def test_misrouting_counts_teams_not_categories() -> None:
    truth = pd.Series(["refund", "refund", "missing_item"])
    pred = pd.Series(["payment_failure", "account", "wrong_item"])
    assert misrouted_per_100(pred, truth) == pytest.approx(100 / 3)


def test_llm_batch_masks_pii_and_retries_missing(tmp_path) -> None:
    replies = [json.dumps({"results": [{"id": 1, "category": "refund", "root_cause": "late refund"}]}),
               json.dumps({"results": [{"id": 2, "category": "app_bug", "root_cause": "otp"}]})]
    provider = MockProvider(ProviderConfig(name="m", kind="mock", model="m"), replies=replies)
    client = LLMClient([provider])
    df = pd.DataFrame({"ticket_id": ["T1", "T2"], "text": ["refund pls, call 9876543210", "otp not coming"],
                       "selected_category": ["refund", "account"], "channel": ["chat", "call"]})
    labels = classify_with_llm(client, df)
    assert labels["T1"].category == "refund" and labels["T2"].category == "app_bug"
    first_prompt = provider.sent[0][-1]["content"]
    assert "9876543210" not in first_prompt and "[PHONE]" in first_prompt
    assert "1. " not in provider.sent[1][-1]["content"]


def test_clusters_name_fallback_when_llm_writes_digits() -> None:
    texts = pd.Series(["refund not received after cancel"] * 20 + ["charged twice refund the extra"] * 20
                      + ["refund status pending since week"] * 20)
    fitted = fit_category("refund", texts)
    provider = MockProvider(handler=lambda m: json.dumps({"name": "Refund 7 days late", "root_cause": "x"}))
    name_clusters(LLMClient([provider]), fitted)
    assert len(fitted.names) >= 3
    assert all(not any(ch.isdigit() for ch in n) for n in fitted.names.values())
    assert sum(fitted.sizes.values()) == 60
