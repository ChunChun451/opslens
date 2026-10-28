# OpsLens — the numbers

Generated from `eval/results.json` on 2026-10-29T00:11:25 (commit d822d1d). Do not edit by hand: run `mingw32-make eval`.


## The floor and the policy

Promises: P1 15 min, P2 30 min, P3 60 min. OpsLens is S2 (pre-registered in eval/PREREG_1530.md, commit c5f5f70): the likely-lost lane, the clock cross-skill test, live risk with a queue-aware clock. Its four estimates come from days 1-35 only.

Pre-registered test-day run (days 43-56, seeds [1, 2, 3, 4, 5], run once): **ship S2 on the 15/30/60 floor**.

| Policy | Missed % | P1 missed % | Late min / 100 |
|---|---|---|---|
| Industry standard | 20.74 | 13.16 | 4,463 |
| Least slack + rescue | 9.76 | 11.03 | 2,491 |
| OpsLens v5 (before S2) | 9.82 | 9.78 | 2,004 |
| OpsLens v5, routing alone | 10.85 | 10.15 | 2,656 |
| OpsLens (S2) | 8.79 | 8.08 | 1,766 |
| OpsLens (S2), routing alone | 9.83 | 8.37 | 2,636 |

Earlier floor for reference (P1 1 h, P2 4 h, P3 24 h; OpsLens v5; not comparable ticket by ticket): OpsLens 2.05%, industry standard 5.51%, least slack + rescue 2.98%.

Data: 107,476 tickets over 56 days; train days [1, 35], validation [36, 42], test [43, 56]. Simulator seeds [1, 2, 3, 4, 5].

## Baseline vs OpsLens (test days, mean ± std over seeds)

| KPI | Baseline A (FIFO) | Baseline B (priority) | Industry standard (skills routing) | OpsLens | OpsLens − industry standard (95% CI) | OpsLens − B (95% CI) |
|---|---|---|---|---|---|---|
| SLA breach % | 25.16 ± 3.33 | 21.94 ± 2.91 | 20.74 ± 3.26 | **8.79** ± 0.91 | -11.95 [-14.88, -9.02] | -13.15 [-15.63, -10.67] |
| P90 resolution (min) | 159.29 ± 48.05 | 154.85 ± 36.15 | 156.40 ± 34.47 | **39.86** ± 4.23 | -116.53 [-155.99, -77.08] | -114.99 [-155.31, -74.66] |
| Mean wait (min) | 46.07 ± 10.59 | 47.77 ± 10.77 | 48.60 ± 11.91 | **14.62** ± 5.68 | -33.98 [-43.12, -24.84] | -33.15 [-40.29, -26.01] |
| Max backlog (tickets) | 428.00 ± 148.11 | 447.80 ± 146.62 | 386.40 ± 124.67 | **257.60** ± 80.05 | -128.80 [-188.89, -68.71] | -190.20 [-277.23, -103.17] |
| Transfers per 100 | 4.54 ± 0.07 | 4.67 ± 0.05 | 1.10 ± 0.03 | **1.00** ± 0.04 | -0.10 [-0.12, -0.07] | -3.67 [-3.75, -3.59] |
| Tickets per agent-hour | 7.85 ± 0.13 | 7.85 ± 0.13 | 7.85 ± 0.13 | **7.84** ± 0.14 | -0.00 [-0.02, +0.01] | -0.00 [-0.02, +0.01] |
| Reopen rate % | 4.00 ± 0.08 | 4.00 ± 0.08 | 4.00 ± 0.08 | **4.73** ± 0.12 | +0.72 [+0.62, +0.82] | +0.72 [+0.62, +0.82] |
| P99 wait (min) | 758.53 ± 26.31 | 818.67 ± 96.96 | 797.64 ± 98.36 | **410.25** ± 186.77 | -387.39 [-514.65, -260.13] | -408.43 [-536.92, -279.93] |
| Load fairness (std of utilisation) | 0.12 ± 0.00 | 0.13 ± 0.00 | 0.14 ± 0.00 | **0.12** ± 0.00 | -0.01 [-0.02, -0.00] | -0.00 [-0.01, +0.00] |
| P1 breach % | 21.84 ± 3.55 | 14.19 ± 3.09 | 13.16 ± 2.95 | **8.08** ± 0.37 | -5.08 [-8.37, -1.79] | -6.11 [-9.55, -2.67] |
| Hindi customers' breach % | 34.46 ± 3.72 | 32.14 ± 3.11 | 30.57 ± 3.45 | **11.70** ± 1.35 | -18.86 [-21.55, -16.17] | -20.43 [-22.67, -18.20] |

