from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from opslens import anyfile as A


def delivery_file(n: int = 3000, days: int = 30, seed: int = 3) -> pd.DataFrame:
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
    assert "Time_taken(min)" not in m["features"]
    report = A.analyse(raw, m, target_min=30)
    w = report["warning"]
    assert w["auc"]["opslens"] > 0.75
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
    raw = raw.iloc[items.index.argsort()]
    raw["closing_note"] = np.where(items["missed"].to_numpy(), "sorry for the delay", "thanks")
    m = mapping_for(raw)
    m["features"].append("closing_note")
    report = A.analyse(raw, m, target_min=30)
    assert "closing_note" in report["dropped_after_the_fact"]


def test_column_names_written_after_an_item_opened_are_not_features():
    assert not A.known_at_open("reassignment_count")
    assert not A.known_at_open("Time_taken(min)")
    assert not A.known_at_open("made_sla")
    assert A.known_at_open("vendor")
    assert A.known_at_open("Road_traffic_density")


def test_who_and_where_of_a_delivery_are_known_when_it_is_ordered_but_not_when_it_arrived():
    for known in ("Delivery_person_Age", "Delivery_location_latitude", "multiple_deliveries", "pickup_location"):
        assert A.known_at_open(known), known
    for after in ("Delivery_person_Ratings", "delivery_time", "Delivery Date", "delivered_at", "Delivered",
                  "pickup_time", "delivery_status", "Time_taken(min)"):
        assert not A.known_at_open(after), after


def test_an_id_column_is_not_learned_from_unless_ticked():
    raw = delivery_file()
    raw["Delivery_person_ID"] = [f"RES{i % 400:03d}DEL0{i % 3}" for i in range(len(raw))]
    raw["Delivery_person_Age"] = (20 + np.arange(len(raw)) % 20).astype(float)
    features = {c["name"]: c["feature"] for c in A.peek(raw)["columns"]}
    assert features["Delivery_person_Age"] and not features["Delivery_person_ID"]


def test_every_picker_gets_the_same_number_of_flags_each_day():
    day = np.repeat([1, 2, 3], [10, 20, 30])
    rng = np.random.default_rng(1)
    for score in (rng.random(60), np.zeros(60), -np.arange(60.0)):
        flagged = A.flags_by_day(day, score)
        assert [int(flagged[day == d].sum()) for d in (1, 2, 3)] == [2, 4, 6]


def test_open_counts_only_look_back():
    assert A.open_counts(np.array([0.0, 1.0, 2.0]), np.array([5.0, 1.5, 9.0])).tolist() == [0, 1, 1]


def test_spreadsheet_day_fractions_read_as_clock_times():
    times = pd.Series(["21:55", "0.458333333", None, "0.958333333"])
    out = A.clock_text(times)
    assert out[[0, 1, 3]].tolist() == ["21:55", "11:00", "23:00"] and pd.isna(out[2])


