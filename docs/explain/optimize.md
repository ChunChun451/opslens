# optimize.py and the OpsLens policy (policies.py) — who should take which ticket now

## What it does
- Every time an agent becomes free or a ticket arrives, OpsLens decides which free agent
  takes which waiting ticket.
- It routes by the classifier's category (so the phone-menu mistakes do not cause transfers).
- It values each ticket by **how much serving it now reduces its breach risk** (risk model),
  plus fairness for time already waited, and a guard so no customer is ever left behind.
- It solves all free agents together as a **min-cost flow** (Google OR-Tools).
- Every assignment comes with a one-line reason a team lead can read.

## How it works, step by step
1. Every 3 simulated minutes, score each waiting ticket with the risk model twice:
   P(breach if it keeps waiting) and P(breach if a capable agent takes it now).
   **Rescue = the difference.** Tickets already lost, and tickets with plenty of time, have little
   rescue value; tickets near their deadline that can still make it have the most.
2. Value of agent a taking ticket i =
   urgency[P1 3 / P2 1.5 / P3 1] × impact (gold ×1.5, order value) × (rescue + 1.0 × hours waited)
   − 2.0 if the agent is not trained for the category − a small scarcity cost.
   - Language must match, always.
   - A cross-skill job (1.6× slower) is only allowed to rescue a ticket with rescue ≥ 0.5.
   - Starvation guard: after 240 minutes a ticket gets +50, so it is served next.
   - Scarcity: a rare agent (e.g. one of 3 Hindi + refund agents) prefers rare work, but never
     sits idle when only common work is waiting.
3. Keep each agent's 30 best tickets; solve "max total value, each ticket once, each agent up to
   their free slots" as a min-cost flow. If it ever took over 1 s we would fall back to greedy
   and log it (it never did).

## Worked example (Saturday 17 Oct, 20:35, test day 48)
Agent C08 (Team C, Hindi) is free. Ticket T060610: P1 missing item, Hindi customer, risk 0.30
higher if it waits → value 3 × 1.1 × (0.30 + 0.1) ≈ 1.49, the best of C08's options → assigned:
"P1 missing item, Hindi, waiting 6 min; breach risk … → … if served now".
That evening (18:00–24:00) breaches add up to **7** under OpsLens, **83** under FIFO and **26**
under priority-first; the queue peaks at 79 tickets vs 132 and 141.

## How the weights were chosen
On **validation days 36–42** only (seeds 1–3), one weight at a time, keeping the lowest breach %
whose slowest customers (P99 wait) are no worse than under Baseline B. Result there: OpsLens
3.75% vs Baseline B 5.94%. Learned along the way: without cross-skill rescue jobs, breaches rise
to 6.48%; fairness aging of 1.0 per hour works best; the scarcity cost matters little (±0.06).

## Results on the held-out test days (43–56, 5 seeds, same tickets and luck)
| | Baseline A (FIFO) | Baseline B (priority) | **OpsLens** |
|---|---|---|---|
| SLA breach % | 13.11 | 6.82 | **5.08** |
| P90 resolution (min) | 185 | 198 | **130** |
| Mean wait (min) | 65 | 68 | **40** |
| P99 wait (min) | 816 | 1,007 | **474** |
| Transfers per 100 | 4.66 | 4.59 | **0.97** |
| Reopen rate % | 3.93 | 3.93 | 4.35 |
OpsLens − Baseline B: breach **−1.74 points, 95% CI [−2.35, −1.13]**; P99 wait −534 min.
OpsLens − Baseline A: breach **−8.02 [−9.01, −7.04]**.
Solver: median 0.08 ms per decision, max 8.8 ms, no fallbacks. 5,000 tickets × 500 agents: 0.115 s.

## Weaknesses
- Reopens rise a little (4.35% vs 3.93%): the price of cross-skill rescue jobs.
- The value formula is hand-built (with tuned weights), not learned end to end.
- Decisions are myopic: the solver does not plan for tickets that will arrive in 10 minutes
  (the scarcity cost is the only look-ahead).

## How to read the code
`policies.py` → `OpsLensPolicy.decide()` (the flow), then `refresh()` (risk and rescue), then
`candidates()` (the value of each pair). `optimize.py` → `ticket_value()`, `solve()`.
Experiments: `eval/run_opslens.py` (`--tune` for validation, default for test).
