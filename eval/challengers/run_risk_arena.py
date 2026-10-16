"""Challenger arena, part 2: TabPFN-3 (Prior Labs) vs our LightGBM breach-risk model.

Run (eval-only venv; needs TABPFN_TOKEN in .env — the owner gets it at ux.priorlabs.ai after
accepting the TabPFN licence; we never accept it for them):
    .venv-challengers/Scripts/python.exe eval/challengers/run_risk_arena.py

PRE-REGISTERED (written before the first run, CLAUDE.md 7.11):
- Same features (opslens/features.py snapshots), same splits: train days 1-35, validation 36-42,
  test 43-56. Snapshots of tickets already past their SLA are excluded, as in run_risk.py.
- TabPFN learns in context, and on a laptop CPU its context must be small: a random 10,000
  train snapshots (seed 0, stratified by breach). Both models are scored on the SAME random
  20,000 test snapshots (seed 0).
- Incumbent = the shipped LightGBM (all train snapshots, isotonic on validation). For
  information we also train LightGBM on the same 10,000 rows.
- Main metric: test AUC. Also PR-AUC, top-10% precision, Brier (TabPFN calibrated with
  isotonic on validation, like ours).
- Rule: ship TabPFN-3 only if its AUC is more than 2% higher (relative: > 1.02 x LightGBM)
  AND scoring one refresh of 300 waiting tickets takes <= 1 s on this CPU (the policy rescores
  every 3 simulated minutes inside a decision with a 1 s budget).
Writes eval/parts/challenger_risk.json.

Example: LightGBM AUC 0.976 → TabPFN-3 would need more than 0.9955 to pass the accuracy half.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from opslens import risk  # noqa: E402
from opslens.classify import TEAM_OF  # noqa: E402
from opslens.config import load_config, load_env_file  # noqa: E402
from opslens.features import snapshots_from_history  # noqa: E402
from run_risk import history_with_predictions  # noqa: E402

MARGIN = 0.02
LATENCY_BUDGET_S = 1.0
CONTEXT_ROWS = 10_000
TEST_ROWS = 20_000


def stratified_sample(feats: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    share = n / len(feats)
    parts = [g.sample(frac=share, random_state=seed) for _, g in feats.groupby("breached")]
    return pd.concat(parts).sort_index()


def main() -> int:
    load_env_file()
    if not os.environ.get("TABPFN_TOKEN"):
        print("TABPFN_TOKEN missing: the owner must accept the TabPFN licence at ux.priorlabs.ai and add the key to .env")
        return 2
    from tabpfn import TabPFNClassifier  # eval-only dependency
    from tabpfn.constants import ModelVersion

    cal = load_config("calendar")
    sp = cal["splits"]
    agents = pd.read_csv(ROOT / "data" / "generated" / "agents.csv")
    h = history_with_predictions()
    weekday = pd.Timestamp(cal["start_date"]).weekday()

    def snaps(first: int, last: int) -> pd.DataFrame:
        return snapshots_from_history(h, agents, TEAM_OF, first, last, first_weekday=weekday)

    train_f = snaps(1, sp["train_last_day"])
    valid_f = snaps(sp["train_last_day"] + 1, sp["validation_last_day"])
    test_f = snaps(sp["validation_last_day"] + 1, sp["test_last_day"])
    incumbent = risk.train(train_f, valid_f)
    small = stratified_sample(train_f, CONTEXT_ROWS, seed=0)
    small_lgbm = risk.train(small, valid_f)
    test_s = test_f.sample(n=min(TEST_ROWS, len(test_f)), random_state=0)
    valid_s = valid_f.sample(n=min(TEST_ROWS, len(valid_f)), random_state=0)

    # TabPFN reads plain numbers; reuse our category coding so both models see identical inputs.
    X = incumbent.matrix
    clf = TabPFNClassifier.create_default_for_version(ModelVersion.V3, device="cpu")
    t0 = time.perf_counter()
    clf.fit(X(small), small["breached"].to_numpy())
    fit_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    raw_valid = clf.predict_proba(X(valid_s))[:, 1]
    raw_test = clf.predict_proba(X(test_s))[:, 1]
    score_s = time.perf_counter() - t0
    one = test_s.head(300)
    t0 = time.perf_counter()
    clf.predict_proba(X(one))
    refresh_s = time.perf_counter() - t0
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw_valid, valid_s["breached"])

    y = test_s["breached"].to_numpy()
    scores = {
        "tabpfn3": risk.evaluate(y, iso.predict(raw_test)),
        "lightgbm_shipped": risk.evaluate(y, incumbent.predict(test_s)),
        "lightgbm_same_10k": risk.evaluate(y, small_lgbm.predict(test_s)),
    }
    for s in scores.values():
        s.pop("calibration", None)
    t0 = time.perf_counter()
    incumbent.predict(one)
    lgbm_refresh_s = time.perf_counter() - t0

    auc_c, auc_l = scores["tabpfn3"]["auc"], scores["lightgbm_shipped"]["auc"]
    accuracy_ok = auc_c > (1 + MARGIN) * auc_l
    latency_ok = refresh_s <= LATENCY_BUDGET_S
    result = {
        "challenger": f"TabPFN-3 ({CONTEXT_ROWS:,} train snapshots in context, CPU)",
        "incumbent": "LightGBM + isotonic (opslens/risk.py)", "main_metric": "test AUC",
        "rule_margin": MARGIN, "latency_budget_s": LATENCY_BUDGET_S, "test_rows": int(len(test_s)),
        "scores": scores, "tabpfn_fit_s": fit_s, "tabpfn_score_s": score_s,
        "refresh_300_s": {"tabpfn3": refresh_s, "lightgbm": lgbm_refresh_s},
        "relative_gain_pct": 100 * (auc_c - auc_l) / auc_l,
        "accuracy_ok": bool(accuracy_ok), "latency_ok": bool(latency_ok),
        "verdict": "ship challenger" if accuracy_ok and latency_ok else "keep LightGBM",
    }
    for name, s in scores.items():
        print(f"{name:20s} AUC {s['auc']:.4f} PR-AUC {s['pr_auc']:.4f} top10 {s['top10_precision']:.3f} Brier {s['brier']:.4f}")
    print(f"300-ticket refresh: TabPFN {refresh_s:.2f}s, LightGBM {lgbm_refresh_s * 1000:.1f} ms -> {result['verdict']}")
    (ROOT / "eval" / "parts" / "challenger_risk.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
