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
   urgency[P1 3 / P2 1.5 / P3 1] × impact (gold ×1.5, order value) × (rescue + aging)
   − 2.0 if the agent is not trained for the category − a small scarcity cost.
   - **Aging is counted in SLA lengths** (3.0 per SLA waited, capped at one SLA): a P1 (60-min
     SLA) gains value 24× faster than a P3 (24-hour SLA), and a ticket already past its SLA stops
     gaining, so lost tickets cannot crowd out tickets that can still be saved.
   - **Guard:** a ticket 240 minutes past its SLA gets +50 and is served next.
   - Language must match, always. A cross-skill job (1.6× slower) only to rescue a ticket with
     rescue ≥ 0.5.
   - Scarcity: a rare agent (e.g. one of 3 Hindi + refund agents) prefers rare work but never
     sits idle when only common work is waiting.
3. Keep each agent's 30 best tickets; solve "max total value, each ticket once, each agent up to
   their free slots" as a min-cost flow. Time limit 1 s, then greedy (never needed).

## The story of v1 and v2 (say it if asked — it is a strength)
Version 1 aged tickets per hour and started the guard after 240 minutes of waiting. It won on
normal test days (5.08% breaches) but **failed the +25% volume stress test: 51.7% vs 29.1%** for
priority-first — under overload, old already-lost tickets crowded out P1s that could be saved.
We kept that result, designed v2 (aging in SLA units, guard after lateness) and chose it **on
validation days only**, at normal volume and +25% volume: v2 2.22% / 12.82% vs Baseline B
5.94% / 16.55% and v1 3.75% / 28.43%. Then we ran the test days once.

## Worked example (Saturday 17 Oct, 18:00–24:00, test day 48)
Breaches that evening add up to **7** with OpsLens, **26** with priority-first and **83** with
FIFO; the queue peaks at 89 tickets vs 141 and 132. A typical decision: agent B10 (Team B,
regional language) takes T060593, a P1 payment failure waiting 8 minutes — value 1.81, the
highest of his options: "P1 payment failure, English, waiting 8 min; low risk - served in turn".

## Results on the held-out test days (43–56, 5 seeds, same tickets and luck)
| | Baseline A (FIFO) | Baseline B (priority) | **OpsLens** |
|---|---|---|---|
| SLA breach % | 13.11 | 6.82 | **2.38** |
| P1 breach % | 27.34 | 9.13 | **4.86** |
| Hindi customers' breach % | 22.11 | 16.18 | **3.84** |
| P90 resolution (min) | 185 | 198 | **141** |
| P99 wait (min) | 816 | 1,007 | **732** |
| Transfers per 100 | 4.66 | 4.59 | **0.97** |
| Reopen rate % | 3.93 | 3.93 | 4.39 |
OpsLens − Baseline B: breach **−4.44 points, 95% CI [−5.58, −3.30]**; P90 −58 min; P99 −275 min.
OpsLens − Baseline A: breach **−10.73 [−12.94, −8.52]**.
Solver: median 0.07 ms per decision, max 2.3 ms, no fallbacks. 5,000 tickets × 500 agents: 0.115 s.
Ablations and stress tests: `docs/NUMBERS.md`.

## Weaknesses
- Reopens rise a little (4.39% vs 3.93%): the price of cross-skill rescue jobs.
- The value formula is hand-built (with tuned weights), not learned end to end.
- With instant decisions, usually one agent is free at a time, so the joint solve rarely beats a
  per-agent greedy pick (see the ablations). It matters at shift starts and at scale.

## How to read the code
`policies.py` → `OpsLensPolicy.decide()` (the flow), then `refresh()` (risk and rescue), then
`candidates()` (the value of each pair). `optimize.py` → `ticket_value()`, `solve()`.
Experiments: `eval/run_opslens.py` (`--tune`), `eval/run_design_v2.py` (v1 vs v2 on validation).
