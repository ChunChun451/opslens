# OpsLens — the numbers

Generated from `eval/results.json` on 2026-10-27T16:02:39 (commit e7960ab). Do not edit by hand: run `mingw32-make eval`.

Data: 64,257 tickets over 56 days; train days [1, 35], validation [36, 42], test [43, 56]. Simulator seeds [1, 2, 3, 4, 5].

## Baseline vs OpsLens (test days, mean ± std over seeds)

| KPI | Baseline A (FIFO) | Baseline B (priority) | Industry standard (skills routing) | OpsLens | OpsLens − industry standard (95% CI) | OpsLens − B (95% CI) |
|---|---|---|---|---|---|---|
| SLA breach % | 20.10 ± 3.24 | 17.33 ± 3.01 | 16.26 ± 3.27 | **11.66** ± 1.67 | -4.61 [-6.61, -2.60] | -5.68 [-7.38, -3.97] |
| P90 resolution (min) | 114.40 ± 39.24 | 117.97 ± 33.11 | 129.55 ± 33.68 | **82.65** ± 17.59 | -46.90 [-68.80, -25.00] | -35.32 [-56.87, -13.76] |
| Mean wait (min) | 35.38 ± 12.22 | 37.37 ± 12.93 | 39.96 ± 14.90 | **19.87** ± 6.51 | -20.09 [-30.88, -9.30] | -17.50 [-25.59, -9.42] |
| Max backlog (tickets) | 166.20 ± 79.85 | 168.20 ± 79.18 | 154.20 ± 62.25 | **144.80** ± 51.80 | -9.40 [-31.93, +13.13] | -23.40 [-60.95, +14.15] |
| Transfers per 100 | 4.27 ± 0.07 | 4.47 ± 0.10 | 1.31 ± 0.02 | **1.18** ± 0.05 | -0.12 [-0.19, -0.05] | -3.29 [-3.45, -3.12] |
| Tickets per agent-hour | 4.76 ± 0.09 | 4.76 ± 0.09 | 4.76 ± 0.09 | **4.76** ± 0.09 | -0.00 [-0.01, +0.01] | -0.00 [-0.01, +0.01] |
| Reopen rate % | 4.01 ± 0.09 | 4.01 ± 0.09 | 4.01 ± 0.09 | **4.64** ± 0.15 | +0.63 [+0.54, +0.71] | +0.63 [+0.54, +0.71] |
| P99 wait (min) | 613.15 ± 180.60 | 703.69 ± 253.37 | 680.98 ± 230.45 | **334.73** ± 197.75 | -346.25 [-504.07, -188.43] | -368.96 [-547.10, -190.83] |
| Load fairness (std of utilisation) | 0.12 ± 0.00 | 0.12 ± 0.01 | 0.13 ± 0.01 | **0.13** ± 0.01 | -0.00 [-0.02, +0.01] | +0.01 [-0.00, +0.02] |
| P1 breach % | 30.45 ± 1.98 | 24.51 ± 1.92 | 22.51 ± 1.53 | **22.73** ± 1.71 | +0.22 [-0.44, +0.89] | -1.78 [-2.21, -1.34] |
| Hindi customers' breach % | 29.40 ± 3.83 | 27.83 ± 3.95 | 26.41 ± 4.06 | **16.66** ± 2.83 | -9.75 [-11.53, -7.97] | -11.17 [-12.97, -9.37] |

OpsLens − Baseline A, breach %: -8.45 [-10.42, -6.47].

## Which part creates the gain (ablations, test days)

| Variant | Breach % | Δ vs full | P90 (min) |
|---|---|---|---|
| OpsLens (full) | 11.66 | +0.00 [+0.00, +0.00] | 82.7 |
| without staffing plan | 11.90 | +0.24 [+0.03, +0.45] | 85.4 |
| without risk scores | 12.97 | +1.31 [+0.17, +2.46] | 95.0 |
| without optimiser (greedy per agent) | 11.67 | +0.01 [-0.35, +0.38] | 82.6 |
| without classifier (menu choice routing) | 12.15 | +0.50 [+0.26, +0.73] | 91.3 |
| without scarcity cost | 11.63 | -0.03 [-0.10, +0.05] | 82.1 |

