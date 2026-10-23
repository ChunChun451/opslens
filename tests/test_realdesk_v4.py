"""Plan v4 on the real service desk: fast-track benchmark, detectors, plants, alerts — small
hand-computed cases (the real-log numbers come from eval/run_realdesk.py)."""

import numpy as np
import pandas as pd
import pytest

from eval import realdesk_plants as P
from opslens import realdesk_fasttrack as FT
from opslens import realdesk_watch as W
from opslens.realdesk import bootstrap_gap, card_groups, score_alerts


# ---- fast-track ------------------------------------------------------------------------------

def test_learn_limits_keeps_the_smallest_limit_that_matches_the_flag_best() -> None:
    hours = np.array([10.0, 50.0, 120.0, 100.0, 400.0, np.nan])
    prio = np.array(["3 - Moderate"] * 3 + ["4 - Low"] * 2 + ["3 - Moderate"])
    flag = np.array([False, False, True, False, True, True])
    limits = FT.learn_limits(hours, prio, flag, np.ones(6, dtype=bool))
    assert limits == {"3 - Moderate": 50.0, "4 - Low": 100.0}   # the NaN incident is ignored
    assert FT.missed_by_rule(hours, prio, limits).tolist() == [False, False, True, False, True, False]
    assert FT.rule_match_pct(hours, prio, flag, np.ones(6, dtype=bool), limits) == 100.0


def test_pickup_wait_counts_only_a_recorded_pickup_after_the_first_hour() -> None:
    t0 = pd.Timestamp("2016-05-02 08:00")
    hours = pd.Timedelta(hours=1)
    incidents = pd.DataFrame({"ticket_id": ["A", "B", "C"], "created_at": [t0, t0, t0]})
    events = pd.DataFrame({
        "number": ["A", "A", "B", "B", "C"],
        "incident_state": ["New", "Active", "New", "Resolved", "Active"],
        "sys_updated_at": [t0, t0 + 13 * hours, t0, t0 + 7 * hours, t0 + pd.Timedelta(minutes=5)],
    })
    # A: New until 21:00, then Active → 12 h after the 09:00 mark. B: New → Resolved, no pickup
    # recorded → 0. C: picked up at 08:05, before the mark → 0.
    assert FT.pickup_wait_after(incidents, events).tolist() == [12.0, 0.0, 0.0]


def test_pick_daily_takes_the_best_scores_each_day_and_breaks_ties_oldest_first() -> None:
    day = np.array([1, 1, 1, 1, 1, 2, 2])
    created = np.array([5, 1, 2, 3, 4, 7, 6])
    score = np.array([0.9, 0.1, 0.5, 0.5, 0.2, 0.3, 0.3])
    picked = FT.pick_daily(day, created, score, 40)
    # Day 1: 5 × 40% = 2 → 0.9 and the older of the two 0.5s (created 2). Day 2: 0.8 → 1, the older.
    assert picked.tolist() == [True, False, True, False, False, False, True]


def test_bootstrap_with_one_week_gives_the_point_value() -> None:
    totals = FT.week_totals(np.array(["w1"] * 4), {"n": np.ones(4), "a": np.array([1, 1, 0, 0]), "b": np.array([1, 0, 0, 0])})
    assert FT.bootstrap_ci(totals, "a", None, 400) == (200.0, 200.0)
    assert FT.bootstrap_ci(totals, "a", "b", 400) == (100.0, 100.0)


def test_unassigned_picker_counts_no_event_yet_as_unassigned() -> None:
    feats = pd.DataFrame({"priority_raw": ["3 - Moderate", "4 - Low", "3 - Moderate"], "state_now": ["New", "Active", None]})
    s = FT.picker_scores(feats, np.zeros(3), np.zeros(3))
    assert s["unassigned"].tolist() == [1.0, 0.0, 1.0] and s["priority"].tolist() == [-3.0, -4.0, -3.0]


# ---- detectors -------------------------------------------------------------------------------

