# OpsLens — the numbers

Generated from `eval/results.json` on 2026-10-16T03:02:38 (commit 9ab294c). Do not edit by hand: run `mingw32-make eval`.

Data: 71,530 tickets over 56 days; train days [1, 35], validation [36, 42], test [43, 56]. Simulator seeds [1, 2, 3, 4, 5].

## Baseline vs OpsLens (test days, mean ± std over seeds)

| KPI | Baseline A (FIFO) | Baseline B (priority) | OpsLens | OpsLens − B (95% CI) |
|---|---|---|---|---|
| SLA breach % | 13.11 ± 2.23 | 6.82 ± 1.34 | **2.20** ± 0.32 | -4.62 [-6.01, -3.23] |
| P90 resolution (min) | 184.78 ± 35.79 | 198.45 ± 44.15 | **140.51** ± 30.65 | -57.94 [-75.51, -40.37] |
| Mean wait (min) | 64.52 ± 14.02 | 68.15 ± 16.38 | **44.76** ± 12.77 | -23.39 [-29.63, -17.15] |
| Max backlog (tickets) | 227.40 ± 48.59 | 233.80 ± 52.21 | **200.60** ± 74.04 | -33.20 [-92.44, +26.04] |
| Transfers per 100 | 4.66 ± 0.03 | 4.59 ± 0.04 | **0.97** ± 0.02 | -3.62 [-3.66, -3.59] |
| Tickets per agent-hour | 5.29 ± 0.10 | 5.29 ± 0.10 | **5.30** ± 0.10 | +0.00 [-0.00, +0.01] |
| Reopen rate % | 3.93 ± 0.15 | 3.93 ± 0.15 | **4.40** ± 0.18 | +0.47 [+0.39, +0.55] |
| P99 wait (min) | 816.27 ± 100.16 | 1,007.37 ± 149.90 | **727.81** ± 188.95 | -279.57 [-407.33, -151.80] |
| Load fairness (std of utilisation) | 0.12 ± 0.01 | 0.12 ± 0.01 | **0.13** ± 0.01 | +0.01 [+0.00, +0.01] |
| P1 breach % | 27.34 ± 4.46 | 9.13 ± 1.52 | **4.89** ± 0.32 | -4.24 [-5.81, -2.68] |
| Hindi customers' breach % | 22.11 ± 3.28 | 16.18 ± 2.98 | **3.46** ± 0.64 | -12.72 [-15.91, -9.53] |

OpsLens − Baseline A, breach %: -10.91 [-13.38, -8.43].

## Which part creates the gain (ablations, test days)

| Variant | Breach % | Δ vs full | P90 (min) |
|---|---|---|---|
| OpsLens (full) | 2.20 | +0.00 [+0.00, +0.00] | 140.5 |
| without staffing plan | 2.25 | +0.05 [-0.06, +0.16] | 149.3 |
| without risk scores | 4.21 | +2.01 [+1.55, +2.47] | 169.1 |
| without optimiser (greedy per agent) | 2.18 | -0.02 [-0.11, +0.06] | 139.2 |
| without classifier (menu choice routing) | 2.34 | +0.14 [+0.01, +0.27] | 155.0 |
| without scarcity cost | 2.23 | +0.03 [-0.10, +0.16] | 142.1 |

## Stress tests (conditions never seen in training)

| Scenario | Baseline A | Baseline B | OpsLens | OpsLens − B |
|---|---|---|---|---|
| +25% volume | 53.55% | 29.06% | **10.71%** | -18.34 [-22.17, -14.51] |
| 10% absenteeism | 20.32% | 9.89% | **3.09%** | -6.79 [-8.06, -5.53] |

## Gold-customer weight sensitivity

| Gold weight | Breach % (all) | Breach % (gold) |
|---|---|---|
| ×1.0 | 2.20 | 2.08 |
| ×1.5 | 2.20 | 1.83 |
| ×2.0 | 2.25 | 1.85 |

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

- Optimiser per decision: median 0.08 ms, max 5.9 ms.
- Scale test: 5,000 tickets × 500 agents solved in 0.051 s.
- Full evaluation pipeline: 19.6 min.
