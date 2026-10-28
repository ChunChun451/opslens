from __future__ import annotations

import json
import math
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_opslens import GENERATED, published_rule
from opslens import risk
from opslens.classify import TEAM_OF
from opslens.config import load_config
from opslens.floor import earliest_start, merge, shift_intervals, unavoidable
from opslens.impact import paired_ci, summarize
from opslens.policies import (OpsLensPolicy, OpsLensSettings, baseline_d, expected_handle_minutes, handle_lognormal,
                              p_longer)
from opslens.simulate import simulate
from opslens.world import apply_staffing_plan, build_world, day_bounds, load_agents

OUT = ROOT / "eval" / "parts" / "food_1530"
FIRST, LAST = 36, 42
SEEDS = [1, 2, 3, 4, 5]
RESCUE_THRESHOLD = 10
HOPELESS = 0.95
CALIB_EVERY_MIN = 20
PRIO = {"P1": 0, "P2": 1, "P3": 2}
KINDS = {
    "opslens": {"policy": "opslens", "staffing": True, "settings": {}},
    "opslens_live": {"policy": "opslens", "staffing": True, "settings": {"use_live_risk": True}},
    "opslens_nostaff": {"policy": "opslens", "staffing": False, "settings": {}},
    "least_slack_rescue": {"policy": "least_slack_rescue", "staffing": False,
                           "params": {"threshold_min": RESCUE_THRESHOLD}},
    "baseline_d": {"policy": "baseline_d", "staffing": False},
}
CAUSES = ["unavoidable", "transfer", "reopen", "cross_skill_too_slow", "passed_over_lost_ticket",
          "passed_over_cross_job", "passed_over_lower_priority", "passed_over_same_priority_more_slack",
          "skill_gap", "busy_when_it_landed", "congestion_more_urgent_work", "other"]


def history_tables():
    history = pd.read_csv(GENERATED / "history.csv", usecols=["created_at", "final_category", "channel",
                                                             "handled_min", "reopens", "resolution_min"])
    start = load_config("calendar")["start_date"]
    return expected_handle_minutes(history, start, last_day=35), handle_lognormal(history, start, last_day=35)