## Stress tests (conditions never seen in training)

| Scenario | Baseline A | Baseline B | OpsLens | OpsLens − B |
|---|---|---|---|---|
| +25% volume | 48.23% | 42.94% | **22.06%** | -20.88 [-24.80, -16.96] |
| 10% absenteeism | 27.00% | 23.62% | **14.61%** | -9.00 [-11.26, -6.75] |

## Gold-customer weight sensitivity

| Gold weight | Breach % (all) | Breach % (gold) |
|---|---|---|
| ×1.0 | 11.47 | 11.27 |
| ×1.5 | 11.66 | 10.10 |
| ×2.0 | 11.73 | 10.03 |

## Patterns

- Planted problems (main data): found 5/5, diagnosed 5/5; false alarms 0.
- Blind test: 48/60 random plants found (80.0%) over 20 datasets; diagnosed 78.3%.
- Live detection of the unseen day-47 surge: 60 min; false alerts 0.5 per week.

## Classification (test days)

- Menu choice 91.0% → local 97.67% → cascade 97.88%; LLM alone 90.8% (400 tickets).
- Sent to the LLM: 1.58%. Wrong-team routing per 100: 5.76 → 1.59.

## Risk model (test days)

- AUC 0.949 (time-left rule 0.796), PR-AUC 0.939, top-10% precision 0.999, Brier 0.0860; at arrival AUC 0.936.
- Real ServiceNow data (UCI, 7,476 test incidents): AUC 0.857 vs priority rule 0.552.

## Forecast (test days)

- WAPE 0.322 vs same-hour-last-week 0.422 (Poisson floor 0.298).
- Conformal coverage: 80% range 79.9%, 90% range 89.3%.

## A stronger baseline: the "SLA due" sort, and how late the late customers are (test days)

| KPI | Baseline A (FIFO) | Baseline B (priority) | Baseline C (SLA due) | Industry standard (skills routing) | OpsLens | OpsLens − C (95% CI) |
|---|---|---|---|---|---|---|
| SLA breach % | 20.10 | 17.33 | 14.25 | 16.26 | 11.66 | -2.59 [-2.98, -2.19] |
| P1 breach % | 30.45 | 24.51 | 22.69 | 22.51 | 22.73 | +0.05 [-1.05, +1.15] |
| Minutes late, mean over breached tickets | 126.21 | 146.90 | 217.94 | 147.88 | 108.63 | -109.31 [-162.80, -55.82] |
| Minutes late per 100 tickets (all customers) | 2,609.97 | 2,625.64 | 3,179.91 | 2,492.53 | 1,302.96 | -1876.95 [-2915.19, -838.71] |
| P99 wait (min) | 613.15 | 703.69 | 891.61 | 680.98 | 334.73 | -556.88 [-849.48, -264.28] |

- Baselines C and D have no weights, so nothing was tuned; they ran on validation days first, then once on test days.
- OpsLens − industry standard, breach %: -4.61 [-6.61, -2.60].

## The strongest published rules, and what perfect information buys them (test days)

| KPI | C: SLA due (EDF) | D: industry standard | Least slack first | Generalized c-mu | OpsLens | Clairvoyant least slack* | Clairvoyant least slack + staffing* |
|---|---|---|---|---|---|---|---|
| SLA breach % | 14.25 | 16.26 | 12.11 | 16.38 | 11.66 | 10.55 | 10.53 |
| P1 breach % | 22.69 | 22.51 | 20.82 | 24.58 | 22.73 | 17.70 | 17.84 |
| Minutes late, mean over breached tickets | 217.94 | 147.88 | 251.35 | 126.75 | 108.63 | 259.30 | 278.41 |
| Minutes late per 100 tickets | 3,179.91 | 2,492.53 | 3,094.13 | 2,135.69 | 1,302.96 | 2,775.37 | 2,954.73 |
| P99 wait (min) | 891.61 | 680.98 | 945.01 | 630.99 | 334.73 | 842.42 | 956.83 |

