# Baselines — does OpsLens beat the best published rules? (added 18 Oct)

## What this does
- Baseline D ("industry standard") is our own reading of what helpdesks ship. A judge can say:
  "you built your own opponent". So we also test the rules the **scheduling literature** says are
  best for deadlines and delay costs.
- Two implementable rules: **least slack first** and the **generalized c-mu rule**.
- One rule that is **not implementable**: a **clairvoyant** least-slack-first that knows each
  ticket's true category and true handle time. It shows what perfect information is worth.
- Same tickets, same luck (common random numbers), same people and hours. Validation first,
  then the test days once. Code: `opslens/policies.py`, `eval/run_best_baselines.py`.

## How it works, step by step
1. **Same routing as D.** One queue. The longest-idle free agent takes the first ticket in the
   queue that they have the skill and the language for. Our classifier gives the category. No
   deliberate cross-skill jobs (D does not do them either). Only the **order** of the queue changes.
2. **Expected handle time.** From history days 1–35 only: mean minutes of work per (category,
   channel), first attempts that did not reopen. Example: refund chat 9.99 min, app_bug chat
   12.66 min, late_delivery chat 6.74 min (`expected_handle_minutes`).
3. **Least slack first** (Conway, Maxwell & Miller 1967; the size-aware deadline hybrid that
   Niyama, arXiv 2503.22562, 2025, finds beats plain EDF under high load):
   `slack = SLA deadline − now − expected handle time`. Smallest slack first. A ticket with
   slack < 0 cannot make its SLA even if someone starts now, so it goes after every ticket that can.
4. **Generalized c-mu** (Van Mieghem 1995; many servers with skills: Mandelbaum & Stolyar 2004):
   serve the ticket with the largest *marginal delay cost × service rate*. The theory needs a
   **convex** cost, so the cost is "minutes past SLA", smoothed at the deadline:
   `C(age) = w · tau·S · softplus((age − S)/(tau·S))`, so `C'(age) = w · sigmoid((age − S)/(tau·S))`,
   and `index = C'(age) / expected handle time`. S = SLA, `w = S^(−beta)`.
   - tau = how soft the corner at the deadline is (in SLA lengths).
   - beta 0 = every late minute costs the same; beta 1 = lateness counted in SLA lengths.
   - **8 shapes** (tau 0.1 / 0.25 / 0.5 / 1.0 × beta 0 / 1) were tried on validation days;
     the lowest breach % was kept: **tau 0.25, beta 1** (4.34%).
5. **Clairvoyant least slack (not implementable).** Least slack first, but it reads the true category (never misroutes)
   and this seed's true handle time for the next attempt. Run without and with OpsLens's
   staffing plan. **The true optimum is not computable**: 18,032 tickets in the test fortnight, 40 agents,
   skills, shifts and random reopens is a huge stochastic scheduling problem.
6. **Gate.** If least slack or c-mu had a validation breach % at or below OpsLens, the test days
   would not have run and the owner would decide. Validation (days 36–42, 3 seeds): OpsLens 2.13%,
   clairvoyant 3.65%, least slack 3.69%, c-mu 4.34%, D 4.56% → gate passed, test days run once.

## Worked example (from the docstrings, real handle times)
At 20:00, all chats, one free agent:
- T1 P1 refund, due 20:12, expected 9.99 min → slack 2.0.
- T2 P2 late_delivery, due 20:05, expected 6.74 → slack −1.7: **cannot make it**.
- T3 P1 app_bug, due 20:20, expected 12.66 → slack 7.3.

Least slack: T1, T3, then T2. Plain EDF (Baseline C) serves T2 first, misses it anyway, and then
misses T1 too. c-mu does the opposite with late tickets: a ticket past its SLA has the **highest**
marginal cost, so c-mu never gives up on a late customer. Example (tau 0.25, beta 1): T1 P1 refund,
age 45 of SLA 60 → (1/60) · sigmoid(−1) / 9.99 = 0.000449; a P2 refund at age 210 of 240 → 0.000157.