class Logged:
    def __init__(self, inner, world, pred, handle, dist, kind):
        self.inner, self.world, self.pred, self.handle, self.dist, self.kind = inner, world, pred, handle, dist, kind
        self.name = inner.name
        self.rows: list[dict] = []
        self.calib: list[tuple] = []
        self.next_calib = -1e9
        self.agent_by_id = {a.agent_id: a for a in world.agents}
        self.ln16 = math.log(world.mismatch_factor)
        self.ln_re = math.log(world.reopen_handle_factor)

    def believed(self, t) -> str:
        return t.known_category or self.pred[t.idx]

    def exp_h(self, cat: str, channel: str, reopens: int) -> float:
        h = self.handle.get((cat, channel)) or self.handle.get(cat) or 6.0
        return h * (self.world.reopen_handle_factor if reopens else 1.0)

    def p_hop(self, cat: str, channel: str, reopens: int, cross: bool, left: float) -> float:
        mu, sigma = self.dist.get((cat, channel)) or self.dist.get(cat) or (math.log(6.0), 0.5)
        mu += (self.ln_re if reopens else 0.0) + (self.ln16 if cross else 0.0)
        return p_longer(mu, sigma, left)

    def decide(self, state, now):
        out = self.inner.decide(state, now)
        if self.kind.startswith("opslens") and now >= self.next_calib and state.waiting:
            self.next_calib = now + CALIB_EVERY_MIN
            self.sample_calibration(state, now)
        if not out:
            return out
        w = self.world
        assigned = {a.ticket_idx for a in out}
        wait_rows = []
        for t in state.waiting.values():
            if t.idx in assigned:
                continue
            cat = self.believed(t)
            eh = self.exp_h(cat, t.channel, t.reopens)
            wait_rows.append((t.idx, t.language, cat, t.sla_deadline_min - now - eh, t.priority))
        for a in out:
            t = state.waiting[a.ticket_idx]
            i = t.idx
            ag = self.agent_by_id[a.agent_id]
            cat = a.believed_category
            cross = bool(a.deliberate_cross_skill)
            eh = self.exp_h(cat, t.channel, t.reopens) * (w.mismatch_factor if cross else 1.0)
            left = t.sla_deadline_min - now
            slack = left - eh
            ph = self.p_hop(cat, t.channel, t.reopens, cross, left)
            ts = state.tickets[i]
            true_cat = w.true_category[i]
            if true_cat in ag.skills or cross:
                base = float(w.base_handle_min[i, min(ts.attempts, w.base_handle_min.shape[1] - 1)])
                if ts.reopens > 0:
                    base *= w.reopen_handle_factor
                dur = base * (w.mismatch_factor if true_cat not in ag.skills else 1.0)
                outcome = "resolve"
            else:
                dur, outcome = w.transfer_discovery_min, "transfer"
            lost = ph >= HOPELESS
            passed = [(k, p) for k, lang, c, s, p in wait_rows
                      if lang in ag.languages and c in ag.skills and s >= 0 and (lost or s < slack)]
            row = {"t": now, "idx": i, "agent": a.agent_id, "cross": cross, "believed": cat, "prio": t.priority,
                   "deadline": t.sla_deadline_min, "exp_h": eh, "slack": slack, "p_hopeless": ph, "dur": dur,
                   "outcome": outcome, "reopen_pass": ts.reopens, "passed": [k for k, _ in passed[:60]],
                   "passed_p1": sum(1 for _, p in passed if p == "P1"), "team": TEAM_OF.get(cat, "?"),
                   "agent_team": ag.team, "own": cat in ag.team_skills}
            if self.kind == "opslens_live":
                clock = self.inner._clock.get(i)
                row["clock_p_wait"] = clock[3] if clock else np.nan
                row["ctx_p_wait"] = self.inner.ctx_wait.get(i, np.nan)
                row["ctx_rescue"] = self.inner.ctx_rescue.get(i, np.nan)
            elif self.kind.startswith("opslens"):
                row["risk_wait"] = self.inner.risk_wait.get(i, np.nan)
                row["rescue"] = self.inner.rescue.get(i, np.nan)
                row["risk_age"] = now - self.inner.last_refresh
            self.rows.append(row)
        return out

    def sample_calibration(self, state, now):
        inner = self.inner
        for t in state.waiting.values():
            left = t.sla_deadline_min - now
            if left <= 0:
                continue
            cat = self.believed(t)
            p_now = self.p_hop(cat, t.channel, t.reopens, False, left)
            if self.kind == "opslens_live":
                clock = inner._clock.get(t.idx)
                self.calib.append((now, t.idx, t.priority, left, p_now, clock[3] if clock else np.nan,
                                   inner.ctx_wait.get(t.idx, np.nan), np.nan))
            else:
                self.calib.append((now, t.idx, t.priority, left, p_now, np.nan, np.nan,
                                   inner.risk_wait.get(t.idx, np.nan)))


def build(job: dict):
    tickets = pd.read_csv(GENERATED / "world_tickets.csv")
    preds = pd.read_csv(GENERATED / "predictions.csv", usecols=["ticket_id", "pred_final"])
    predicted = dict(zip(preds.ticket_id, preds.pred_final))
    agents = load_agents()
    if job.get("staffing"):
        agents = apply_staffing_plan(agents, json.loads((GENERATED / "staffing_plan.json").read_text(encoding="utf-8")))
    world = build_world(tickets, seed=job["seed"], agents=agents, gen_cfg=load_config("generator"))
    handle, dist = history_tables()
    if job["policy"] == "baseline_d":
        policy = baseline_d(world, predicted)
    elif job["policy"] == "least_slack_rescue":
        policy = published_rule(job, world, predicted)
    else:
        weights = {**load_config("optimizer"), **job.get("weights", {})}
        settings = OpsLensSettings(**job.get("settings", {}))
        policy = OpsLensPolicy(world, predicted, risk.load(GENERATED / "models"), weights, settings,
                               handle_dist=dist if settings.use_live_risk else None)
    pred = [predicted.get(tid) or sel for tid, sel in zip(world.ticket_ids, world.selected_category)]
    return world, Logged(policy, world, pred, handle, dist, job["kind"])


