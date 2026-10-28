# Design note: OpsLens on the 15 / 30 / 60 minute promises

Status: for owner review. Nothing here is adopted. No test day (43-56) was run.

Data: validation days 36-42 (warm-up day 35), seeds 1-5, the branch's floor and models.
Every policy got the same tickets, the same luck and the same agents.
Scripts: `eval/run_diag_1530.py`, `eval/run_retune_1530.py`.
Outputs: `eval/parts/food_1530/diagnosis.json`, `diagnosis_tickets.csv`, `retune_1530.json` (+ `.txt` logs).
The runs reproduce the first look exactly (OpsLens 7.74% / P1 8.24%).

## 1. Where we stand (validation days, 5 seeds)

| Policy | Missed % | P1 missed % | Hindi missed % |
|---|---|---|---|
| Industry standard (Baseline D) | 14.61 | 9.94 | 25.06 |
| Least slack + rescue (10 min) | 7.82 | 9.32 | 12.33 |
| OpsLens now | 7.74 | 8.24 | 12.04 |
| OpsLens live risk | 8.15 | 7.67 | 11.30 |

- OpsLens now − least slack + rescue: −0.08 [−0.51, +0.36] overall (a tie), P1 −1.09 [−1.78, −0.39].
- Live risk − OpsLens now: +0.41 [+0.22, +0.59] overall (worse), P1 −0.57 [−0.98, −0.16] (better).
- The physical floor (no legal policy could make it) is 4.57% of tickets (603.8 per run), and 4.92% of P1s.
- So OpsLens now misses 3.17 points above the floor (418 tickets per run). Least slack + rescue: 3.24. Industry: 10.04.
- The staffing plan only covers test days 43-56. On validation days OpsLens with and without it is identical.

## 2. Why OpsLens misses (avoidable misses per run)

Each avoidable miss gets one cause. The rules are in `diagnosis.json` → `cause_rules`. In short:
"passed over" means a free trained agent who speaks the language took another ticket with more slack
(or a lost one) while this one was still savable.

| Cause | OpsLens now | of which P1 | Live risk | Least slack + rescue |
|---|---|---|---|---|
| Passed over for a lost ticket (domino) | **123.2** | 8.6 | **247.0** | 0 |
| Skill gap (no trained agent in its language on shift) | **92.8** | 54.8 | 20.6 | 119.6 |
| Congestion (agents only took tickets with less slack) | 57.4 | 30.6 | 84.4 | 113.2 |
| Passed over for same/higher priority with more slack | 33.6 | 7.8 | 40.2 | 0 |
| Busy when it landed (all trained agents busy to its last start) | 31.2 | 29.4 | 29.4 | 18.6 |
| Reopened | 28.0 | 5.8 | 8.2 | **92.0** |
| Cross-skill too slow (1.6x) | 24.0 | 13.2 | 4.6 | **74.6** |
| Transfer (wrong team first) | 12.4 | 10.0 | 16.2 | 10.2 |
| Passed over for lower priority | 11.4 | 7.2 | 15.2 | 0 |
| Passed over for a cross-skill job | 4.2 | 1.2 | 6.0 | 0 |
| **Total avoidable** | **418.2** | **168.6** | **471.8** | **428.2** |

What stands out:
- **The domino is the biggest cause.** 123 misses per run (0.93 points). 104 of them are Team D tickets, mostly P3.
  Per run, OpsLens serves 244 lost tickets while a savable ticket waits for the same agent. 197 of those were already past their promise.
  A lost ticket keeps value 0.4 × urgency (aging_lost 0.2 + rescue floor 0.2). That beats a young P3 (about 0.45 after 5 minutes).
  Live risk doubles the domino (247). Its rescue for young P3s is lower, so they lose these ties more often.
- **Lost really means lost.** Of 846 tickets per run served with P(miss even if served now) ≥ 0.95, 1.4 made it (0.17%).
  Of the waiting tickets sampled at that level, 100% missed.
