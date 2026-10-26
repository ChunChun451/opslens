from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens import risk
from opslens.features import CATEGORICAL, FEATURES

MODELS = ROOT / "data" / "generated" / "models"
LOGREG_FILE = MODELS / "w7_logreg.pkl"
BOOT = 1000
SEEDS = [1, 2, 3, 4, 5]
FIRST, LAST = 43, 56
NUMERIC = [f for f in FEATURES if f not in CATEGORICAL]


class LogRegRisk:
    def __init__(self, train_feats: pd.DataFrame, valid_feats: pd.DataFrame) -> None:
        prep = ColumnTransformer([
            ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), NUMERIC),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ])
        self.pipe = Pipeline([("prep", prep), ("clf", LogisticRegression(C=1.0, max_iter=3000))])
        self.pipe.fit(self._x(train_feats), train_feats["breached"].astype(int))
        self.calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self.calibrator.fit(self.raw(valid_feats), valid_feats["breached"].astype(int))

    @staticmethod
    def _x(feats: pd.DataFrame) -> pd.DataFrame:
        x = feats[FEATURES].copy()
        for c in CATEGORICAL:
            x[c] = x[c].astype(str)
        for c in NUMERIC:
            x[c] = pd.to_numeric(x[c], errors="coerce").astype(float)
        return x

    def raw(self, feats: pd.DataFrame) -> np.ndarray:
        return self.pipe.predict_proba(self._x(feats))[:, 1]

    def predict(self, feats: pd.DataFrame) -> np.ndarray:
        return self.calibrator.predict(self.raw(feats))


class TimeLeftRule:
    def __init__(self, valid_feats: pd.DataFrame) -> None:
        self.calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0, increasing=False)
        self.calibrator.fit(valid_feats["time_left_min"].to_numpy(float), valid_feats["breached"].astype(int))

    def predict(self, feats: pd.DataFrame) -> np.ndarray:
        return self.calibrator.predict(feats["time_left_min"].to_numpy(float))