def run_diag(job: dict) -> dict:
    started = time.perf_counter()
    world, logged = build(job)
    warm, _ = day_bounds(job["first_day"] - 1, job["first_day"] - 1)
    start, end = day_bounds(job["first_day"], job["last_day"])
    result = simulate(world, logged, warm, end, metric_start_min=start, seed_label=str(job["seed"]))
    floor = unavoidable(world, warm, start, end)
    causes = classify_misses(world, result.tickets, logged.rows, floor, warm, end)
    t = result.tickets.copy()
    t["cause"] = t["idx"].map(causes).fillna("kept")
    t["team"] = t["category"].map(TEAM_OF)
    t["hour"] = ((t["created_min"] % 1440) // 60).astype(int)
    t["channel"] = [world.channel[i] for i in t["idx"]]
    keep = ["idx", "ticket_id", "created_min", "first_pickup_min", "resolved_min", "breached", "priority", "language",
            "category", "team", "hour", "channel", "transfers", "reopens", "mismatch_used", "cause", "sla_min"]
    rows = pd.DataFrame(logged.rows)
    return {"job": job, "kpis": summarize(result), "tickets": t[keep].to_dict("list"),
            "assignments": rows.drop(columns=["passed"]).to_dict("list") if len(rows) else {},
            "passed_count": [len(p) for p in rows["passed"]] if len(rows) else [],
            "calib": logged.calib, "seconds": time.perf_counter() - started}


def classify_misses(world, tickets: pd.DataFrame, rows: list[dict], floor: set[int], warm: float,
                    end: float) -> dict[int, str]:
    first_day, last_day = int(warm // 1440) - 1, int(end // 1440) + 3
    shifts = {k: shift_intervals(world, k, first_day, last_day) for k in range(len(world.agents))}
    cover_cache: dict = {}

    def cover(lang, cat):
        if (lang, cat) not in cover_cache:
            cover_cache[(lang, cat)] = merge([iv for k, a in enumerate(world.agents)
                                              if lang in a.languages and cat in a.skills for iv in shifts[k]])
        return cover_cache[(lang, cat)]

    by_ticket: dict[int, list[dict]] = defaultdict(list)
    passed_events: dict[int, list[tuple[float, dict]]] = defaultdict(list)
    by_agent: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_ticket[r["idx"]].append(r)
        by_agent[r["agent"]].append(r["t"])
        for k in r["passed"]:
            passed_events[k].append((r["t"], r))
    capable_agents: dict = {}
    out: dict[int, str] = {}
    for rec in tickets[tickets["breached"]].itertuples():
        i = int(rec.idx)
        created = float(rec.created_min)
        deadline = created + float(rec.sla_min)
        b0 = float(world.base_handle_min[i, 0])
        latest = deadline - b0
        if i in floor:
            out[i] = "unavoidable"
            continue
        if rec.transfers > 0:
            out[i] = "transfer"
            continue
        if rec.reopens > 0:
            out[i] = "reopen"
            continue
        served = [r for r in by_ticket.get(i, []) if r["outcome"] == "resolve"]
        if rec.mismatch_used and served and served[0]["t"] + b0 <= deadline:
            out[i] = "cross_skill_too_slow"
            continue
        events = [r for t0, r in passed_events.get(i, []) if t0 <= latest]
        if events:
            kinds = set()
            for r in events:
                if r["p_hopeless"] >= HOPELESS:
                    kinds.add("passed_over_lost_ticket")
                elif r["cross"]:
                    kinds.add("passed_over_cross_job")
                elif PRIO[r["prio"]] > PRIO[rec.priority]:
                    kinds.add("passed_over_lower_priority")
                else:
                    kinds.add("passed_over_same_priority_more_slack")
            out[i] = next(c for c in CAUSES if c in kinds)
            continue
        lang, cat = world.language[i], world.true_category[i]
        if earliest_start(cover(lang, cat), created) > latest:
            out[i] = "skill_gap"
            continue
        key = (lang, cat)
        if key not in capable_agents:
            capable_agents[key] = [a.agent_id for a in world.agents if lang in a.languages and cat in a.skills]
        started = any(created <= s <= latest for aid in capable_agents[key] for s in by_agent.get(aid, ()))
        out[i] = "congestion_more_urgent_work" if started else "busy_when_it_landed"
    for i in tickets.loc[tickets["breached"], "idx"]:
        out.setdefault(int(i), "other")
    return out


def load_frames(results: list[dict]):
    tickets, assigns, calib = {}, {}, {}
    for r in results:
        key = (r["job"]["kind"], r["job"]["seed"])
        tickets[key] = pd.DataFrame(r["tickets"])
        assigns[key] = pd.DataFrame(r["assignments"]).assign(passed_count=r["passed_count"])
        calib[key] = pd.DataFrame(r["calib"], columns=["t", "idx", "prio", "left", "p_now_clock", "clock_p_wait",
                                                       "ctx_p_wait", "stale_risk_wait"])
    return tickets, assigns, calib


def per_seed_mean(frames: list[pd.DataFrame], fn) -> dict:
    vals = [fn(f) for f in frames]
    keys = sorted({k for v in vals for k in v}, key=str)
    return {str(k): round(float(np.mean([v.get(k, 0.0) for v in vals])), 2) for k in keys}


def decompose(tickets: dict, kind: str) -> dict:
    frames = [tickets[(kind, s)] for s in SEEDS]
    n = np.mean([len(f) for f in frames])
    out = {"tickets_per_run": round(float(n), 1),
           "missed_per_run": round(float(np.mean([f["breached"].sum() for f in frames])), 1),
           "breach_pct": round(float(np.mean([100 * f["breached"].mean() for f in frames])), 2),
           "by_cause": per_seed_mean(frames, lambda f: f.loc[f.breached, "cause"].value_counts().to_dict())}
    out["by_cause_pct_of_tickets"] = {c: round(100 * v / n, 2) for c, v in out["by_cause"].items()}
    for dim in ("priority", "team", "language"):
        out[f"cause_by_{dim}"] = per_seed_mean(
            frames, lambda f, d=dim: {f"{a}|{b}": v for (a, b), v in
                                      f[f.breached].groupby([d, "cause"]).size().items()})
        out[f"breach_pct_by_{dim}"] = per_seed_mean(
            frames, lambda f, d=dim: (100 * f.groupby(d)["breached"].mean()).to_dict())
        out[f"tickets_by_{dim}"] = per_seed_mean(frames, lambda f, d=dim: f.groupby(d).size().to_dict())
    out["missed_by_hour"] = per_seed_mean(frames, lambda f: f[f.breached].groupby("hour").size().to_dict())
    out["avoidable_missed_by_hour"] = per_seed_mean(
        frames, lambda f: f[f.breached & (f.cause != "unavoidable")].groupby("hour").size().to_dict())
    out["p1_cause_by_hour"] = per_seed_mean(
        frames, lambda f: {f"{a}|{b}": v for (a, b), v in
                           f[f.breached & (f.priority == "P1")].groupby(["hour", "cause"]).size().items()})
    return out


def compare(tickets: dict, a: str, b: str) -> tuple[dict, pd.DataFrame]:
    rows = []
    summary = defaultdict(list)
    for s in SEEDS:
        x, y = tickets[(a, s)].set_index("idx"), tickets[(b, s)].set_index("idx")
        j = x.join(y[["breached", "cause", "first_pickup_min"]], rsuffix="_b")
        lost = j[j["breached"] & ~j["breached_b"]]
        won = j[~j["breached"] & j["breached_b"]]
        summary["a_missed_b_kept"].append(len(lost))
        summary["a_kept_b_missed"].append(len(won))
        summary["both_missed"].append(int((j["breached"] & j["breached_b"]).sum()))
        for name, part, cause_col in (("a_missed_b_kept", lost, "cause"), ("a_kept_b_missed", won, "cause_b")):
            for c, v in part[cause_col].value_counts().items():
                summary[f"{name}|cause|{c}"].append(v)
            for c, v in part["priority"].value_counts().items():
                summary[f"{name}|priority|{c}"].append(v)
            for c, v in part["team"].value_counts().items():
                summary[f"{name}|team|{c}"].append(v)
            for c, v in part.groupby(["priority", cause_col]).size().items():
                summary[f"{name}|priority_cause|{c[0]}|{c[1]}"].append(v)
            rows.append(part.reset_index().assign(seed=s, side=name, pickup_delay_vs_other=(
                part["first_pickup_min"] - part["first_pickup_min_b"]).to_numpy()))
    out = {k: round(float(np.sum(v)) / len(SEEDS), 2) for k, v in summary.items()}
    table = pd.concat(rows, ignore_index=True)
    out["median_pickup_delay_min"] = {
        side: round(float(table.loc[table.side == side, "pickup_delay_vs_other"].median()), 2)
        for side in ("a_missed_b_kept", "a_kept_b_missed")}
    return out, table


def assignment_stats(assigns: dict, tickets: dict, kind: str) -> dict:
    out = defaultdict(list)
    for s in SEEDS:
        a = assigns[(kind, s)]
        t = tickets[(kind, s)].set_index("idx")
        a = a[a["idx"].isin(t.index)]
        breached = t["breached"].reindex(a["idx"]).to_numpy().astype(bool)
        hop = (a["p_hopeless"] >= HOPELESS).to_numpy()
        p1 = (a["prio"] == "P1").to_numpy()
        waiting_savable = (a["passed_count"] > 0).to_numpy()
        cr = a["cross"].to_numpy().astype(bool)
        futile = cr & (a["slack"] < 0).to_numpy()
        neg = (a["slack"] < 0).to_numpy()
        out["assignments"].append(len(a))
        out["hopeless_served"].append(int(hop.sum()))
        out["hopeless_served_p1"].append(int((hop & p1).sum()))
        out["hopeless_served_but_kept"].append(int((hop & ~breached).sum()))
        out["hopeless_served_while_savable_waited"].append(int((hop & waiting_savable).sum()))
        out["cross_jobs"].append(int(cr.sum()))
        out["cross_jobs_p1"].append(int((cr & p1).sum()))
        out["cross_jobs_kept"].append(int((cr & ~breached).sum()))
        out["cross_jobs_futile_by_expectation"].append(int(futile.sum()))
        out["cross_jobs_futile_p1"].append(int((futile & p1).sum()))
        out["cross_jobs_futile_kept"].append(int((futile & ~breached).sum()))
        unlikely = cr & (a["p_hopeless"] > 0.5).to_numpy()
        out["cross_jobs_fit_below_half"].append(int(unlikely.sum()))
        out["cross_jobs_fit_below_half_kept"].append(int((unlikely & ~breached).sum()))
        out["cross_jobs_mean_p_fit"].append(float(1 - a.loc[cr, "p_hopeless"].mean()) if cr.any() else 0.0)
        reopened = t["reopens"].reindex(a["idx"]).to_numpy() > 0
        out["cross_jobs_reopened"].append(int((cr & reopened).sum()))
        out["served_with_negative_slack"].append(int(neg.sum()))
        out["served_past_deadline"].append(int((a["deadline"] <= a["t"]).sum()))
        out["served_negative_slack_while_savable_waited"].append(int((neg & waiting_savable).sum()))
        past = (a["deadline"] <= a["t"]).to_numpy()
        blocking = hop & waiting_savable
        out["lost_served_while_savable_waited_past_deadline"].append(int((blocking & past).sum()))
        out["lost_served_while_savable_waited_before_deadline"].append(int((blocking & ~past).sum()))
        for p in ("P1", "P2", "P3"):
            out[f"lost_served_while_savable_waited_{p}"].append(int((blocking & (a["prio"] == p).to_numpy()).sum()))
        for team in ("A", "B", "C", "D"):
            out[f"lost_served_while_savable_waited_team_{team}"].append(
                int((blocking & (a["team"] == team).to_numpy()).sum()))
        p1_waited = (a["passed_p1"] > 0).to_numpy()
        out["picks_while_savable_p1_waited"].append(int(p1_waited.sum()))
        for p in ("P1", "P2", "P3"):
            out[f"picks_while_savable_p1_waited_took_{p}"].append(
                int((p1_waited & (a["prio"] == p).to_numpy()).sum()))
        out["picks_while_savable_p1_waited_took_lost"].append(int((p1_waited & hop).sum()))
        out["mean_exp_handle_served"].append(float(a["exp_h"].mean()))
    return {k: round(float(np.mean(v)), 2) for k, v in out.items()}


def auc(y: np.ndarray, p: np.ndarray) -> float:
    ok = ~np.isnan(p)
    y, p = y[ok], p[ok]
    pos, neg = p[y], p[~y]
    if not len(pos) or not len(neg):
        return float("nan")
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def calibration(calib: dict, tickets: dict) -> dict:
    out = {}
    for kind, cols in (("opslens_live", {"clock part": "clock_p_wait", "LightGBM part (re-scored)": "ctx_p_wait",
                                         "P(miss even if served now)": "p_now_clock"}),
                       ("opslens", {"LightGBM, refreshed every 3 min": "stale_risk_wait",
                                    "P(miss even if served now)": "p_now_clock"})):
        frames = []
        for s in SEEDS:
            c = calib[(kind, s)]
            t = tickets[(kind, s)].set_index("idx")
            c = c[c["idx"].isin(t.index)].copy()
            c["y"] = t["breached"].reindex(c["idx"]).to_numpy().astype(bool)
            frames.append(c)
        c = pd.concat(frames, ignore_index=True)
        res = {"rows": len(c), "base_rate": round(float(c["y"].mean()), 4)}
        series = {name: c[col].to_numpy(float) for name, col in cols.items()}
        if kind == "opslens_live":
            for wgt in (0.0, 0.25, 0.5, 0.75, 1.0):
                series[f"blend clock weight {wgt}"] = wgt * c["clock_p_wait"].to_numpy(float) + (1 - wgt) * c[
                    "ctx_p_wait"].to_numpy(float)
        y = c["y"].to_numpy()
        p1 = (c["prio"] == "P1").to_numpy()
        for name, p in series.items():
            ok = ~np.isnan(p)
            res[name] = {"auc": round(auc(y, p), 4), "brier": round(float(np.mean((p[ok] - y[ok]) ** 2)), 4),
                         "mean_p": round(float(np.mean(p[ok])), 4), "n": int(ok.sum()),
                         "auc_p1": round(auc(y[p1], p[p1]), 4)}
        hop = c["p_now_clock"].to_numpy(float) >= HOPELESS
        res["p_now_ge_0.95"] = {"rows": int(hop.sum()),
                                "missed_share": round(float(y[hop].mean()), 4) if hop.any() else None}
        out[kind] = res
    return out


def erlang_tail(arrivals: float, aht: float, n: int, t: float) -> float:
    load = arrivals * aht / 60.0
    if n <= load:
        return 1.0
    b = 1.0
    for k in range(1, n + 1):
        b = load * b / (k + load * b)
    c = n * b / (n - load * (1 - b))
    return c * math.exp(-(n - load) * t / aht)


def erlang_mean_wait(arrivals: float, aht: float, n: int) -> float:
    load = arrivals * aht / 60.0
    if n <= load:
        return math.inf
    return erlang_tail(arrivals, aht, n, 0.0) * aht / (n - load)


def staffing_targets() -> dict:
    from opslens.ingest import load_history
    from opslens.staffing import MAX_RHO, TARGET_WAIT_MIN
    h = load_history()
    h = h[h["day"] <= 35].assign(team=lambda d: d["final_category"].map(TEAM_OF))
    sla = load_config("sla")["sla_minutes"]
    created = pd.to_datetime(h["created_at"])
    h = h.assign(how=created.dt.weekday * 24 + created.dt.hour)
    weeks = 5.0
    out = {}
    for team, g in h.groupby("team"):
        aht = float(g["handled_min"].mean())
        promises = np.array([sla[p] for p in g["priority"]], dtype=float)
        tight = float(np.percentile(promises, 10))
        answer_within = max(1.0, tight - aht)
        need_now = need_sl = gap = late_hours = 0
        for _, n in g.groupby("how").size().items():
            lam = n / weeks
            load = lam * aht / 60.0
            k = max(1, math.ceil(load / MAX_RHO))
            while erlang_mean_wait(lam, aht, k) > TARGET_WAIT_MIN:
                k += 1
            m = max(1, math.ceil(load / MAX_RHO))
            while erlang_tail(lam, aht, m, answer_within) > 0.2:
                m += 1
            need_now += k
            need_sl += m
            gap += max(0, m - k)
            late_hours += int(erlang_tail(lam, aht, k, answer_within) > 0.2)
        out[team] = {"aht_min": round(aht, 2), "p1_share": round(float((g["priority"] == "P1").mean()), 3),
                     "mean_promise_min": round(float(promises.mean()), 1), "answer_within_min": round(answer_within, 1),
                     "agent_hours_per_week_mean_wait_15": need_now, "agent_hours_per_week_service_level": need_sl,
                     "hours_per_week_where_target_15_leaves_over_20pct_waiting_too_long": late_hours,
                     "extra_agent_hours_per_week": gap}
    return {"rule_now": f"Erlang C mean wait <= {TARGET_WAIT_MIN:.0f} min, occupancy <= {MAX_RHO}",
            "rule_proposed": "Erlang C P(wait > tightest promise (10th pct) - AHT) <= 20%, occupancy <= 0.85",
            "train_days": [1, 35], "teams": out}


def run_all(workers: int) -> list[dict]:
    jobs = [{"kind": k, "seed": s, "first_day": FIRST, "last_day": LAST, **spec}
            for k, spec in KINDS.items() for s in SEEDS]
    jobs.sort(key=lambda j: j["policy"] != "opslens")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run_diag, jobs))


