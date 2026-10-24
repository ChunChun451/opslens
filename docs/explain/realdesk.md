# realdesk — OpsLens on a real public service desk (UCI ServiceNow log)

## For the dashboard: exact shapes (read this first)

Everything is in `results.realdesk` (from `GET /api/results`). The Plan v3 keys `summary`, `cards`,
`early_warning`, `forecast`, `routing` are unchanged. Plan v4 adds six keys. Percentages are
0–100 floats; counts are ints; `ci_low` / `ci_high` are the 95% interval (whole test weeks resampled).

**1. `fasttrack` (W3) — whose pick saves more missed deadlines?**
```
fasttrack = {
  question: str, assumption: str,            // ALWAYS show the assumption next to the numbers
  deadline_rule: {
    chosen_on_check: "resolution time",      // or "... with waits on others paused" (the loser)
    limits_h: {"3 - Moderate": 91.0, "4 - Low": 325.0},
    match_pct: {learn, check, test},         // rule vs the company's own SLA flag
    candidates: {<clock>: {limits_h, match_pct}},
    left_out: {priorities: ["1 - Critical", "2 - High"], test_incidents, flag_missed_pct, why}
  },
  pickup: {definition, new_to_resolved_pct, waited_after_1h_pct},
  population: {test_incidents, scored, no_resolution_time, missed_by_rule, missed_by_rule_pct,
               missed_by_flag_pct, weeks, busy_weeks},
  ceiling: {saved, saved_pct_of_misses, missed_pct_after, pickup_hours_saved},   // everyone fast-tracked
  whole_log: {incidents, missed_pct, with_resolution_time, with_resolution_time_missed_pct,
              without_resolution_time, without_resolution_time_missed_pct},
  pickers: [{id, label}],                    // show in this order: priority, unassigned, oldest, logistic, opslens
  logistic: {C, check_auc},
  budgets: [10, 20, 30],
  results: {"10" | "20" | "30": {<picker id>: PICK}},
  opslens_minus: {"10" | "20" | "30": {<other picker id>: {diff, ci_low, ci_high}}},
  rule: {text, budget: 20, best_other, diff, ci_low, ci_high, passed: bool},
  by_week: [{week: "2016-05-02/2016-05-08", incidents, missed, saved: {<picker id>: int}}],  // 5 busy weeks
  example: {ticket_id, opened, priority, limit_h, resolution_h, wait_after_1h_h, fast_tracked_h,
            company_flag_missed},              // one real saved incident, for the screen
  busy_weeks_opslens_ahead_of_best_other: int
}
PICK = {picked, saved, ci_low, ci_high, saved_pct_of_misses, missed_pct_after, pickup_hours_saved, hit_rate_pct}
```
Evidence paths: `realdesk.fasttrack.results.20.opslens.saved`, `realdesk.fasttrack.rule.passed`.
If `rule.passed` is false the screen must NOT say OpsLens picks better; say who saved most.

**2. `impact` (W9) — the problem statement's three headings, real desk, 20% budget**
```
impact = {
  budget_pct: 20, assumption: str,
  turnaround: {pickup_hours_saved_opslens, pickup_hours_saved_priority, misses_avoided_opslens,
               misses_avoided_priority, misses_avoided_ceiling, ci_opslens: [low, high]},
  productivity: {claim: null, text},         // show the text: there is no productivity claim
  service_quality: {met_deadline_pct_as_it_happened, met_deadline_pct_opslens,
                    met_deadline_pct_priority, met_deadline_pct_ceiling},
  money: {shown: false, why}                 // no ₹ view on the real desk
}
```

**3. `replication` (W4a) — is each card still true on later months?**
```
replication = {
  cards: [{id: "R1" | "R2" | "R3", title, comparison_text,
           learning: {value, comparison, gap, ratio, n_group, n_comparison},
           test: {value, comparison, gap, ratio, n_group, n_comparison, ci_low, ci_high},
           replicates: bool}],               // same order as realdesk.cards
  replicated: int, of: int, rule: str
}
```
`value` / `comparison` = SLA missed % in the finding / in what it is compared with; `gap` = the
difference in points. Problems screen: "still true on later months" when `replicates`.