def metrics(y: np.ndarray, p: np.ndarray, rank: np.ndarray | None = None) -> dict:
    out = risk.evaluate(y, p)
    if rank is not None:
        order = np.argsort(-rank)
        out["auc"] = float(roc_auc_score(y, rank))
        out["pr_auc"] = float(average_precision_score(y, rank))
        out["top10_precision"] = float(y[order[: max(1, len(y) // 10)]].mean())
    return out


def cluster_bootstrap(y: np.ndarray, scores: dict[str, np.ndarray], tickets: np.ndarray, rng) -> dict:
    codes, uniq = pd.factorize(tickets)
    rows_of = pd.Series(np.arange(len(codes))).groupby(codes).apply(np.array).to_list()
    stats = {name: {"auc": [], "brier": []} for name in scores}
    for _ in range(BOOT):
        pick = rng.integers(0, len(uniq), size=len(uniq))
        idx = np.concatenate([rows_of[k] for k in pick])
        for name, (rank, prob) in scores.items():
            stats[name]["auc"].append(roc_auc_score(y[idx], rank[idx]))
            stats[name]["brier"].append(brier_score_loss(y[idx], prob[idx]))
    out = {}
    q = lambda a: [round(float(np.percentile(a, 2.5)), 4), round(float(np.percentile(a, 97.5)), 4)]
    for name in scores:
        out[name] = {"auc_ci95": q(stats[name]["auc"]), "brier_ci95": q(stats[name]["brier"])}
        if name != "lightgbm":
            d_auc = np.array(stats["lightgbm"]["auc"]) - np.array(stats[name]["auc"])
            d_brier = np.array(stats["lightgbm"]["brier"]) - np.array(stats[name]["brier"])
            out[name]["lightgbm_minus_this_auc_ci95"] = q(d_auc)
            out[name]["lightgbm_minus_this_brier_ci95"] = q(d_brier)
    return out


def offline_compare() -> tuple[dict, LogRegRisk]:
    from eval.run_risk import history_with_predictions
    from opslens.classify import TEAM_OF
    from opslens.config import load_config
    from opslens.features import snapshots_from_history

    cal = load_config("calendar")
    sp = cal["splits"]
    first_weekday = pd.Timestamp(cal["start_date"]).weekday()
    agents = pd.read_csv(ROOT / "data" / "generated" / "agents.csv")
    h = history_with_predictions()
    snaps = lambda a, b: snapshots_from_history(h, agents, TEAM_OF, a, b, first_weekday=first_weekday)
    train_f, valid_f = snaps(1, sp["train_last_day"]), snaps(sp["train_last_day"] + 1, sp["validation_last_day"])
    test_f = snaps(sp["validation_last_day"] + 1, sp["test_last_day"])
    print(f"snapshots: train {len(train_f):,}, validation {len(valid_f):,}, test {len(test_f):,}", flush=True)

    lgbm = risk.load(MODELS)
    logreg = LogRegRisk(train_f, valid_f)
    rule = TimeLeftRule(valid_f)
    y = test_f["breached"].astype(int).to_numpy()
    probs = {"lightgbm": lgbm.predict(test_f), "logistic_regression": logreg.predict(test_f),
             "time_left_rule": rule.predict(test_f)}
    ranks = {"lightgbm": lgbm.raw(test_f), "logistic_regression": logreg.raw(test_f),
             "time_left_rule": -test_f["time_left_min"].to_numpy(float)}
    first = (~test_f.duplicated("ticket_id")).to_numpy()
    out = {"rows": int(len(y)), "tickets": int(test_f["ticket_id"].nunique()), "models": {}}
    for name in probs:
        out["models"][name] = {"all_rows": metrics(y, probs[name], ranks[name]),
                               "at_arrival": metrics(y[first], probs[name][first], ranks[name][first])}
        m = out["models"][name]["all_rows"]
        print(f"  {name:20s} AUC {m['auc']:.4f}  PR-AUC {m['pr_auc']:.4f}  top10 {m['top10_precision']:.3f}  "
              f"Brier {m['brier']:.4f}", flush=True)
    boot = cluster_bootstrap(y, {k: (ranks[k], probs[k]) for k in probs}, test_f["ticket_id"].to_numpy(),
                             np.random.default_rng(7))
    for name in probs:
        out["models"][name]["bootstrap"] = boot[name]
    print("  bootstrap:", json.dumps(boot), flush=True)
    return out, logreg


def run_variant(job: dict) -> dict:
    import eval.run_opslens as R
    original = risk.load
    if job.get("risk_variant") == "logistic_regression":
        model = pickle.loads(LOGREG_FILE.read_bytes())
        R.risk.load = lambda folder: model
    try:
        return R.run_one(job)
    finally:
        R.risk.load = original


def dispatch_compare() -> dict:
    from concurrent.futures import ProcessPoolExecutor

    from opslens.impact import mean_std, paired_ci

    variants = {"lightgbm": {}, "logistic_regression": {"risk_variant": "logistic_regression"},
                "no_risk_model": {"settings": {"use_risk": False, "label": "no_risk"}}}
    jobs = [{"policy": "opslens", "seed": s, "first_day": FIRST, "last_day": LAST, "staffing": True,
             "tag": name, **extra} for name, extra in variants.items() for s in SEEDS]
    with ProcessPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run_variant, jobs))
    by = {name: sorted([r for r in results if r["job"]["tag"] == name], key=lambda r: r["job"]["seed"]) for name in variants}
    kpi = lambda rs, k: [r["kpis"][k] for r in rs]
    base = kpi(by["lightgbm"], "turnaround.breach_pct")
    out = {"seeds": SEEDS, "days": [FIRST, LAST], "variants": {}}
    for name in variants:
        b = kpi(by[name], "turnaround.breach_pct")
        ci = paired_ci(b, base)
        out["variants"][name] = {
            "breach_pct": dict(zip(("mean", "std"), mean_std(b))), "per_seed": b,
            "late_minutes_per_100": float(np.mean(kpi(by[name], "quality.late_minutes_per_100"))),
            "p90_resolution_min": float(np.mean(kpi(by[name], "turnaround.p90_resolution_min"))),
            "minus_lightgbm": {"mean": ci["mean_diff"], "ci95": [ci["ci_low"], ci["ci_high"]]}}
        print(f"  dispatch {name:20s} breach {np.mean(b):.3f}%  ({ci['mean_diff']:+.3f} [{ci['ci_low']:+.3f}, "
              f"{ci['ci_high']:+.3f}] vs LightGBM)", flush=True)
    return out


def alerts_compare() -> dict:
    from eval.run_forecast import TEAMS, event_uplift, predict_normal_day, team_workload
    from opslens import forecast as F
    from opslens import staffing as S
    from opslens.classify import CATEGORIES, TEAM_OF
    from opslens.config import load_config
    from opslens.ingest import load_history

    cal = load_config("calendar")
    sp = cal["splits"]
    first_weekday = pd.Timestamp(cal["start_date"]).weekday()
    events = {e["day"] for e in cal["known_events"]}
    h = load_history()
    preds = pd.read_csv(ROOT / "data" / "generated" / "predictions.csv", usecols=["ticket_id", "pred_final"])
    h = h.merge(preds, on="ticket_id")
    aht = h[h["day"] <= sp["validation_last_day"]].groupby("final_category")["handled_min"].mean().to_dict()
    rows = F.add_features(F.hourly_counts(h, "pred_final", cal["days"], CATEGORIES), first_weekday, events)
    train = rows[(rows["day"] >= 8) & (rows["day"] <= sp["train_last_day"])]
    valid = rows[(rows["day"] > sp["train_last_day"]) & (rows["day"] <= sp["validation_last_day"])]
    model = F.train(train[~train["day"].isin(events)], valid[~valid["day"].isin(events)])
    uplift = event_uplift(model, train, events)
    forecasters = {
        "opslens": lambda part: np.where(part["day"].isin(events), predict_normal_day(model, part) * uplift,
                                         predict_normal_day(model, part)),
        "naive_last_week": lambda part: part["lag_168"].fillna(0).to_numpy(float),
    }
    q_team = {}
    for name, fc in forecasters.items():
        wf, wy = team_workload(valid, fc(valid), aht), team_workload(valid, valid["count"].to_numpy(), aht)
        q_team[name] = F.conformal_q(wy["arrivals"].to_numpy(), wf["arrivals"].to_numpy(), 0.8)

    test_h = h[h["day"] > sp["validation_last_day"]].copy()
    test_h["team"] = test_h["final_category"].map(TEAM_OF)
    test_h["hour_index"] = (test_h["minute_of_run"] // 60).astype(int)
    by_hour = test_h.groupby(["team", "hour_index"])["breached"].agg(["size", "mean"])
    team_rate = test_h.groupby("team")["breached"].mean()
    outcome_true = {(t, hi) for (t, hi), r in by_hour.iterrows() if r["size"] >= 5 and r["mean"] >= 2 * team_rate[t]}

    shifts = S.shifts_from_agents(pd.read_csv(ROOT / "data" / "generated" / "agents.csv"))
    rules = ("erlang_gap", "rho_085")
    alerts = {(rule, name): [] for rule in rules for name in forecasters}
    workload_true = {rule: set() for rule in rules}
    for first_day in (sp["validation_last_day"] + 1, sp["validation_last_day"] + 8):
        part = rows[rows["day"].isin(range(first_day, first_day + 7))]
        cov = S.coverage(shifts, TEAMS, first_day, 7, first_weekday)
        offset = (first_day - 1) * 24
        plan_hour = offset

        def flags(arrivals_workload: pd.DataFrame, rule: str) -> pd.DataFrame:
            wl = arrivals_workload.copy()
            wl["hour_index"] = wl["hour_index"] - offset
            if rule == "erlang_gap":
                return (S.needed_per_hour(wl).reindex_like(cov).fillna(0) - cov) >= 1.5
            work = wl.pivot(index="hour_index", columns="team", values="agent_hours").reindex_like(cov).fillna(0)
            return work > cov * S.MAX_RHO

        def add(flagged: pd.DataFrame, sink, with_lead: bool) -> None:
            for team in TEAMS:
                for hr, on in flagged[team].items():
                    if on and hr % 24 in S.DAY_HOURS:
                        if with_lead:
                            sink.append((team, hr + offset, hr + offset - plan_hour))
                        else:
                            sink.add((team, hr + offset))

        actual_wl = team_workload(part, part["count"].to_numpy(), aht)
        for rule in rules:
            add(flags(actual_wl, rule), workload_true[rule], False)
        for name, fc in forecasters.items():
            wl = team_workload(part, fc(part), aht)
            wl["arrivals"] = F.interval(wl["arrivals"].to_numpy(), q_team[name])[1]
            wl["agent_hours"] = wl["arrivals"] * wl["aht_min"] / 60.0
            for rule in rules:
                add(flags(wl, rule), alerts[(rule, name)], True)

    n_day_hours = 14 * len(list(S.DAY_HOURS)) * len(TEAMS)
    day_truth_outcome = {(t, hi) for (t, hi) in outcome_true if hi % 24 in S.DAY_HOURS}
    out = {"team_hours_scored": n_day_hours, "truth_outcome_hours": len(day_truth_outcome),
           "q80_team": {k: round(v, 3) for k, v in q_team.items()}, "rules": {}}
    for rule in rules:
        block = {"truth_workload_hours": len(workload_true[rule]), "predictors": {}}
        for name in forecasters:
            items = alerts[(rule, name)]
            predicted = {(t, hi) for t, hi, _ in items}
            lead = {(t, hi): ld for t, hi, ld in items}
            res = {"alert_hours": len(predicted)}
            for truth_name, truth in (("workload", workload_true[rule]), ("outcome", day_truth_outcome)):
                hits = predicted & truth
                p = len(hits) / len(predicted) if predicted else 0.0
                r = len(hits) / len(truth) if truth else 0.0
                blocks = alert_blocks(sorted(predicted))
                block_hits = sum(any(x in truth for x in b) for b in blocks)
                res[truth_name] = {"precision": round(p, 3), "recall": round(r, 3),
                                   "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0, "blocks": len(blocks),
                                   "block_precision": round(block_hits / len(blocks), 3) if blocks else None,
                                   "median_lead_hours_of_hits": float(np.median([lead[k] for k in hits])) if hits else None}
            block["predictors"][name] = res
            print(f"  alerts {rule:10s} {name:16s} {len(predicted):3d} hours | workload P {res['workload']['precision']:.2f} "
                  f"R {res['workload']['recall']:.2f} | outcome P {res['outcome']['precision']:.2f} "
                  f"R {res['outcome']['recall']:.2f} | lead {res['workload']['median_lead_hours_of_hits']}", flush=True)
        out["rules"][rule] = block
    return out


def alert_blocks(hours: list[tuple[str, int]]) -> list[list[tuple[str, int]]]:
    blocks, run = [], []
    for item in hours:
        if run and (item[0] != run[-1][0] or item[1] != run[-1][1] + 1 or item[1] % 24 == 0):
            if len(run) >= 2:
                blocks.append(run)
            run = []
        run.append(item)
    if len(run) >= 2:
        blocks.append(run)
    return blocks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-dispatch", action="store_true")
    parser.add_argument("--alerts-only", action="store_true", help="recompute (b) only; keep the rest of w7.json")
    args = parser.parse_args()
    started = time.perf_counter()
    import eval.run_w7 as me
    path = ROOT / "eval" / "parts" / "w7.json"
    if args.alerts_only:
        out = json.loads(path.read_text(encoding="utf-8"))
        out["alerts"] = me.alerts_compare()
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"updated the alerts in {path.relative_to(ROOT)}")
        return 0
    print("(a) risk models on the test snapshots", flush=True)
    offline, logreg = me.offline_compare()
    me.LOGREG_FILE.write_bytes(pickle.dumps(logreg))
    print("(b) bottleneck alerts", flush=True)
    alerts = me.alerts_compare()
    dispatch = None
    if not args.skip_dispatch:
        print("(a) inside the dispatcher (test days, 5 seeds)", flush=True)
        dispatch = me.dispatch_compare()
    out = {"risk_offline": offline, "risk_in_dispatch": dispatch, "alerts": alerts,
           "seconds": round(time.perf_counter() - started, 1)}
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({out['seconds']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
