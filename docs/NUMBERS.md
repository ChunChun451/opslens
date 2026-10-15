# OpsLens — the numbers

Generated from `eval/results.json` on 2026-10-16T00:22:40 (commit 7a5ed0a). Do not edit by hand: run `mingw32-make eval`.

Data: 71,530 tickets over 56 days; train days [1, 35], validation [36, 42], test [43, 56]. Simulator seeds [1, 2, 3, 4, 5].

## Baseline vs OpsLens (test days, mean ± std over seeds)

| KPI | Baseline A (FIFO) | Baseline B (priority) | OpsLens | OpsLens − B (95% CI) |
|---|---|---|---|---|
| SLA breach % | 13.11 ± 2.23 | 6.82 ± 1.34 | **2.38** ± 0.54 | -4.44 [-5.58, -3.30] |
| P90 resolution (min) | 184.78 ± 35.79 | 198.45 ± 44.15 | **140.79** ± 31.15 | -57.66 [-75.08, -40.24] |
| Mean wait (min) | 64.52 ± 14.02 | 68.15 ± 16.38 | **45.55** ± 13.47 | -22.61 [-28.57, -16.65] |
| Max backlog (tickets) | 227.40 ± 48.59 | 233.80 ± 52.21 | **197.00** ± 69.47 | -36.80 [-91.67, +18.07] |
| Transfers per 100 | 4.66 ± 0.03 | 4.59 ± 0.04 | **0.97** ± 0.02 | -3.62 [-3.66, -3.59] |
| Tickets per agent-hour | 5.29 ± 0.10 | 5.29 ± 0.10 | **5.30** ± 0.10 | +0.00 [-0.00, +0.01] |
| Reopen rate % | 3.93 ± 0.15 | 3.93 ± 0.15 | **4.39** ± 0.19 | +0.46 [+0.34, +0.57] |
| P99 wait (min) | 816.27 ± 100.16 | 1,007.37 ± 149.90 | **732.09** ± 192.48 | -275.28 [-394.29, -156.26] |
| Load fairness (std of utilisation) | 0.12 ± 0.01 | 0.12 ± 0.01 | **0.13** ± 0.01 | +0.01 [+0.00, +0.01] |
| P1 breach % | 27.34 ± 4.46 | 9.13 ± 1.52 | **4.86** ± 0.38 | -4.27 [-5.77, -2.78] |
| Hindi customers' breach % | 22.11 ± 3.28 | 16.18 ± 2.98 | **3.84** ± 1.18 | -12.35 [-14.82, -9.87] |

OpsLens − Baseline A, breach %: -10.73 [-12.94, -8.52].

## Which part creates the gain (ablations, test days)

| Variant | Breach % | Δ vs full | P90 (min) |
|---|---|---|---|
| OpsLens (full) | 2.38 | +0.00 [+0.00, +0.00] | 140.8 |
| without staffing plan | 2.48 | +0.10 [+0.04, +0.16] | 150.9 |
| without risk scores | 5.16 | +2.78 [+1.70, +3.86] | 178.3 |
| without optimiser (greedy per agent) | 2.40 | +0.03 [-0.02, +0.08] | 139.8 |
| without classifier (menu choice routing) | 2.60 | +0.22 [+0.00, +0.43] | 155.0 |
| without scarcity cost | 2.45 | +0.07 [+0.02, +0.11] | 141.5 |

## Stress tests (conditions never seen in training)

| Scenario | Baseline A | Baseline B | OpsLens | OpsLens − B |
|---|---|---|---|---|
| +25% volume | 53.55% | 29.06% | **40.53%** | +11.48 [+4.96, +18.00] |
| 10% absenteeism | 20.32% | 9.89% | **3.68%** | -6.20 [-7.02, -5.39] |

## Gold-customer weight sensitivity

| Gold weight | Breach % (all) | Breach % (gold) |
|---|---|---|
| ×1.0 | 2.37 | 2.27 |
| ×1.5 | 2.38 | 1.81 |
| ×2.0 | 2.44 | 1.80 |

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

## Speed

- Optimiser per decision: median 0.07 ms, max 2.3 ms.
- Scale test: 5,000 tickets × 500 agents solved in 0.047 s.
- Full evaluation pipeline: 19.6 min.