OpsLens − Baseline A, breach %: -16.37 [-19.39, -13.36].

## Which part creates the gain (ablations, test days)

| Variant | Breach % | Δ vs full | P90 (min) |
|---|---|---|---|
| OpsLens (full) | 8.79 | +0.00 [+0.00, +0.00] | 39.9 |
| without staffing plan | 9.83 | +1.04 [+0.76, +1.33] | 44.7 |
| without the learned risk model (clock only) | 8.82 | +0.03 [-0.12, +0.18] | 40.3 |
| without the likely-lost lane | 9.35 | +0.57 [+0.31, +0.82] | 41.3 |
| without the clock cross-skill test (old 0.5 rule) | 8.78 | -0.01 [-0.07, +0.05] | 41.1 |
| without the queue-aware clock | 9.33 | +0.55 [+0.39, +0.70] | 41.1 |
| without optimiser (greedy per agent) | 8.87 | +0.09 [-0.07, +0.25] | 40.3 |
| without classifier (menu choice routing) | 9.74 | +0.95 [+0.87, +1.03] | 44.2 |
| without scarcity cost | 8.81 | +0.03 [-0.07, +0.13] | 40.4 |

## Stress tests (conditions never seen in training)

| Scenario | Baseline A | Baseline B | OpsLens | OpsLens − B |
|---|---|---|---|---|
| +25% volume | 51.14% | 43.57% | **18.15%** | -25.42 [-28.53, -22.31] |
| 10% absenteeism | 32.58% | 27.83% | **11.30%** | -16.53 [-18.89, -14.17] |

## Gold-customer weight sensitivity

| Gold weight | Breach % (all) | Breach % (gold) |
|---|---|---|
| ×1.0 | 8.84 | 9.17 |
| ×1.5 | 8.79 | 6.44 |
| ×2.0 | 8.91 | 6.04 |

## Patterns

- Planted problems (main data): found 4/5, diagnosed 4/5; false alarms 1.
- Blind test: 52/60 random plants found (86.7%) over 20 datasets; diagnosed 86.7%.
- Live detection of the unseen day-47 surge: 60 min; false alerts 0.0 per week.

## Classification (test days)

- Menu choice 90.8% → local 98.20% → cascade 98.22%; LLM alone 91.5% (400 tickets).
- Sent to the LLM: 1.35%. Wrong-team routing per 100: 5.78 → 1.26.

## Risk model (test days)

- AUC 0.973 (time-left rule 0.671), PR-AUC 0.991, top-10% precision 0.999, Brier 0.0539; at arrival AUC 0.956.
- Real ServiceNow data (UCI, 7,476 test incidents): AUC 0.857 vs priority rule 0.552.

## Forecast (test days)

- WAPE 0.265 vs same-hour-last-week 0.355 (Poisson floor 0.228).
- Conformal coverage: 80% range 78.3%, 90% range 88.9%.

## A stronger baseline: the "SLA due" sort, and how late the late customers are (test days)

| KPI | Baseline A (FIFO) | Baseline B (priority) | Baseline C (SLA due) | Industry standard (skills routing) | OpsLens | OpsLens − C (95% CI) |
|---|---|---|---|---|---|---|
| SLA breach % | 25.16 | 21.94 | 15.20 | 20.74 | 8.79 | -6.42 [-7.27, -5.57] |
| P1 breach % | 21.84 | 14.19 | 13.38 | 13.16 | 8.08 | -5.30 [-7.48, -3.11] |
| Minutes late, mean over breached tickets | 168.67 | 202.87 | 310.91 | 212.84 | 197.03 | -113.88 [-146.09, -81.66] |
| Minutes late per 100 tickets (all customers) | 4,287.82 | 4,495.63 | 4,775.13 | 4,462.99 | 1,765.69 | -3009.44 [-3642.03, -2376.84] |
| P99 wait (min) | 758.53 | 818.67 | 991.00 | 797.64 | 410.25 | -580.76 [-658.84, -502.67] |

- Baselines C and D have no weights, so nothing was tuned; they ran on validation days first, then once on test days.
- OpsLens − industry standard, breach %: -11.95 [-14.88, -9.02].

## The strongest published rules, and what perfect information buys them (test days)