def test_share_z_never_trusts_a_spread_smaller_than_chance() -> None:
    past = np.array([0.25, 0.30, 0.30, 0.35, 0.30, 0.20, 0.40])   # median 0.30, MAD 0.05
    assert W.share_z(9, 12, past) == pytest.approx(3.40, abs=0.01)   # the docstring example


def weekday_table(days: pd.DatetimeIndex, per_day: int, category: str = "C1", team: str = "G1") -> pd.DataFrame:
    rows = []
    for d in days:
        for i in range(per_day):
            rows.append({"ticket_id": f"{d.date()}-{i}", "created_at": d + pd.Timedelta(hours=9), "date": d,
                         "category": category, "team": team, "resolution_h": 30.0 if i < 3 else 2.0,
                         "open_24h": i < 3, "bounced_24h": False})
    return pd.DataFrame(rows)


def test_spike_detector_flags_a_doubled_day_and_not_a_normal_one() -> None:
    days = pd.date_range("2016-04-01", "2016-05-10")
    days = days[days.weekday < 5]
    table = weekday_table(days, 20)
    extra = weekday_table(pd.DatetimeIndex(["2016-05-10"]), 20)
    extra["ticket_id"] = extra["ticket_id"] + "x"
    alerts = W.watch(pd.concat([table, extra], ignore_index=True), "2016-05-09", "2016-05-10")
    spikes = alerts[alerts["type"] == "spike"]
    assert spikes["known_on"].tolist() == [pd.Timestamp("2016-05-10")] and spikes["value"].tolist() == [40]


def test_slowdown_detector_flags_a_team_whose_incidents_stay_open_the_next_day() -> None:
    days = pd.date_range("2016-04-01", "2016-05-10")
    days = days[days.weekday < 5]
    table = weekday_table(days, 10)
    slow = (table["date"] == pd.Timestamp("2016-05-09")).to_numpy()   # 3 of 10 open usually; 9 of 10 that day
    table.loc[slow, "open_24h"] = [True] * 9 + [False]
    alerts = W.watch(table, "2016-05-09", "2016-05-10")
    slowdowns = alerts[alerts["type"] == "slowdown"]
    assert slowdowns["known_on"].tolist() == [pd.Timestamp("2016-05-10")]   # known the day after
    assert alerts[alerts["type"] == "spike"].empty


# ---- plants ----------------------------------------------------------------------------------

def test_plants_change_only_their_own_segment_and_window() -> None:
    days = pd.date_range("2016-05-02", "2016-05-13")
    days = days[days.weekday < 5]
    table = weekday_table(days, 10)
    plant = {"type": "slowdown", "segment": "G1", "first_day": pd.Timestamp("2016-05-09"),
             "last_day": pd.Timestamp("2016-05-15"), "size": 15.0}
    out = P.plant_slowdown(table, plant)
    in_week = (out["date"] >= plant["first_day"]).to_numpy()
    assert out.loc[in_week, "open_24h"].all()                 # 2 h × 15 = 30 h > 24 h
    assert out.loc[~in_week, "open_24h"].sum() == 3 * 5       # the first week is untouched
    spike = {"type": "spike", "segment": "C1", "first_day": pd.Timestamp("2016-05-04"),
             "last_day": pd.Timestamp("2016-05-04"), "extra_incidents": 7}
    grown = P.plant_spike(table, spike, np.random.default_rng(0))
    assert len(grown) == len(table) + 7 and (grown["date"] == spike["first_day"]).sum() == 17


def test_score_set_matches_type_segment_and_window() -> None:
    plants = [{"type": "bounce", "segment": "C1", "first_day": pd.Timestamp("2016-05-09"), "last_day": pd.Timestamp("2016-05-15")}]
    alerts = pd.DataFrame({"type": ["bounce", "bounce", "spike"], "segment": ["C1", "C2", "C1"],
                           "known_on": pd.to_datetime(["2016-05-11", "2016-05-11", "2016-05-10"])})
    scored, unmatched = P.score_set(alerts, plants)
    assert scored[0]["found"] and scored[0]["delay_days"] == 2 and unmatched == 2


# ---- cards and alerts ------------------------------------------------------------------------

