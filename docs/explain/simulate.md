# opslens/simulate.py, world.py, policies.py, impact.py — the fair test bench

## What it does
- `simulate.py` replays a support floor minute by minute: tickets arrive, agents pick them up,
  finish, transfer them, customers reopen them. It works for any policy.
- `world.py` builds a `World`: the tickets, the 40 agents, and one seed's "luck" (handle times,
  reopens, absences).
- `policies.py` has the two baselines. OpsLens (M7) uses the same interface.
- `impact.py` turns a run into KPIs and compares policies with a paired 95% confidence interval.

## How it works, step by step
1. Events wait in a heap, sorted by time: FINISH, REOPEN, ARRIVAL, DECIDE. The clock jumps to
   the next event (nothing happens in between, so it is fast: 56 days in about 11 seconds).
2. After any arrival, finish or reopen, the policy is asked `decide(state, now)` right away.
   A 2-minute tick also asks it, to catch agents starting their shift.
3. The policy sees only what a real helpdesk shows (`TicketView`): times, channel, priority,
   language, the picked category. **It never sees the true category or the luck draws.**
4. An agent who opens a ticket outside their skills, thinking it was theirs, spends 4 minutes
   and sends it back (a transfer). A policy may also say "handle it anyway": then it takes
   1.6× longer and is more likely to be reopened.
5. Illegal decisions (wrong language, busy agent) raise an error: a policy cannot cheat.

## Common random numbers (why the comparison is fair)
All luck is drawn before the run and looked up by ticket *number*. Ticket T000812's first
attempt takes the same base time under every policy; only a policy's choices change the
outcome. A test proves it: Baseline A and B give each ticket exactly the same work content
but different resolution times.

## Worked examples (real numbers)
- **Hand-computed:** 2 agents, 3 tickets at minute 0 needing 10, 10 and 5 minutes. Agents take
  the first two at 0; the third starts at 10 and ends at 15. Resolution times 10, 10, 15 —
  the test checks this exactly.
- **Erlang C:** 3 agents, 10-minute average handling, 0.24 tickets per minute (utilisation 0.8),
  60,000 tickets. Simulated average wait **10.97 min** vs the textbook formula **10.79 min**
  (1.7% apart); chance of waiting **0.644** vs **0.647**.
- **Baselines on the 14 test days (43–56), 5 seeds, 18,032 tickets:**

| KPI | Baseline A (FIFO) | Baseline B (priority) | B − A, 95% CI |
|---|---|---|---|
| Breach % | 13.11 ± 2.23 | 6.82 ± 1.34 | −6.29 [−7.50, −5.07] |
| Mean resolution (min) | 80.7 | 84.6 | +4.0 [+0.6, +7.4] |
| P99 wait (min) | 816 | 1,007 | +191 [+97, +286] |

Priority-first saves P1 tickets but makes low-priority customers wait much longer. OpsLens must
beat **both**: fewer breaches *and* no starved customers.

## Weaknesses
- Agents are interchangeable apart from skills and languages; no breaks or learning.
- A customer never gives up (no abandonment); a reopen happens at most once.
- The floor is our model. That is why we also check the risk model and the pattern finder on
  real ServiceNow data (UCI), and why the Erlang-C test exists.

## How to read the code
1. `simulate.py` → `simulate()` (the loop), then `_start_work()` and `_finish()`.
2. `policies.py` → `TeamQueuePolicy.decide()` and `_pick()`.
3. `world.py` → `build_world()` (where the luck is drawn).
4. `impact.py` → `summarize()` and `paired_ci()`.
Tests: `tests/test_simulate.py` (hand cases, transfers, reopens, CRN, Erlang C).