| KPI | C: SLA due (EDF) | D: industry standard | Least slack first | Generalized c-mu | OpsLens | Clairvoyant least slack* | Clairvoyant least slack + staffing* |
|---|---|---|---|---|---|---|---|
| SLA breach % | 15.20 | 20.74 | 11.59 | 21.48 | 8.79 | 10.24 | 9.76 |
| P1 breach % | 13.38 | 13.16 | 11.60 | 16.42 | 8.08 | 10.69 | 10.39 |
| Minutes late, mean over breached tickets | 310.91 | 212.84 | 372.22 | 168.29 | 197.03 | 399.49 | 368.75 |
| Minutes late per 100 tickets | 4,775.13 | 4,462.99 | 4,353.68 | 3,650.46 | 1,765.69 | 4,127.36 | 3,622.68 |
| P99 wait (min) | 991.00 | 797.64 | 938.63 | 816.54 | 410.25 | 920.24 | 888.21 |

*Not implementable: knows each ticket's true category and true handle time. Not the optimum either (the true optimum for this many tickets cannot be computed).

| OpsLens − … | Breach % (95% CI) | Late minutes per 100 (95% CI) |
|---|---|---|
| C: SLA due (EDF) | -6.42 [-7.27, -5.57] | -3009 [-3642, -2377] |
| D: industry standard | -11.95 [-14.88, -9.02] | -2697 [-3451, -1944] |
| Least slack first | -2.80 [-2.90, -2.69] | -2588 [-3147, -2029] |
| Generalized c-mu | -12.69 [-15.98, -9.41] | -1885 [-2277, -1493] |
| Clairvoyant least slack* | -1.46 [-1.75, -1.16] | -2362 [-2824, -1899] |
| Clairvoyant least slack + staffing* | -0.97 [-1.35, -0.59] | -1857 [-2476, -1238] |

- What perfect information buys the best rule (clairvoyant − least slack), breach %: -1.34 [-1.54, -1.15].
- Chosen on validation days 36-42 only: c-mu tau 0.5, beta 1.0 (of 8 shapes; lowest validation breach %, ties broken by fewer late minutes per 100). Validation breach %: OpsLens 7.15, least slack 9.64, c-mu 15.09 → gate passed; test days run once.

### Least slack + cross-skill rescue (the same freedom as OpsLens)

| KPI | Least slack first | Least slack + cross-skill rescue | OpsLens |
|---|---|---|---|
| SLA breach % | 11.59 | 9.76 | 8.79 |
| P1 breach % | 11.60 | 11.03 | 8.08 |
| Minutes late, mean over breached tickets | 372.22 | 251.77 | 197.03 |
| Minutes late per 100 tickets | 4,353.68 | 2,490.56 | 1,765.69 |
| P99 wait (min) | 938.63 | 660.40 | 410.25 |
| Reopen rate % | 4.00 | 4.84 | 4.73 |

| OpsLens − … | Breach % (95% CI) | Late minutes per 100 (95% CI) | Reopen rate % (95% CI) |
|---|---|---|---|
| Least slack + cross-skill rescue | -0.98 [-1.28, -0.67] | -725 [-931, -519] | -0.11 [-0.19, -0.04] |
| Least slack first | -2.80 [-2.90, -2.69] | -2588 [-3147, -2029] | +0.72 [+0.62, +0.82] |

- What the rescue buys least slack (rescue − plain), breach %: -1.82 [-2.04, -1.60].
- Rule: when no skilled agent is free and a ticket's slack is below the threshold but a 1.6× slower job can still make the SLA, a free agent with the language takes it as a deliberate cross-skill job. Threshold chosen on validation days 36-42 only (lowest validation breach %, ties broken by fewer late minutes per 100): 10 min. Validation breach %: 2 min 9.58%, 5 min 8.15%, 10 min 7.84%, 15 min 8.17%, 20 min 8.27%, 30 min 9.05%, 60 min 9.68%, 120 min 9.68%, 240 min 9.68%; OpsLens 7.15 → gate passed; test days run once. OpsLens and plain least slack were run again beside it and reproduced exactly: yes.

## The real public service desk (UCI ServiceNow log, CC BY 4.0)

- 24,918 incidents, 70 teams, 234 agents; 36.6% missed their SLA, 45.6% were passed between teams. Learning 2016-02-29 to 2016-05-02; test 2016-05-02 to 2017-02-16 (7,476 incidents).
- Where open time goes: being worked on 35.4%, waiting for a vendor 6.4%, waiting for another fix 2.5%, waiting for the user 31.4%, waiting to be picked up 24.3%.
- Incidents that wait on someone outside the team miss their SLA 2.4× as often: 74.5 vs 31.2 (incidents that never waited).
- 24% of all open time is spent waiting for someone to pick the incident up: 64.8 vs 33.1 (incidents picked up within 8 h).
- Category 26: 57% of incidents are passed between teams: 58.2 vs 13.1 (Category 26 incidents that stayed with one team).