- **Skill gap is the biggest P1 cause** (54.8 of 168.6). It is Team B (76.6) and Hindi (63.8): Hindi payment failures when no Hindi payments agent is on shift.
  Live risk cuts skill gap from 92.8 to 20.6. Its clock part knows no trained agent is coming, so it rescues cross-skill.
  OpsLens now blocks those rescues: the LightGBM rescue must reach 0.5 (cross_skill_min_rescue).
- **Least slack + rescue pays for its rescues.** It runs 1,136 cross-skill jobs per run (819 on P1).
  That gives 92 reopen misses and 75 too-slow misses. OpsLens now has 28 and 24.
- **Least slack + rescue never has a domino.** It ranks negative-slack tickets last, so it never takes a lost ticket while a savable one waits.
- **Busy when it landed** is almost all P1 (29.4), mostly Team B and Hindi. It is not mainly Team A.
- **P1 misses cluster at lunch and dinner.** Avoidable P1 misses per run: 12:00-13:59 44.2; 19:00-22:59 45.4; all other hours 79.0.

## 3. Ticket by ticket: OpsLens now vs least slack + rescue (per run)

| | Tickets | Main causes (the decision that mattered) |
|---|---|---|
| Least slack kept, OpsLens missed | 242.2 (P1 89.0) | OpsLens served a lost ticket instead 80.2; skill gap 39.2; congestion 34.6; took a same-priority ticket with more slack 27.2; busy 15.8; reopen 15.0; cross-skill too slow 11.8; took lower priority 8.8 |
| OpsLens kept, least slack missed | 252.2 (P1 144.2) | Least slack's rescue reopened 73.8 (P1 68.2); skill gap 68.0; cross-skill too slow 50.8 (P1 29.4); congestion 47.2 |

- Where OpsLens loses, it picked the ticket up 16 minutes later (median) than least slack did.
- Live risk vs least slack: live misses 320.8 that least slack keeps, and 181.6 of them are the domino. It keeps 277.2 that least slack misses (skill gap 102.2, reopen 75.8).
- Live vs OpsLens now: live loses 218.8 (domino 118.4) and wins 165.2 (skill gap 72.8).
- Ticket lists: `eval/parts/food_1530/diagnosis_tickets.csv`.

## 4. How much do the stale weights explain? Very little.

We re-chose the main weights on validation days only, using the 15/60/240 coordinate search plus the P1 urgency weight (`retune_1530.json`).
- Only one weight moved: aging_per_sla 3.0 → 6.0.
- In-sample (so optimistic): −0.10 [−0.22, +0.03] overall, and **P1 +0.34 [+0.11, +0.56] worse**.
- Under the adoption rule below, this would be rejected (P1 rises).
- Other findings: cross_skill_min_rescue 0.3 or 0.7 is worse than 0.5. P1 urgency 5 lowers P1 (8.25%) but raises overall (7.84%). The other weights are flat.
- So the gap to least slack is about structure, not tuning.

## 5. The risk model (evidence for lever 1)

We sampled every waiting ticket every 20 minutes and scored P(miss if it keeps waiting) against what happened. Days 36-42, 5 seeds.

| Score | AUC | P1 AUC | Brier | Mean score (actual rate) |
|---|---|---|---|---|
| Live: clock part | 0.673 | 0.809 | 0.232 | 0.084 (0.283) |
| Live: LightGBM, re-scored every decision | 0.826 | 0.818 | 0.223 | 0.492 (0.283) |
| Blend 0.25 / 0.5 / 0.75 clock | 0.830 / 0.828 / 0.825 | 0.825 / 0.829 / 0.832 | 0.167 / 0.150 / 0.172 | |
| Now: LightGBM refreshed every 3 min (own run) | 0.833 | 0.860 | 0.191 | 0.427 (0.231) |

- The clock part predicts a third of the real risk.
  It takes the soonest-free capable agent for every waiting ticket. It ignores the queue ahead.
- The 3-minute-old LightGBM score ranks as well as the fresh one. Staleness is not the problem on this floor.
- The blend weight barely changes ranking (AUC 0.825-0.830 across 0.25-0.75).

## 6. The levers

Effects are guesses from the counts above, as points of missed % on validation days, against OpsLens now.
They are not measured. Ranked by expected value.

