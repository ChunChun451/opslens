# Food-delivery promises: pre-registration (27 Oct 2026)

Committed before any validation-day weight choice and before any test-day run on the new promises.

## Why

The simulated food floor used IT-helpdesk promise lengths (P1 1 h, P2 4 h, P3 24 h), and some
late-delivery tickets were P3, so a customer whose food was late could get a 24-hour promise. The owner
decided on 27 Oct to use food-delivery promises.

## Promise lengths (config/sla.yaml)

| Priority | Meaning | Before | Now |
|---|---|---|---|
| P1 | live order | 60 min | 15 min |
| P2 | delivered but wrong | 240 min | 60 min |
| P3 | no live order | 1440 min | 240 min |

## Priority table (config/generator.yaml, share of P1 / P2 / P3)

Written and committed (2883269) before the first run.

| Category | Before | Now |
|---|---|---|
| late_delivery | .70 / .25 / .05 | 1 / 0 / 0 |
| payment_failure | .60 / .35 / .05 | 1 / 0 / 0 |
| missing_item | .55 / .40 / .05 | 0 / .95 / .05 |
| wrong_item | .30 / .60 / .10 | 0 / .95 / .05 |
| refund | .10 / .65 / .25 | 0 / .85 / .15 |
| app_bug | .15 / .45 / .40 | .10 / .20 / .70 |
| account | .02 / .28 / .70 | .02 / .08 / .90 |
| restaurant_partner | .20 / .50 / .30 | .05 / .15 / .80 |

Email no longer downgrades late delivery or payment failed from P1 to P2 (`always_p1`). Other email P1s
still become P2, as before.

## Calibration (Baseline A, the 56-day history)

Targets (CLAUDE.md): breach 12-18%, mean utilisation 0.70-0.80, Team C weekend-dinner rho 1.2-1.5.

| Setup | Breach | Utilisation | Team C rho |
|---|---|---|---|
| Old roster, 1,130 tickets per weekday, old promises (15 Oct) | 13.1% | 0.80 | 1.40 |
| Old roster, 1,130 per weekday, new promises | 37.9% | 0.80 | 1.40 |
| Searched roster, 1,017 per weekday, new promises (shipped) | 17.9% | 0.71 | 1.53 |

The roster search changed start hours, teams and days off, never the promises. It was scored on
days 1-14, 1-28 and 1-42 only (never the test days), with these guards: Hindi speakers may not join
Team B, so the planted Hindi refund gap stays 3 agents (B01, B02, B05, none at night); the night
generalists A09, B11, D11 stay at 22:00; Team C's weekend-dinner rho stays at most 1.5 on the
search's own ticket draw. Team sizes now A 13, B 12, C 5, D 10 (before 9, 11, 9, 11).

With a 15-minute P1 promise, first-come-first-served needs capacity that follows the lunch and dinner
peaks, so the breach target is reached only near the bottom of the utilisation range, and Team C's
weekend-dinner rho lands 0.03 above its range on the final draw. The owner accepted this on 27 Oct
(volume x0.90, rho 1.53) rather than trying ticket draws until all three landed.

Planted signals in the new history: Hindi refunds and payments wait 170.8 min vs 9.3 min for English;
cluster 17 is 4.9% of wrong items vs 1.9% of tickets; transfers per 100: call 11.8, chat 2.1.

## Rules for what follows

1. Weights and thresholds are chosen on validation days 36-42 only; test days 43-56 are run once.
2. Optimizer weights: `eval/run_retune_sla.py`, rule in the file (coordinate search over a fixed grid,
   3 seeds, lowest validation breach among values whose P99 wait is at most the industry standard's;
   the shipped value stays unless another is better by more than 0.02 points). The classifier threshold,
   live-alert rule and least-slack-rescue threshold are re-chosen by their own scripts on validation
   days, as before.
3. After the weights are frozen: the full `make eval` with the blind test, the 30 random worlds and a
   new sealed world, each once. Nothing is re-run to get a better number.
4. Sealed world: data seed 8383 (never used), generated after the freeze, run once.
5. 30 random worlds: same seeds 7001-7030 and the same rule as before (OpsLens lowest, within 0.05
   points, in at least 27 of 30). Promise lengths are drawn around the new promises: P1 10-20 min,
   P2 40-80 min, P3 160-320 min (before: 30-90, 120-360, 720-2160).
6. Stop and report, without forcing a result, if OpsLens does not beat the industry standard
   (Baseline D) on the test days.
7. Results measured on the earlier promises (v1-v3 records, v4, the v5 confirmation, the CP-SAT roster,
   v6, sealed worlds 4242 and 5151) are kept as they are and labelled as measured on the earlier
   promises.