def helpdesk_file(n: int = 1500, days: int = 40, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    opened = pd.Timestamp("2026-01-05") + pd.to_timedelta(np.sort(rng.uniform(0, days * 1440, n)), unit="min")
    group = rng.choice(["Network", "Apps", "Access"], n, p=[0.3, 0.4, 0.3])
    hours = rng.gamma(2.0, 6.0, n) + 14 * (group == "Network")
    return pd.DataFrame({
        "Ticket": [f"T{i:05d}" for i in range(n)],
        "Date Created": opened.strftime("%Y-%m-%d %H:%M"),
        "Closed On": (opened + pd.to_timedelta(hours, unit="h")).strftime("%Y-%m-%d %H:%M"),
        "Priority Level": rng.choice(["High", "Medium", "Low"], n),
        "Support Group": group,
        "Issue Type": rng.choice(["Password", "VPN", "Laptop", "Email"], n),
        "SLA Breached": np.where(hours > 24, "Yes", "No"),
    })


def test_the_shadow_timeline_replays_the_day_and_adds_up_to_its_totals():
    raw = delivery_file()
    report = A.analyse(raw, mapping_for(raw), target_min=30)
    sh = report["shadow"]
    line = sh["timeline"]
    assert len(line) == sh["items"] and sum(x["missed"] for x in line) == sh["misses"]
    for name in sh["caught"]:
        assert sum(name in x["flagged"] for x in line) == sh["flags"]
        assert sum(name in x["flagged"] and x["missed"] for x in line) == sh["caught"][name]
    opened = [x["opened_min"] for x in line]
    assert opened == sorted(opened) and 0 <= opened[0] and opened[-1] < 1440
    assert all(x["ended_min"] >= x["opened_min"] for x in line)
    assert all(("reasons" in x) == ("opslens" in x["flagged"]) for x in line)


def test_the_shadow_flags_never_read_what_happened_later():
    raw = delivery_file()
    raw["on_time"] = pd.to_numeric(raw["Time_taken(min)"].str.extract(r"(\d+)")[0]) <= 25
    m = mapping_for(raw)
    assert m["sla_met"] == "on_time"
    before = A.analyse(raw, m)
    flipped = raw.copy()
    later = np.arange(len(raw)) >= int(0.7 * len(raw))
    flipped.loc[later, "on_time"] = ~flipped.loc[later, "on_time"]
    after = A.analyse(flipped, m)
    keep = lambda r: [(x["id"], x["flagged"], x["risk"]) for x in r["shadow"]["timeline"]]
    assert keep(before) == keep(after)
    assert before["shadow"]["misses"] != after["shadow"]["misses"]


def test_the_forecast_reads_only_days_a_week_or_more_before():
    rng = np.random.default_rng(2)
    counts = pd.DataFrame({"team": ["A"] * 60 + ["B"] * 60, "day": list(range(60)) * 2, "count": rng.poisson(20, 120)})
    before = A.lag_features(counts, first_weekday=0)
    changed = counts.copy()
    changed.loc[(changed["team"] == "A") & (changed["day"] == 40), "count"] += 50
    after = A.lag_features(changed, first_weekday=0)
    same = before["day"] <= 46
    pd.testing.assert_frame_equal(before.loc[same, A.FORECAST_INPUTS], after.loc[same, A.FORECAST_INPUTS])
    row = (before["team"] == "A") & (before["day"] == 47)
    assert after.loc[row, "lag_7"].item() == before.loc[row, "lag_7"].item() + 50


def test_the_team_forecast_learns_before_it_scores_and_reports_both_forecasts():
    raw = delivery_file(n=9000, days=90)
    report = A.analyse(raw, mapping_for(raw), target_min=30)
    f = report["forecast"]
    assert "needs" not in f and len(f["teams"]) == 3
    assert f["learned_days"][1] < f["scored_days"][0]
    assert f["chosen_on_check"] in ("learned", "same_weekday_last_week")
    assert f["wape_learned"] > 0 and f["wape_same_weekday_last_week"] > 0
    assert 0 < len(f["first_week"]) <= 7 * len(f["teams"])
    assert sum(t["items"] for t in f["by_team"]) == f["items_scored"]


def test_a_file_without_team_priority_or_category_says_what_each_part_needs():
    raw = delivery_file().drop(columns=["City"])
    report = A.analyse(raw, mapping_for(raw), target_min=30)
    assert report["needs"]["team"] == "a team column" and report["needs"]["priority"] == "a priority column"
    assert report["needs"]["category"] == "a category column"
    assert report["forecast"] == {"needs": "a team column"} and report["needs"]["forecast"] == "a team column"
    assert report["warning"]["vs"]["rival"] == "rule" and "priority" not in report["warning"]["auc"]
    for key in ("team", "category", "priority"):
        assert f"by_{key}" in report["summary"] or key in report["needs"]
    assert report["shadow"].get("timeline") or report["shadow"].get("timeline_note")


def test_a_helpdesk_export_is_guessed_without_help():
    raw = helpdesk_file()
    peek = A.peek(raw)
    m = peek["suggested"]
    assert (m["created_at"], m["resolved_at"], m["breached"]) == ("Date Created", "Closed On", "SLA Breached")
    assert (m["priority"], m["team"], m["category"], m["id"]) == ("Priority Level", "Support Group", "Issue Type", "Ticket")
    assert peek["ask"] == [] and peek["plan"]["problem"] is None
    assert peek["plan"]["miss"] == {"rule": "breached", "column": "SLA Breached", "target_min": None, "assumed": False}
    report = A.analyse(raw, m)
    assert report["miss"]["rule"] == "breached" and report["summary"]["by_team"][0]["name"] == "Network"
    assert "SLA Breached" not in report["features"]


def test_opslens_asks_only_what_it_cannot_guess():
    raw = helpdesk_file().rename(columns={"Date Created": "t_a", "Closed On": "t_b"})
    peek = A.peek(raw)
    assert [q["role"] for q in peek["ask"]] == ["created_at", "end"] and peek["plan"] is None
    assert [o["column"] for o in peek["ask"][0]["options"]] == ["t_a", "t_b"]
    assert {"column": "t_b", "role": "resolved_at"} in peek["ask"][1]["options"]


def test_the_default_promise_is_the_median_rounded_up():
    assert [A.round_promise(m) for m in (21.4, 20, 26, 50, 700, 2000)] == [25, 25, 30, 60, 720, 2880]
    plan = A.peek(delivery_file())["plan"]
    assert plan["miss"] == {"rule": "promise", "column": None, "target_min": 25.0, "assumed": True}
    assert plan["median_min"] < 25 and 0 < plan["missed_pct"] < 50
    assert (plan["learn_items"], plan["test_items"]) == (2100, 900)


def test_a_refusal_is_one_sentence_and_one_fix():
    raw = delivery_file(n=120, days=20)
    plan = A.check_mapping(raw, mapping_for(raw), 30)
    assert plan["problem"].startswith("This file cannot be analysed: only 120 usable rows")
    assert plan["problem"].endswith("Try a longer export, a few months of items.")
    junk = pd.DataFrame({"name": ["a", "b"] * 400, "colour": ["red", "blue"] * 400})
    assert A.check_mapping(junk, {"created_at": "name"}, 30)["problem"] == A.NO_END


@pytest.mark.parametrize("unit", ["ns", "us", "s"])
def test_hour_before_and_open_counts_do_not_depend_on_the_time_unit(unit: str) -> None:
    created = pd.to_datetime(["2026-10-01 10:00", "2026-10-01 10:30", "2026-10-01 10:50", "2026-10-01 12:00"]).as_unit(unit)
    items = pd.DataFrame({"created_at": created, "end_at": created + pd.Timedelta(minutes=45)})
    X = A.feature_frame(items)
    assert X["arrived in the hour before"].tolist() == [0, 1, 2, 0]
    assert X["open when it arrived"].tolist() == [0, 1, 1, 0]


def test_plan_effect_adds_up_on_the_later_items_and_counts_an_overlap_once():
    cells = [[0, 0, 600, 60], [0, 1, 100, 40], [1, 0, 150, 45], [1, 1, 50, 35], [3, 0, 80, 40], [2, 1, 20, 10]]
    alone = A.plan_effect(cells, [], False, 0.5)
    assert alone["before"] == alone["after"] == 230 and alone["fewer"] == 0 and alone["items"] == 1000
    warn = A.plan_effect(cells, [], True, 0.5)
    assert warn["flagged_misses"] == 85 and warn["fewer"] == round(0.5 * 85)
    group = A.plan_effect(cells, [0], False, 0.5)
    rest = (60 + 40 + 10) / (600 + 100 + 20)
    assert group["after"] == round(110 + rest * (150 + 50 + 80))
    other = A.plan_effect(cells, [1], False, 0.5)
    both = A.plan_effect(cells, [0, 1], False, 0.5)
    assert both["fixed_items"] == 150 + 50 + 80 + 20
    assert max(group["fewer"], other["fewer"]) <= both["fewer"] < group["fewer"] + other["fewer"]
    plan = A.plan_effect(cells, [0], True, 0.5)
    assert plan["fewer"] == plan["from_fixes"] + plan["from_warning"]
    assert plan["after"] < min(group["after"], warn["after"])


def test_a_group_that_misses_less_than_the_rest_is_never_made_worse():
    cells = [[0, 0, 100, 50], [1, 0, 100, 5]]
    assert A.plan_effect(cells, [0], False, 0.5)["after"] == 55


def test_the_report_effects_match_its_own_measured_numbers():
    raw = delivery_file()
    report = A.analyse(raw, mapping_for(raw), target_min=30)
    w, impact = report["warning"], report["impact"]
    assert impact["warn"]["before"] == w["misses"] and impact["warn"]["items"] == w["items"]
    assert impact["warn"]["flagged_misses"] == round(w["caught_pct"]["opslens"] * w["misses"] / 100)
    for card, single in zip(report["cards"], impact["cards"]):
        assert single["fixed_items"] == card["test_items"]
        assert single["rest_pct"] == card["test_rest_pct"]
        gap = card["test_items"] * max(0.0, card["test_pct"] - card["test_rest_pct"]) / 100
        assert abs(single["fewer"] - gap) <= max(1.0, 0.001 * card["test_items"])
