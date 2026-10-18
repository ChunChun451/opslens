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
5. **Clairvoyant ceiling.** Least slack first, but it reads the true category (never misroutes)
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
| Clairvoyant ceiling (not implementable) | 3.81 | 6.71 | 3,380.06 | 1,373.25 |
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

## Weaknesses (say them before a judge does)
- **The rules may not make cross-skill jobs**; OpsLens may (when rescue ≥ 0.5). That is part of
  what OpsLens adds, but "least slack + cross-skill rescue" was not tested. The cost shows: OpsLens
  reopen rate 4.40% vs 3.93% for every rule.
- The clairvoyant is a ceiling **for this rule**, not for the problem. We cannot say how far
  OpsLens is from the true optimum, only that perfect information adds little to a sorting rule.
- c-mu's theory is a heavy-traffic result; our floor is busy only at peaks, so it is not
  "optimal" here. Only two shape parameters were searched (8 shapes).
- Expected handle time ignores the agent (all skilled agents are equally fast in our simulator).

## How to read the code
1. `opslens/policies.py` → `RankedSkillsPolicy.decide` (the routing loop, same as D).
2. `LeastSlackPolicy.rank`, `GeneralizedCMuPolicy.index`, `ClairvoyantSlackPolicy.slack`.
3. `eval/run_best_baselines.py` → `validation()` (grid + gate), then `test()`.
4. Tests: `tests/test_best_baselines.py` (hand-computed cases, one per rule).