## Results (test days 43–56, 5 seeds; `results.json → best_baselines`)
| | Breach % | P1 breach % | Late min per 100 | P99 wait (min) |
|---|---|---|---|---|
| D: industry standard | 5.51 | 7.55 | 1,477.02 | 947.99 |
| C: SLA due (EDF) | 5.40 | 8.94 | 4,189.41 | 1,434.88 |
| Generalized c-mu | 5.30 | 7.97 | 1,255.00 | 910.30 |
| Least slack first | 3.96 | 7.00 | 3,525.96 | 1,378.51 |
| Clairvoyant least slack (not implementable) | 3.81 | 6.71 | 3,380.06 | 1,373.25 |
| **OpsLens** | **2.20** | **4.89** | **528.93** | **727.81** |

OpsLens − least slack: −1.75 [−2.07, −1.44] points; − c-mu: −3.10 [−4.50, −1.69];
− clairvoyant: −1.61 [−1.89, −1.33]. Perfect information buys least slack only −0.14 [−0.27, −0.01].

How to read this:
- **Least slack is the strongest published rule on breach %**, and it pays with lateness: the
  tickets it gives up on wait long (3,525.96 late minutes per 100, worse than D).
- **c-mu is the opposite**: best baseline on lateness (1,255.00) but hardly better than D on breaches.
- A sorting rule has to choose between the two goals. OpsLens beats both rules on **both** goals,
  and it also beats the clairvoyant rule: its gain comes from **better decisions** (which ticket
  is worth a rescue, a deliberate cross-skill job, which agent takes which ticket), not from
  knowing more. Without the risk model OpsLens falls to 4.21% (`ablations`), about where least slack is.

## Least slack + cross-skill rescue (the same freedom as OpsLens; `results.json → best_baselines.rescue`)
**Why.** OpsLens may give a ticket to an agent without the skill (1.6× slower, reopen chance 15%
instead of 4%) when its rescue value is ≥ 0.5. The rules above may not. A judge can say "the
comparison is rigged". So least slack gets the same freedom, by a plain rule, not a model
(`LeastSlackRescuePolicy`).

**The rule, step by step**
1. Every free agent first takes skilled work, exactly as in least slack first.
2. Agents still free now have no skilled work they can take. Going through the queue, most
   urgent first, a waiting ticket is **rescued** by the longest-idle of them who speaks its
   language, when both are true:
   - it is in danger: `slack < threshold` (slack as above), and
   - a slow job can still make it: `deadline − now − 1.6 × expected handle ≥ 0`.
     (Rescuing a ticket that will be late anyway only burns a slow job and a reopen risk.)
3. The job is marked `deliberate_cross_skill=True`: the simulator makes it 1.6× slower and
   gives it the higher reopen chance, exactly as for OpsLens.

**Worked example** (threshold 30, chat, every refund agent busy): T1 P1 refund due in 25 min,
expected 9.99 → slack 15.0 (in danger); slow way 25 − 16.0 = 9.0 ≥ 0 → free agent A09 (late
delivery team) takes it. T2 P1 refund due in 12 min → slow way 12 − 16.0 = −4.0 → not rescued;
it waits for a refund agent.

**Threshold chosen on validation days 36–42 only** (3 seeds, lowest breach %): 10 min 3.26%,
20 min 2.99%, **30 min 2.82%**, 60 min 3.35%, 120 min 3.19%, 240 min 2.90%. OpsLens 2.13% → the
gate passed (it stops the test run if the rule is at or below OpsLens). Then the test days ran
once, with OpsLens and plain least slack run again beside it: both reproduced their stored
numbers exactly.

**Results (test days 43–56, 5 seeds)**
| | Breach % | Late min per 100 | Reopen rate % | P99 wait (min) |
|---|---|---|---|---|
| Least slack first | 3.96 | 3,525.96 | 3.93 | 1,378.51 |
| Least slack + cross-skill rescue | 2.98 | 1,960.33 | 4.09 | 927.64 |
| **OpsLens** | **2.20** | **528.93** | 4.40 | **727.81** |

