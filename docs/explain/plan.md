# plan.py — "Your plan": accept a recommendation, see what it changes

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
   first request 26.7–28.5 s (the workers start and load the data), a new plan on a day already
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
`apply_items()` → `effect_by_heading()` (make eval) or `run_plan_day()` + `impact_answer()` (live).
Then `eval/run_plan_items.py` → `main()`, and `server/app.py` → `plan_impact()`,
`run_plan_jobs()`. The one-day runner is `opslens/whatif.py` → `simulate_day()`, shared with the
What-if panel. Tests: `tests/test_plan.py`.

## For the dashboard (response shapes)
- `results.plan.items[*]`: `id`, `kind` (staffing / playbook), `title`, `owner`, `when`,
  `assumptions`, `effect` = `{turnaround: [row], productivity: [row], quality: [row]}`, each row
  `{key, label, unit, better, without, with, diff, ci_low, ci_high, n}`. `results.plan.all_items`
  has the same `effect` for every item together; `results.plan.kpis` lists the rows in order.
- `POST /api/plan/impact {"day": 48, "items": ["staff_43_C02", "pb_F2"]}` →
  `{day, weekday, policy, seeds, items: [{id, kind, title, when, in_effect, tickets_removed,
  tickets_rerouted, agents_changed}], turnaround: [row], productivity: [row], quality: [row],
  runtime_s, note}`, each row `{key, label, unit, better, without, with, delta, delta_by_seed}`.
  Unknown or repeated id, or a day outside 43-56 → 400 `{"error": ...}`; no `plan` in results → 503.
