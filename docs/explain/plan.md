# plan.py — "Your plan": accept a recommendation, see what it changes

## For the dashboard: exact shapes (read this first)

**KPI keys** (no dots, so they work in evidence paths), in display order:

| Heading | Keys |
|---|---|
| `turnaround` | `breaches`, `breach_pct`, `mean_resolution_min`, `p90_resolution_min` |
| `productivity` | `tickets`, `busy_agent_hours`, `tickets_per_agent_hour`, `transfers` |
| `quality` | `reopen_rate_pct`, `late_minutes_per_100` |

`headings`, `labels`, `units` and `better` ("lower" / "higher" / `null`) come with the data, in
`results.plan` and in every live answer, so the screen never hard-codes them.
`tickets_per_agent_hour` has `better: null`: it falls when a playbook prevents tickets.

**Item ids** are stable strings, safe to show next to each recommendation:
- staffing move: `staff_<first day of its week>_<agent id>`, e.g. `staff_43_C02`;
- playbook: the playbook's own id, e.g. `pb_F2` (same as `results.playbooks.playbooks[*].id`).

`results.plan.items[i]` for i = 0..11 are the staffing moves in **the same order** as
`results.recommendations.staffing_moves[i]` (same agent, same week). So a screen that lists
`staffing_moves` sends `results.plan.items[i].id`, not its own `move-<i>` id; the server answers 400
to ids it does not know.

**1. Precomputed, each item alone** — `results.plan` (from `GET /api/results`):
```
plan = {
  test_days: [43, 56], warmup_day: 42, seeds: [1, 2, 3, 4, 5], policy: "opslens",
  without: "OpsLens dispatch on the published roster, nothing accepted (...)",
  headings: {turnaround: [keys], productivity: [keys], quality: [keys]},
  labels: {key: "customers who missed the SLA", ...}, units: {key: "tickets", ...},
  better: {key: "lower" | "higher" | null},
  base_kpis: {key: {mean, std}},            // nothing accepted, 14 test days
  alerts_used: [...],                        // used by the status-banner playbook; ignore
  items: [ITEM, ...],                        // 18: 12 staffing moves, then 6 playbooks
  all_items: {ids: [...], effect: EFFECT}    // every item accepted together (its own run, not a sum)
}
ITEM = {
  id, kind: "staffing" | "playbook", title, owner, when: "days 43-49", first_day, last_day,
  assumptions: [str],                        // show them; "ASSUMPTION: ..." = a business guess
  change: {agent_id, start_hour, days_off},  // staffing only
  action, scenario, card_id,                 // playbook only (card_id → patterns.cards)
  effect: EFFECT                             // this item ALONE vs nothing accepted
}
EFFECT = {key: {without, with, diff, ci_low, ci_high, n}}
```
`diff` = mean over the 5 paired seeds of (with − without); `[ci_low, ci_high]` = its 95% CI. If the
CI contains 0, say "no clear effect". Evidence path example: `plan.items[13].effect.breaches.diff`.

**2. Live, the whole plan on one day** — `POST /api/plan/impact`:
```
request:  {"day": 48, "items": ["staff_43_C02", "pb_F2"]}   // day 43-56; ids in any order; [] allowed
response: {
  day: 48, weekday: "Sat", policy: "opslens", seeds: [1, 2, 3],
  items: [{id, kind, title, when, in_effect, tickets_removed, tickets_rerouted, agents_changed}],
  headings: {turnaround: [keys], productivity: [keys], quality: [keys]},
  labels: {key: str}, units: {key: str}, better: {key: "lower" | "higher" | null},
  without: {key: number}, with: {key: number}, delta: {key: number},  // means over the 3 seeds
  delta_by_seed: {key: [d1, d2, d3]},                                 // shows how noisy one day is
  seconds: 17.7,
  note: "Simulated now: OpsLens dispatch on day 48 (day 47 as warm-up), 3 seeds; ..."
}
errors:   400 {"error": "unknown plan item ids: move-0"}  (unknown or repeated id, day outside 43-56)
          503 {"error": "results.json has no plan items yet: run make eval"}
```
- `in_effect: false` = the item changes nothing that day (a week-43 move asked for day 52, a day-off
  swap on a day it does not touch, a status banner on a day with no alert). Grey it out.
- Time: first request ~27-31 s (6 worker processes start and load the data), a new plan ~18 s, the
  same plan again instant. Tip: when the plan panel opens, POST `{"day": 48, "items": []}` in the
  background; it starts the workers and caches the day's "without" runs, so the first real click
  takes ~18 s. Requests are served one at a time.

## What it does
- OpsLens recommends two kinds of big decisions a person must approve: **staffing moves**
  (one agent, one week, a new start time or day off) and **fix-at-source playbooks**
  (an action for a team outside support, e.g. "cross-train two Hindi speakers").
- Each one is a **plan item** with a stable id: `staff_43_C02`, `pb_F2`.
- When the manager accepts items, OpsLens shows what they would change for **turnaround,
  productivity and service quality** — the problem statement's three words.
- Two views: each item **alone**, measured in `make eval` on the 14 test days (5 seeds); and the
  **whole plan together**, simulated live for one day (`POST /api/plan/impact`).

## How it works, step by step
1. **The catalogue.** `staffing_items()` reads the weekly staffing plans (made on days 42 and 49,
   `data/generated/staffing_plan.json`). Each move changes exactly one agent, so the item keeps
   only that agent's new shift. `playbook_items()` reads the playbooks (`eval/parts/playbooks.json`).
   Today: 12 staffing moves + 6 playbooks = 18 items.
