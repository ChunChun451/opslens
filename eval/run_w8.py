"""W8: are the risk explanations faithful? Design (pre-registered): docs/explain/w8_faithfulness.md.

Run:  python eval/run_w8.py

(a) Deletion test: remove a ticket's top reason (replace it with 30 random training rows' values,
    average) vs remove one random other feature; on the raw score (log-odds) and the probability.
(b) Planted Hindi refund/payment segment: share of shown tickets whose top 3 reasons name
    language/skill, vs a control (non-Hindi Team B tickets).
(c) is in opslens/policies.py (with_runner_up) and tests/test_w8.py.
Writes eval/parts/w8.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens import risk  # noqa: E402
from opslens.features import FEATURES  # noqa: E402

MODELS = ROOT / "data" / "generated" / "models"
SEED = 8
SAMPLE = 3000
BACKGROUND = 30
BOOT = 1000
SHOWN_AT = 0.5
SKILL_FEATURES = {"capable_on_shift", "language", "queue_team_language"}


def snapshots() -> tuple[pd.DataFrame, pd.DataFrame]:
    from eval.run_risk import history_with_predictions
    from opslens.classify import TEAM_OF
    from opslens.config import load_config
    from opslens.features import snapshots_from_history

    cal = load_config("calendar")
    sp = cal["splits"]
    first_weekday = pd.Timestamp(cal["start_date"]).weekday()
    agents = pd.read_csv(ROOT / "data" / "generated" / "agents.csv")
    h = history_with_predictions()
    snaps = lambda a, b: snapshots_from_history(h, agents, TEAM_OF, a, b, first_weekday=first_weekday)  # noqa: E731
    return snaps(1, sp["train_last_day"]), snaps(sp["validation_last_day"] + 1, sp["test_last_day"])


def removed_scores(model: risk.RiskModel, M: np.ndarray, B: np.ndarray, cols: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mean raw score and mean calibrated probability after replacing, for each row i, the features
    cols[i] (shape n × k) with each background row's values."""
    n, k = cols.shape
    rep = np.repeat(M, len(B), axis=0)
    bg = np.tile(np.arange(len(B)), n)
    for j in range(k):
        c = np.repeat(cols[:, j], len(B))
        rep[np.arange(len(rep)), c] = B[bg, c]
    raw = model.booster.predict(rep, raw_score=True, num_threads=4)
    prob = model.calibrator.predict(model.booster.predict(rep, num_threads=4))
    return raw.reshape(n, len(B)).mean(axis=1), prob.reshape(n, len(B)).mean(axis=1)


def cluster_ci(values: np.ndarray, tickets: np.ndarray, rng) -> list[float]:
    codes, uniq = pd.factorize(tickets)
    rows_of = pd.Series(np.arange(len(codes))).groupby(codes).apply(np.array).to_list()
    means = []
    for _ in range(BOOT):
        idx = np.concatenate([rows_of[k] for k in rng.integers(0, len(uniq), size=len(uniq))])
        means.append(values[idx].mean())
    return [round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)]


