# OpsLens — the numbers

Generated from `eval/results.json` on 2026-10-19T02:26:32 (commit 37c630d). Do not edit by hand: run `mingw32-make eval`.

Data: 71,530 tickets over 56 days; train days [1, 35], validation [36, 42], test [43, 56]. Simulator seeds [1, 2, 3, 4, 5].

## Baseline vs OpsLens (test days, mean ± std over seeds)

| KPI | Baseline A (FIFO) | Baseline B (priority) | Industry standard (skills routing) | OpsLens | OpsLens − industry standard (95% CI) | OpsLens − B (95% CI) |
|---|---|---|---|---|---|---|
| SLA breach % | 13.08 ± 2.24 | 6.77 ± 1.25 | 5.51 ± 1.35 | **2.05** ± 0.36 | -3.46 [-4.77, -2.15] | -4.72 [-5.98, -3.46] |
| P90 resolution (min) | 183.49 ± 36.55 | 196.17 ± 37.61 | 203.55 ± 58.73 | **140.44** ± 30.42 | -63.11 [-99.18, -27.03] | -55.73 [-65.00, -46.46] |
| Mean wait (min) | 64.02 ± 14.04 | 68.03 ± 15.68 | 65.74 ± 17.61 | **45.05** ± 12.79 | -20.70 [-26.96, -14.44] | -22.98 [-28.69, -17.28] |
| Max backlog (tickets) | 224.80 ± 49.65 | 236.20 ± 51.87 | 220.40 ± 48.03 | **209.00** ± 75.65 | -11.40 [-72.10, +49.30] | -27.20 [-85.47, +31.07] |
| Transfers per 100 | 4.63 ± 0.04 | 4.62 ± 0.04 | 1.01 ± 0.01 | **0.97** ± 0.02 | -0.05 [-0.07, -0.03] | -3.66 [-3.70, -3.61] |
| Tickets per agent-hour | 5.29 ± 0.10 | 5.29 ± 0.10 | 5.29 ± 0.10 | **5.30** ± 0.10 | +0.00 [-0.00, +0.01] | +0.00 [-0.00, +0.01] |
| Reopen rate % | 3.93 ± 0.15 | 3.93 ± 0.15 | 3.93 ± 0.15 | **4.44** ± 0.18 | +0.50 [+0.41, +0.59] | +0.50 [+0.41, +0.59] |
| P99 wait (min) | 817.16 ± 91.73 | 1,009.15 ± 162.70 | 941.19 ± 199.63 | **728.39** ± 187.94 | -212.80 [-278.87, -146.73] | -280.76 [-403.08, -158.43] |
| Load fairness (std of utilisation) | 0.12 ± 0.01 | 0.12 ± 0.00 | 0.14 ± 0.00 | **0.13** ± 0.01 | -0.01 [-0.02, +0.00] | +0.01 [+0.00, +0.02] |
| P1 breach % | 27.25 ± 4.44 | 9.01 ± 1.50 | 7.50 ± 1.12 | **4.84** ± 0.35 | -2.65 [-3.68, -1.63] | -4.16 [-5.66, -2.67] |
| Hindi customers' breach % | 22.15 ± 3.35 | 16.17 ± 2.83 | 13.32 ± 2.55 | **2.72** ± 0.54 | -10.60 [-13.27, -7.93] | -13.45 [-16.51, -10.38] |

OpsLens − Baseline A, breach %: -11.03 [-13.48, -8.58].

## Which part creates the gain (ablations, test days)

| Variant | Breach % | Δ vs full | P90 (min) |
|---|---|---|---|
| OpsLens (full) | 2.05 | +0.00 [+0.00, +0.00] | 140.4 |
| without staffing plan | 2.11 | +0.06 [-0.02, +0.14] | 151.3 |
| without risk scores | 4.19 | +2.15 [+1.66, +2.63] | 169.8 |
| without optimiser (greedy per agent) | 2.03 | -0.02 [-0.04, +0.01] | 139.3 |
| without classifier (menu choice routing) | 2.21 | +0.16 [+0.06, +0.27] | 154.2 |
| without scarcity cost | 2.06 | +0.01 [-0.07, +0.09] | 142.9 |

## Stress tests (conditions never seen in training)

| Scenario | Baseline A | Baseline B | OpsLens | OpsLens − B |
|---|---|---|---|---|
| +25% volume | 53.60% | 28.86% | **10.53%** | -18.33 [-21.65, -15.00] |
| 10% absenteeism | 20.21% | 9.84% | **2.94%** | -6.90 [-8.17, -5.64] |

