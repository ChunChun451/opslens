# floor.py — the physical floor, and the proof that no policy can beat it

## What it does
- For every ticket, it computes the earliest moment the ticket could possibly be resolved, if every
  agent on shift were free for it the moment it needs one (unlimited capacity).
- If even that earliest moment is past the SLA, the ticket breaches under **any** policy. These
  tickets are the floor.
- It is exact: no simulation, no sampling, just four plans per ticket. The test days take 2 seconds.
- It turns "OpsLens is good" into "OpsLens captures X% of everything that is possible".

## Is the floor the same for any data?
**No.** The *method* works for any data; the *number* belongs to the data. 1.31% is the floor of our
14 test days (18,032 tickets, 5 seeds of luck: 1.23–1.38%). Change the tickets, the SLAs, the roster
or the luck and the floor changes. On a real company's export you would compute it again.

## The proof in simple words
Take one ticket and any policy the simulator accepts (work starts only with an agent who is on shift
and speaks the customer's language — the simulator refuses anything else).
1. Under the policy, the ticket waits, maybe gets transferred, gets worked on, maybe reopens, gets
   worked on again.
2. A transfer only wastes time. (Since 18 Oct a transfer does not change how long the real work takes.)
3. Each piece of work is done either by a trained agent (normal time) or by an untrained agent who
   speaks the language (1.6× the time, and a reopen chance of 15% instead of 4%).
4. With unlimited agents, nothing else can delay the ticket, and finishing earlier never hurts.
   So the best plan starts each piece of work at the earliest moment someone suitable is on shift.
5. There are only four plans (trained or not, for the first work and for the work after a reopen).
   The best of the four is the fastest the ticket can ever be resolved. A real policy follows one
   of these plans, and never starts earlier. So it can never be faster. ∎

## How we checked the proof (not just wrote it)
`tests/test_floor.py` builds 25 random small worlds (random shifts, languages, skills, reopens,
SLAs). Ten policies — FIFO, priority, SLA-due, industry standard, least slack, clairvoyant, OpsLens
v3 and v4, and two policies that make **random legal choices** — must each breach every ticket the
floor calls unavoidable. No counterexample. The floors are not trivial (8–28 of 40 tickets), and in
3 of the 25 worlds the best policy hits the floor exactly, so the bound can be tight.

## What we found while proving it (the useful part)
1. **A fairness flaw in our simulator.** A ticket's work time was drawn per *attempt*, and a
   transfer counted as an attempt. So a misrouted ticket got a different work time than the same
   ticket routed right: policies with many transfers (FIFO: 4.6 per 100) did not see exactly the same
   luck as OpsLens (1.0). And a clever policy could have misrouted on purpose to re-roll a long job.
   Fixed: the k-th piece of real work always uses draw k. Every number was regenerated.
2. **A missing safety check.** The simulator did not refuse work started by an agent who is off
   shift. Our policies never did it, but now it is enforced (a test proves it).
3. **v4 did not survive.** A cheaper cross-skill price (v4) looked better under the old simulator.
   Under the corrected one its gain was not clearly above zero, so our pre-registered rule kept v3.
4. **Where the floor comes from** says where to invest: tickets whose own work is longer than
   their SLA cannot be saved by routing; tickets that breach only because nobody who speaks the
   language is trained and on shift can be saved by cross-training (see the playbooks).

## Weaknesses
- The floor is optimistic: no real floor has unlimited agents. The true best possible breach rate
  lies between the floor and the best policy we know.
- It is a bound for this simulator's rules. A real floor has things the simulator does not model
  (e.g. an agent handling two chats at once), which could move it.

## How to read the code
`opslens/floor.py`: `unavoidable()` builds, per language and category, when trained and untrained
agents are on shift (`shift_intervals`, `merge`), then `best_resolution()` tries the four plans per
ticket with `earliest_start()`. `eval/run_floor.py` runs it on the test days (both rosters) and
computes the share captured. Tests: `tests/test_floor.py`.
