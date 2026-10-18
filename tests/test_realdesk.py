"""The real public service desk: the event-log helpers measure what they claim."""

import pandas as pd

from opslens.realdesk import masks, time_in_states


def test_time_in_states_adds_up_the_hours_per_state() -> None:
    # New 2 h → Active 5 h → Awaiting User Info 20 h → Resolved (the docstring example).
    t0 = pd.Timestamp("2016-03-01 08:00")
    events = pd.DataFrame({
        "number": ["INC1"] * 4,
        "incident_state": ["New", "Active", "Awaiting User Info", "Resolved"],
        "sys_updated_at": [t0, t0 + pd.Timedelta(hours=2), t0 + pd.Timedelta(hours=7), t0 + pd.Timedelta(hours=27)],
    })
    st = time_in_states(events).loc["INC1"]
    assert st["waiting to be picked up"] == 2 and st["being worked on"] == 5 and st["waiting for the user"] == 20


def test_check_period_is_the_end_of_learning_and_test_comes_later() -> None:
    created = pd.date_range("2016-03-01", periods=10, freq="D")
    incidents = pd.DataFrame({"created_at": created, "split": ["train"] * 7 + ["test"] * 3})
    learn, check, test = masks(incidents)
    assert learn.sum() + check.sum() == 7 and test.sum() == 3
    assert created[learn].max() < created[check].min() and created[check].max() < created[test].min()
