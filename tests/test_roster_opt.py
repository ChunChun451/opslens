import numpy as np
import pandas as pd

from opslens.roster_opt import options_for, plan_roster, weighted_shortage
from opslens.staffing import Shift, plan_moves

FIRST_WEEKDAY = 0


def test_options_keep_hours_and_two_consecutive_days_off() -> None:
    s = Shift("C05", "C", 14, 9, frozenset({5, 6}))
    opts = options_for(s)
    assert len(opts) == 5 * 7 and s in opts
    assert all(o.hours == 9 and len(o.days_off) == 2 for o in opts)
    assert all(any(o.days_off == {d, (d + 1) % 7} for d in range(7)) for o in opts)
    assert {o.start_hour for o in opts} == {12, 13, 14, 15, 16}
    assert options_for(Shift("A09", "A", 22, 9, frozenset({0, 1}))) == [Shift("A09", "A", 22, 9, frozenset({0, 1}))]


def small_case():
    shifts = [Shift(f"C0{i}", "C", start, 9, frozenset(off)) for i, (start, off) in
              enumerate([(8, {5, 6}), (8, {5, 6}), (12, {0, 1}), (14, {5, 6}), (14, {2, 3})], 1)]
    hours = 7 * 24
    need = np.zeros(hours)
    for day in range(7):
        need[day * 24 + 9: day * 24 + 17] = 1.5
        if day in (5, 6):
            need[day * 24 + 18: day * 24 + 23] = 4
    need_df = pd.DataFrame({"C": need})
    return shifts, need_df, need_df * 0.8


def test_change_limit_and_never_worse_than_greedy() -> None:
    shifts, need, load = small_case()
    before = weighted_shortage(shifts, need, 1, 7, FIRST_WEEKDAY, load)
    greedy, _ = plan_moves(shifts, need, 1, 7, FIRST_WEEKDAY, load=load, max_moves=2)
    new, changes, info = plan_roster(shifts, need, 1, 7, FIRST_WEEKDAY, load=load, max_changes_per_team=2,
                                     time_limit_s=10)
    assert info["status"] == "OPTIMAL"
    assert len(changes) <= 2
    assert sorted(s.agent_id for s in new) == sorted(s.agent_id for s in shifts)
    after = weighted_shortage(new, need, 1, 7, FIRST_WEEKDAY, load)
    assert after < before
    assert after + len(changes) <= weighted_shortage(greedy, need, 1, 7, FIRST_WEEKDAY, load) + 2 + 1e-6