| On the test months | OpsLens | What the desk used |
|---|---|---|
| SLA-miss warning 1 h after opening (AUC) | 0.857 | priority field 0.552 |
| Share of all SLA misses in the riskiest 20% | 49.9% | 24.6% |
| Daily new incidents per team (WAPE, lower is better) | 0.365 | same day last week 0.341 |
| Right team first time (OpsLens only when sure, 54% of incidents) | 78.2% | desk on the same incidents 77.8% |

- Not better than the desk: the forecast (check weeks chose learned (LightGBM)) and team routing (net +19 incidents: 319 fixed, 300 made wrong). Reported, not claimed.

### Real desk, Plan v4: fast-track 20% of each day's new incidents (test months)

Assumption: A log cannot be replayed. We assume a fast-tracked incident is picked up the moment its first hour ends and that everything after the pickup happens exactly as it really did.

| Picker | Misses saved | 95% CI |
|---|---|---|
| The desk's priority field (then oldest) | 29 | 18.2 - 44.2 |
| Still unassigned at 1 hour (then oldest) | 115 | 102.8 - 120.3 |
| Oldest first | 29 | 18.2 - 44.2 |
| Logistic regression, same features as OpsLens | 100 | 76.9 - 129.4 |
| OpsLens early warning (LightGBM) | 108 | 86.5 - 136.9 |

- Ceiling (everyone fast-tracked): 223 saved. Pre-registered rule (OpsLens beats the best other picker, Still unassigned at 1 hour (then oldest)): NOT passed, -7 [-30.5, 29.1].
- Findings still true on later months: 3 of 3.
- Blind plants in the real log: 9 of 60 found (15.0%); false alarms 7.7 per 30 clean days.
- Week-ahead overload alerts (learned): precision 77.6%, recall 92.8% vs every weekday 54.0% / 97.9%.

## How close to perfect (test days)

- Physical floor: 4.72% of tickets breach even with unlimited agents and perfect routing (their own work and reopens exceed the SLA, or nobody on shift speaks their language).
- OpsLens is 4.06 points above that floor and captures 75% ± 1 of the improvement possible over the industry standard: (D − OpsLens) ÷ (D − floor), per seed.

## New sealed world (data seed 9393, corrected simulator, run once)

| KPI | Industry standard | Least slack first | Least slack + rescue | Generalized c-mu | OpsLens | Floor |
|---|---|---|---|---|---|---|
| SLA breach % | 18.73 | 10.95 | 9.24 | 19.49 | 8.16 | 4.54 |
| Minutes late per 100 tickets | 3,625.15 | 3,577.74 | 2,003.51 | 3,006.13 | 1,384.76 | — |

- Share of the possible improvement captured: 74% ± 1. Retrained risk AUC 0.969. New world (unused seed 9393) generated after OpsLens S2 was frozen on the 15/30/60 floor; weights and estimates unchanged, routine retraining of the classifier, risk model and forecast; run once.

## Sealed second world (data seed 4242, generated after the freeze, run once)

> Earlier food floor (P1 1 h, P2 4 h, P3 24 h promises), OpsLens v5. Not yet re-run on the 15/30/60 floor.

| KPI | Baseline A (FIFO) | Baseline B (priority) | Baseline C (SLA due) | OpsLens |
|---|---|---|---|---|
| SLA breach % | 15.22 | 8.21 | 6.13 | 3.07 |
| Minutes late per 100 tickets | 3,433.60 | 2,989.54 | 5,326.21 | 893.19 |

- OpsLens − Baseline C, breach %: -3.06 [-3.67, -2.45]. Retrained risk AUC 0.970. Classifier: cascade (local + LLM). Weights unchanged.

## Sealed world re-run with every baseline (data seed 4242)

> Earlier food floor (P1 1 h, P2 4 h, P3 24 h promises), OpsLens v5. Not yet re-run on the 15/30/60 floor.

