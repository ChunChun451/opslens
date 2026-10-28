from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from opslens.features import CATEGORICAL, FEATURES

PARAMS = {
    "objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 50,
    "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
    "verbose": -1, "seed": 7, "deterministic": True, "num_threads": 4,
}


@dataclass
class RiskModel:
    booster: lgb.Booster
    calibrator: IsotonicRegression
    categories: dict[str, list[str]]

    def frame(self, feats: pd.DataFrame) -> pd.DataFrame:
        X = feats[FEATURES].copy()
        for col in CATEGORICAL:
            X[col] = pd.Categorical(X[col].astype(str), categories=self.categories[col])
        return X

    def matrix(self, feats: pd.DataFrame) -> np.ndarray:
        columns = []
        for col in FEATURES:
            if col in CATEGORICAL:
                codes = {v: float(k) for k, v in enumerate(self.categories[col])}
                columns.append([codes.get(str(v), np.nan) for v in feats[col]])
            else:
                columns.append(feats[col].to_numpy(dtype=float))
        return np.column_stack(columns)

    def raw(self, feats: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(self.matrix(feats), num_threads=1)

    def predict(self, feats: pd.DataFrame) -> np.ndarray:
        return self.calibrator.predict(self.raw(feats))

    def predict_matrix(self, X: np.ndarray) -> np.ndarray:
        raw = self.booster.predict(X, num_threads=1)
        return np.interp(raw, self.calibrator.X_thresholds_, self.calibrator.y_thresholds_)


def train(train_feats: pd.DataFrame, valid_feats: pd.DataFrame, rounds: int = 2000) -> RiskModel:
    categories = {c: sorted(train_feats[c].astype(str).unique()) for c in CATEGORICAL}
    model = RiskModel(booster=None, calibrator=None, categories=categories)
    dtrain = lgb.Dataset(model.frame(train_feats), train_feats["breached"], categorical_feature=CATEGORICAL)
    dvalid = lgb.Dataset(model.frame(valid_feats), valid_feats["breached"], categorical_feature=CATEGORICAL,
                         reference=dtrain)
    model.booster = lgb.train(PARAMS, dtrain, num_boost_round=rounds, valid_sets=[dvalid],
                              callbacks=[lgb.early_stopping(50, verbose=False)])
    model.calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    model.calibrator.fit(model.raw(valid_feats), valid_feats["breached"])
    return model


def evaluate(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict:
    order = np.argsort(-p)
    top = order[: max(1, len(p) // 10)]
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    which = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    calibration = [
        {"predicted": float(p[which == b].mean()), "observed": float(y[which == b].mean()), "n": int((which == b).sum())}
        for b in range(bins) if (which == b).any()
    ]
    return {
        "auc": float(roc_auc_score(y, p)), "pr_auc": float(average_precision_score(y, p)),
        "top10_precision": float(y[top].mean()), "brier": float(brier_score_loss(y, p)),
        "base_rate": float(y.mean()), "n": int(len(y)), "calibration": calibration,
    }


NAMES = {"hi": "Hindi", "en": "English", "other": "regional-language"}


def reason_text(feature: str, row: pd.Series) -> str:
    v = row[feature]
    team = row.get("team", "?")
    templates = {
        "ahead_in_team_queue": lambda: f"{v:.0f} tickets ahead in Team {team}'s queue",
        "queue_team": lambda: f"{v:.0f} Team {team} tickets waiting",
        "queue_team_language": lambda: f"{v:.0f} Team {team} tickets waiting in this language",
        "queue_total": lambda: f"{v:.0f} tickets waiting on the floor",
        "capable_on_shift": lambda: (("no agent on shift can serve " if round(v) == 0 else
                                      "1 agent on shift can serve " if round(v) == 1 else
                                      f"only {v:.0f} agents on shift can serve ") +
                                     f"{NAMES.get(row['language'], row['language'])} "
                                     f"{str(row['category_pred']).replace('_', ' ')}"),
        "on_shift_team": lambda: f"{v:.0f} Team {team} agents on shift",
        "in_progress_team": lambda: f"{v:.0f} Team {team} tickets already in work",
        "arrivals_team_last_hour": lambda: f"{v:.0f} Team {team} tickets arrived in the last hour",
        "time_left_min": lambda: f"{v:.0f} min left of {row['sla_min']:.0f} min SLA",
        "age_min": lambda: f"waiting {v:.0f} min",
        "sla_min": lambda: f"SLA {v:.0f} min",
        "language": lambda: f"{NAMES.get(v, v)} customer",
        "category_pred": lambda: f"{str(v).replace('_', ' ')} ticket",
        "priority": lambda: f"priority {v}",
        "channel": lambda: f"{v} ticket",
        "tier": lambda: f"{v} customer",
        "hour_band": lambda: f"{v} time",
        "hour": lambda: f"{float(v):.0f}:00",
        "is_weekend": lambda: "weekend" if v else "weekday",
        "order_value_inr": lambda: f"order value Rs {float(v):.0f}",
    }
    make = templates.get(feature)
    return make() if make else f"{feature} = {v}"


def top_reasons(model: RiskModel, feats: pd.DataFrame, k: int = 3) -> list[list[dict]]:
    X = model.frame(feats)
    contrib = model.booster.predict(X, pred_contrib=True)[:, :-1]
    out = []
    for i in range(len(feats)):
        positive = np.clip(contrib[i], 0, None)
        total = positive.sum()
        reasons = []
        for j in np.argsort(-contrib[i])[:k]:
            if contrib[i, j] <= 0 or total <= 0:
                continue
            share = float(positive[j] / total)
            reasons.append({"feature": FEATURES[j], "contribution": round(share, 3),
                            "text": f"{reason_text(FEATURES[j], feats.iloc[i])} — {share:.0%} of the push"})
        out.append(reasons)
    return out


def risk_if_assigned_now(model: RiskModel, feats: pd.DataFrame) -> np.ndarray:
    changed = feats.copy()
    changed["ahead_in_team_queue"] = 0
    changed["capable_on_shift"] = changed["capable_on_shift"].clip(lower=1)
    return model.predict(changed)


def save(model: RiskModel, folder) -> None:
    import json
    from pathlib import Path

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    model.booster.save_model(str(folder / "risk_booster.txt"))
    calib = {"x": model.calibrator.X_thresholds_.tolist(), "y": model.calibrator.y_thresholds_.tolist(),
             "categories": model.categories}
    (folder / "risk_calibration.json").write_text(json.dumps(calib), encoding="utf-8")


def load(folder) -> RiskModel:
    import json
    from pathlib import Path

    folder = Path(folder)
    booster = lgb.Booster(model_file=str(folder / "risk_booster.txt"))
    calib = json.loads((folder / "risk_calibration.json").read_text(encoding="utf-8"))
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(calib["x"], calib["y"])
    return RiskModel(booster=booster, calibrator=iso, categories=calib["categories"])
