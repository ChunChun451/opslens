"""Generate the 56-day operations dataset, plant the problems, and make history with Baseline A.

Run:  mingw32-make gen

Outputs (data/generated/, git-ignored, fully reproducible from the seed):
- world_tickets.csv  the TRUTH (true category, text, ...). Only the simulator reads it.
- history.csv        the helpdesk export: what a company would give us. Produced by running
                     Baseline A in the simulator on all 56 days. The engine reads this.
- agents.csv         the roster as a table.
- ../planted.json    the planted problems and decoys. Only eval/ reads it.

How volume is made, step by step:
1. Each day gets a total: 1,130 on weekdays, ×1.15 at weekends, ×1.35 on the two sale days,
   ×1.12 on the busy-but-normal decoy day, times a small random day-to-day factor.
2. Each hour gets its share of the day (lunch and dinner peaks, `hourly_profile`).
3. Each category gets its share of the hour, with lifts: late deliveries and missing items
   rise at meal peaks; planted spikes multiply one category in a few hours.
4. The number of tickets is a Poisson draw around that expected value.

Example: Saturday 20:00, missing_item.
    day total 1,130 × 1.15 = 1,299.5; hour share 7.3/92.9 = 7.86% → 102.1 tickets;
    missing_item share 0.14 × peak lift 1.2 × weekend-dinner lift 1.35 → 23.2 expected.
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

from data.text_bank import RESTAURANTS, TextBank  # noqa: E402
from opslens.config import load_config  # noqa: E402
from opslens.policies import baseline_a  # noqa: E402
from opslens.simulate import MINUTES_PER_DAY, available_minutes, simulate  # noqa: E402
from opslens.world import agents_table, build_world, load_agents  # noqa: E402

OUT_DIR = ROOT / "data" / "generated"
PLANTED_PATH = ROOT / "data" / "planted.json"
BITEXT_PATH = ROOT / "data" / "public" / "bitext" / "bitext_customer_support_27k_v11.csv"
HISTORY_SEED = 0


# ---- Volume ----------------------------------------------------------------------------------

def day_totals(cfg: dict, rng: np.random.Generator, first_weekday: int) -> np.ndarray:
    """Expected tickets for each day 1..N (index 0 = day 1)."""
    days = int(cfg["days"])
    totals = np.full(days, float(cfg["tickets_per_weekday"]))
    for d in range(1, days + 1):
        if (first_weekday + d - 1) % 7 in (5, 6):
            totals[d - 1] *= float(cfg["weekend_multiplier"])
    for event in cfg["known_events"]:
        totals[event["day"] - 1] *= float(event["multiplier"])
    for decoy in cfg["decoys"]:
        if decoy["kind"] == "busy_normal_day":
            totals[decoy["day"] - 1] *= float(decoy["multiplier"])
    noise = np.exp(rng.normal(0.0, float(cfg["day_noise_sd"]), days))
    return totals * noise


def category_lift(cfg: dict, day: int, weekday: int, hour: int, category: str) -> float:
    """Multiplier for one category in one hour: meal peaks + planted spikes."""
    lift = 1.0
    peak = cfg["peak_category_lift"]
    if hour in peak["hours"]:
        lift *= float(peak["lift"].get(category, 1.0))
    planted = cfg["planted"]
    team_c = planted["team_c_weekend_dinner"]
    if team_c["enabled"] and weekday in (5, 6) and hour in team_c["hours"]:
        lift *= float(team_c["weekend_lift"].get(category, 1.0))
    for key in ("payment_spike", "app_bug_surge"):
        spike = planted[key]
        if spike["enabled"] and day == spike["day"] and hour in spike["hours"] and category == spike["category"]:
            lift *= float(spike["multiplier"])
    return lift


# ---- Ticket attributes -----------------------------------------------------------------------

def pick(rng: np.random.Generator, probs: dict[str, float]) -> str:
    keys = list(probs)
    weights = np.array([probs[k] for k in keys], dtype=float)
    return str(rng.choice(keys, p=weights / weights.sum()))


def cluster_weights(cfg: dict) -> np.ndarray:
    """Restaurant-cluster popularity: a few big clusters, a long tail (Zipf-like)."""
    k = np.arange(int(cfg["restaurant_clusters"]))
    w = 1.0 / (k + 1.0) ** 0.8
    return w / w.sum()


def choose_selected_category(cfg: dict, rng: np.random.Generator, true_cat: str, channel: str) -> str:
    """The category the customer picks. Sometimes wrong — much more often in the IVR menu."""
    p_wrong = float(cfg["wrong_selection_prob"][channel])
    ivr = cfg["planted"]["ivr_misrouting"]
    if ivr["enabled"] and channel == ivr["channel"]:
        p_wrong = float(ivr["wrong_selection_prob"])
    if rng.random() >= p_wrong:
        return true_cat
    likely = cfg["likely_confusions"].get(true_cat, [])
    if likely and rng.random() < 0.7:
        return str(rng.choice(likely))
    others = [c for c in cfg["categories"] if c != true_cat]
    return str(rng.choice(others))


def make_tickets(cfg: dict, bank: TextBank) -> pd.DataFrame:
    seed = int(cfg["seed"])
    rng = np.random.default_rng([seed, 10])  # structure: counts, times, attributes
    rng_text = np.random.default_rng([seed, 11])  # text only, so editing templates moves nothing else
    first_weekday = pd.Timestamp(cfg["start_date"]).weekday()
    profile = np.array(cfg["hourly_profile"], dtype=float)
    profile = profile / profile.sum()
    totals = day_totals(cfg, rng, first_weekday)
    clusters = cluster_weights(cfg)
    partner = cfg["planted"]["partner_cluster"]

    rows: list[dict] = []
    for day in range(1, int(cfg["days"]) + 1):
        weekday = (first_weekday + day - 1) % 7
        for hour in range(24):
            hour_total = totals[day - 1] * profile[hour]
            for category, share in cfg["categories"].items():
                expected = hour_total * float(share) * category_lift(cfg, day, weekday, hour, category)
                for _ in range(rng.poisson(expected)):
                    rows.append(one_ticket(cfg, rng, day, hour, category, clusters, partner))

    tickets = pd.DataFrame(rows).sort_values("created_min", kind="stable").reset_index(drop=True)
    tickets.insert(0, "ticket_id", [f"T{n:06d}" for n in range(1, len(tickets) + 1)])
    start = pd.Timestamp(cfg["start_date"])
    tickets["created_at"] = start + pd.to_timedelta(tickets["created_min"], unit="m")
    tickets["text"] = [
        bank.make_text(rng_text, r.category, r.language, r.restaurant_name, r.order_id)
        for r in tickets.itertuples()
    ]
    return tickets


def one_ticket(cfg, rng, day, hour, category, clusters, partner) -> dict:
    channel = pick(rng, cfg["channels"])
    priority = ["P1", "P2", "P3"][int(rng.choice(3, p=cfg["priority_probs"][category]))]
    if channel == "email" and priority == "P1":
        priority = "P2"
    tier = "gold" if rng.random() < float(cfg["gold_share"]) else "normal"
    value = float(cfg["order_value_median_inr"]) * np.exp(rng.normal(0, float(cfg["order_value_sigma"])))
    if tier == "gold":
        value *= 1.3
    weights = clusters
    if partner["enabled"] and category == partner["category"]:
        weights = clusters.copy()
        weights[int(partner["cluster_id"])] *= float(partner["multiplier"])
        weights = weights / weights.sum()
    cluster = int(rng.choice(len(weights), p=weights))
    return {
        "created_min": (day - 1) * MINUTES_PER_DAY + hour * 60 + float(rng.uniform(0, 60)),
        "day": day,
        "category": category,
        "selected_category": choose_selected_category(cfg, rng, category, channel),
        "channel": channel,
        "priority": priority,
        "language": pick(rng, cfg["languages"]),
        "customer_tier": tier,
        "order_value_inr": round(value),
        "restaurant_cluster_id": cluster,
        "restaurant_name": RESTAURANTS[cluster % len(RESTAURANTS)],
        "order_id": str(int(rng.integers(1_000_000_000, 9_999_999_999))),
    }


# ---- Planted problems ------------------------------------------------------------------------

def planted_record(cfg: dict) -> dict:
    p = cfg["planted"]
    problems = [
        {"id": "P1", "name": "Hindi payments and refunds wait long", "cause_type": "skill_gap",
         "segment": {"language": "hi", "category": ["refund", "payment_failure"]},
         "mechanism": "only 3 agents (B01, B02, B05) have Hindi + refund/payment skills, none at night"},
        {"id": "P2", "name": "Team C overloaded at weekend dinner", "cause_type": "capacity",
         "segment": {"team": "C", "weekday": [5, 6], "hour": p["team_c_weekend_dinner"]["hours"]},
         "mechanism": "evening Team C agents are off at weekends; missing/wrong items x1.35"},
        {"id": "P3a", "name": "Payment-failure spike (bad app release)", "cause_type": "volume_spike",
         "segment": {"category": p["payment_spike"]["category"], "day": p["payment_spike"]["day"],
                     "hour": p["payment_spike"]["hours"]},
         "mechanism": f"x{p['payment_spike']['multiplier']} volume", "period": "history"},
        {"id": "P3b", "name": "App-bug surge (unseen, test period)", "cause_type": "volume_spike",
         "segment": {"category": p["app_bug_surge"]["category"], "day": p["app_bug_surge"]["day"],
                     "hour": p["app_bug_surge"]["hours"]},
         "mechanism": f"x{p['app_bug_surge']['multiplier']} volume", "period": "test"},
        {"id": "P4", "name": "Wrong items from one restaurant cluster", "cause_type": "partner_issue",
         "segment": {"category": p["partner_cluster"]["category"],
                     "restaurant_cluster_id": p["partner_cluster"]["cluster_id"]},
         "mechanism": f"x{p['partner_cluster']['multiplier']} wrong-item rate"},
        {"id": "P5", "name": "IVR menu mislabels call tickets", "cause_type": "process",
         "segment": {"channel": p["ivr_misrouting"]["channel"]},
         "mechanism": f"{p['ivr_misrouting']['wrong_selection_prob']:.0%} wrong selected category -> transfers"},
    ]
    return {"generated_from_seed": cfg["seed"], "problems": problems, "decoys": cfg["decoys"]}


# ---- History (the helpdesk export) -----------------------------------------------------------

def make_history(tickets: pd.DataFrame, result_tickets: pd.DataFrame, agents: pd.DataFrame,
                 start: pd.Timestamp, sla: dict) -> pd.DataFrame:
    out = result_tickets.set_index("ticket_id")
    hist = tickets[[
        "ticket_id", "created_at", "channel", "selected_category", "priority", "language",
        "customer_tier", "order_value_inr", "restaurant_cluster_id", "text", "category",
    ]].rename(columns={"category": "final_category"}).set_index("ticket_id")
    hist = hist.join(out[["first_pickup_min", "resolved_min", "wait_min", "resolution_min",
                          "handled_min", "transfers", "reopens", "last_agent", "breached"]])
    hist["first_pickup_at"] = start + pd.to_timedelta(hist["first_pickup_min"], unit="m")
    hist["resolved_at"] = start + pd.to_timedelta(hist["resolved_min"], unit="m")
    hist["sla_min"] = hist["priority"].map(sla["sla_minutes"])
    team_of = dict(zip(agents["agent_id"], agents["team"]))
    hist["resolved_by"] = hist["last_agent"]
    hist["resolved_by_team"] = hist["last_agent"].map(team_of)
    return hist.drop(columns=["first_pickup_min", "resolved_min", "last_agent"]).reset_index()


# ---- Calibration report ----------------------------------------------------------------------

def team_c_weekend_dinner_rho(world, tickets: pd.DataFrame, cfg: dict) -> float:
    """Work arriving for Team C's categories at weekend dinner ÷ Team C minutes on shift then."""
    hours = cfg["planted"]["team_c_weekend_dinner"]["hours"]
    first_weekday = world.first_weekday
    t = tickets.copy()
    t["weekday"] = (first_weekday + t["day"] - 1) % 7
    t["hour"] = (t["created_min"] % MINUTES_PER_DAY) // 60
    mask = t["category"].isin(["missing_item", "wrong_item"]) & t["weekday"].isin([5, 6]) & t["hour"].isin(hours)
    idx = np.nonzero(mask.to_numpy())[0]
    work = float(world.base_handle_min[idx, 0].sum())
    capacity = 0.0
    for day in range(1, int(cfg["days"]) + 1):
        if (first_weekday + day - 1) % 7 not in (5, 6):
            continue
        start = (day - 1) * MINUTES_PER_DAY + min(hours) * 60
        end = (day - 1) * MINUTES_PER_DAY + (max(hours) + 1) * 60
        for k, agent in enumerate(world.agents):
            if agent.team == "C":
                capacity += available_minutes(world, k, start, end)
    return work / capacity if capacity else float("inf")