| KPI | C: SLA due (EDF) | D: industry standard | Least slack first | Generalized c-mu | OpsLens | Clairvoyant least slack* | Clairvoyant least slack + staffing* |
|---|---|---|---|---|---|---|---|
| SLA breach % | 6.13 | 6.34 | 4.21 | 6.12 | 3.07 | 4.00 | 3.68 |
| P1 breach % | 9.94 | 7.57 | 7.21 | 8.75 | 5.34 | 6.84 | 6.27 |
| Minutes late, mean over breached tickets | 850.06 | 277.20 | 1,064.46 | 236.36 | 283.71 | 1,067.68 | 810.24 |
| Minutes late per 100 tickets | 5,326.21 | 1,771.11 | 4,559.95 | 1,445.45 | 893.19 | 4,348.15 | 3,029.47 |
| P99 wait (min) | 1,687.74 | 992.40 | 1,672.73 | 950.40 | 744.04 | 1,615.99 | 1,155.38 |

- OpsLens − D, breach %: -3.27 [-4.45, -2.10]; − least slack -1.15 [-1.35, -0.94]; − c-mu -3.06 [-4.40, -1.71]. Retrained risk AUC 0.970. Classifier: cascade (local + LLM).
- Baselines were added after the first sealed run, so this world was run a second time (the first run is kept above, unchanged). OpsLens weights and the c-mu shape are frozen; nothing was chosen on this world.

Least slack + cross-skill rescue (added after the re-run; this world built a third time, only this rule run beside OpsLens and plain least slack):

| KPI | Least slack first | Least slack + cross-skill rescue | OpsLens |
|---|---|---|---|
| SLA breach % | 4.21 | 3.35 | 3.07 |
| P1 breach % | 7.21 | 5.84 | 5.34 |
| Minutes late, mean over breached tickets | 1,064.46 | 726.62 | 283.71 |
| Minutes late per 100 tickets | 4,559.95 | 2,525.42 | 893.19 |
| P99 wait (min) | 1,672.73 | 1,064.51 | 744.04 |
| Reopen rate % | 3.93 | 4.05 | 4.29 |

- OpsLens − least slack + rescue: breach % -0.28 [-0.40, -0.16], late minutes per 100 -1632 [-2767, -498], reopen rate % +0.24 [+0.16, +0.32]. OpsLens and plain least slack reproduced the re-run exactly: yes.
- Policies in both runs (baseline_a, baseline_b, baseline_c, opslens): per-seed results identical to the first run.

## Fix-at-source playbooks (test days, change vs the same policy without it)

| Playbook | Owner | Tickets prevented | Breaches: priority-first | Breaches: OpsLens | Agent-hours (OpsLens) |
|---|---|---|---|---|---|
| Cross-train 2 Hindi-speaking agents on payment failure and refund | Training / workforce | 0 | -167.4 [-295.5, -39.3] | -91.8 [-150.3, -33.3] | -26.3 |
| Fix the phone menu (IVR) | Product / IVR team | 0 | -398.0 [-539.4, -256.6] | -4.6 [-51.4, +42.2] | -7.5 |
| Self-serve instant refund on weekday dinner (Team C) | Product | 195 | -137.6 [-267.5, -7.7] | -56.4 [-86.2, -26.6] | -15.0 |
| Status banner the moment a spike alert fires | Product / customer comms | 41 | -226.0 [-352.6, -99.4] | -62.4 [-83.8, -41.0] | -8.1 |
| Kitchen order-check for restaurant cluster 17 | Partner operations | 69 | -26.0 [-78.1, +26.1] | -26.0 [-75.2, +23.2] | -7.6 |
| Status banner the moment a spike alert fires | Product / customer comms | 41 | -226.0 [-352.6, -99.4] | -62.4 [-83.8, -41.0] | -8.1 |
| **All together** | | 325 | -1127.4 [-1264.0, -990.8] | -294.8 [-369.4, -220.2] | -68.8 |

- OpsLens with every playbook vs priority-first today: breaches -3809.8 [-4523.9, -3095.7] (of 5864), breach % -14.2 [-16.8, -11.5] points.
- Assumptions (labelled in config/playbooks.yaml) were re-run at their low and high values; see `playbooks[].sensitivity` in results.json.

## Your plan: each recommendation alone (test days, change vs OpsLens with nothing accepted)

Without the plan: breach 9.83%. Change with 95% CI over the seeds.

