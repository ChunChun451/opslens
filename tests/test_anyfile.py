"""Tests for opslens/anyfile.py ("OpsLens on your file").

What they prove: a relevant file of any shape goes through (a delivery-order file with the date
and time in separate columns and a duration instead of an end time); a file that is not about
work items, or too small, is refused with the reason; no feature uses the future; a column
written after the fact (it gives the outcome away) is dropped; every picker gets the same
number of flags. The delivery file is generated here (ours), so the test needs no download.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from opslens import anyfile as A


def delivery_file(n: int = 3000, days: int = 30, seed: int = 3) -> pd.DataFrame:
    """Orders shaped like a public food-delivery export: late when traffic is jammed on festivals."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2022-03-01")
    when = start + pd.to_timedelta(np.sort(rng.uniform(0, days * 24 * 60, n)), unit="min")
    traffic = rng.choice(["Low ", "Medium ", "High ", "Jam "], n, p=[0.35, 0.3, 0.2, 0.15])
    festival = rng.choice(["No ", "Yes "], n, p=[0.9, 0.1])
    weather = rng.choice(["conditions Sunny", "conditions Stormy", "conditions Fog", "conditions Cloudy"], n)
    minutes = 18 + 8 * (traffic == "Jam ") + 4 * (traffic == "High ") + 9 * (festival == "Yes ") + rng.normal(0, 4, n)
    return pd.DataFrame({
        "ID": [f"0x{i:04x}" for i in range(n)],
        "Delivery_person_Ratings": rng.uniform(3.5, 5, n).round(1),
        "Order_Date": when.strftime("%d-%m-%Y"),
        "Time_Orderd": when.strftime("%H:%M:%S"),
        "Weatherconditions": weather,
        "Road_traffic_density": traffic,
        "Festival": festival,
        "City": rng.choice(["Metropolitian ", "Urban ", "Semi-Urban "], n),
        "Time_taken(min)": [f"(min) {int(round(m))}" for m in minutes],
    })


def mapping_for(raw: pd.DataFrame) -> dict:
    peek = A.peek(raw)
    m = dict(peek["suggested"])
    m["features"] = [c["name"] for c in peek["columns"] if c["feature"] and c["name"] not in m.values()]
    return m


def test_a_delivery_file_goes_through_with_a_promised_time():
    raw = delivery_file()
    m = mapping_for(raw)
    assert m["created_at"] == "Order_Date" and m["created_time"] == "Time_Orderd"
    assert m["duration_min"] == "Time_taken(min)"
    assert "Time_taken(min)" not in m["features"]  # the outcome is never a feature
    report = A.analyse(raw, m, target_min=30)
    w = report["warning"]
    assert w["auc"]["opslens"] > 0.75  # traffic and festival make lateness predictable
    assert report["shadow"]["flags"] == round(0.2 * report["shadow"]["items"])
    assert any(c["column"] == "Road_traffic_density" for c in report["cards"])
    assert report["learn"]["items"] + report["test"]["items"] == report["summary"]["items"]


def test_a_file_that_is_not_about_work_items_is_refused():
    rng = np.random.default_rng(0)
    junk = pd.DataFrame({"name": [f"person {i}" for i in range(800)], "favourite_colour": rng.choice(["red", "blue"], 800)})
    with pytest.raises(ValueError, match="map either an end time|tell OpsLens"):
        A.analyse(junk, {"created_at": "name", "resolved_at": None}, target_min=30)


def test_a_small_file_is_refused_with_the_reason():
    raw = delivery_file(n=120, days=20)
    with pytest.raises(ValueError, match="only 120 usable rows"):
        A.analyse(raw, mapping_for(raw), target_min=30)


def test_features_never_use_the_future():
    raw = delivery_file(n=1500)
    items, _ = A.build_items(raw, mapping_for(raw), 30)
    before = A.feature_frame(items)
    later = delivery_file(n=600, seed=9)
    later["Order_Date"] = (pd.Timestamp("2022-06-01") + pd.to_timedelta(np.arange(600), unit="h")).strftime("%d-%m-%Y")
    more, _ = A.build_items(pd.concat([raw, later], ignore_index=True), mapping_for(raw), 30)
    after = A.feature_frame(more).iloc[: len(items)]
    pd.testing.assert_frame_equal(before.reset_index(drop=True), after.reset_index(drop=True), check_categorical=False)


def test_a_column_written_after_the_fact_is_dropped():
    raw = delivery_file()
    items, _ = A.build_items(raw, mapping_for(raw), 30)
    raw = raw.iloc[items.index.argsort()]  # same order as the items
    raw["closing_note"] = np.where(items["missed"].to_numpy(), "sorry for the delay", "thanks")
    m = mapping_for(raw)
    m["features"].append("closing_note")  # the person ticked it by mistake
    report = A.analyse(raw, m, target_min=30)
    assert "closing_note" in report["dropped_after_the_fact"]


def test_column_names_written_after_an_item_opened_are_not_features():
    assert not A.known_at_open("reassignment_count")
    assert not A.known_at_open("Time_taken(min)")
    assert not A.known_at_open("made_sla")
    assert A.known_at_open("vendor")
    assert A.known_at_open("Road_traffic_density")


def test_every_picker_gets_the_same_number_of_flags_each_day():
    day = np.repeat([1, 2, 3], [10, 20, 30])
    rng = np.random.default_rng(1)
    for score in (rng.random(60), np.zeros(60), -np.arange(60.0)):
        flagged = A.flags_by_day(day, score)
        assert [int(flagged[day == d].sum()) for d in (1, 2, 3)] == [2, 4, 6]


def test_open_counts_only_look_back():
    assert A.open_counts(np.array([0.0, 1.0, 2.0]), np.array([5.0, 1.5, 9.0])).tolist() == [0, 1, 1]