**4. `blind_plants` (W4b) — 20 random problem sets planted in the real test weeks**
```
blind_plants = {
  window: ["2016-05-02", "2016-06-05"], days: 35, sets: 20, plants: 60, found, recall_pct,
  by_type: {"spike" | "slowdown" | "bounce": {found, of, median_delay_days | null,
                                              upper_half_of_range: {from, found, of}}},
  median_delay_days,
  clean_alerts, false_alarms_per_30_days,    // detectors on the real weeks with NO plants
  clean_alert_list: [{type, segment, known_on: "2016-05-02", z}],
  clean_check_alerts,                        // same, on the clean check weeks
  unmatched_alerts_per_set,
  ranges: {spike_multiplier: [lo, hi], slow_factor, bounce_share, window_days, min_weekday_median,
           seeds: [first, last], match_slack_days},
  detector: {z, window_days, min_excess_count, min_day_count, min_excess_share},
  set_list: [{seed, alerts, unmatched_alerts,
              plants: [{type, segment, first_day, last_day, size, extra_incidents?, found, delay_days | null}]}]
}
```

**5. `forecast_candidates` (W7c)**
```
forecast_candidates = {
  candidates: {same_day_last_week: label, learned: label, average: label},
  wape_check: {<id>: float}, wape_test: {<id>: float},   // lower is better
  chosen_on_check: <id>, wape_test_chosen, best_on_test: <id>,
  team_days_check, team_days_test, note
}
```

**6. `alerts` (W7b) — "this team gets more new incidents than it usually closes", a week ahead**
```
alerts = {
  chosen_forecast: <id>, team_days, overloaded_share_pct, definition,
  scores: {same_day_last_week | learned | average | every_weekday: {alerts, overloaded, hits,
                                                                    precision_pct, recall_pct}},
  by_team: [{team, usual_closures, alerts, overloaded, hits, precision_pct, recall_pct}],  // chosen forecast
  labels: {<id>: str}                        // every_weekday = a calendar rule, the reference to beat
}
```
Risks screen (real): show the chosen forecast's hit rate next to the calendar rule's.

**7. `fasttrack_second_look` and `detector_second_look` (23 Oct, pre-registered in `f9b5e02`)**
Second looks after W3 and W4b missed. Both were chosen on the check weeks and run once; the first
verdicts above stay as they are. Show them as "a second look", never instead of the first result.
```
fasttrack_second_look = {
  why, label, candidates: [{id, label}], check_incidents,
  check_saved_20: {unassigned, opslens, unassigned_then_risk, rescue_model, unassigned_then_rescue},
  chosen_on_check: "rescue_model", chosen_label, rescue_model_rounds,
  results: {"10" | "20" | "30": {unassigned | opslens | <chosen>: {saved, ci_low, ci_high}}},
  chosen_minus_unassigned: {"10" | "20" | "30": {diff, ci_low, ci_high}},
  rule: {text, budget: 20, diff, ci_low, ci_high, passed: bool}
}
detector_second_look = {
  label, max_false_alarms_per_30_days: 10,
  candidates: [{name, slow_flag, pool_days, z, check_found, check_plants, check_false_alarms_per_30_days}],
  chosen_on_check: str, chosen: {name, slow_flag, pool_days, z},
  test_seeds: [9201, 9220], test_plants: 60, found_v1, found_v2, recall_v1_pct, recall_v2_pct,
  v2_minus_v1: {diff, ci_low, ci_high}, clean_alerts_v2, false_alarms_per_30_days_v2,
  clean_alert_list_v2: [{type, segment, known_on, z}], rule: {text, passed: bool}
}
```