def print_report(cfg, world, tickets, result, history, seconds: float) -> None:
    targets = cfg["calibration_targets"]
    res = result.tickets
    breach = 100 * res["breached"].mean()
    busy = sum(result.agent_busy_minutes.values())
    avail = sum(result.agent_available_minutes.values())
    util = busy / avail
    rho_c = team_c_weekend_dinner_rho(world, tickets, cfg)
    print(f"tickets: {len(tickets):,}  over {cfg['days']} days  (sim {seconds:.1f}s, {result.decisions:,} decisions)")
    print(f"Baseline A breach %     {breach:5.1f}   target {targets['breach_pct']}")
    print(f"mean utilisation        {util:5.2f}   target {targets['mean_utilisation']}")
    print(f"Team C wknd dinner rho  {rho_c:5.2f}   target {targets['team_c_weekend_dinner_rho']}")
    h = history
    print("breach % by resolving team:", (100 * h.groupby("resolved_by_team")["breached"].mean()).round(1).to_dict())
    print("breach % by priority:", (100 * h.groupby("priority")["breached"].mean()).round(1).to_dict())
    refunds = h[h["final_category"].isin(["refund", "payment_failure"])]
    print("Team B categories, mean wait (min) by language:",
          refunds.groupby("language")["wait_min"].mean().round(1).to_dict())
    wrong = h[h["final_category"] == "wrong_item"]
    share17 = (wrong["restaurant_cluster_id"] == 17).mean()
    base17 = (h["restaurant_cluster_id"] == 17).mean()
    print(f"cluster 17: {share17:.1%} of wrong items vs {base17:.1%} of all tickets")
    print("transfers per 100 tickets by channel:", (100 * h.groupby("channel")["transfers"].mean()).round(1).to_dict())
    print(f"reopen rate {h['reopens'].mean():.1%}   unresolved {h['resolution_min'].isna().sum()}")