*Not implementable: knows each ticket's true category and true handle time. Not the optimum either (the true optimum for this many tickets cannot be computed).

| OpsLens − … | Breach % (95% CI) | Late minutes per 100 (95% CI) |
|---|---|---|
| C: SLA due (EDF) | -2.59 [-2.98, -2.19] | -1877 [-2915, -839] |
| D: industry standard | -4.61 [-6.61, -2.60] | -1190 [-2060, -319] |
| Least slack first | -0.45 [-1.36, +0.46] | -1791 [-2677, -905] |
| Generalized c-mu | -4.72 [-7.23, -2.22] | -833 [-1395, -271] |
| Clairvoyant least slack* | +1.11 [-0.11, +2.33] | -1472 [-2147, -798] |
| Clairvoyant least slack + staffing* | +1.13 [-0.07, +2.33] | -1652 [-2777, -527] |

- What perfect information buys the best rule (clairvoyant − least slack), breach %: -1.56 [-1.95, -1.16].
- Chosen on validation days 36-42 only: c-mu tau 0.25, beta 1.0 (of 8 shapes; lowest validation breach %, ties broken by fewer late minutes per 100). Validation breach %: OpsLens 9.76, least slack 11.19, c-mu 13.34 → gate passed; test days run once.

### Least slack + cross-skill rescue (the same freedom as OpsLens)

| KPI | Least slack first | Least slack + cross-skill rescue | OpsLens |
|---|---|---|---|
| SLA breach % | 12.11 | 11.28 | 11.66 |
| P1 breach % | 20.82 | 22.06 | 22.73 |
| Minutes late, mean over breached tickets | 251.35 | 165.03 | 108.63 |
| Minutes late per 100 tickets | 3,094.13 | 1,897.09 | 1,302.96 |
| P99 wait (min) | 945.01 | 472.36 | 334.73 |
| Reopen rate % | 4.01 | 4.80 | 4.64 |

| OpsLens − … | Breach % (95% CI) | Late minutes per 100 (95% CI) | Reopen rate % (95% CI) |
|---|---|---|---|
| Least slack + cross-skill rescue | +0.38 [-0.55, +1.32] | -594 [-927, -261] | -0.15 [-0.27, -0.04] |
| Least slack first | -0.45 [-1.36, +0.46] | -1791 [-2677, -905] | +0.63 [+0.54, +0.71] |

- What the rescue buys least slack (rescue − plain), breach %: -0.83 [-1.01, -0.65].
- Rule: when no skilled agent is free and a ticket's slack is below the threshold but a 1.6× slower job can still make the SLA, a free agent with the language takes it as a deliberate cross-skill job. Threshold chosen on validation days 36-42 only (lowest validation breach %, ties broken by fewer late minutes per 100): 30 min. Validation breach %: 10 min 10.81%, 20 min 10.44%, 30 min 10.41%, 60 min 12.39%, 120 min 12.19%, 240 min 12.94%; OpsLens 9.76 → gate passed; test days run once. OpsLens and plain least slack were run again beside it and reproduced exactly: yes.

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

- Physical floor: 5.84% of tickets breach even with unlimited agents and perfect routing (their own work and reopens exceed the SLA, or nobody on shift speaks their language).
- OpsLens is 5.82 points above that floor and captures 44% ± 2 of the improvement possible over the industry standard: (D − OpsLens) ÷ (D − floor), per seed.

## New sealed world (data seed 6262, corrected simulator, run once)

| KPI | Industry standard | Least slack first | Least slack + rescue | Generalized c-mu | OpsLens | Floor |
|---|---|---|---|---|---|---|
| SLA breach % | 5.84 | 4.04 | 3.11 | 5.71 | 2.20 | 1.31 |
| Minutes late per 100 tickets | 1,616.95 | 3,659.50 | 2,396.43 | 1,228.59 | 569.49 | — |

