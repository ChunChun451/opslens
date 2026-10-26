from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens import forecast as F
from opslens import staffing as S
from opslens.classify import CATEGORIES, TEAM_OF
from opslens.config import load_config
from opslens.ingest import load_history

TEAMS = ["A", "B", "C", "D"]


def predict_normal_day(model, rows: pd.DataFrame) -> np.ndarray:
    return model.predict(rows[F.FEATURES].assign(is_event=0))


def event_uplift(model, rows: pd.DataFrame, event_days: set[int]) -> float:
    past = rows[rows["day"].isin(event_days)]
    if past.empty:
        return 1.0
    return float(past["count"].sum() / predict_normal_day(model, past).sum())


def noise_floor_wape(forecast: np.ndarray, draws: int = 200, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    sims = rng.poisson(forecast, size=(draws, len(forecast)))
    return float(np.mean([np.abs(s - forecast).sum() / max(s.sum(), 1) for s in sims]))


def team_workload(rows: pd.DataFrame, values: np.ndarray, aht: dict[str, float]) -> pd.DataFrame:
    df = rows[["category", "hour_index", "day"]].assign(n=values)
    df["team"] = df["category"].astype(str).map(TEAM_OF)
    df["minutes"] = df["n"] * df["category"].astype(str).map(aht)
    out = df.groupby(["team", "hour_index", "day"], observed=True).agg(arrivals=("n", "sum"), minutes=("minutes", "sum")).reset_index()
    out["aht_min"] = (out["minutes"] / out["arrivals"].where(out["arrivals"] > 0)).fillna(np.mean(list(aht.values())))
    out["agent_hours"] = out["minutes"] / 60.0
    return out


def bottleneck_blocks(gap: pd.DataFrame, start_ts: pd.Timestamp, first_hour: int, min_gap: float = 1.5) -> list[dict]:
    blocks = []
    for team in gap.columns:
        series = gap[team]
        run = []
        for h, value in series.items():
            if run and h % 24 == 0:
                if len(run) >= 2:
                    blocks.append(make_block(team, run, start_ts, first_hour))
                run = []
            if value >= min_gap:
                run.append((h, value))
                continue
            if len(run) >= 2:
                blocks.append(make_block(team, run, start_ts, first_hour))
            run = []
        if len(run) >= 2:
            blocks.append(make_block(team, run, start_ts, first_hour))
    return sorted(blocks, key=lambda b: -b["agent_hours_short"])


def make_block(team: str, run: list, start_ts: pd.Timestamp, first_hour: int) -> dict:
    t0 = start_ts + pd.Timedelta(hours=run[0][0] - first_hour)
    t1 = start_ts + pd.Timedelta(hours=run[-1][0] - first_hour + 1)
    short = sum(v for _, v in run)
    peak = max(v for _, v in run)
    return {"team": team, "start": t0.isoformat(timespec="minutes"), "end": t1.isoformat(timespec="minutes"),
            "peak_gap_agents": round(float(peak), 1), "agent_hours_short": round(float(short), 1),
            "text": f"Team {team} short by up to {peak:.1f} agents, {t0:%a %d %b %H:%M}-{t1:%H:%M}"}


def main() -> int:
    started = time.perf_counter()
    cal = load_config("calendar")
    sp = cal["splits"]
    first_weekday = pd.Timestamp(cal["start_date"]).weekday()
    start_ts = pd.Timestamp(cal["start_date"])
    events = {e["day"] for e in cal["known_events"]}
    h = load_history()
    preds = pd.read_csv(ROOT / "data" / "generated" / "predictions.csv", usecols=["ticket_id", "pred_final"])
    h = h.merge(preds, on="ticket_id")
    known = h[h["day"] <= sp["validation_last_day"]]
    aht = known.groupby("final_category")["handled_min"].mean().to_dict()

    rows = F.add_features(F.hourly_counts(h, "pred_final", cal["days"], CATEGORIES), first_weekday, events)
    train = rows[(rows["day"] >= 8) & (rows["day"] <= sp["train_last_day"])]
    valid = rows[(rows["day"] > sp["train_last_day"]) & (rows["day"] <= sp["validation_last_day"])]
    test = rows[rows["day"] > sp["validation_last_day"]].reset_index(drop=True)
    model = F.train(train[~train["day"].isin(events)], valid[~valid["day"].isin(events)])
    uplift = event_uplift(model, train, events)

    def forecast(part: pd.DataFrame) -> np.ndarray:
        base = predict_normal_day(model, part)
        return np.where(part["day"].isin(events), base * uplift, base)

    q80 = F.conformal_q(valid["count"].to_numpy(), forecast(valid), 0.8)
    wl_valid_f = team_workload(valid, forecast(valid), aht)
    wl_valid_y = team_workload(valid, valid["count"].to_numpy(), aht)
    q80_team = F.conformal_q(wl_valid_y["arrivals"].to_numpy(), wl_valid_f["arrivals"].to_numpy(), 0.8)
    q90 = F.conformal_q(valid["count"].to_numpy(), forecast(valid), 0.9)
    f_test = forecast(test)
    y = test["count"].to_numpy()
    naive = test["lag_168"].to_numpy()
    lo80, hi80 = F.interval(f_test, q80)
    lo90, hi90 = F.interval(f_test, q90)
    wl_f = team_workload(test, f_test, aht)
    wl_y = team_workload(test, y, aht)
    wl_n = team_workload(test, naive, aht)
    surge = ((test["day"] == 47) & (test["category"].astype(str) == "app_bug")).to_numpy()
    metrics = {
        "wape_model": F.wape(y, f_test), "wape_naive": F.wape(y, naive),
        "wape_noise_floor": noise_floor_wape(f_test),
        "wape_model_without_unseen_surge": F.wape(y[~surge], f_test[~surge]),
        "wape_team_hour_workload_model": F.wape(wl_y["minutes"].to_numpy(), wl_f["minutes"].to_numpy()),
        "wape_team_hour_workload_naive": F.wape(wl_y["minutes"].to_numpy(), wl_n["minutes"].to_numpy()),
        "coverage_80": F.coverage(y, lo80, hi80), "coverage_90": F.coverage(y, lo90, hi90),
        "q80": q80, "q90": q90, "q80_team": q80_team, "event_uplift": uplift,
        "best_iteration": int(model.best_iteration),
    }
    sale = test["day"] == 50
    metrics["sale_day_error_pct"] = float(100 * (f_test[sale].sum() - y[sale].sum()) / y[sale].sum())
    for k, v in metrics.items():
        print(f"{k:36s} {v:.3f}")

    agents = pd.read_csv(ROOT / "data" / "generated" / "agents.csv")
    shifts = S.shifts_from_agents(agents)
    plans, all_blocks = [], []
    for first_day in (sp["validation_last_day"] + 1, sp["validation_last_day"] + 8):
        days = list(range(first_day, first_day + 7))
        part = test[test["day"].isin(days)]
        wl = team_workload(part, forecast(part), aht)
        wl["arrivals"] = F.interval(wl["arrivals"].to_numpy(), q80_team)[1]
        wl["hour_index"] = wl["hour_index"] - (first_day - 1) * 24
        need = S.needed_per_hour(wl)
        cov = S.coverage(shifts, TEAMS, first_day, 7, first_weekday)
        before = S.shortage(cov, need)
        load = S.load_per_hour(wl)
        new_shifts, moves = S.plan_moves(shifts, need, first_day, 7, first_weekday, load=load)
        after = S.shortage(S.coverage(new_shifts, TEAMS, first_day, 7, first_weekday), need)
        gap = need.reindex_like(cov).fillna(0) - cov
        blocks = bottleneck_blocks(gap, start_ts + pd.Timedelta(days=first_day - 1), 0)
        all_blocks += blocks
        plans.append({"first_day": first_day, "last_day": first_day + 6, "shortage_before": round(before, 1),
                      "shortage_after": round(after, 1), "moves": moves,
                      "shifts": [{"agent_id": s.agent_id, "start_hour": s.start_hour,
                                  "days_off": sorted(s.days_off)} for s in new_shifts]})
        print(f"plan days {first_day}-{first_day + 6}: shortage {before:.1f} -> {after:.1f} agent-hours, "
              f"{len(moves)} moves: " + "; ".join(f"{m['agent_id']} {m['change']}" for m in moves))
    for b in sorted(all_blocks, key=lambda b: -b["agent_hours_short"])[:5]:
        print("  bottleneck:", b["text"], f"({b['agent_hours_short']} agent-hours)")

    view = test[test["day"].isin([55, 56])]
    fv = forecast(view)
    lo, hi = F.interval(fv, q80)
    parts = {name: team_workload(view, v, aht) for name, v in (("f", fv), ("lo", lo), ("hi", hi), ("y", view["count"].to_numpy()))}
    cov = S.coverage(shifts, TEAMS, 55, 2, first_weekday)
    horizon = []
    for i, r in parts["f"].iterrows():
        hour = int(r["hour_index"] - 54 * 24)
        horizon.append({
            "time": (start_ts + pd.Timedelta(hours=int(r["hour_index"]))).isoformat(timespec="minutes"),
            "team": r["team"], "demand_hours": round(float(r["agent_hours"]), 2),
            "lo80": round(float(parts["lo"].loc[i, "agent_hours"]), 2), "hi80": round(float(parts["hi"].loc[i, "agent_hours"]), 2),
            "capacity_hours": round(float(cov.loc[hour, r["team"]]) * S.MAX_RHO, 2),
            "actual_hours": round(float(parts["y"].loc[i, "agent_hours"]), 2),
        })

    out = ROOT / "eval" / "parts"
    out.mkdir(parents=True, exist_ok=True)
    (out / "forecast.json").write_text(json.dumps({"metrics": metrics, "horizon": horizon, "bottlenecks": all_blocks,
                                                   "plans": [{k: v for k, v in p.items() if k != "shifts"} for p in plans],
                                                   "aht_min": aht}, indent=1), encoding="utf-8")
    (ROOT / "data" / "generated" / "staffing_plan.json").write_text(json.dumps(plans, indent=1), encoding="utf-8")
    print(f"wrote eval/parts/forecast.json and data/generated/staffing_plan.json ({time.perf_counter() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