2. **Applying items.** `apply_staffing_move()` gives the one agent a week-specific shift
   (an "override" for days 43-49, say); nobody else changes. A playbook uses
   `playbooks.apply_scenario()` (removes or re-routes tickets, or trains agents). `apply_items()`
   does all accepted items, always in catalogue order, so click order never changes the answer.
3. **Without vs with.** "Without" = the shipped OpsLens policy on the published roster, nothing
   accepted. "With" = the same days, same tickets, same luck (common random numbers), plus the
   items. The difference is the plan's effect and nothing else.
4. **Each item alone (make eval).** `eval/run_plan_items.py` runs nothing-accepted, each of the 18
   items alone, and all 18 together: 20 set-ups × 5 seeds = 100 runs of the 14 test days. For
   every KPI it stores the mean without, the mean with, and the paired difference with a 95% CI.
   Written to `results.plan`.
5. **The whole plan, live.** The endpoint simulates one test day (the day before as warm-up)
   with OpsLens, without and with ALL accepted items, for 3 seeds. One run takes about 20 s, so
   the 6 runs go to 6 worker processes at the same time. Finished runs are kept in memory: the
   "without" runs of a day are shared by every plan asked for that day. Measured on this laptop:
   first request 26.7–30.8 s (the workers start and load the data), a new plan on a day already
   asked about 17.7 s, a new day 18.5 s, the same plan again 0.0 s.
6. **In effect?** A move only matters on days when the agent's shift is different. "Day off on
   Monday instead of Friday" changes nothing on a Wednesday. The endpoint says so per item
   (`in_effect`), instead of showing a zero as if it were measured.

## The KPIs (same words on screen)
| Heading | KPI | Better |
|---|---|---|
| Turnaround | customers who missed the SLA (count), SLA breach rate, mean and P90 resolution time | lower |
| Productivity | tickets that reach an agent, agent-hours of work, transfers between teams | lower |
| Productivity | tickets resolved per agent-hour | no direction (falls when tickets are prevented: agents are less busy, not slower) |
| Quality | reopen rate, minutes past SLA per 100 tickets | lower |

## Worked example
**Nothing accepted** (OpsLens on the published roster, test days 43-56, mean of 5 seeds): 18,032
tickets, 379.8 customers miss their SLA (2.11%), mean resolution 66.78 min, 518.55 minutes past
SLA per 100 tickets. (Same as the M8 "without staffing plan" ablation — a built-in check.)

**Accept "Cross-train 2 Hindi-speaking agents" (`pb_F2`) alone.** A09 and D11 get the refund and
payment skills; nothing else changes. Same tickets, same luck:
- Turnaround: 379.8 → 353.0 customers miss the SLA, **−26.8** (95% CI −39.01 to −14.59);
  mean resolution 66.78 → 63.56 min.
- Productivity: agent-hours of work **−22.82** (fewer slow cross-skill jobs); same tickets.
- Quality: reopen rate 4.48% → 4.36%; minutes past SLA per 100 tickets 518.55 → 431.61 (**−86.94**).

**Accept "Deepak W. (C02) starts 07:00 instead of 08:00, days 43-49" alone:** −1.2 customers
(CI −5.45 to +3.05). The interval contains zero: **no clear effect**, and the screen should say so.

**Accept all 18 items together:** −48.8 customers (CI −63.13 to −34.47), mean resolution −12.55 min,
206 tickets never reach an agent, −66.32 agent-hours, −161.72 minutes past SLA per 100 tickets.
(Same as `results.playbooks.all` under OpsLens: 331 customers with everything accepted — the second
built-in check.)

**Live, one day.** `POST /api/plan/impact {"day": 48, "items": ["staff_43_C02", "pb_F2"]}` on
Saturday day 48, 3 seeds: 28.667 → 25.333 customers miss the SLA (−3.333), seed by seed −4, 0, −6.
Asked for day 52, the week-43 move is `in_effect: false` and every delta is exactly 0.

## Weaknesses
- **Staffing moves are small.** Each moves one person by an hour or one day off. Under OpsLens their
  effect alone is inside the noise — the M8 ablation already said the whole staffing plan adds
  little under OpsLens. We show that honestly ("no clear effect") instead of hiding the moves.
- **Twelve moves, twelve tests.** At 95%, about one in twenty intervals misses zero by luck alone.
  Arjun N.'s day-off swap (days 43-49) is −7.6 [−15.03, −0.17]: just clear of zero; treat it as a
  hint, not a proof.
- **Items are measured alone, and live together.** Effects do not simply add up: two items can
  help the same customers. The live endpoint simulates the accepted items together, so the plan
  total is measured, not summed.
- **One day is noisy.** The live answer is one day, 3 seeds; `delta_by_seed` shows the spread. The
  14-day, 5-seed numbers in `results.plan` are the solid ones.
- **Playbook assumptions.** A playbook's effect is its effect *if* the fix works as assumed
  (`config/playbooks.yaml`, labelled ASSUMPTION, re-run low/high in `results.playbooks`).
- **Why the playbooks are measured again here.** `results.playbooks` measures each playbook against
  OpsLens with every staffing move already in place, and keeps fewer KPIs. The plan needs one
  "nothing accepted" starting point and all three headings, so `run_plan_items.py` replays them.

## How to read the code
`opslens/plan.py`: `staffing_items()` / `playbook_items()` (the catalogue) → `check_ids()` →
`apply_items()` → `effect_by_kpi()` (make eval) or `run_plan_day()` + `impact_answer()` (live).
Then `eval/run_plan_items.py` → `main()`, and `server/app.py` → `plan_impact()`,
`run_plan_jobs()`. The one-day runner is `opslens/whatif.py` → `simulate_day()`, shared with the
What-if panel. Tests: `tests/test_plan.py`.