**8. `shadow` (W11, 24 Oct) — shadow mode on real days: what OpsLens said vs what happened**
Frozen models, no retraining, test months only (`opslens/realdesk_shadow.py`). The picks are exactly
the W3 benchmark's picks for those days (checked in code). Minutes count from the day's midnight, so
`picked_up_at` / `resolved_at` can exceed 1440 (a later day) or be `null`.
```
shadow = {
  assumption: str,                           // the W3 fast-track assumption: show it with the saved counts
  how: str, privacy: str,                    // UCI has no free text, nothing needed masking
  min_day_incidents: 50,
  days: [{date: "2016-05-02", weekday: "Mon", opened, missed_flag}],    // every test day with >= 50 new incidents
  showcase: "2016-05-05", showcase_why: str, others_why: str,
  pickers: ["opslens", "priority", "unassigned"], features: [str],
  shown_days: [DAY, ...]                     // [0] = showcase, then 4 more (busiest weekday of each other busy week)
}
DAY = {date, weekday, summary: SUMMARY, incidents: [INCIDENT, ...]}   // incidents sorted by opened_at
SUMMARY = {
  incidents, benchmark_incidents,            // benchmark = Moderate/Low (Critical/High: the desk fast-tracks them anyway)
  actual_misses, actual_misses_benchmark,    // company's own SLA flag
  opslens:  {flagged, caught, recall_pct, precision_pct},   // flagged = the day's top 20% at the 1-hour mark
  priority: {flagged, caught, recall_pct, precision_pct},   // caught = flagged AND missed (benchmark incidents)
  fast_track_saved: {opslens, priority, unassigned}         // under the assumption
}
INCIDENT = {
  ticket_id, opened_at: int, priority: "3 - Moderate", in_benchmark: bool,
  risk: 0.514, reasons: [{text: "state after 1 h: New", share: 0.56}, ...],   // up to 3, same wording as at_risk
  unassigned_at_1h: bool, top20_opslens: bool, top20_priority: bool, pick_unassigned: bool,
  picked_up_at: int | null, resolved_at: int | null,
  picked_up_recorded: bool,                  // false: New straight to Resolved, no pickup in the log
  first_state: str, made_sla: bool,          // the company's flag
  rule_missed: bool | null,                  // our deadline rule; null when not scorable
  fast_track_saved: {opslens: bool, priority: bool, unassigned: bool}
}
```
For an hour-by-hour replay: an incident appears at `opened_at`, gets its OpsLens score and flags at
`opened_at + 60`, is picked up at `picked_up_at`, resolves at `resolved_at`.
Showcase (Thu 5 May 2016): 403 incidents, 111 missed by the company's flag; of the 102 misses in the
benchmark, OpsLens's top 20% at the 1-hour mark caught 53 (recall 52.0%, precision 67.1%), the
priority field's top 20% caught 16 (15.7%, 20.3%). Fast-track saved that day: OpsLens 5, priority
field 5, still unassigned 9.

## What it does
- Answers the five questions on a real company's IT service desk: 24,918 incidents, a real SLA flag.
- Plan v3 showed a prediction win (early warning). Plan v4 asks for proof a judge can trust:
  an **outcome** (fast-track benchmark), **findings that stay true** on later months, **plants**
  hidden in the real log, **alerts scored**, and a **fair forecast choice**.
- Learning = first 70% of incidents by opening time; every choice on its last 20% ("check");
  everything reported on the last 30% ("test"). The rules were committed before the first run
  (commit `4706f8f`).

## How it works, step by step
1. **Deadline rule** (`realdesk_fasttrack.deadline_rule`). The log has the company's SLA flag but
   not its clock. Per priority we learn the limit that best matches the flag on the learning part:
   **91 h for "3 - Moderate", 325 h for "4 - Low"**. The check part chose plain resolution time
   (97.5% match) over "waits on others paused" (89.5%). On the test months the rule matches the
   flag **97.8%** of the time. Critical and High (207 test incidents) are flagged missed 98.6% of the
   time whatever happened, so they are left out of the benchmark.
2. **Pickup wait after 1 h** (`pickup_wait_after`). Pickup = the first event that is not "New".
   31.3% of test incidents went from New straight to Resolved: no pickup was recorded and their New
   time includes the fix, so we count **no** wait for them. This understates every saving.