def main() -> int:
    started = time.perf_counter()
    results = run_all(workers=15)
    print(f"runs done in {time.perf_counter() - started:.0f}s", flush=True)
    tickets, assigns, calib = load_frames(results)
    kpis = defaultdict(list)
    for r in sorted(results, key=lambda r: r["job"]["seed"]):
        kpis[r["job"]["kind"]].append(r["kpis"])
    rows = {k: {kpi: round(float(np.mean([x[kpi] for x in v])), 3)
                for kpi in ("turnaround.breach_pct", "segment.p1_breach_pct", "segment.hindi_breach_pct",
                            "quality.late_minutes_per_100", "productivity.transfers_per_100",
                            "quality.reopen_rate_pct", "quality.mean_utilisation")} for k, v in kpis.items()}
    paired = {}
    for a, b in (("opslens", "least_slack_rescue"), ("opslens_live", "least_slack_rescue"),
                 ("opslens_live", "opslens"), ("opslens", "opslens_nostaff"),
                 ("opslens_nostaff", "least_slack_rescue"), ("opslens", "baseline_d")):
        paired[f"{a} - {b}"] = {kpi: paired_ci([x[kpi] for x in kpis[a]], [x[kpi] for x in kpis[b]])
                                for kpi in ("turnaround.breach_pct", "segment.p1_breach_pct")}
    decomposition = {k: decompose(tickets, k) for k in KINDS}
    comparisons, tables = {}, []
    for a, b in (("opslens", "least_slack_rescue"), ("opslens_live", "least_slack_rescue"),
                 ("opslens_nostaff", "least_slack_rescue"), ("opslens_live", "opslens")):
        comparisons[f"{a} vs {b}"], table = compare(tickets, a, b)
        if b == "least_slack_rescue" and a in ("opslens", "opslens_live"):
            tables.append(table.assign(pair=f"{a} vs {b}"))
    stats = {k: assignment_stats(assigns, tickets, k) for k in KINDS}
    calibs = calibration(calib, tickets)
    staffing = staffing_targets()
    out = {"days": [FIRST, LAST], "seeds": SEEDS, "least_slack_rescue_threshold_min": RESCUE_THRESHOLD,
           "hopeless_threshold": HOPELESS, "causes": CAUSES,
           "cause_rules": {
               "unavoidable": "opslens/floor.py: no legal policy could finish it in time (same roster as the run)",
               "transfer": "routed to the wrong team at least once (4-min discovery, back in the queue)",
               "reopen": "came back after a first resolution (not already in the unavoidable floor)",
               "cross_skill_too_slow": "served cross-skill; the same start at trained speed would have made it",
               "passed_over_*": ("while it was still savable (expected slack >= 0, before its last trained start), "
                                 "a free trained agent who speaks its language took another ticket with more slack, "
                                 "or a ticket with P(miss even if served now) >= 0.95; the label is the worst such "
                                 "pick: lost ticket > cross-skill job > lower priority > same/higher priority"),
               "skill_gap": "no trained agent in its language on shift between arrival and its last start",
               "busy_when_it_landed": "trained agents in its language were on shift but none started any work "
                                      "between its arrival and its last start (all busy)",
               "congestion_more_urgent_work": "trained agents started work in its window, but only on tickets "
                                              "with less slack than it had",
           },
           "kpis": rows, "paired": paired, "decomposition": decomposition, "ticket_level": comparisons,
           "assignments": stats, "risk_calibration": calibs, "staffing_targets": staffing,
           "seconds": round(time.perf_counter() - started, 1),
           "note": "validation days 36-42 only (warm-up day 35); diagnosis, not an adoption test"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "diagnosis.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    cols = ["pair", "side", "seed", "ticket_id", "priority", "team", "language", "category", "channel", "hour",
            "cause", "cause_b", "created_min", "first_pickup_min", "first_pickup_min_b", "pickup_delay_vs_other"]
    pd.concat(tables, ignore_index=True)[cols].round(2).to_csv(OUT / "diagnosis_tickets.csv", index=False)
    print_summary(out)
    return 0


def print_summary(out: dict) -> None:
    for k, r in out["kpis"].items():
        print(f"{k:20s} breach {r['turnaround.breach_pct']:6.2f}  P1 {r['segment.p1_breach_pct']:6.2f}  "
              f"Hindi {r['segment.hindi_breach_pct']:6.2f}")
    for k, d in out["paired"].items():
        b, p = d["turnaround.breach_pct"], d["segment.p1_breach_pct"]
        print(f"  {k:38s} {b['mean_diff']:+.2f} [{b['ci_low']:+.2f}, {b['ci_high']:+.2f}]  "
              f"P1 {p['mean_diff']:+.2f} [{p['ci_low']:+.2f}, {p['ci_high']:+.2f}]")
    for k in ("opslens", "opslens_live", "least_slack_rescue"):
        print(k, out["decomposition"][k]["by_cause"])


if __name__ == "__main__":
    raise SystemExit(main())