### Lever 3 (rank 1): a "likely lost" lane
- **Evidence.** Domino 123 misses per run now, 247 with live risk (Team D, P3). Lost tickets served while savable ones waited: 244 per run (197 already past promise).
  At P ≥ 0.95, 99.8% of served tickets and 100% of sampled waiting tickets missed anyway.
- **Mechanism.** If P(miss even if served now by this agent) ≥ 0.95, the ticket goes behind every savable ticket that agent could take.
  P uses the lognormal handle time, 1.6x for cross-skill, and the agent's speed. It includes tickets already past their promise.
  An agent with nothing savable still takes it, so no time is wasted.
  The 8-hour guard is unchanged and still pulls a very late ticket to the front.
- **Expected.** Overall −0.4 to −0.7 on OpsLens now; −0.8 to −1.3 on live risk. P1 −0.05 to −0.2 (few P1 victims; lost P1s were lost anyway).
- **Risk.** Late minutes and P99 wait of lost tickets rise. Least slack + rescue shows the size: 1,226 late min/100 vs 1,145 for OpsLens.
  The freed time still has to be spent later. The lane could lock in: a starved ticket becomes lost, then waits longer. The guard bounds this.

### Lever 2 (rank 2): cross-skill only when it can fit, and when no trained agent can come in time
- **Evidence.** Skill gap: 92.8 now (P1 54.8, Team B Hindi) vs 20.6 with the live clock.
  OpsLens now's cross jobs already fit on average (mean P(fit) 0.94; only 10 per run futile by expectation). So "fit the slack" alone changes little.
  The real costs are elsewhere. The 0.5 LightGBM gate blocks rescues the clock allows.
  Cross-skill work reopens 15% of the time vs 4% (least slack + rescue: 92 reopen misses per run).
- **Mechanism.** Allow a cross-skill job only when two things are true.
  First, P(1.6x handle fits the slack) × (1 − 0.15) > P(a trained agent starts and finishes in time) × (1 − 0.04).
  Second, it beats leaving the ticket for the trained queue. The clock part answers both.
  This replaces the 0.5 LightGBM gate. The mismatch penalty stays for the value.