| Item | Missed SLA (customers) | Mean resolution (min) | Agent-hours | Minutes past SLA per 100 |
|---|---|---|---|---|
| Feroz A. (D08, Team D): day off on Thu instead of Sun (days 43-49) | -78.8 [-122.4, -35.2] | -2.4 [-4.1, -0.7] | -1.5 [-4.3, +1.4] | -218 [-387, -49] |
| Amit T. (D04, Team D): start 07:00 instead of 08:00 (days 43-49) | +9.8 [-31.0, +50.6] | +0.4 [-0.1, +0.9] | -0.3 [-0.9, +0.3] | +34 [-19, +87] |
| Sneh Y. (C03, Team C): start 08:00 instead of 06:00 (days 43-49) | +2.4 [-1.9, +6.7] | +0.0 [-0.1, +0.1] | +0.2 [-0.2, +0.5] | -0 [-6, +5] |
| Neha G. (A04, Team B): day off on Wed instead of Mon (days 43-49) | -16.6 [-33.0, -0.2] | -0.2 [-0.6, +0.2] | -0.4 [-1.3, +0.5] | -17 [-55, +22] |
| Nikhil A. (B08, Team B): start 15:00 instead of 14:00 (days 43-49) | -17.6 [-39.1, +3.9] | -0.4 [-0.7, -0.0] | -0.3 [-1.2, +0.6] | -33 [-67, +1] |
| Pooja V. (B05, Team B): start 08:00 instead of 06:00 (days 43-49) | -9.8 [-28.7, +9.1] | -0.5 [-1.7, +0.6] | -1.5 [-4.3, +1.4] | -54 [-163, +55] |
| Neha G. (A04, Team B): day off on Wed instead of Mon (days 50-56) | -68.4 [-88.9, -47.9] | -3.3 [-5.7, -1.0] | -1.6 [-3.7, +0.5] | -322 [-555, -89] |
| Chetan G. (D06, Team D): day off on Thu instead of Mon (days 50-56) | -71.8 [-124.6, -19.0] | -4.0 [-5.6, -2.5] | -1.7 [-4.6, +1.2] | -395 [-557, -232] |
| Amit T. (D04, Team D): start 07:00 instead of 08:00 (days 50-56) | -9.6 [-50.8, +31.6] | -0.0 [-1.1, +1.0] | -0.9 [-2.5, +0.8] | -4 [-109, +101] |
| Kavita D. (B01, Team B): day off on Tue instead of Mon (days 50-56) | -46.0 [-88.2, -3.8] | -2.1 [-4.0, -0.2] | -1.2 [-2.4, +0.1] | -208 [-397, -19] |
| Nikhil A. (B08, Team B): start 15:00 instead of 14:00 (days 50-56) | -6.0 [-31.6, +19.6] | +0.2 [-0.4, +0.7] | +0.2 [-1.1, +1.5] | +17 [-37, +70] |
| Sneh Y. (C03, Team C): start 08:00 instead of 06:00 (days 50-56) | +7.0 [+3.1, +10.9] | +0.2 [+0.0, +0.4] | +0.4 [-0.0, +0.8] | +19 [+0, +38] |
| Cross-train 2 Hindi-speaking agents on payment failure and refund (days 43-56) | -131.0 [-173.5, -88.5] | -3.3 [-5.0, -1.7] | -28.0 [-36.0, -20.0] | -316 [-473, -158] |
| Fix the phone menu (IVR) (days 43-56) | -29.4 [-82.7, +23.9] | -0.5 [-1.3, +0.3] | -7.1 [-9.2, -5.1] | -43 [-119, +34] |
| Self-serve instant refund on weekday dinner (Team C) (days 43-56) | -73.8 [-103.7, -43.9] | -1.4 [-2.2, -0.6] | -15.6 [-17.4, -13.8] | -130 [-208, -53] |
| Status banner the moment a spike alert fires (days 43-56) | -60.6 [-83.0, -38.2] | -1.0 [-1.2, -0.7] | -8.0 [-9.9, -6.1] | -84 [-109, -59] |
| Kitchen order-check for restaurant cluster 17 (days 43-56) | -24.6 [-87.8, +38.6] | -0.6 [-1.5, +0.2] | -7.2 [-9.8, -4.6] | -59 [-140, +22] |
| Status banner the moment a spike alert fires (days 43-56) | -60.6 [-83.0, -38.2] | -1.0 [-1.2, -0.7] | -8.0 [-9.9, -6.1] | -84 [-109, -59] |
| **All items together** | -574.0 [-643.3, -504.7] | -14.9 [-23.0, -6.9] | -73.9 [-82.5, -65.4] | -1384 [-2215, -553] |

## Day by day (test days, 5 seeds)

OpsLens missed fewer deadlines than the industry standard on 14 of 14 days. Daily rows add up exactly to the totals: True.

