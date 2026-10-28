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

## Test days 43-56 (run once, 28 Oct, frozen S2; harness commit c6e5ffd)

Seeds 1-5, as in the main evaluation. OpsLens rows use the staffing plan, as shipped; "routing alone" rows do not.

| Policy | Missed % | P1 missed % | P99 wait | Late min / 100 | Hindi missed % |
|---|---|---|---|---|---|
| Industry standard | 20.74 | 13.16 | 797.6 | 4,463 | 30.57 |
| Least slack + rescue | 9.76 | 11.03 | 660.4 | 2,491 | 15.15 |
| OpsLens today | 9.82 | 9.78 | 522.2 | 2,004 | 15.49 |
| OpsLens today, routing alone | 10.85 | 10.15 | 694.6 | 2,657 | 16.77 |
| **S2** | **8.79** | **8.08** | 410.2 | 1,766 | 11.70 |
| S2, routing alone | 9.83 | 8.37 | 697.1 | 2,636 | 12.77 |

| Difference | Missed % | P1 |
|---|---|---|
| S2 − industry standard | −11.95 [−14.88, −9.02] | −5.08 [−8.37, −1.79] |
| S2 − least slack + rescue | −0.98 [−1.28, −0.67] | −2.95 [−3.68, −2.22] |
| S2 − OpsLens today | −1.04 [−1.30, −0.78] | −1.70 [−1.87, −1.53] |
| S2 routing alone − industry standard | −10.91 [−14.05, −7.77] | −4.80 [−8.05, −1.54] |
| S2 routing alone − least slack + rescue | +0.07 [−0.11, +0.25] | −2.67 [−3.36, −1.98] |
| OpsLens today − industry standard | −10.92 [−13.66, −8.17] | −3.38 [−6.78, +0.02] |
| OpsLens today − least slack + rescue | +0.06 [−0.44, +0.57] | −1.25 [−2.06, −0.44] |

**Verdict: ship S2 on the 15/30/60 floor.** Step 1 of the owner's order holds: it beats the industry standard
(interval below 0 overall and on P1) and least slack + rescue (interval below 0 overall; P1 −2.95).

Said openly:
- Routing alone, S2 ties least slack + rescue overall (+0.07 [−0.11, +0.25]). It is clearly better on P1 (−2.67) and on Hindi.
  Of S2's 0.98-point lead over least slack, about 1 point comes from the staffing plan.
- OpsLens today would not have passed step 2: its P1 interval against the industry standard reaches +0.02.
- The test days are busier than validation (industry standard 20.7% vs 13.9%).