- The rescue is worth a lot to least slack: −0.98 [−1.16, −0.80] breach points.
- OpsLens − rescue rule: breach −0.78 [−0.99, −0.56] points; late minutes per 100
  −1,431 [−2,057, −805]; reopen rate +0.31 [+0.22, +0.40] points.

How to read this:
- **The fairness gap was real.** More than half of OpsLens's lead over least slack (0.98 of
  1.75 points) came from the freedom to do cross-skill jobs, not from the risk model and the
  optimiser.
- **OpsLens still wins** on breaches and by far on lateness, with the same freedom on both sides.
- **OpsLens still reopens more** (4.40% vs 4.09%): it makes more cross-skill jobs. That cost is
  measured and inside every OpsLens number above.
- The grid is not smooth (60 min is worse than both 30 and 240), and it has 3 seeds only: read
  the choice as "about 30 min", not as an exact optimum.

## The sealed second world (data seed 4242, `results.json → sealed_world_rerun`)
The sealed world was generated after the freeze and first run without these baselines, so it was
run a second time with D and the new rules. Nothing was chosen on it: OpsLens weights and the c-mu
shape are frozen. A, B, C and OpsLens came out identical to the first run, seed for seed.
- Breach %: OpsLens 3.07, clairvoyant + staffing 3.68, clairvoyant 4.00, least slack 4.21,
  c-mu 6.12, C 6.13, D 6.34.
- OpsLens − least slack −1.15 [−1.35, −0.94]; − D −3.27 [−4.45, −2.10]; − clairvoyant + staffing
  −0.62 [−0.84, −0.39]. The gap to the clairvoyant rule is smaller here than on the main world.
- Late minutes per 100: OpsLens 893.19 vs c-mu 1,445.45 and D 1,771.11. But the mean lateness of
  a breached ticket is 283.71 min for OpsLens vs 236.36 for c-mu and 277.20 for D: OpsLens has
  far fewer late tickets, and those few are not served faster than under c-mu.
- **Least slack + cross-skill rescue** (added later; the world was built a third time, only this
  rule ran beside OpsLens and plain least slack, which reproduced the re-run exactly; threshold
  30 min from the main world's validation days): breach % 3.35 vs OpsLens 3.07 →
  OpsLens − rescue −0.28 [−0.40, −0.16]. Late minutes per 100: 2,525.42 vs 893.19
  (−1,632 [−2,767, −498]). Reopen rate 4.05% vs 4.29% (+0.24 [+0.16, +0.32]).
  **Here the rescue rule closes most of the gap** (least slack alone: −1.15). OpsLens still wins
  on breaches, and by far on lateness, but on this world the breach lead is small.

## Weaknesses (say them before a judge does)
- **Cross-skill freedom.** Only least slack got a rescue rule; c-mu and the clairvoyant did not.
  The rescue rule is one plain rule with one parameter (6 thresholds tried); a smarter hand-made
  rule could close more of the gap. OpsLens still reopens more (4.40% vs 4.09%).
- Clairvoyant least slack is **not an upper bound** (OpsLens beats it). It shows what perfect
  information buys the best simple rule (−0.14 points). We cannot say how far OpsLens is from the
  true optimum.
- c-mu's theory is a heavy-traffic result; our floor is busy only at peaks, so it is not
  "optimal" here. Only two shape parameters were searched (8 shapes).
- Expected handle time ignores the agent (all skilled agents are equally fast in our simulator).

## How to read the code
1. `opslens/policies.py` → `RankedSkillsPolicy.decide` (the routing loop, same as D).
2. `LeastSlackPolicy.rank`, `GeneralizedCMuPolicy.index`, `ClairvoyantSlackPolicy.slack`,
   `LeastSlackRescuePolicy.rescue_candidate` and its `decide` (step 2 is the rescue pass).
3. `eval/run_best_baselines.py` → `validation()` (grid + gate), then `test()`; the rescue stage
   is `rescue_validation()` → gate → `rescue_test()` (`--rescue`).
4. Tests: `tests/test_best_baselines.py` (hand-computed cases, one per rule).