| Day | Tickets | Industry standard | OpsLens |
|---|---|---|---|
| Mon 12 Oct | 1,639 | 27.80% | 9.04% |
| Tue 13 Oct | 1,689 | 11.84% | 5.20% |
| Wed 14 Oct | 1,852 | 15.77% | 7.73% |
| Thu 15 Oct | 1,714 | 11.11% | 6.50% |
| Fri 16 Oct | 1,884 | 18.50% | 10.20% |
| Sat 17 Oct | 2,165 | 22.83% | 6.58% |
| Sun 18 Oct | 2,004 | 23.27% | 7.01% |
| Mon 19 Oct | 2,546 | 53.06% | 20.52% |
| Tue 20 Oct | 1,840 | 21.87% | 7.20% |
| Wed 21 Oct | 1,779 | 12.29% | 6.54% |
| Thu 22 Oct | 1,853 | 13.93% | 7.24% |
| Fri 23 Oct | 1,685 | 10.11% | 5.84% |
| Sat 24 Oct | 1,904 | 10.35% | 6.13% |
| Sun 25 Oct | 2,174 | 22.93% | 12.07% |

## Agents with several chats at once (test days, 5 seeds)

A chat started while k-1 others are open takes x(1 + s(k-1)); s is an assumption. 'Equal load' raises
the volume by k/(1+s(k-1)) so the floor is as busy as today.

| Chats (k) | Slowdown (s) | Load | Volume | First come | Urgent first | SLA due | Industry std | OpsLens | OpsLens - industry [95% CI] |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 0.25 | equal load | x1.60 | 24.18% | 21.06% | 15.71% | 19.72% | 8.98% | -10.74 [-13.09, -8.39] |
| 2 | 0.25 | today | x1.00 | 10.01% | 9.55% | 8.78% | 9.15% | 5.31% | -3.84 [-4.19, -3.49] |
| 2 | 0.50 | equal load | x1.33 | 25.36% | 22.62% | 17.10% | 20.92% | 10.91% | -10.00 [-12.33, -7.67] |
| 2 | 0.50 | today | x1.00 | 13.31% | 12.43% | 10.92% | 11.79% | 6.52% | -5.27 [-6.44, -4.10] |
| 3 | 0.25 | equal load | x2.00 | 24.28% | 21.30% | 16.31% | 19.63% | 9.87% | -9.76 [-11.89, -7.63] |
| 3 | 0.25 | today | x1.00 | 9.36% | 9.22% | 8.83% | 8.91% | 5.46% | -3.45 [-3.58, -3.32] |
| 3 | 0.50 | equal load | x1.50 | 26.69% | 24.30% | 19.78% | 22.03% | 14.01% | -8.01 [-9.96, -6.06] |
| 3 | 0.50 | today | x1.00 | 12.70% | 12.26% | 11.40% | 11.52% | 7.24% | -4.28 [-4.98, -3.57] |

Pre-registered rule (OpsLens beats industry standard in all four equal-load settings): PASSED. Optimiser ablation at k = 3, s = 0.25: greedy - min-cost flow +0.19 [+0.05, +0.33] points.

## 30 random worlds we did not design (test days, 3 seeds each)

> Earlier food floor (P1 1 h, P2 4 h, P3 24 h promises), OpsLens v5. Not yet re-run on the 15/30/60 floor.

OpsLens lowest (within 0.05 points) in 19 of 30 worlds (rule needs 27); median OpsLens - industry standard -8.19 points, 95% CI [-12.20, -3.28]. Rule NOT passed.
Breakdown (from the same runs, added after them): OpsLens beats the industry standard in 29 of 30; it is lowest in 13 of 13 worlds up to x1.05 today's load and 6 of 17 heavier ones. All 11 losses are to least_slack, at x1.06 load or more; in 10 of them OpsLens keeps late customers less late.
Diagnosis of the 11 losses (same worlds rebuilt, reproduced exactly: True; analysis after the result): OpsLens misses fewer gold customers in 11, keeps late customers less late in 11, fewer P1 in 4, fewer Hindi in 5.

