import numpy as np
import pandas as pd

from eval.run_w7 import LogRegRisk, TimeLeftRule, alert_blocks
from opslens.features import CATEGORICAL, FEATURES


def fake_snapshots(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({f: rng.normal(size=n) for f in FEATURES if f not in CATEGORICAL})
    for c in CATEGORICAL:
        df[c] = rng.choice(["a", "b", "c"], size=n)
    df["time_left_min"] = rng.uniform(0, 240, size=n)
    df["breached"] = (rng.uniform(size=n) < 1 / (1 + np.exp(df["time_left_min"] / 40 - 2))).astype(int)
    return df


def test_rivals_have_the_policy_interface_and_learn_time_left() -> None:
    train, valid, test = fake_snapshots(3000, 1), fake_snapshots(1000, 2), fake_snapshots(500, 3)
    lr, rule = LogRegRisk(train, valid), TimeLeftRule(valid)
    for model in (lr, rule):
        p = model.predict(test)
        assert p.shape == (500,) and ((p >= 0) & (p <= 1)).all()
    order = np.argsort(test["time_left_min"].to_numpy())
    assert (np.diff(rule.predict(test)[order]) <= 1e-12).all()
    assert np.corrcoef(lr.predict(test), -test["time_left_min"])[0, 1] > 0.5


def test_alert_blocks_split_by_team_gap_and_midnight() -> None:
    hours = [("A", 10), ("A", 11), ("A", 12), ("A", 14), ("B", 15), ("B", 16), ("C", 23), ("C", 24)]
    assert alert_blocks(hours) == [[("A", 10), ("A", 11), ("A", 12)], [("B", 15), ("B", 16)]]
