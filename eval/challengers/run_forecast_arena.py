"""Challenger arena, part 1: Chronos-2 (Amazon, 2025, zero-shot) vs our LightGBM forecast.

Run (eval-only venv, needs torch + chronos-forecasting):
    .venv-challengers/Scripts/python.exe eval/challengers/run_forecast_arena.py

PRE-REGISTERED (written before the first run, CLAUDE.md 7.11):
- Same data: hourly ticket counts per predicted category (pred_final), the series our forecast uses.
- Same test hours: days 43-56. Forecast origins at 00:00 of each day; Chronos sees every hour
  before the origin (days 1 .. d-1) and the known-event flag as a future covariate.
- Main metric: hourly per-category WAPE at lead 1-24 h (each test hour scored once).
  Also reported: lead 25-48 h, 80% interval coverage, team-free totals, without the day-47 surge.
- LightGBM is exactly eval/run_forecast.py (train days 8-35, early stop 36-42, sale uplift). Its
  features are lags of 168 h and more, so its forecast for an hour is the same from any origin
  within 7 days; it is not re-trained per origin.
- Rule: ship Chronos-2 only if its main WAPE is more than 2% lower (relative: < 0.98 x LightGBM)
  AND one 48-hour forecast of all categories takes <= 10 s on this laptop CPU (the forecast is
  refreshed every 15 minutes; 10 s leaves room for the rest of the refresh).
Writes eval/parts/challenger_forecast.json.

Example: if LightGBM scores 0.305 and Chronos-2 0.296, Chronos is 2.95% better -> it passes the
accuracy half of the rule, and then must also pass the 10 s latency check.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from opslens import forecast as F  # noqa: E402
from opslens.classify import CATEGORIES  # noqa: E402
from opslens.config import load_config  # noqa: E402
from opslens.ingest import load_history  # noqa: E402
from run_forecast import event_uplift, predict_normal_day  # noqa: E402

MARGIN = 0.02
LATENCY_BUDGET_S = 10.0
HORIZON = 48


def lightgbm_forecast(rows: pd.DataFrame, sp: dict, events: set[int]) -> pd.Series:
    """Our production forecast for every test row, exactly as eval/run_forecast.py makes it."""
    train = rows[(rows["day"] >= 8) & (rows["day"] <= sp["train_last_day"])]
    valid = rows[(rows["day"] > sp["train_last_day"]) & (rows["day"] <= sp["validation_last_day"])]
    model = F.train(train[~train["day"].isin(events)], valid[~valid["day"].isin(events)])
    uplift = event_uplift(model, train, events)
    test = rows[rows["day"] > sp["validation_last_day"]]
    base = predict_normal_day(model, test)
    return pd.Series(np.where(test["day"].isin(events), base * uplift, base), index=test.index)


def chronos_frames(rows: pd.DataFrame, origin_days: list[int], start: pd.Timestamp,
                   events: set[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One series per (category, origin): context = all hours before the origin."""
    contexts, futures = [], []
    for day in origin_days:
        origin_h = (day - 1) * 24
        for cat in CATEGORIES:
            item = f"{cat}|{day}"
            past = rows[(rows["category"].astype(str) == cat) & (rows["hour_index"] < origin_h)]
            contexts.append(pd.DataFrame({
                "item_id": item, "timestamp": start + pd.to_timedelta(past["hour_index"], unit="h"),
                "target": past["count"].astype(float).to_numpy(), "is_event": past["is_event"].to_numpy(),
            }))
            hours = np.arange(origin_h, origin_h + HORIZON)
            futures.append(pd.DataFrame({
                "item_id": item, "timestamp": start + pd.to_timedelta(hours, unit="h"),
                "is_event": np.isin(hours // 24 + 1, list(events)).astype(int),
            }))
    return pd.concat(contexts, ignore_index=True), pd.concat(futures, ignore_index=True)


def main() -> int:
    from chronos import Chronos2Pipeline  # eval-only dependency

    cal = load_config("calendar")
    sp = cal["splits"]
    start = pd.Timestamp(cal["start_date"])
    events = {e["day"] for e in cal["known_events"]}
    h = load_history()
    preds = pd.read_csv(ROOT / "data" / "generated" / "predictions.csv", usecols=["ticket_id", "pred_final"])
    h = h.merge(preds, on="ticket_id")
    rows = F.add_features(F.hourly_counts(h, "pred_final", cal["days"], CATEGORIES), start.weekday(), events)
    test = rows[rows["day"] > sp["validation_last_day"]].copy()
    test["lgbm"] = lightgbm_forecast(rows, sp, events)

    pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cpu")
    first_test = sp["validation_last_day"] + 1
    origins = list(range(first_test - 1, sp["test_last_day"] + 1))  # day 42 origin covers lead 25-48 of day 43
    ctx, fut = chronos_frames(rows, origins, start, events)
    t0 = time.perf_counter()
    out = pipeline.predict_df(ctx, future_df=fut, id_column="item_id", timestamp_column="timestamp", target="target",
                              prediction_length=HORIZON, quantile_levels=[0.1, 0.5, 0.9])
    batch_s = time.perf_counter() - t0
    # Latency of one real refresh: the 8 category series of one origin, 48 hours ahead.
    one = ctx["item_id"].str.endswith(f"|{sp['test_last_day']}")
    t0 = time.perf_counter()
    pipeline.predict_df(ctx[one], future_df=fut[fut["item_id"].isin(ctx.loc[one, "item_id"].unique())],
                        id_column="item_id", timestamp_column="timestamp", target="target",
                        prediction_length=HORIZON, quantile_levels=[0.1, 0.5, 0.9])
    one_refresh_s = time.perf_counter() - t0

    out[["category", "origin"]] = out["item_id"].str.split("|", expand=True)
    out["origin"] = out["origin"].astype(int)
    out["hour_index"] = ((out["timestamp"] - start) / pd.Timedelta(hours=1)).round().astype(int)
    out["lead_day"] = out["hour_index"] // 24 + 1 - out["origin"]  # 0 = lead 1-24 h, 1 = lead 25-48 h
    key = ["category", "hour_index"]
    test["category"] = test["category"].astype(str)
    q80 = F.conformal_q(*valid_arrays(rows, sp, events), 0.8)
    scores = {}
    for lead, name in ((0, "lead_1_24h"), (1, "lead_25_48h")):
        part = out[out["lead_day"] == lead][key + ["predictions", "0.1", "0.9"]]
        merged = test.merge(part, on=key, how="inner")
        y = merged["count"].to_numpy()
        no_surge = ~((merged["day"] == 47) & (merged["category"] == "app_bug")).to_numpy()
        lo80, hi80 = F.interval(merged["lgbm"].to_numpy(), q80)
        scores[name] = {
            "hours_scored": int(len(merged)),
            "wape_chronos2": F.wape(y, np.clip(merged["predictions"].to_numpy(), 0, None)),
            "wape_lightgbm": F.wape(y, merged["lgbm"].to_numpy()),
            "wape_seasonal_naive": F.wape(y, merged["lag_168"].to_numpy()),
            "wape_chronos2_without_surge": F.wape(y[no_surge], np.clip(merged["predictions"].to_numpy(), 0, None)[no_surge]),
            "wape_lightgbm_without_surge": F.wape(y[no_surge], merged["lgbm"].to_numpy()[no_surge]),
            "coverage80_chronos2": F.coverage(y, merged["0.1"].to_numpy(), merged["0.9"].to_numpy()),
            "coverage80_lightgbm_conformal": F.coverage(y, lo80, hi80),
        }
    main_c, main_l = scores["lead_1_24h"]["wape_chronos2"], scores["lead_1_24h"]["wape_lightgbm"]
    accuracy_ok = main_c < (1 - MARGIN) * main_l
    latency_ok = one_refresh_s <= LATENCY_BUDGET_S
    result = {
        "challenger": "Chronos-2 (amazon/chronos-2, zero-shot, CPU)", "incumbent": "LightGBM Poisson (opslens/forecast.py)",
        "main_metric": "hourly per-category WAPE, lead 1-24 h, test days 43-56", "rule_margin": MARGIN,
        "latency_budget_s": LATENCY_BUDGET_S, "scores": scores, "one_refresh_s": one_refresh_s,
        "all_origins_batch_s": batch_s, "relative_gain_pct": 100 * (main_l - main_c) / main_l,
        "accuracy_ok": bool(accuracy_ok), "latency_ok": bool(latency_ok),
        "verdict": "ship challenger" if accuracy_ok and latency_ok else "keep LightGBM",
    }
    for name, s in scores.items():
        print(name, {k: round(v, 3) for k, v in s.items()})
    print(f"one 48h refresh {one_refresh_s:.1f}s, all origins {batch_s:.0f}s; gain {result['relative_gain_pct']:.1f}% "
          f"-> {result['verdict']}")
    (ROOT / "eval" / "parts" / "challenger_forecast.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


def valid_arrays(rows: pd.DataFrame, sp: dict, events: set[int]) -> tuple[np.ndarray, np.ndarray]:
    """Validation actuals and LightGBM forecasts, for the conformal interval (as in run_forecast.py)."""
    train = rows[(rows["day"] >= 8) & (rows["day"] <= sp["train_last_day"])]
    valid = rows[(rows["day"] > sp["train_last_day"]) & (rows["day"] <= sp["validation_last_day"])]
    model = F.train(train[~train["day"].isin(events)], valid[~valid["day"].isin(events)])
    uplift = event_uplift(model, train, events)
    base = predict_normal_day(model, valid)
    return valid["count"].to_numpy(), np.where(valid["day"].isin(events), base * uplift, base)


if __name__ == "__main__":
    raise SystemExit(main())
