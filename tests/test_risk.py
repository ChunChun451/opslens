import numpy as np
import pandas as pd
import pytest

from opslens import risk
from opslens.features import FEATURES, QueueSnapshot, features_for_snapshot, snapshots_from_history

TEAM_OF = {"refund": "B", "late_delivery": "A"}
AGENTS = pd.DataFrame({
    "agent_id": ["B01", "A01"], "team": ["B", "A"], "languages": ["en|hi", "en"],
    "skills": ["refund|payment_failure", "late_delivery"], "shift_start_hour": [0, 0],
    "shift_hours": [24, 24], "days_off": ["", ""],
})


def tiny_history() -> pd.DataFrame:
    start = pd.Timestamp("2026-08-31")
    rows = []
    for i, (created, picked, resolved, cat, lang) in enumerate([
        (10, 50, 70, "refund", "hi"), (20, 90, 100, "refund", "en"), (30, 35, 45, "late_delivery", "en"),
        (40, 200, 260, "refund", "hi"), (130, 140, 150, "late_delivery", "en"),
    ]):
        rows.append({
            "ticket_id": f"T{i}", "created_at": start + pd.Timedelta(minutes=created),
            "first_pickup_at": start + pd.Timedelta(minutes=picked), "resolved_at": start + pd.Timedelta(minutes=resolved),
            "minute_of_run": float(created), "category_pred": cat, "priority": "P2", "channel": "chat",
            "language": lang, "customer_tier": "normal", "order_value_inr": 300.0, "sla_min": 240.0,
            "breached": False,
        })
    return pd.DataFrame(rows)


def test_queue_features_by_hand() -> None:
    feats = snapshots_from_history(tiny_history(), AGENTS, TEAM_OF, 1, 1, every_min=45).set_index("ticket_id")
    at45 = feats[feats["t"] == 45]
    assert sorted(at45.index) == ["T0", "T1", "T3"]
    assert at45.loc["T3", "ahead_in_team_queue"] == 2
    assert at45.loc["T0", "queue_team_language"] == 2
    assert at45.loc["T3", "capable_on_shift"] == 1
    assert at45.loc["T1", "age_min"] == 25 and at45.loc["T1", "time_left_min"] == 215
    assert at45.loc["T0", "in_progress_team"] == 0


def test_features_never_use_the_future() -> None:
    h = tiny_history()
    t = 45.0
    before = snapshots_from_history(h, AGENTS, TEAM_OF, 1, 1, every_min=t)
    before = before[before["t"] == t].drop(columns="breached").reset_index(drop=True)

    future = h.copy()
    later = future["first_pickup_at"] > future["created_at"].min() + pd.Timedelta(minutes=t)
    future.loc[later, "first_pickup_at"] += pd.Timedelta(hours=5)
    future["resolved_at"] += pd.Timedelta(hours=7)
    future["breached"] = ~future["breached"]
    new_ticket = future.iloc[[0]].assign(ticket_id="T9", created_at=future["created_at"].min() + pd.Timedelta(minutes=60),
                                         minute_of_run=60.0)
    future = pd.concat([future, new_ticket], ignore_index=True)
    after = snapshots_from_history(future, AGENTS, TEAM_OF, 1, 1, every_min=t)
    after = after[after["t"] == t].drop(columns="breached").reset_index(drop=True)
    pd.testing.assert_frame_equal(before, after)


def test_breached_tickets_are_not_scored() -> None:
    h = tiny_history()
    h.loc[h["ticket_id"] == "T3", "sla_min"] = 10.0
    feats = snapshots_from_history(h, AGENTS, TEAM_OF, 1, 1, every_min=60)
    assert "T3" not in set(feats.loc[feats["t"] == 60, "ticket_id"])


def test_empty_snapshot() -> None:
    snap = QueueSnapshot(t=10, waiting=pd.DataFrame(columns=["ticket_id", "created_min", "category_pred", "priority",
                                                             "channel", "language", "tier", "order_value_inr",
                                                             "sla_min", "transfers_so_far"]),
                         in_progress_by_team={}, arrivals_last_hour_by_team={},
                         on_shift=pd.DataFrame(columns=["agent_id", "team", "languages", "skills"]))
    assert features_for_snapshot(snap, TEAM_OF).empty


def synthetic_feats(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "category_pred": rng.choice(["refund", "late_delivery"], n), "priority": rng.choice(["P1", "P2"], n),
        "channel": "chat", "language": rng.choice(["en", "hi"], n), "tier": "normal", "team": "B",
        "hour_band": "dinner", "age_min": rng.uniform(0, 100, n), "time_left_min": rng.uniform(1, 240, n),
        "sla_min": 240.0, "order_value_inr": 300.0, "hour": 20, "is_weekend": 0, "queue_total": 50,
        "queue_team": rng.integers(0, 40, n), "queue_team_language": 5, "ahead_in_team_queue": rng.integers(0, 40, n),
        "on_shift_team": 5, "capable_on_shift": rng.integers(0, 4, n), "in_progress_team": 3,
        "arrivals_team_last_hour": 10, "transfers_so_far": 0,
    })
    logit = 2.5 - 0.03 * df["time_left_min"] + 0.08 * df["ahead_in_team_queue"] - 0.8 * df["capable_on_shift"]
    df["breached"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    df["ticket_id"] = [f"T{i}" for i in range(n)]
    return df


def test_risk_model_learns_and_round_trips(tmp_path) -> None:
    model = risk.train(synthetic_feats(4000, 1), synthetic_feats(1500, 2), rounds=200)
    test = synthetic_feats(1500, 3)
    p = model.predict(test)
    assert risk.evaluate(test["breached"].to_numpy(), p)["auc"] > 0.8
    risk.save(model, tmp_path)
    again = risk.load(tmp_path)
    assert np.allclose(again.predict(test), p)
    reasons = risk.top_reasons(model, test.head(5))
    for rs in reasons:
        assert sum(r["contribution"] for r in rs) <= 1.0 + 1e-9
        assert all(r["feature"] in FEATURES and r["contribution"] > 0 for r in rs)
    after = risk.risk_if_assigned_now(model, test.head(50))
    assert (after <= model.predict(test.head(50)) + 1e-9).mean() > 0.9


def test_evaluate_known_values() -> None:
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.4, 0.35, 0.8])
    out = risk.evaluate(y, p, bins=2)
    assert out["auc"] == pytest.approx(0.75)
    assert out["base_rate"] == 0.5 and out["n"] == 4