| World | Volume | Chats | Mismatch | Industry std | Least slack | OpsLens | Best other |
|---|---|---|---|---|---|---|---|
| 7001 | x1.91 | 3 | x1.81 | 23.85% | 11.10% | 14.50% | least_slack |
| 7002 | x1.10 | 1 | x1.29 | 24.16% | 9.89% | 7.34% | least_slack |
| 7003 | x0.91 | 1 | x1.81 | 3.50% | 3.16% | 1.66% | least_slack |
| 7004 | x0.87 | 1 | x1.43 | 6.86% | 4.92% | 2.88% | least_slack |
| 7005 | x1.30 | 1 | x1.27 | 41.16% | 15.12% | 16.86% | least_slack |
| 7006 | x1.57 | 2 | x1.41 | 48.10% | 20.49% | 25.41% | least_slack |
| 7007 | x2.85 | 2 | x1.37 | 21.21% | 11.57% | 12.79% | least_slack |
| 7008 | x1.97 | 3 | x1.47 | 30.44% | 11.68% | 17.10% | least_slack |
| 7009 | x1.08 | 1 | x1.94 | 7.13% | 3.92% | 3.24% | least_slack |
| 7010 | x2.28 | 3 | x1.21 | 4.49% | 2.85% | 2.87% | least_slack |
| 7011 | x1.39 | 3 | x1.70 | 4.36% | 3.74% | 4.75% | least_slack |
| 7012 | x1.32 | 3 | x1.77 | 20.53% | 8.74% | 7.84% | least_slack |
| 7013 | x0.89 | 1 | x1.28 | 29.02% | 14.74% | 11.22% | least_slack |
| 7014 | x1.23 | 1 | x1.80 | 23.31% | 9.91% | 11.69% | least_slack |
| 7015 | x3.10 | 3 | x1.57 | 22.44% | 12.39% | 11.35% | least_slack |
| 7016 | x1.13 | 2 | x1.50 | 5.72% | 4.42% | 3.04% | least_slack |
| 7017 | x2.19 | 2 | x1.91 | 11.18% | 5.81% | 3.82% | least_slack |
| 7018 | x1.23 | 2 | x1.35 | 23.29% | 9.88% | 8.55% | least_slack |
| 7019 | x2.00 | 2 | x1.98 | 34.62% | 10.89% | 13.50% | least_slack |
| 7020 | x1.13 | 1 | x1.63 | 7.11% | 4.11% | 2.90% | least_slack |
| 7021 | x1.27 | 3 | x1.97 | 3.15% | 2.86% | 1.58% | least_slack |
| 7022 | x0.80 | 1 | x1.45 | 4.18% | 3.77% | 1.90% | least_slack |
| 7023 | x2.26 | 3 | x1.90 | 46.96% | 22.92% | 27.46% | least_slack |
| 7024 | x0.92 | 3 | x1.32 | 5.88% | 5.00% | 3.31% | least_slack |
| 7025 | x1.23 | 1 | x1.46 | 45.13% | 14.56% | 19.65% | least_slack |
| 7026 | x2.39 | 3 | x1.77 | 21.40% | 9.95% | 13.43% | least_slack |
| 7027 | x1.34 | 2 | x1.90 | 3.90% | 3.34% | 2.50% | least_slack |
| 7028 | x1.45 | 3 | x1.37 | 6.22% | 4.77% | 3.67% | least_slack |
| 7029 | x1.14 | 2 | x1.54 | 17.36% | 7.25% | 5.64% | least_slack |
| 7030 | x1.54 | 2 | x1.27 | 4.46% | 3.69% | 2.86% | least_slack |

## v6 overload mode: adoption test (candidate C, run once)

> Earlier food floor (P1 1 h, P2 4 h, P3 24 h promises), OpsLens v5. Not yet re-run on the 15/30/60 floor.

Main validation days, 20 fresh seeds: v6 - v5 -0.006 [-0.028, +0.017] points (gate: upper bound below +0.05) - passed. 30 NEW worlds: v6 lowest (within 0.05 points) in 18 (rule needs 27; v5 in the same worlds: 16); v6 better than v5 in 15, worse in 6, mean -0.26 points. Beats the industry standard: v6 30 of 30, v5 30 of 30. Adopted: no - v5 stays.

## Challenger arena (pre-registered: ship only if > 2% better AND within the latency budget)

> Earlier food floor (P1 1 h, P2 4 h, P3 24 h promises), OpsLens v5. Not yet re-run on the 15/30/60 floor.

- Forecast: Chronos-2 (zero-shot) WAPE 0.304 vs LightGBM 0.305 (+0.4%), 80% coverage 76.2% vs 79.2%; one 48 h refresh 1.7 s → **keep LightGBM**.
- Risk: TabPFN-3 not run yet (needs a TabPFN licence key).

## Speed

- Optimiser per decision: median 0.07 ms, max 3.4 ms.
- Scale test: 5,000 tickets × 500 agents solved in 0.048 s.
- Full evaluation pipeline: 156.9 min.