- Share of the possible improvement captured: 81% ± 4. Retrained risk AUC 0.982. New world (unused seed) generated after OpsLens v5 was frozen, under the corrected simulator (work draws no longer shifted by transfers); weights unchanged, routine retraining; run once.

## Sealed second world (data seed 4242, generated after the freeze, run once)

| KPI | Baseline A (FIFO) | Baseline B (priority) | Baseline C (SLA due) | OpsLens |
|---|---|---|---|---|
| SLA breach % | 15.22 | 8.21 | 6.13 | 3.07 |
| Minutes late per 100 tickets | 3,433.60 | 2,989.54 | 5,326.21 | 893.19 |

- OpsLens − Baseline C, breach %: -3.06 [-3.67, -2.45]. Retrained risk AUC 0.970. Classifier: cascade (local + LLM). Weights unchanged.

## Sealed world re-run with every baseline (data seed 4242)

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
| Fix the phone menu (IVR) | Product / IVR team | 0 | -123.4 [-200.2, -46.6] | -20.4 [-42.2, +1.4] | -5.3 |
| Cross-train 2 Hindi-speaking agents on payment failure and refund | Training / workforce | 0 | -96.8 [-124.5, -69.1] | -44.2 [-75.5, -12.9] | -11.5 |
| Self-serve instant refund on weekend dinner (Team C) | Product | 70 | -10.0 [-25.2, +5.2] | -10.0 [-15.0, -5.0] | -10.1 |
| Status banner the moment a spike alert fires | Product / customer comms | 29 | -90.6 [-129.3, -51.9] | -20.2 [-39.3, -1.1] | -9.2 |
| Self-serve instant refund on weekday night (Team B) | Product | 26 | -13.6 [-20.4, -6.8] | -1.6 [-13.8, +10.6] | -4.3 |
| Kitchen order-check for restaurant cluster 17 | Partner operations | 57 | -16.6 [-40.4, +7.2] | -20.8 [-43.3, +1.7] | -6.7 |
| **All together** | | 187 | -341.8 [-435.8, -247.8] | -106.4 [-121.5, -91.3] | -51.7 |

- OpsLens with every playbook vs priority-first today: breaches -1025.0 [-1301.4, -748.6] (of 2805), breach % -6.2 [-7.9, -4.5] points.
- Assumptions (labelled in config/playbooks.yaml) were re-run at their low and high values; see `playbooks[].sensitivity` in results.json.

## Your plan: each recommendation alone (test days, change vs OpsLens with nothing accepted)

Without the plan: breach 11.90%. Change with 95% CI over the seeds.

