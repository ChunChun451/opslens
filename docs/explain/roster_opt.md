# W5 — A CP-SAT weekly roster (pre-registered design)

## For the dashboard: exact shape (read this first)
`results.staffing_opt` (= `eval/parts/roster_opt.json`):
```
design:  {days: [36, 42], seeds, forecast, chosen: "cpsat_n4",
          rosters: {published | greedy | cpsat_n1..n4: [{first_day, weighted_shortage, changes: [{agent_id, team, change}],
                    status?, objective_agent_hours?, best_bound_agent_hours?, wall_s?}]},
          means: {roster: {breach_pct, late_minutes_per_100, p90_resolution_min}}, per_seed: {roster: {kpi: [..]}},
          chosen_minus_greedy | greedy_minus_published: {kpi: {mean_diff, ci95: [lo, hi]}}}
confirm: {seeds: 26..45, candidate, means, per_seed, candidate_minus_greedy, adopted: false}
test:    {days: [43, 56], seeds, greedy_equals_product_plan: true, rosters, means, per_seed,
          candidate_minus_greedy | greedy_minus_published | candidate_minus_published}
```
Proof-screen line: "We tried an exact roster optimiser (CP-SAT). It beats our greedy planner on the
planning score every week, but not on customers — so we keep the simple one."

## Results (22 Oct) — NOT adopted (pre-registered rule failed at the design stage)
| stage | published | greedy (product) | CP-SAT, N = 4 | CP-SAT − greedy, missed SLA |
|---|---|---|---|---|
| design, days 36–42, seeds 1–5 | 1.92% | 1.82% | 1.81% | −0.016 [−0.131, +0.099] |
| confirm, same week, seeds 26–45 | — | 1.81% | 1.78% | −0.034 [−0.071, +0.002] |
| test, days 43–56, seeds 1–5 (once) | 2.11% | **2.05%** | 2.25% | **+0.21 [+0.05, +0.37]** (worse) |

- **The search works:** weighted shortage (the objective) greedy → CP-SAT: 1,308 → 1,274 (validation),
  1,340 → 1,308 and 1,426 → 1,389 (test weeks). N = 1, 2 proven optimal in ~17 s; N = 3, 4 stop at 30 s.
- **The objective is the limit:** fitting the Erlang-C need harder does not lower missed SLAs, and on the
  test weeks it raises them. The P80 forecast's errors and the dispatcher's cross-skill rescues decide
  the outcome more than an extra agent-hour where Erlang C asks for one.
- Secondary: in the confirmation CP-SAT's P90 resolution was 7.3 min better [−10.2, −4.5]; on test days
  it was not (+9.1 [−0.8, +19.1]). Greedy reproduces the product's plan and its 2.046% exactly.
- What we say: "We tried the exact optimiser. It wins on the planner's own score and ties or loses on
  customers, so the product keeps the simple, readable moves." Next lever (not done): an objective
  measured in simulated breaches, not in Erlang shortfall.

Plan v4, item W5. Owner: Claude 2. **Committed on 22 Oct 2026 before any W5 roster was built or
simulated.** Results are reported whatever they are.

Why: today `opslens/staffing.py` makes up to 6 greedy single moves a week, and removing the whole
staffing plan costs only +0.06 points (ablation). An operations-research judge asks: "is that the
plan's limit, or the greedy search's?" A real tour-scheduling optimiser answers it.
**Expectation stated before the run:** the headroom is small (+0.06 points for the whole plan),
so CP-SAT may well tie greedy. If it does, we report that and keep greedy.

## The model (`opslens/roster_opt.py`, OR-Tools CP-SAT)
- **Decides,** for each day agent (night agents, start 22:00, stay fixed): a start hour within ±2 h of
  today's and inside 06:00–16:00 (greedy's bounds), and **2 consecutive days off** (as every agent
  has today; 7 choices). Same people, same 9-hour shifts, same 5 working days → same hours per person.
  35 options per agent, exactly one chosen.
- **Coverage** per team and hour = Σ chosen options' presence (0.95 attendance, `shift_vector`).
- **Objective** (agent-hours, day hours 07:00–24:00, the greedy planner's own measure):
  Σ max(0, need − coverage) + 3 × Σ max(0, offered load − coverage) + 1.0 per changed agent
  (the greedy planner's `min_gain`). Integers ×100. Need = Erlang C at the forecast's P80 team band.
- **At most N changed agents per team per week**, N ∈ {1, 2, 3, 4} chosen on validation.
- Time limit 30 s per week, 8 workers; the result reports whether it was proven optimal.

## Evaluation
1. **Design (validation week, days 36–42).** A forecast that never saw days 36–42: LightGBM trained
   on days 8–28, early-stopped and conformal-fitted on days 29–35 (the product's method, shifted one
   week back). From it: the published roster, greedy moves (`plan_moves`, product settings), and
   CP-SAT for each N. Each roster runs OpsLens dispatch on days 36–42 (warm-up day 35), seeds 1–5,
   same tickets and luck. N\* = lowest mean breach %.
2. **Adoption rule:** CP-SAT(N\*) − greedy breach % has a paired 95% CI entirely below 0 on the design
   seeds, AND again on **20 fresh seeds (26–45)**, same validation week, N\* fixed. Also reported:
   minutes past SLA per 100 tickets, P90 resolution, shortage in agent-hours.
3. **Test days once (43–56),** whatever the outcome, with the product's own forecasts (plans made on
   days 42 and 49, as `eval/run_forecast.py`): published vs greedy vs CP-SAT(N\*), seeds 1–5.
4. If adopted: `eval/run_forecast.py` would switch planners and Claude 1 re-runs the plan items and
   `make eval` (every number that depends on the roster moves, on purpose). If not adopted, the
   product keeps greedy and the Proof screen says "we tried the exact optimiser; it ties".

## Output
`eval/run_roster_opt.py` → `eval/parts/roster_opt.json`; proposed `results.staffing_opt`.

## Amendments
(none yet)
