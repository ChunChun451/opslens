from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens import risk
from opslens.adapters.uci_incidents import load_uci, risk_features
from opslens.classify import TEAM_OF
from opslens.config import load_config
from opslens.features import snapshots_from_history
from opslens.ingest import load_history
from opslens.privacy import mask_pii

MODELS = ROOT / "data" / "generated" / "models"
PRIORITY_SCORE = {"P1": 3, "P2": 2, "P3": 1}


SNAPSHOT_EVERY_MIN = 10.0


def history_with_predictions() -> pd.DataFrame:
    h = load_history()
    preds = pd.read_csv(ROOT / "data" / "generated" / "predictions.csv", usecols=["ticket_id", "pred_final"])
    return h.merge(preds, on="ticket_id", how="left").rename(columns={"pred_final": "category_pred"})


def uci_check() -> dict:
    incidents, events = load_uci()
    feats = risk_features(incidents, events)
    cat_cols = ["priority_raw", "impact", "urgency", "category", "channel", "first_team", "team_now", "state_now"]
    num_cols = ["reassignments_now", "updates_now", "knowledge", "hour", "weekday", "open_in_team"]
    X = feats[cat_cols + num_cols].copy()
    for c in cat_cols:
        X[c] = X[c].astype("category")
    train, test = feats["split"] == "train", feats["split"] == "test"
    cut = feats.loc[train, "created_at"].quantile(0.8)
    fit, stop = train & (feats["created_at"] <= cut), train & (feats["created_at"] > cut)
    dfit = lgb.Dataset(X[fit], feats.loc[fit, "breached"], categorical_feature=cat_cols)
    dstop = lgb.Dataset(X[stop], feats.loc[stop, "breached"], categorical_feature=cat_cols, reference=dfit)
    booster = lgb.train(risk.PARAMS, dfit, 2000, valid_sets=[dstop], callbacks=[lgb.early_stopping(50, verbose=False)])
    p = booster.predict(X[test])
    y = feats.loc[test, "breached"].to_numpy()
    rule = roc_auc_score(y, -feats.loc[test, "priority_raw"].str[0].astype(float))
    out = risk.evaluate(y, p)
    print(f"UCI real data: {test.sum():,} test incidents, breach rate {y.mean():.3f}, "
          f"AUC {out['auc']:.3f} (priority rule {rule:.3f}), PR-AUC {out['pr_auc']:.3f}, top-10% precision {out['top10_precision']:.3f}")
    return {"auc": out["auc"], "pr_auc": out["pr_auc"], "top10_precision": out["top10_precision"],
            "n": int(test.sum()), "base_rate": out["base_rate"], "priority_rule_auc": float(rule)}


def demo_at_risk(model: risk.RiskModel, feats: pd.DataFrame, h: pd.DataFrame, t: float) -> list[dict]:
    snap = feats[feats["t"] == t].copy()
    snap["p"] = model.predict(snap)
    top = snap.sort_values("p", ascending=False).head(10)
    reasons = risk.top_reasons(model, top)
    after = risk.risk_if_assigned_now(model, top)
    info = h.set_index("ticket_id")
    out = []
    for (_, row), why, p_after in zip(top.iterrows(), reasons, after):
        ticket = info.loc[row["ticket_id"]]
        lang = {"hi": "Hindi", "other": "regional-language"}.get(row["language"], "")
        skill = str(row["category_pred"]).replace("_", " ")
        out.append({
            "ticket_id": row["ticket_id"], "created_at": str(ticket["created_at"])[:16],
            "category": row["category_pred"], "priority": row["priority"], "language": row["language"],
            "text": mask_pii(str(ticket["text"])).text, "probability": round(float(row["p"]), 3),
            "minutes_to_sla": round(float(row["time_left_min"]), 1), "reasons": why,
            "action": f"assign now to a free agent who handles {skill}" + (f" in {lang}" if lang else ""),
            "probability_after_action": round(float(p_after), 3),
        })
    return out


def main() -> int:
    started = time.perf_counter()
    calendar = load_config("calendar")
    splits = calendar["splits"]
    first_weekday = pd.Timestamp(calendar["start_date"]).weekday()
    agents = pd.read_csv(ROOT / "data" / "generated" / "agents.csv")
    h = history_with_predictions()

    def snaps(first: int, last: int) -> pd.DataFrame:
        return snapshots_from_history(h, agents, TEAM_OF, first, last, every_min=SNAPSHOT_EVERY_MIN,
                                      first_weekday=first_weekday)

    train_f = snaps(1, splits["train_last_day"])
    valid_f = snaps(splits["train_last_day"] + 1, splits["validation_last_day"])
    test_f = snaps(splits["validation_last_day"] + 1, splits["test_last_day"])
    print(f"snapshot rows: train {len(train_f):,}, validation {len(valid_f):,}, test {len(test_f):,} "
          f"({time.perf_counter() - started:.0f}s)")

    model = risk.train(train_f, valid_f)
    risk.save(model, MODELS)
    p = model.predict(test_f)
    y = test_f["breached"].to_numpy()
    all_rows = risk.evaluate(y, p)
    first = ~test_f.duplicated("ticket_id")
    at_arrival = risk.evaluate(y[first.to_numpy()], p[first.to_numpy()])
    rules = {
        "time_left_auc": float(roc_auc_score(y, -test_f["time_left_min"])),
        "priority_auc": float(roc_auc_score(y, test_f["priority"].map(PRIORITY_SCORE))),
    }
    print(f"test rows: AUC {all_rows['auc']:.3f} (time-left rule {rules['time_left_auc']:.3f}, priority rule "
          f"{rules['priority_auc']:.3f}), PR-AUC {all_rows['pr_auc']:.3f}, top-10% precision "
          f"{all_rows['top10_precision']:.3f}, Brier {all_rows['brier']:.4f}, base rate {all_rows['base_rate']:.3f}")
    print(f"at arrival: AUC {at_arrival['auc']:.3f}, PR-AUC {at_arrival['pr_auc']:.3f}, top-10% precision "
          f"{at_arrival['top10_precision']:.3f}, base rate {at_arrival['base_rate']:.3f}, n {at_arrival['n']:,}")
    importance = pd.Series(model.booster.feature_importance("gain"), index=model.booster.feature_name())
    print("top features by gain:", (importance / importance.sum()).sort_values(ascending=False).head(6).round(3).to_dict())

    sat_evening = test_f[(test_f["is_weekend"] == 1) & (test_f["hour"].between(19, 22))]
    t_demo = sat_evening.groupby("t").size().idxmax()
    at_risk = demo_at_risk(model, test_f, h, float(t_demo))
    for row in at_risk[:3]:
        print(f"  {row['ticket_id']} p={row['probability']} -> {row['probability_after_action']} | "
              + " | ".join(r["text"] for r in row["reasons"]))

    realdata = uci_check()
    part = {
        "test": all_rows, "at_arrival": at_arrival, "rules": rules, "demo_minute": float(t_demo),
        "at_risk": at_risk, "realdata": realdata, "best_iteration": int(model.booster.best_iteration),
        "feature_gain": (importance / importance.sum()).round(4).to_dict(),
    }
    out = ROOT / "eval" / "parts"
    out.mkdir(parents=True, exist_ok=True)
    (out / "risk.json").write_text(json.dumps(part, indent=1), encoding="utf-8")
    print(f"wrote eval/parts/risk.json and the model ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
