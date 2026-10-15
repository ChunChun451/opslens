# forecast.py and staffing.py — the next 48 hours, and who should work when

## What they do
- `forecast.py` predicts tickets per category for every hour ahead, with an 80% and a 90% range.
- It turns tickets into **work** (tickets × average handle minutes) per team.
- `staffing.py` uses **Erlang C** to compute how many agents each team needs per hour.
- It proposes **budget-neutral** changes (same people, same hours per week): move a shift start
  by 1–2 hours, or swap a day off to a quieter day.
- Bottlenecks = team-hours where the forecast's upper range needs more agents than scheduled.

## How the forecast works
1. Features known 48 hours ahead: hour, weekday, weekend, and the counts in the same hour
   1, 2, 3 and 4 weeks earlier (the most recent is 168 hours back, so no leakage).
2. LightGBM with a Poisson objective (the target is a count), trained on days 8–35.
3. Sale days: forecast as a normal day, then × the uplift measured on past sale days (1.17).
4. Range: split-conformal. On validation days we measure |actual − forecast| ÷ √(forecast + 1);
   the 80% quantile is q80 = 1.15. Range = forecast ± q80 × √(forecast + 1).

## Results (test days 43–56)
| | WAPE (hourly, per category) |
|---|---|
| OpsLens forecast | **0.305** |
| Same hour last week | 0.415 |
| Floor: a perfect forecast of Poisson counts | 0.280 |
- 80% range covered the truth **79.2%** of the time; 90% range **90.0%**.
- Per team-hour workload WAPE: 0.235 vs 0.321 for the naive forecast.
- Weakness: the festive sale day was under-forecast by **16.6%** (only one past sale to learn from).

## How staffing works
1. Needed agents per team-hour = the smallest N with Erlang-C average wait ≤ 15 min and
   utilisation ≤ 0.85, using the team's upper (80%) arrivals.
2. Scheduled = roster × 0.95 (absence).
3. Score = missing agent-hours, where hours with **more work than people** (backlog grows) count
   3×. Nights are excluded: three cross-trained night agents cover every team by design.
4. Greedy: try every small change for every agent, keep the best, repeat up to 6 times a week,
   one change per person. Plans are made weekly with data up to the planning day only.

## Worked example (plan for days 43–49, made on day 42)
Biggest bottleneck: Team C short by up to 5 agents, Saturday 19:00–24:00 (planted problem 2).
Moves chosen: **C05 takes Monday off instead of Saturday**, B02 (Arjun, Hindi + refunds) takes
Monday off instead of Friday, C06 Friday instead of Tuesday, and three morning starts at 07:00
instead of 08:00. Missing agent-hours 654 → 636. The simulator (M7) measures what that is worth.

## Weaknesses
- Team-by-team Erlang C ignores that cross-trained agents help other teams, so "needed" is
  conservative.
- The greedy search is simple and stops at 6 moves; a full scheduling solver could do more.

## How to read the code
`forecast.py`: `add_features()`, `train()`, `conformal_q()`. `staffing.py`: `agents_needed()`,
`plan_moves()`. Experiment: `eval/run_forecast.py`.
