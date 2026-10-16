# playbooks.py — fix the problem at its source, and measure it

## What it does
- Every evidence card names a cause (process, partner, skill gap, spike, capacity).
- For each cause, OpsLens writes an **upstream action** for a team outside support:
  product (phone menu, status banner, self-serve refund), partner operations, training.
- Each action comes with a **scenario**: how the tickets or the roster would change.
- `eval/run_playbooks.py` replays the 14 held-out test days with that change, under
  priority-first and under OpsLens, and reports what it saves — with a 95% interval.
- The LLM writes the request to the owner team, under the same no-digit rule as the brief.

## How it works, step by step
1. `playbooks_from_cards()` reads the cards found on history days (1–42). The card's own
   segment and numbers decide the scenario:
   - **Process** (phone tickets transferred 13.0 vs 2.6 per 100) → "fix the phone menu".
     Scenario: 80% of wrong phone-menu choices become right (2.6 ÷ 13.0 = 20% remain, the
     level of the other channels).
   - **Partner** (cluster 17: 24.5% wrong items vs 9.6%) → "kitchen order-check".
     Scenario: remove the cluster's extra wrong-item tickets, down to the normal share.
   - **Skill gap** (Hindi refunds wait 336 vs 66 min) → "cross-train 2 Hindi speakers".
     `pick_cross_trainees()` picks agents who already speak Hindi and whose shifts cover the
     most hours that no trained Hindi agent covers today. It picked A09 and D11 (night shifts).
   - **Volume spike** → "status banner the moment a live spike alert fires". Scenario: for 4 h
     after each alert OpsLens raised on the test days (the false one included), 30% of new
     tickets of that category are not opened (ASSUMPTION).
   - **Capacity** (Team C weekend dinner, Team B weekday night) → "self-serve instant refund
     for orders up to ₹300 in that window". 60% of eligible customers use it (ASSUMPTION).
   - Cause "other" gets no playbook.
2. `apply_scenario()` changes a copy of the test-day tickets (or the roster). The same
   tickets are removed for every policy and seed, so the comparison stays paired.
3. The simulator replays days 43–56 (day 42 warm-up), 5 seeds, and we compare with the same
   policy without the playbook.
4. Every ASSUMPTION is re-run at a low and a high value (3 seeds).

## Worked example
**Cross-train 2 Hindi speakers (A09, D11, both on night shifts).** Hindi refund and payment
tickets waited 336 min on average vs 66 min for comparable tickets (history days). We gave A09
and D11 the refund and payment skills and replayed days 43–56:
- priority-first: **83 fewer customers missed the SLA** (95% CI 35 to 131);
- OpsLens: **51 fewer** (CI 30 to 71), and 19 fewer agent-hours of work (likely fewer slow
  cross-skill rescue jobs; we did not measure that directly).

The full table (test days, change vs the same policy without the playbook):

| Playbook | Tickets prevented | Breaches, priority-first | Breaches, OpsLens |
|---|---|---|---|
| Fix the phone menu | 0 (344 fewer transfers) | −46 [−75, −18] | −3 [−18, +12] |
| Cross-train 2 Hindi speakers | 0 | −83 [−131, −35] | −51 [−71, −30] |
| Self-serve refund, Team C weekend dinner | 83 | −17 [−27, −7] | −1 [−15, +13] |
| Status banner on spike alerts | 30 | −11 [−16, −5] | −8 [−16, −0] |
| Kitchen order-check, cluster 17 | 67 | −14 [−24, −3] | −4 [−21, +12] |
| Self-serve refund, Team B weekday night | 23 | −13 [−20, −5] | +0 [−20, +20] |
| **All together** | 206 | **−179 [−219, −139]** | **−57 [−73, −40]** |

**How to read it.** Under priority-first every playbook helps. Under OpsLens most of them are
inside the noise, because OpsLens already absorbs those symptoms (its classifier already fixes
the phone-menu mistakes). The one that clearly adds is cross-training: it is new capacity in the
one place OpsLens cannot route around. So the two are complements: OpsLens with every playbook
has 889 fewer breaches over the two weeks than priority-first today (of 1,230; CI 652 to 1,127).

Assumptions moved as expected: the banner saves 1–16 breaches under priority-first as the share
of customers who read it goes from 15% to 50%; self-serve uptake 30% → 80% moves Team C's effect
from −13 to −21. Exact values: `playbooks[].sensitivity` in `eval/results.json`.

## Weaknesses
- Effects of a real fix are unknown before it is done; we show the effect *if* the fix works
  as assumed, and the assumptions are visible and varied.
- Ticket removal is random inside the segment; a real fix may remove easier or harder tickets.
- Cross-training is assumed finished and free; training time is not in the simulator.
- The capacity playbook only touches the overloaded window, so its effect is small by design.

## How to read the code
`opslens/playbooks.py`: `playbooks_from_cards()` → one `*_playbook()` per cause type →
`apply_scenario()` (one `if` branch per scenario kind). Then `eval/run_playbooks.py` →
`main()`; the scenario hook is in `eval/run_opslens.py` → `run_one()`.
Assumptions: `config/playbooks.yaml`. Tests: `tests/test_playbooks.py`.
