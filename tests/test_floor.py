import numpy as np
import pytest

from opslens.floor import earliest_start, merge, unavoidable
from opslens.policies import (ClairvoyantSlackPolicy, LeastSlackPolicy, OpsLensPolicy, OpsLensSettings, baseline_a,
                              baseline_b, baseline_c, baseline_d)
from opslens.simulate import Agent, Assignment, simulate
from tests.test_optimize import WEIGHTS
from tests.test_simulate import make_world

CATS = ["refund", "late_delivery", "app_bug"]


class RandomLegalPolicy:
    name = "random legal"

    def __init__(self, seed: int) -> None:
        self.rng = np.random.default_rng(seed)

    def decide(self, state, now):
        free = state.free_agents(now)
        out = []
        for t in state.waiting_tickets():
            ok = [a for a in free if t.language in a.languages]
            if not ok or self.rng.random() < 0.3:
                continue
            a = ok[self.rng.integers(len(ok))]
            free.remove(a)
            cat = CATS[self.rng.integers(len(CATS))]
            out.append(Assignment(t.idx, a.agent_id, cat, deliberate_cross_skill=bool(self.rng.random() < 0.5)))
        return out


def random_world(seed: int):
    rng = np.random.default_rng(seed)
    agents = []
    for k in range(4):
        langs = {"en"} | ({"hi"} if rng.random() < 0.4 else set())
        skills = frozenset(rng.choice(CATS, size=rng.integers(1, 3), replace=False).tolist())
        agents.append(Agent(f"a{k}", f"a{k}", "A", skills, skills, frozenset(langs),
                            shift_start_min=int(rng.integers(0, 24)) * 60, shift_minutes=480, days_off=frozenset()))
    n = 40
    created = np.sort(rng.uniform(0, 1440, n))
    handles = rng.lognormal(np.log(15), 0.6, size=(n, 3))
    prio = rng.choice(["P1", "P2"], n).tolist()
    world = make_world(created.tolist(), handles, agents, true_cat=rng.choice(CATS, n).tolist(),
                       selected=rng.choice(CATS, n).tolist(), priority=prio,
                       language=rng.choice(["en", "hi"], n, p=[0.7, 0.3]).tolist(),
                       reopen_u=rng.uniform(0, 0.3, n).tolist(), reopen_delay=rng.uniform(30, 180, n).tolist())
    world.sla_min[:] = [60.0 if p == "P1" else 240.0 for p in prio]
    return world


def policies(world, seed):
    return [baseline_a(), baseline_b(), baseline_c(), baseline_d(world, {}), LeastSlackPolicy(world, {}, {}),
            ClairvoyantSlackPolicy(world), OpsLensPolicy(world, {}, None, WEIGHTS, OpsLensSettings(use_risk=False)),
            OpsLensPolicy(world, {}, None, {**WEIGHTS, "mismatch_cost": 0.8, "new_ticket_rescue": 0.9},
                          OpsLensSettings(use_risk=False)),
            RandomLegalPolicy(seed), RandomLegalPolicy(seed + 1000)]


@pytest.mark.parametrize("seed", range(25))
def test_no_policy_beats_the_floor(seed: int) -> None:
    world = random_world(seed)
    floor = unavoidable(world, 0.0, 0.0, 1440.0)
    for policy in policies(world, seed):
        out = simulate(world, policy, 0, 1440, decide_every_min=2).tickets
        breached = set(out.loc[out["breached"], "idx"])
        assert floor <= breached, f"{policy.name} saved a ticket the floor called unavoidable: {floor - breached}"


def test_earliest_start_on_a_hand_example() -> None:
    cover = merge([(600.0, 1080.0), (0.0, 480.0), (300.0, 400.0)])
    assert cover == ([0.0, 600.0], [480.0, 1080.0])
    assert earliest_start(cover, 100.0) == 100.0
    assert earliest_start(cover, 500.0) == 600.0
    assert earliest_start(cover, 2000.0) == float("inf")


def test_cross_skill_saves_a_night_ticket_in_the_floor() -> None:
    trained = Agent("t", "t", "B", frozenset({"refund"}), frozenset({"refund"}), frozenset({"en", "hi"}),
                    shift_start_min=540, shift_minutes=480, days_off=frozenset())
    night = Agent("n", "n", "D", frozenset({"app_bug"}), frozenset({"app_bug"}), frozenset({"en", "hi"}),
                  shift_start_min=1320, shift_minutes=540, days_off=frozenset())
    world = make_world([1410.0], [20.0], [trained, night], language=["hi"], true_cat=["refund"], sla=240.0)
    assert unavoidable(world, 0.0, 0.0, 2880.0) == set()
    world_without_night = make_world([1410.0], [20.0], [trained], language=["hi"], true_cat=["refund"], sla=240.0)
    assert unavoidable(world_without_night, 0.0, 0.0, 2880.0) == {0}