def main() -> int:
    started = time.perf_counter()
    rng = np.random.default_rng(SEED)
    model = risk.load(MODELS)
    train_f, test_f = snapshots()
    p = model.predict(test_f)
    shown = test_f[p >= SHOWN_AT].reset_index(drop=True)
    print(f"test rows {len(test_f):,}; shown (P >= {SHOWN_AT}) {len(shown):,}", flush=True)
    contrib = model.booster.predict(model.frame(shown), pred_contrib=True)[:, :-1]

    # ---- (a) deletion test on a sample ----
    pick = np.sort(rng.choice(len(shown), size=min(SAMPLE, len(shown)), replace=False))
    sample, C = shown.iloc[pick].reset_index(drop=True), contrib[pick]
    M = model.matrix(sample)
    B = model.matrix(train_f.iloc[rng.choice(len(train_f), size=BACKGROUND, replace=False)])
    order = np.argsort(-C, axis=1)
    top1, top3 = order[:, :1], order[:, :3]
    n_feat = len(FEATURES)
    rand1 = np.array([[rng.choice([f for f in range(n_feat) if f != t])] for t in top1[:, 0]])
    rand3 = np.array([rng.choice([f for f in range(n_feat) if f not in set(t)], size=3, replace=False) for t in top3])
    base_raw = model.booster.predict(M, raw_score=True, num_threads=4)
    base_prob = model.calibrator.predict(model.booster.predict(M, num_threads=4))
    tickets = sample["ticket_id"].to_numpy()
    deletion = {"rows": int(len(sample)), "tickets": int(pd.Series(tickets).nunique()), "background_rows": BACKGROUND}
    for name, top, rand in (("top1_vs_random1", top1, rand1), ("top3_vs_random3", top3, rand3)):
        raw_top, prob_top = removed_scores(model, M, B, top)
        raw_rand, prob_rand = removed_scores(model, M, B, rand)
        d_top, d_rand = base_raw - raw_top, base_raw - raw_rand
        pd_top, pd_rand = base_prob - prob_top, base_prob - prob_rand
        diff = d_top - d_rand
        res = {
            "share_top_drops_more_logodds": round(float((d_top > d_rand).mean()), 4),
            "share_top_drops_more_probability": round(float((pd_top > pd_rand).mean()), 4),
            "mean_drop_top_logodds": round(float(d_top.mean()), 4), "mean_drop_random_logodds": round(float(d_rand.mean()), 4),
            "mean_drop_top_probability": round(float(pd_top.mean()), 4),
            "mean_drop_random_probability": round(float(pd_rand.mean()), 4),
            "top_minus_random_logodds": {"mean": round(float(diff.mean()), 4), "ci95": cluster_ci(diff, tickets, rng)},
        }
        res["share_ci95"] = cluster_ci((d_top > d_rand).astype(float), tickets, rng)
        deletion[name] = res
        print(f"  {name}: top drops more in {res['share_top_drops_more_logodds']:.1%} (log-odds), "
              f"{res['share_top_drops_more_probability']:.1%} (probability); mean drop {res['mean_drop_top_logodds']:.2f} "
              f"vs {res['mean_drop_random_logodds']:.2f} log-odds; diff CI {res['top_minus_random_logodds']['ci95']}", flush=True)
    t1 = deletion["top1_vs_random1"]
    deletion["rule_faithful"] = bool(t1["share_top_drops_more_logodds"] >= 0.80 and t1["top_minus_random_logodds"]["ci95"][0] > 0)

    # ---- (b) reasons vs the planted cause ----
    pos = np.where(contrib > 0, contrib, -np.inf)
    top3_all = np.argsort(-pos, axis=1)[:, :3]
    names = np.array(FEATURES)
    has_skill = np.array([any(names[j] in SKILL_FEATURES and contrib[i, j] > 0 for j in row)
                          for i, row in enumerate(top3_all)])
    planted = (shown["language"] == "hi") & shown["category_pred"].isin(["refund", "payment_failure"])
    control = (shown["team"] == "B") & (shown["language"] != "hi")
    segment = {}
    for name, mask in (("planted_hindi_refund_payment", planted), ("control_team_b_not_hindi", control)):
        m = mask.to_numpy()
        segment[name] = {"rows": int(m.sum()), "tickets": int(shown.loc[m, "ticket_id"].nunique()),
                         "share_skill_reason_in_top3": round(float(has_skill[m].mean()), 4) if m.any() else None,
                         "ci95": cluster_ci(has_skill[m].astype(float), shown.loc[m, "ticket_id"].to_numpy(), rng)
                         if m.any() else None}
        print(f"  {name}: {segment[name]}", flush=True)
    segment["skill_features"] = sorted(SKILL_FEATURES)
    most_common = pd.Series(names[top3_all[planted.to_numpy(), 0]]).value_counts().head(5).to_dict()
    segment["planted_top1_reason_counts"] = {k: int(v) for k, v in most_common.items()}

    out = {"shown_threshold": SHOWN_AT, "shown_rows": int(len(shown)), "deletion": deletion, "reasons_vs_plant": segment,
           "runner_up": "opslens/policies.py with_runner_up; regression: tests/test_w8.py (same assignments)",
           "seconds": round(time.perf_counter() - started, 1)}
    path = ROOT / "eval" / "parts" / "w8.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({out['seconds']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