| Item | Missed SLA (customers) | Mean resolution (min) | Agent-hours | Minutes past SLA per 100 |
|---|---|---|---|---|
| Yash X. (C08, Team C): start 16:00 instead of 18:00 (days 43-49) | +6.4 [+2.0, +10.8] | +0.1 [-0.1, +0.3] | -0.1 [-1.1, +1.0] | +7 [-7, +21] |
| Ruchi P. (C09, Team C): start 14:00 instead of 16:00 (days 43-49) | +4.6 [-2.6, +11.8] | +0.1 [-0.1, +0.3] | -0.3 [-1.3, +0.6] | +3 [-10, +15] |
| Bhavna S. (D05, Team D): start 07:00 instead of 08:00 (days 43-49) | +3.8 [-7.5, +15.1] | -0.1 [-0.2, +0.1] | +0.8 [-0.6, +2.2] | -4 [-22, +15] |
| Gita K. (D09, Team D): start 15:00 instead of 17:00 (days 43-49) | -0.2 [-14.8, +14.4] | +0.0 [-0.2, +0.3] | -0.2 [-0.8, +0.3] | +0 [-16, +16] |
| Kavita D. (B01, Team B): start 15:00 instead of 14:00 (days 43-49) | -7.8 [-16.1, +0.5] | -0.2 [-0.4, -0.1] | -1.3 [-2.1, -0.5] | -15 [-17, -13] |
| Amit T. (D04, Team D): start 07:00 instead of 09:00 (days 43-49) | -2.0 [-15.8, +11.8] | +0.1 [-0.5, +0.8] | -0.7 [-1.9, +0.6] | +13 [-30, +56] |
| Yash X. (C08, Team C): start 16:00 instead of 18:00 (days 50-56) | -2.4 [-12.2, +7.4] | -0.1 [-0.5, +0.2] | -0.2 [-1.2, +0.9] | -12 [-49, +24] |
| Ruchi P. (C09, Team C): start 14:00 instead of 16:00 (days 50-56) | +3.6 [-16.4, +23.6] | +0.2 [-0.9, +1.3] | -0.9 [-2.7, +0.8] | +22 [-70, +113] |
| Kavita D. (B01, Team B): day off on Thu instead of Mon (days 50-56) | -23.2 [-70.7, +24.3] | -1.7 [-4.8, +1.4] | +1.1 [-1.6, +3.7] | -145 [-442, +152] |
| Aditya B. (B06, Team B): start 07:00 instead of 09:00 (days 50-56) | -10.6 [-22.0, +0.8] | -0.2 [-0.7, +0.2] | -1.1 [-2.7, +0.6] | -17 [-49, +15] |
| Anjali F. (C01, Team B): start 16:00 instead of 18:00 (days 50-56) | +1.2 [-3.4, +5.8] | -0.0 [-0.2, +0.1] | +0.7 [-0.7, +2.0] | -4 [-14, +7] |
| Shreya L. (B07, Team B): start 15:00 instead of 14:00 (days 50-56) | -2.8 [-36.0, +30.4] | -0.2 [-1.5, +1.1] | -0.9 [-2.2, +0.3] | -18 [-145, +108] |
| Fix the phone menu (IVR) (days 43-56) | -24.4 [-51.1, +2.3] | -0.6 [-1.5, +0.3] | -6.5 [-11.2, -1.8] | -42 [-113, +29] |
| Cross-train 2 Hindi-speaking agents on payment failure and refund (days 43-56) | -44.6 [-75.8, -13.4] | -2.6 [-4.3, -0.9] | -13.9 [-17.6, -10.2] | -259 [-425, -93] |
| Self-serve instant refund on weekend dinner (Team C) (days 43-56) | -9.2 [-15.7, -2.7] | -0.2 [-0.3, -0.1] | -10.2 [-11.1, -9.2] | +2 [-2, +6] |
| Status banner the moment a spike alert fires (days 43-56) | -16.2 [-27.8, -4.6] | -0.8 [-1.0, -0.5] | -9.9 [-13.4, -6.5] | -18 [-29, -7] |
| Self-serve instant refund on weekday night (Team B) (days 43-56) | -4.2 [-13.6, +5.2] | -0.1 [-0.2, +0.1] | -5.8 [-6.9, -4.8] | -3 [-25, +18] |
| Kitchen order-check for restaurant cluster 17 (days 43-56) | -4.4 [-15.9, +7.1] | -0.4 [-1.2, +0.3] | -8.2 [-12.8, -3.6] | -21 [-83, +41] |
| **All items together** | -145.0 [-190.5, -99.5] | -6.5 [-10.1, -3.0] | -56.0 [-58.5, -53.5] | -510 [-877, -143] |

## Day by day (test days, 5 seeds)

OpsLens missed fewer deadlines than the industry standard on 14 of 14 days. Daily rows add up exactly to the totals: True.

| Day | Tickets | Industry standard | OpsLens |
|---|---|---|---|
| Mon 12 Oct | 983 | 11.37% | 9.07% |
| Tue 13 Oct | 1,029 | 15.12% | 11.91% |
| Wed 14 Oct | 1,067 | 16.57% | 11.42% |
| Thu 15 Oct | 1,083 | 11.78% | 8.99% |
| Fri 16 Oct | 1,124 | 17.35% | 10.98% |
| Sat 17 Oct | 1,278 | 17.07% | 10.70% |
| Sun 18 Oct | 1,264 | 11.80% | 8.84% |
| Mon 19 Oct | 1,527 | 32.01% | 23.03% |
| Tue 20 Oct | 1,114 | 19.98% | 12.96% |
| Wed 21 Oct | 1,029 | 18.43% | 11.68% |
| Thu 22 Oct | 1,118 | 14.11% | 10.93% |
| Fri 23 Oct | 1,014 | 10.99% | 9.31% |
| Sat 24 Oct | 1,255 | 12.78% | 10.60% |
| Sun 25 Oct | 1,297 | 12.88% | 9.07% |