3. **Pickers** at the 1-hour mark: priority field; still unassigned (state New, or no event yet);
   oldest first; logistic regression (C = 1.0 chosen on check, AUC 0.865 there); OpsLens (LightGBM).
   Each day each picker fast-tracks round(k × the day's incidents), best score first, ties oldest first.
4. **Saved** = missed by the rule as it happened, met once the pickup wait after 1 h is removed.
5. **CIs** by resampling whole test weeks (39 weeks; 5 busy weeks hold almost all incidents).
6. **Replication** (`realdesk.replicate_cards`): the same groups as cards R1–R3, measured on the
   test months; replicates if the gap keeps its sign with a CI excluding 0.
7. **Detectors** (`realdesk_watch.watch`): every day, spike (count), slowdown (share still open
   24 h after opening) and bounce (share passed on within 24 h), robust z ≥ 3.5 against the same kind
   of day in the 28 days before. **Plants** (`eval/realdesk_plants.py`, eval only): one spike
   (×0.5–2.0), one 7-day slowdown (×1.5–3.0 resolution time), one 7-day bounce (15–40%) per set,
   seeds 9101–9120, in categories / teams with ≥ 8 incidents per weekday.
8. **Forecast candidates and alerts** (`realdesk.team_daily` → `forecast_candidates`,
   `bottleneck_alerts`): same day last week, learned, average of both; check weeks pick by WAPE.

## Worked example (real numbers, test months)
**One incident** (`fasttrack.example`). INC0024933, "3 - Moderate", opened Mon 2 May 2016 13:24,
resolved after 96.9 h → missed the 91 h limit (the company's flag says missed too). After its 14:24
mark it still waited 74.4 h for someone to pick it up; fast-tracked, it resolves after 22.5 h →
**saved**. It is the first incident OpsLens's 20% pick saves.

**The benchmark.** 7,269 test incidents (Moderate and Low), 6,947 with a resolution time, 1,674
missed by the rule (24.1%). Ceiling, everyone picked up at 1 h: **223 saved** (13.3% of misses).
At the 20% budget (1,447 incidents fast-tracked):

| Picker | Saved | 95% CI |
|---|---|---|
| Priority field (then oldest) | 29 | 18.2 – 44.2 |
| Oldest first | 29 | 18.2 – 44.2 |
| Logistic regression | 100 | 76.9 – 129.4 |
| **OpsLens (LightGBM)** | **108** | 86.5 – 136.9 |
| **Still unassigned at 1 hour** | **115** | 102.8 – 120.3 |

**Pre-registered rule: NOT passed.** The best other picker is "still unassigned at 1 hour":
OpsLens − unassigned = −7 [−30.5, +29.1]. OpsLens was ahead in 2 of the 5 busy weeks. OpsLens
does beat the desk's priority field clearly: +79 [+50.1, +111.7] misses saved.

**Why the simple rule ties OpsLens.** Fast-track only helps an incident that is still waiting at
1 hour. "Still unassigned" picks exactly those. OpsLens ranks by *risk of missing*, and many
risky incidents are already being worked on or waiting for the user — fast-tracking cannot save
them. Risk is not the same as *rescue* (the food world's lesson, seen again on real data).

**Impact, three headings (20%, OpsLens's pick, under the fast-track assumption).**
Turnaround: 108 misses avoided [86.5, 136.9] vs 29 for the priority field (ceiling 223); 84,011
pickup hours removed vs 15,299 (a few incidents waited for weeks, so this sum is dominated by them).
Productivity: no claim. Service quality: incidents meeting the deadline 75.9% → 77.5% (priority
field 76.3%, ceiling 79.1%). Money: not shown (no cost per missed deadline exists for this desk).

**Why 36.6% on the screen but 24.1% here.** 36.6% counts all 24,918 incidents. The 23,362 with a
resolution time missed 38.2%; the 1,556 without one were flagged missed only 11.9% (still open
when the log ends). And the test months are much better than March: the benchmark's 24.1% is the
rule on May's Moderate/Low incidents (the company flag says 22.0% on the same incidents).

**Replication: 3 of 3 cards still true on the test months.**
R1 (waits on someone outside the team): gap 43.3 → 45.8 points [39.5, 50.8].
R2 (picked up after more than 8 h): 31.7 → 37.7 [34.5, 41.5].
R3 (Category 26 passed between teams): 45.1 → 37.6 [26.5, 54.5].

**Blind plants: 9 of 60 found (15%).** Spikes 6 of 20 (5 of the 8 in the upper half of the size
range, delay 0 days: alert the same evening); slowdowns 0 of 20; bounces 3 of 20 (median delay 1
day). Clean test weeks: 9 alerts in 35 days = 7.7 per 30 days, 7 of them Category 28 on 7 weekdays
in a row (a real burst in the log, or a false alarm — we cannot tell). Example: Category 42 on
Mon 2 May had 101 incidents vs a usual 54.5 (MAD 6) → z 5.2 → alert.

**Forecast candidates.** Check weeks: learned 0.377, average 0.433, same day last week 0.567 →
learned chosen. Test weeks: average **0.326** (best), same day last week 0.341, learned 0.365 (worst).
The check weeks picked the candidate that did worst later — reported as it is.

**Alerts, 240 test team-days, 97 overloaded (40.4%).** Learned forecast: precision 77.6%, recall
92.8%; same day last week 76.6% / 84.5%; average 72.8% / 93.8%; calendar rule "every weekday"
54.0% / 97.9%. The forecast adds precision over the calendar, mostly on big teams (Group 70 and
Group 20: 90.9% / 100%); for teams that usually close 2–3 incidents a day every weekday is an overload.

## Second looks (23 Oct)
**Rescue picker.** W3 showed that ranking by risk ties "still unassigned": fast-track only helps an
incident that is still waiting. OpsLens's food dispatcher ranks by *rescue*, so three rescue-style
pickers were written down first and the check weeks chose one: the **rescue model** (LightGBM trained
on the learning part to predict "would fast-track save this one?"; 77 saved on the check weeks, vs 59
for still unassigned). On the test months at 20%: **160 saved** [117.9, 208.6] vs 115 for still
unassigned and 108 for the risk score: +45 [0.0, 100.5]. The interval does not exclude zero, so the
rule is **not passed**. At 10% the gap is +46 [30.8, 66.7], at 30% +25 [5.1, 62.6] — clear at the
other two budgets, but the rule names 20%. Say it as it is: "the rescue model saved the most at every
budget; at the pre-registered 20% budget the gap is not proven".

**Detector v2.** Eight settings (slowdown signal "open after 24 h" or "not closed within 2 h", 1 or 3
days pooled, z 3.5 or 3.0) on 60 plants in the check weeks. Pooling 3 days found twice as many (18 of
60 vs 9) but no setting stayed within 10 false alarms per 30 clean check days (fewest: 15.0, the v1
setting). The pre-registered fallback kept the fewest-false-alarm setting, which is v1, so v2 = v1:
**11 of 60** fresh test plants for both, 7.7 false alarms per 30 days. Not passed. The honest lesson:
on this log, every setting that finds more plants also raises more false alarms than the limit we set first.

## Weaknesses
- **The fast-track is an assumption**, not a replay: we remove waiting time and keep everything else.
  In real life a fast lane can slow the rest of the queue. Shown on screen.
- **Conservative pickup**: incidents that went New → Resolved count no wait. With "all New time is
  waiting" every number would be bigger; we chose the side that cannot flatter us.
- **5 busy weeks.** The test months are 5 dense weeks and a sparse tail; a week bootstrap with few
  real clusters can be too narrow. That is why `by_week` is shown.
- **Detectors are weak on this log.** A ×2–3 slowdown of a team that resolves most incidents in under
  an hour barely changes "still open after 24 h" — the slowdown detector watched the wrong signal for
  such teams (fixed before the run, so it stays). Daily noise in real categories hides spikes below
  about ×1.25. We report it instead of re-tuning on the test weeks.
- **Overload alerts** compare arrivals with "usual closures", which includes weekends; for small teams
  that makes most weekdays an overload, so the calendar rule is the honest reference.
- **One deadline rule per priority** is our reconstruction of a clock we cannot see (97.8% agreement).

## How to read the code
`eval/run_realdesk.py` → `main()` shows the order. Fast-track: `opslens/realdesk_fasttrack.py` →
`fasttrack_benchmark()` (calls `deadline_rule`, `pickup_wait_after`, `logistic_scores`,
`picker_scores`, `pick_daily`, `bootstrap_ci`), then `impact()`. Cards, forecast and alerts:
`opslens/realdesk.py` → `replicate_cards()`, `team_daily()` → `forecast_candidates()`,
`bottleneck_alerts()`. Detectors: `opslens/realdesk_watch.py` → `watch()`. Plants (eval only):
`eval/realdesk_plants.py` → `random_plant_set()`, `apply_plants()`, `score_set()`.
Tests: `tests/test_realdesk.py`, `tests/test_realdesk_v4.py`.