def test_score_alerts_docstring_example() -> None:
    predicted = np.array([True] * 10 + [False] * 10)
    actual = np.array([True] * 7 + [False] * 3 + [True] * 7 + [False] * 3)
    s = score_alerts(predicted, actual)
    assert (s["precision_pct"], s["recall_pct"]) == (70.0, 50.0)


def test_bootstrap_gap_with_one_week_is_the_gap() -> None:
    missed = np.array([True] * 6 + [False] * 4 + [True] * 2 + [False] * 8)
    group = np.array([True] * 10 + [False] * 10)
    low, high = bootstrap_gap(np.array(["w"] * 20), missed, group, ~group)
    assert low == pytest.approx(40.0) and high == pytest.approx(40.0)


def test_card_groups_split_waits_pickups_and_bounces() -> None:
    h = pd.DataFrame({"final_category": ["C26", "C26", "C9"], "transfers": [2, 0, 1]}, index=["a", "b", "c"])
    st = pd.DataFrame({"waiting for the user": [0.0, 3.0, 0.0], "waiting to be picked up": [9.0, 1.0, 0.0]}, index=["a", "b", "c"])
    g = card_groups(h, st, "C26")
    assert g["R1"][0].tolist() == [False, True, False]
    assert g["R2"][0].tolist() == [True, False, False]
    assert g["R3"][0].tolist() == [True, False, False] and g["R3"][1].tolist() == [False, True, False]


# ---- second looks (23 Oct) -------------------------------------------------------------------

def test_pool_of_one_is_exactly_the_v1_comparison() -> None:
    dates = pd.date_range("2016-04-01", "2016-05-10")
    opened = pd.Timestamp("2016-05-09")
    today, windows = W.pooled_windows(dates, opened, 1)
    assert today.tolist() == [dates.get_loc(opened)]
    assert windows[:, 0].tolist() == W.comparable_days(dates, opened).tolist()


def test_pooled_windows_skip_weekends_and_never_overlap_today() -> None:
    dates = pd.date_range("2016-04-01", "2016-05-10")
    today, windows = W.pooled_windows(dates, pd.Timestamp("2016-05-09"), 3)   # a Monday
    assert [str(dates[i].date()) for i in today] == ["2016-05-05", "2016-05-06", "2016-05-09"]
    assert windows.max() < today.min()


def test_pooling_finds_a_steady_rise_that_one_day_misses() -> None:
    days = pd.date_range("2016-03-20", "2016-05-12")
    days = days[days.weekday < 5]
    table = weekday_table(days, 10)                       # 3 of 10 open after 24 h on a usual day
    slow = table["date"].isin(pd.to_datetime(["2016-05-09", "2016-05-10", "2016-05-11"])).to_numpy()
    for d in ("2016-05-09", "2016-05-10", "2016-05-11"):  # 6 of 10 for three days in a row
        rows = (table["date"] == pd.Timestamp(d)).to_numpy()
        table.loc[rows, "open_24h"] = [True] * 6 + [False] * 4
    assert slow.sum() == 30
    one = W.share_alerts(table, pd.DatetimeIndex(["2016-05-12"]), "team", "open_24h", "slowdown", 3.5, 1)
    three = W.share_alerts(table, pd.DatetimeIndex(["2016-05-12"]), "team", "open_24h", "slowdown", 3.5, 3)
    assert one == [] and len(three) == 1                  # 6/10 alone: z 2.1; 18/30 pooled: z 3.6


def test_slowdown_plant_also_updates_the_two_hour_signal() -> None:
    days = pd.date_range("2016-05-09", "2016-05-13")
    table = weekday_table(days, 10)
    table["open_2h"] = ~(table["resolution_h"] <= 2.0)
    plant = {"type": "slowdown", "segment": "G1", "first_day": days[0], "last_day": days[-1], "size": 1.5}
    out = P.plant_slowdown(table, plant)
    assert out["open_2h"].all() and out["open_24h"].sum() == 15   # 2 h × 1.5 = 3 h: not within 2 h, still within 24 h