## Gold-customer weight sensitivity

| Gold weight | Breach % (all) | Breach % (gold) |
|---|---|---|
| ×1.0 | 2.03 | 1.98 |
| ×1.5 | 2.05 | 1.79 |
| ×2.0 | 2.07 | 1.83 |

## Patterns

- Planted problems (main data): found 5/5, diagnosed 5/5; false alarms 1.
- Blind test: 57/60 random plants found (95.0%) over 20 datasets; diagnosed 95.0%.
- Live detection of the unseen day-47 surge: 45 min; false alerts 0.5 per week.

## Classification (test days)

- Menu choice 90.9% → local 97.97% → cascade 98.08%; LLM alone 90.0% (400 tickets).
- Sent to the LLM: 1.54%. Wrong-team routing per 100: 5.71 → 1.20.

## Risk model (test days)

- AUC 0.976 (time-left rule 0.884), PR-AUC 0.955, top-10% precision 0.996, Brier 0.0554; at arrival AUC 0.966.
- Real ServiceNow data (UCI, 7,476 test incidents): AUC 0.857 vs priority rule 0.552.

## Forecast (test days)

- WAPE 0.305 vs same-hour-last-week 0.415 (Poisson floor 0.280).
- Conformal coverage: 80% range 79.2%, 90% range 90.0%.

## A stronger baseline: the "SLA due" sort, and how late the late customers are (test days)

| KPI | Baseline A (FIFO) | Baseline B (priority) | Baseline C (SLA due) | Industry standard (skills routing) | OpsLens | OpsLens − C (95% CI) |
|---|---|---|---|---|---|---|
| SLA breach % | 13.08 | 6.77 | 5.38 | 5.51 | 2.05 | -3.33 [-3.97, -2.69] |
| P1 breach % | 27.25 | 9.01 | 8.87 | 7.50 | 4.84 | -4.03 [-5.42, -2.63] |
| Minutes late, mean over breached tickets | 210.91 | 328.11 | 772.71 | 261.87 | 223.82 | -548.89 [-713.03, -384.75] |
| Minutes late per 100 tickets (all customers) | 2,789.67 | 2,255.96 | 4,206.04 | 1,432.37 | 482.68 | -3723.37 [-4999.63, -2447.10] |
| P99 wait (min) | 817.16 | 1,009.15 | 1,422.47 | 941.19 | 728.39 | -694.08 [-1075.03, -313.12] |

- Baselines C and D have no weights, so nothing was tuned; they ran on validation days first, then once on test days.
- OpsLens − industry standard, breach %: -3.46 [-4.77, -2.15].

## The strongest published rules, and what perfect information buys them (test days)

| KPI | C: SLA due (EDF) | D: industry standard | Least slack first | Generalized c-mu | OpsLens | Clairvoyant least slack* | Clairvoyant least slack + staffing* |
|---|---|---|---|---|---|---|---|
| SLA breach % | 5.38 | 5.51 | 3.94 | 5.27 | 2.05 | 3.81 | 3.81 |
| P1 breach % | 8.87 | 7.50 | 6.97 | 7.99 | 4.84 | 6.71 | 6.83 |
| Minutes late, mean over breached tickets | 772.71 | 261.87 | 891.73 | 238.33 | 223.82 | 876.45 | 833.21 |
| Minutes late per 100 tickets | 4,206.04 | 1,432.37 | 3,552.01 | 1,237.68 | 482.68 | 3,380.06 | 3,247.22 |
| P99 wait (min) | 1,422.47 | 941.19 | 1,386.21 | 905.22 | 728.39 | 1,373.25 | 1,456.91 |

*Not implementable: knows each ticket's true category and true handle time. Not the optimum either (the true optimum for this many tickets cannot be computed).

| OpsLens − … | Breach % (95% CI) | Late minutes per 100 (95% CI) |
|---|---|---|
| C: SLA due (EDF) | -3.33 [-3.97, -2.69] | -3723 [-5000, -2447] |
| D: industry standard | -3.46 [-4.77, -2.15] | -950 [-1364, -535] |
| Least slack first | -1.89 [-2.18, -1.61] | -3069 [-4286, -1853] |
| Generalized c-mu | -3.23 [-4.57, -1.88] | -755 [-1158, -352] |
| Clairvoyant least slack* | -1.77 [-2.06, -1.48] | -2897 [-4024, -1771] |
| Clairvoyant least slack + staffing* | -1.76 [-1.94, -1.58] | -2765 [-4355, -1174] |