- **Expected.** On OpsLens now: overall −0.2 to −0.4; P1 −0.5 to −0.9 (most of the 54.8 P1 skill-gap misses). On live risk: about 0 to −0.05 (only the reopen term is new).
- **Risk.** Rescues take Hindi speakers from their own queues (live risk's congestion is 84 vs 57). More cross work means more reopens.

### Lever 1 (rank 3): the live risk blend and per-decision re-scoring
- **Evidence.** Live risk's gains come from the clock in cross-skill decisions (skill gap 92.8 → 20.6). Its losses come from the queue value (domino 123 → 247; congestion 57 → 84).
  The clock under-predicts by 3x because it ignores the queue ahead. The blend weight moves AUC by under 0.01.
- **Mechanism.** Do not tune the 0.5 first. Use the clock only where it is right: the cross-skill test (lever 2) and the lost test (lever 3).
  Keep the re-scored LightGBM part for the queue value. If the clock goes into the value too, first make it count the queue.
  That means the wait until the k-th capable agent frees, where k is the ticket's rank by slack among tickets needing those agents.
  Only then choose the weight from {0.25, 0.5, 0.75} on validation days.
- **Expected.** The blend weight alone: ±0.1. Clock-for-gates (with levers 2 and 3) keeps live's P1 gain (−0.5) without its +0.41 overall loss.
- **Risk.** The queue-aware clock costs compute (already 8-10 s per simulated day). It is a new model with its own errors.

### Lever 5 (rank 4): never push another P1's slack below zero (hard rule)
- **Evidence.** Per run, an agent took another ticket while a savable P1 it could serve was waiting 470 times (182 P2, 39 P3, 43 lost tickets, 249 other P1s).
  But only about 25 P1 misses per run trace to such a pick (lost 8.6, lower priority 7.2, same priority 7.8, cross job 1.2). Most of those P1s were served in time by another agent.
- **Mechanism.** Before a non-P1 pick, check whether some waiting P1 that this agent could serve would have no other capable agent free before its last start.
  If so, the agent takes the P1. This needs the queue-aware next-free estimate from lever 1.
  Without that check the rule would block hundreds of harmless picks per run.
- **Expected.** P1 −0.2 to −0.4. Overall 0 to +0.1 (P2 and P3 wait a little longer).
- **Risk.** A hard rule on noisy handle-time guesses holds agents for P1s that someone else would have served. P2 misses may rise. Lever 3 already covers the 8.6 lost-ticket cases.

### Lever 4 (rank 5): shorter jobs first when slack is comfortable
- **Evidence.** Weak. Same-priority passes 33.6 and congestion 57.4 per run show order matters in peaks.
  But nothing here shows short-first would save them. Mean served handle time is 5.1 min; Team D's is 7-8 min.
- **Mechanism.** Among tickets whose slack is above, say, 2x their expected handle time, prefer the shorter one (value per expected minute).
  Tickets near their last start keep their order.
- **Expected.** Overall 0 to −0.15. P1 about 0 to slightly better (late deliveries are the shortest jobs).
- **Risk.** Team D (longest jobs, already the worst team) waits longer. With lever 3 that can ratchet: starved D tickets become lost and go to the back.

### Lever 6 (rank 6): a staffing target that matches the promises
- **Evidence.** On validation days this lever has no effect by design: the plan only covers test days.
  The Erlang C check on training days uses the target "answered within the tightest promise minus handle time, for 80%", instead of "mean wait ≤ 15 min".
  Under that check, today's target leaves Team B short in 34 hours per week and Team A in 9. Teams C and D are fine.
- **Mechanism.** Same agent-hours. Plan moves would go to Team B (P1 payment failures, Hindi) at lunch and dinner.
- **Expected.** Test days only: P1 −0.1 to −0.3, overall ±0.1. It cannot be checked on validation days unless we build a validation-week plan from days 1-35 only (that would need its own pre-registration).
- **Risk.** W5's roster search found no gain; the plan moves at most 6 shifts a week. The plan helps only OpsLens, so routing alone must also be reported.

### Lever 7 (not now): keep-ready capacity for imminent P1s
- **Evidence.** Busy-when-it-landed P1 misses: 29.4 per run, mostly Team B and Hindi. Least slack + rescue cuts the same cause to 16 by cross-skill rescue.
  So lever 2 is the cheaper fix. The evidence does not demand idle capacity.
- **Revisit** only if busy-when-it-landed P1 misses stay above 20 per run after levers 2 and 3.

## 7. Proposed candidates (to be fixed in code before any run)

- **S1** = OpsLens now + lever 3 + lever 2 (clock used only for these two gates).
- **S2** = S1 + lever 1 (queue-aware clock in the value; blend weight chosen from {0.25, 0.5, 0.75}).
- **S3** = S2 + lever 5.
- Levers 4 and 6 wait. Lever 7 is not built.

## 8. Proposed pre-registered adoption rule

1. **Design run (validation days 36-42 only).** Candidates S1-S3 vs OpsLens now. Seeds 1-10, paired with common random numbers (seeds 1-5 are already seen; 10 seeds narrow the interval).
2. **Pass** = the 95% interval of (candidate − OpsLens now) overall missed % is entirely below 0, **and** the mean P1 missed % difference is ≤ 0.
   Guardrail: P99 wait no worse than the industry standard's (the existing re-tune rule).
3. **Pick.** Among passing candidates, the lowest validation missed %. Within 0.05 points, the simpler one wins.
4. **Confirm once** on 20 fresh seeds (101-120), validation days, same two conditions. If it fails, OpsLens now stays. No second try on those seeds.
5. **Ship bar on test days 43-56 (run once, frozen code and weights):**
   - beat the industry standard clearly: 95% interval below 0 overall **and** on P1;
   - beat least slack + rescue, not tie: 95% interval below 0 overall, and mean P1 difference ≤ 0;
   - show routing alone too (OpsLens without the staffing plan), because only OpsLens gets the plan.
   If the bar is not met, ship main's 1 h / 4 h / 24 h promises.
6. Today, OpsLens now fails step 5 against least slack + rescue on validation days (−0.08 [−0.51, +0.36]). S1 is expected to clear it by about 0.5-1.0 points.
