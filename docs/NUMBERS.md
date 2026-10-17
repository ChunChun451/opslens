# OpsLens — the numbers

Generated from `eval/results.json` on 2026-10-17T14:20:04 (commit 4d6f787). Do not edit by hand: run `mingw32-make eval`.

Data: 71,530 tickets over 56 days; train days [1, 35], validation [36, 42], test [43, 56]. Simulator seeds [1, 2, 3, 4, 5].

## Baseline vs OpsLens (test days, mean ± std over seeds)

| KPI | Baseline A (FIFO) | Baseline B (priority) | Industry standard (skills routing) | OpsLens | OpsLens − industry standard (95% CI) | OpsLens − B (95% CI) |
|---|---|---|---|---|---|---|
| SLA breach % | 13.11 ± 2.23 | 6.82 ± 1.34 | 5.51 ± 1.45 | **2.20** ± 0.32 | -3.31 [-4.79, -1.84] | -4.62 [-6.01, -3.23] |
| P90 resolution (min) | 184.78 ± 35.79 | 198.45 ± 44.15 | 202.70 ± 56.74 | **140.51** ± 30.65 | -62.20 [-95.79, -28.60] | -57.94 [-75.51, -40.37] |
| Mean wait (min) | 64.52 ± 14.02 | 68.15 ± 16.38 | 65.67 ± 17.45 | **44.76** ± 12.77 | -20.91 [-27.38, -14.44] | -23.39 [-29.63, -17.15] |
| Max backlog (tickets) | 227.40 ± 48.59 | 233.80 ± 52.21 | 221.60 ± 46.95 | **200.60** ± 74.04 | -21.00 [-82.82, +40.82] | -33.20 [-92.44, +26.04] |
| Transfers per 100 | 4.66 ± 0.03 | 4.59 ± 0.04 | 1.02 ± 0.01 | **0.97** ± 0.02 | -0.06 [-0.08, -0.03] | -3.62 [-3.66, -3.59] |
| Tickets per agent-hour | 5.29 ± 0.10 | 5.29 ± 0.10 | 5.29 ± 0.10 | **5.30** ± 0.10 | +0.00 [-0.00, +0.01] | +0.00 [-0.00, +0.01] |
| Reopen rate % | 3.93 ± 0.15 | 3.93 ± 0.15 | 3.93 ± 0.15 | **4.40** ± 0.18 | +0.47 [+0.39, +0.55] | +0.47 [+0.39, +0.55] |
| P99 wait (min) | 816.27 ± 100.16 | 1,007.37 ± 149.90 | 947.99 ± 213.24 | **727.81** ± 188.95 | -220.19 [-306.02, -134.35] | -279.57 [-407.33, -151.80] |
| Load fairness (std of utilisation) | 0.12 ± 0.01 | 0.12 ± 0.01 | 0.14 ± 0.00 | **0.13** ± 0.01 | -0.01 [-0.02, -0.00] | +0.01 [+0.00, +0.01] |
| P1 breach % | 27.34 ± 4.46 | 9.13 ± 1.52 | 7.55 ± 1.19 | **4.89** ± 0.32 | -2.66 [-3.81, -1.51] | -4.24 [-5.81, -2.68] |
| Hindi customers' breach % | 22.11 ± 3.28 | 16.18 ± 2.98 | 13.35 ± 2.81 | **3.46** ± 0.64 | -9.89 [-12.82, -6.96] | -12.72 [-15.91, -9.53] |

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

## A stronger baseline: the "SLA due" sort, and how late the late customers are (test days)

| KPI | Baseline A (FIFO) | Baseline B (priority) | Baseline C (SLA due) | Industry standard (skills routing) | OpsLens | OpsLens − C (95% CI) |
|---|---|---|---|---|---|---|
| SLA breach % | 13.11 | 6.82 | 5.40 | 5.51 | 2.20 | -3.20 [-3.93, -2.46] |
| P1 breach % | 27.34 | 9.13 | 8.94 | 7.55 | 4.89 | -4.05 [-5.67, -2.44] |
| Minutes late, mean over breached tickets | 212.65 | 328.03 | 765.89 | 268.53 | 229.85 | -536.04 [-687.99, -384.09] |
| Minutes late per 100 tickets (all customers) | 2,820.08 | 2,281.67 | 4,189.41 | 1,477.02 | 528.93 | -3660.48 [-4916.26, -2404.70] |
| P99 wait (min) | 816.27 | 1,007.37 | 1,434.88 | 947.99 | 727.81 | -707.08 [-1085.48, -328.68] |

- Baselines C and D have no weights, so nothing was tuned; they ran on validation days first, then once on test days.
- OpsLens − industry standard, breach %: -3.31 [-4.79, -1.84].

## Sealed second world (data seed 4242, generated after the freeze, run once)

| KPI | Baseline A (FIFO) | Baseline B (priority) | Baseline C (SLA due) | OpsLens |
|---|---|---|---|---|
| SLA breach % | 15.22 | 8.21 | 6.13 | 3.07 |
| Minutes late per 100 tickets | 3,433.60 | 2,989.54 | 5,326.21 | 893.19 |

- OpsLens − Baseline C, breach %: -3.06 [-3.67, -2.45]. Retrained risk AUC 0.970. Classifier: cascade (local + LLM). Weights unchanged.

## Fix-at-source playbooks (test days, change vs the same policy without it)

| Playbook | Owner | Tickets prevented | Breaches: priority-first | Breaches: OpsLens | Agent-hours (OpsLens) |
|---|---|---|---|---|---|
| Fix the phone menu (IVR) | Product / IVR team | 0 | -46.4 [-75.3, -17.5] | -3.0 [-18.3, +12.3] | -2.7 |
| Cross-train 2 Hindi-speaking agents on payment failure and refund | Training / workforce | 0 | -83.2 [-131.4, -35.0] | -50.6 [-71.4, -29.8] | -19.4 |
| Self-serve instant refund on weekend dinner (Team C) | Product | 83 | -16.8 [-26.6, -7.0] | -1.0 [-15.3, +13.3] | -11.4 |
| Status banner the moment a spike alert fires | Product / customer comms | 30 | -10.6 [-16.1, -5.1] | -8.2 [-16.3, -0.1] | -8.7 |
| Kitchen order-check for restaurant cluster 17 | Partner operations | 67 | -13.6 [-23.9, -3.3] | -4.2 [-20.7, +12.3] | -10.8 |
| Self-serve instant refund on weekday night (Team B) | Product | 23 | -12.8 [-20.3, -5.3] | +0.2 [-19.8, +20.2] | -4.8 |
| **All together** | | 206 | -179.0 [-218.9, -139.1] | -56.6 [-73.3, -39.9] | -56.7 |

- OpsLens with every playbook vs priority-first today: breaches -889.4 [-1126.6, -652.2] (of 1230), breach % -4.9 [-6.2, -3.6] points.
- Assumptions (labelled in config/playbooks.yaml) were re-run at their low and high values; see `playbooks[].sensitivity` in results.json.

## Challenger arena (pre-registered: ship only if > 2% better AND within the latency budget)

- Forecast: Chronos-2 (zero-shot) WAPE 0.304 vs LightGBM 0.305 (+0.4%), 80% coverage 76.2% vs 79.2%; one 48 h refresh 1.7 s → **keep LightGBM**.
- Risk: TabPFN-3 not run yet (needs the owner's TabPFN licence key).

## Speed

- Optimiser per decision: median 0.06 ms, max 0.9 ms.
- Scale test: 5,000 tickets × 500 agents solved in 0.038 s.
- Full evaluation pipeline: 55.9 min.
