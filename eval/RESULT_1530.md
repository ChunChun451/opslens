# Result of the pre-registered 15 / 30 / 60 design run

Rule: `eval/PREREG_1530.md` (commit c5f5f70, before any run). Validation days 36-42 only. No test day was run.

## Estimates (days 1-35; the policy never reads the generator's settings)

| Number | Estimate | True | Source |
|---|---|---|---|
| Cross-skill slowdown | 1.609 | 1.6 | training-days pilot, 2,452 clean cross-skill jobs |
| Reopen after cross-skill work | 0.149 | 0.15 | pilot, 2,881 cross-skill first services |
| Reopen after trained work | 0.041 | 0.04 | history.csv, 64,580 tickets |
| Work-time factor after a reopen | 0.607 | 0.6 | history.csv, 2,640 reopened tickets |

## Design run (seeds 1-10)

| Policy | Missed % | P1 missed % | P99 wait (min) | Late min / 100 |
|---|---|---|---|---|
| Industry standard | 13.87 | 10.76 | 615.9 | 2,577 |
| Least slack + rescue | 7.69 | 9.35 | 231.5 | 1,256 |
| OpsLens today | 7.66 | 8.46 | 221.0 | 1,146 |
| S1 (lost lane + cross-skill gate) | 7.33 | 7.50 | 123.0 | 969 |
| **S2** (S1 + live risk, queue-aware clock, weight 0.5) | **6.90** | **7.00** | 96.7 | 942 |
| S3 (S2 + P1 guard) | 6.92 | 6.92 | 102.2 | 944 |

- vs OpsLens today: S1 −0.33 [−0.46, −0.20], P1 −0.96; S2 −0.76 [−0.90, −0.63], P1 −1.45; S3 −0.74 [−0.88, −0.60], P1 −1.53.
- All three passed all four checks. S2 was picked: lowest missed %; S3 is within 0.05 points but more complex.
- S2's blend weight: 0.25 → 6.93, 0.5 → 6.90, 0.75 → 6.91. The untuned 0.5 stays.

## Confirmation (seeds 101-120, run once)

| Policy | Missed % | P1 missed % | P99 wait | Late min / 100 |
|---|---|---|---|---|
| Industry standard | 13.57 | 10.70 | 611.1 | 2,469 |
| Least slack + rescue | 7.82 | 9.47 | 255.7 | 1,269 |
| OpsLens today | 7.83 | 8.67 | 254.8 | 1,190 |
| **S2** | **7.11** | **7.27** | 95.0 | 990 |

- S2 − OpsLens today: −0.73 [−0.83, −0.62], P1 −1.40 [−1.56, −1.23]. All four checks pass: **confirmed**.
- S2 − industry standard: −6.46 [−6.97, −5.96], P1 −3.43 [−3.93, −2.94].
- S2 − least slack + rescue: −0.71 [−0.81, −0.61], P1 −2.20 [−2.33, −2.08].
- OpsLens today − least slack + rescue: +0.02 [−0.11, +0.14] (the tie, again).

## Next (owner's call)

The test-day run (43-56, once, frozen code) under the ship bar in section 5 of the pre-registration.
Not run yet.