## Agents with several chats at once (test days, 5 seeds)

A chat started while k-1 others are open takes x(1 + s(k-1)); s is an assumption. 'Equal load' raises
the volume by k/(1+s(k-1)) so the floor is as busy as today.

| Chats (k) | Slowdown (s) | Load | Volume | First come | Urgent first | SLA due | Industry std | OpsLens | OpsLens - industry [95% CI] |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 0.25 | equal load | x1.60 | 20.15% | 17.65% | 15.50% | 16.64% | 12.41% | -4.23 [-5.91, -2.55] |
| 2 | 0.25 | today | x1.00 | 11.39% | 11.07% | 10.70% | 10.54% | 8.36% | -2.18 [-2.55, -1.81] |
| 2 | 0.50 | equal load | x1.33 | 22.55% | 20.74% | 18.51% | 19.48% | 15.37% | -4.11 [-5.75, -2.48] |
| 2 | 0.50 | today | x1.00 | 15.05% | 14.49% | 13.91% | 13.70% | 11.20% | -2.50 [-3.13, -1.88] |
| 3 | 0.25 | equal load | x2.00 | 21.46% | 19.64% | 17.76% | 18.39% | 14.34% | -4.05 [-5.77, -2.34] |
| 3 | 0.25 | today | x1.00 | 12.13% | 12.05% | 11.80% | 11.57% | 9.23% | -2.34 [-2.74, -1.93] |
| 3 | 0.50 | equal load | x1.50 | 26.05% | 24.91% | 23.16% | 23.32% | 19.58% | -3.74 [-5.10, -2.38] |
| 3 | 0.50 | today | x1.00 | 17.50% | 17.32% | 17.04% | 16.54% | 13.57% | -2.97 [-3.38, -2.56] |

Pre-registered rule (OpsLens beats industry standard in all four equal-load settings): PASSED. Optimiser ablation at k = 3, s = 0.25: greedy - min-cost flow +0.34 [+0.18, +0.49] points.

## 30 random worlds we did not design (test days, 3 seeds each)

OpsLens lowest (within 0.05 points) in 19 of 30 worlds (rule needs 27); median OpsLens - industry standard -8.19 points, 95% CI [-12.20, -3.28]. Rule NOT passed.
Breakdown (from the same runs, added after them): OpsLens beats the industry standard in 29 of 30; it is lowest in 13 of 13 worlds up to x1.05 today's load and 6 of 17 heavier ones. All 11 losses are to least_slack, at x1.06 load or more; in 10 of them OpsLens keeps late customers less late.

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

Main validation days, 20 fresh seeds: v6 - v5 -0.006 [-0.028, +0.017] points (gate: upper bound below +0.05) - passed. 30 NEW worlds: v6 lowest (within 0.05 points) in 18 (rule needs 27; v5 in the same worlds: 16); v6 better than v5 in 15, worse in 6, mean -0.26 points. Beats the industry standard: v6 30 of 30, v5 30 of 30. Adopted: no - v5 stays.

## Challenger arena (pre-registered: ship only if > 2% better AND within the latency budget)

- Forecast: Chronos-2 (zero-shot) WAPE 0.304 vs LightGBM 0.305 (+0.4%), 80% coverage 76.2% vs 79.2%; one 48 h refresh 1.7 s → **keep LightGBM**.
- Risk: TabPFN-3 not run yet (needs a TabPFN licence key).

## Speed

- Optimiser per decision: median 0.06 ms, max 2.2 ms.
- Scale test: 5,000 tickets × 500 agents solved in 0.063 s.
- Full evaluation pipeline: 103.4 min.