- What perfect information buys the best rule (clairvoyant − least slack), breach %: -0.13 [-0.25, +0.00].
- Chosen on validation days 36-42 only: c-mu tau 0.25, beta 1.0 (of 8 shapes; lowest validation breach %, ties broken by fewer late minutes per 100). Validation breach %: OpsLens 2.02, least slack 3.68, c-mu 4.34 → gate passed; test days run once.

### Least slack + cross-skill rescue (the same freedom as OpsLens)

| KPI | Least slack first | Least slack + cross-skill rescue | OpsLens |
|---|---|---|---|
| SLA breach % | 3.94 | 2.98 | 2.05 |
| P1 breach % | 6.97 | 5.52 | 4.84 |
| Minutes late, mean over breached tickets | 891.73 | 649.20 | 223.82 |
| Minutes late per 100 tickets | 3,552.01 | 1,969.19 | 482.68 |
| P99 wait (min) | 1,386.21 | 930.08 | 728.39 |
| Reopen rate % | 3.93 | 4.10 | 4.44 |

| OpsLens − … | Breach % (95% CI) | Late minutes per 100 (95% CI) | Reopen rate % (95% CI) |
|---|---|---|---|
| Least slack + cross-skill rescue | -0.94 [-1.14, -0.73] | -1487 [-2110, -863] | +0.33 [+0.24, +0.43] |
| Least slack first | -1.89 [-2.18, -1.61] | -3069 [-4286, -1853] | +0.50 [+0.41, +0.59] |

- What the rescue buys least slack (rescue − plain), breach %: -0.96 [-1.14, -0.77].
- Rule: when no skilled agent is free and a ticket's slack is below the threshold but a 1.6× slower job can still make the SLA, a free agent with the language takes it as a deliberate cross-skill job. Threshold chosen on validation days 36-42 only (lowest validation breach %, ties broken by fewer late minutes per 100): 30 min. Validation breach %: 10 min 3.22%, 20 min 2.97%, 30 min 2.81%, 60 min 3.27%, 120 min 3.18%, 240 min 2.98%; OpsLens 2.02 → gate passed; test days run once. OpsLens and plain least slack were run again beside it and reproduced exactly: yes.

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

## How close to perfect (test days)

- Physical floor: 1.31% of tickets breach even with unlimited agents and perfect routing (their own work and reopens exceed the SLA, or nobody on shift speaks their language).
- OpsLens is 0.74 points above that floor and captures 83% ± 4 of the improvement possible over the industry standard: (D − OpsLens) ÷ (D − floor), per seed.

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
| Fix the phone menu (IVR) | Product / IVR team | 0 | -39.0 [-56.4, -21.6] | -0.4 [-13.1, +12.3] | -3.5 |
| Cross-train 2 Hindi-speaking agents on payment failure and refund | Training / workforce | 0 | -79.0 [-131.4, -26.6] | -33.6 [-44.3, -22.9] | -21.5 |
| Self-serve instant refund on weekend dinner (Team C) | Product | 83 | -12.6 [-22.3, -2.9] | -5.0 [-10.3, +0.3] | -10.7 |
| Status banner the moment a spike alert fires | Product / customer comms | 30 | -5.0 [-13.9, +3.9] | -4.2 [-10.5, +2.1] | -7.4 |
| Kitchen order-check for restaurant cluster 17 | Partner operations | 67 | -9.2 [-25.7, +7.3] | -3.4 [-14.6, +7.8] | -10.2 |
| Self-serve instant refund on weekday night (Team B) | Product | 23 | -16.8 [-29.9, -3.7] | -1.4 [-8.5, +5.7] | -1.7 |
| **All together** | | 206 | -162.6 [-200.6, -124.6] | -38.0 [-50.6, -25.4] | -59.4 |

- OpsLens with every playbook vs priority-first today: breaches -889.2 [-1119.4, -659.0] (of 1220), breach % -4.9 [-6.2, -3.6] points.
- Assumptions (labelled in config/playbooks.yaml) were re-run at their low and high values; see `playbooks[].sensitivity` in results.json.

## Challenger arena (pre-registered: ship only if > 2% better AND within the latency budget)

- Forecast: Chronos-2 (zero-shot) WAPE 0.304 vs LightGBM 0.305 (+0.4%), 80% coverage 76.2% vs 79.2%; one 48 h refresh 1.7 s → **keep LightGBM**.
- Risk: TabPFN-3 not run yet (needs the owner's TabPFN licence key).

## Speed

- Optimiser per decision: median 0.07 ms, max 1.5 ms.
- Scale test: 5,000 tickets × 500 agents solved in 0.083 s.
- Full evaluation pipeline: 48.5 min.