def main() -> int:
    cfg = load_config("generator")
    sla = load_config("sla")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bank = TextBank.from_bitext_csv(BITEXT_PATH)
    tickets = make_tickets(cfg, bank)
    if "--tickets-only" in sys.argv:  # calibration helper: skip the slow history simulation
        tickets.to_csv(OUT_DIR / "world_tickets.csv", index=False)
        print(f"tickets: {len(tickets):,} (history not simulated)")
        return 0
    agents = load_agents()
    agents_df = agents_table(agents)

    world = build_world(tickets, seed=HISTORY_SEED, agents=agents, gen_cfg=cfg, sla_cfg=sla)
    started = time.perf_counter()
    end_min = int(cfg["days"]) * MINUTES_PER_DAY
    result = simulate(world, baseline_a(), 0, end_min, seed_label="history")
    seconds = time.perf_counter() - started

    start = pd.Timestamp(cfg["start_date"])
    history = make_history(tickets, result.tickets, agents_df, start, sla)
    tickets.to_csv(OUT_DIR / "world_tickets.csv", index=False)
    history.to_csv(OUT_DIR / "history.csv", index=False)
    agents_df.to_csv(OUT_DIR / "agents.csv", index=False)
    PLANTED_PATH.write_text(json.dumps(planted_record(cfg), indent=2), encoding="utf-8")
    print_report(cfg, world, tickets, result, history, seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
