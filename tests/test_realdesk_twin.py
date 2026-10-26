import numpy as np
import pandas as pd

from opslens import realdesk_twin as T


def tiny(opened_h, prio, stage_list, agents=("a1",), team="G1", days=2) -> T.TwinInput:
    roster = T.Roster()
    for d in range(days):
        roster.team_agents[d] = {team: list(agents)}
        roster.agent_teams[d] = {a: [team] for a in agents}
    return T.TwinInput(ids=[f"I{i}" for i in range(len(opened_h))], opened=np.array(opened_h, dtype=float) * 60,
                       prio=np.array(prio), deadline=np.full(len(opened_h), np.inf), stage_list=stage_list,
                       roster=roster, n_days=days)


def test_docstring_example_desk_takes_the_urgent_one_first_at_eight() -> None:
    inp = tiny([7.0, 7.5], [3, 1], [[(T.WORK, "G1", 2.0)], [(T.WORK, "G1", 2.0)]])
    r = T.run(inp, share=0.5, k=1, policy=T.Policy())
    assert r.pickup.tolist() == [120.0, 30.0]
    assert r.resolved.tolist() == [180.0, 90.0]


def test_two_slots_work_in_parallel_and_waits_release_the_slot() -> None:
    inp = tiny([9.0, 9.0], [3, 3], [[(T.WORK, "G1", 1.0), (T.WAIT, "G1", 5.0), (T.WORK, "G1", 1.0)],
                                    [(T.WORK, "G1", 3.0)]])
    r = T.run(inp, share=1.0, k=2, policy=T.Policy())
    assert r.pickup.tolist() == [0.0, 0.0]
    assert r.resolved.tolist() == [7 * 60.0, 3 * 60.0]


def test_work_starts_only_on_duty_but_finishes_after_hours() -> None:
    inp = tiny([18.5, 19.5], [3, 3], [[(T.WORK, "G1", 3.0)], [(T.WORK, "G1", 1.0)]])
    r = T.run(inp, share=1.0, k=2, policy=T.Policy())
    assert r.pickup.tolist() == [0.0, (24 + 8 - 19.5) * 60]
    assert r.resolved.tolist() == [180.0, (24 + 9 - 19.5) * 60]


def test_cut_shortens_the_duty_window_from_the_end() -> None:
    inp = tiny([17.0], [3], [[(T.WORK, "G1", 1.0)]])
    full = T.run(inp, share=1.0, k=1, policy=T.Policy())
    cut = T.run(inp, share=1.0, k=1, policy=T.Policy(), cut=0.2, cut_from_minute=0.0)
    assert full.pickup[0] == 0.0 and cut.pickup[0] == 15 * 60.0


def test_stages_follow_the_real_states_and_teams() -> None:
    t = pd.Timestamp("2016-03-01 08:00")
    h = pd.Timedelta(hours=1)
    events = pd.DataFrame({
        "number": ["X"] * 6 + ["Y"] * 2,
        "incident_state": ["New", "Active", "Awaiting User Info", "Active", "Resolved", "Closed", "New", "Resolved"],
        "assignment_group": ["G1", "G1", "G1", "G2", "G2", "G2", "G3", "G3"],
        "sys_updated_at": [t, t + h, t + 4 * h, t + 24 * h, t + 26 * h, t + 99 * h, t, t + 2 * h],
    })
    st = T.stages(events)
    assert st["X"] == [(T.WORK, "G1", 3.0), (T.WAIT, "G1", 20.0), (T.WORK, "G2", 2.0)]
    assert st["Y"] == [(T.WORK, "G3", 2.0)]


def test_incident_with_no_stages_is_never_resolved() -> None:
    inp = tiny([9.0], [3], [[]])
    r = T.run(inp, share=1.0, k=1, policy=T.Policy())
    assert np.isnan(r.pickup[0]) and np.isnan(r.resolved[0])
