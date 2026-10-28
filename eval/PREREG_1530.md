# Pre-registration: the last design run on the 15 / 30 / 60 minute promises

Written and committed before any candidate run. Owner decision of 28 Oct 2026: approved
`eval/DESIGN_1530.md` with two changes and a fallback. This is the last attempt: one design run,
no second round of tweaking. The code in this commit is frozen for the runs below.

## 1. What the policy may know

The policy never reads the generator's settings. Four numbers are estimated before the run and saved to
`eval/parts/food_1530/estimates_1530.json`, next to the true values (for reporting only):

| Number | Used in | Estimated from |
|---|---|---|
| Reopen chance after trained work | lever 2 | history.csv, days 1-35: share of tickets that reopened |
| Work-time factor for a reopened ticket | levers 2, 3 | history.csv, days 1-35: handled minutes of reopened tickets vs the same category and channel without a reopen |
| Cross-skill slowdown | levers 2, 3 | training-days pilot (below): geometric mean of cross-skill work minutes over the lognormal median for the same category and channel |
| Reopen chance after cross-skill work | lever 2 | training-days pilot: share of first services done cross-skill that reopened |

The history holds no cross-skill work: Baseline A never assigns any, and 0 of 67,543 training tickets were
handled by an agent without the skill. Owner's choice (28 Oct): a **training-days pilot**.
OpsLens today runs in the simulator on days 1-35 only, seed 0 (not a design or confirmation seed).
It runs as five weekly runs, each with the day before as warm-up. Its cross-skill first services are recorded.
The slowdown uses only those that were neither transferred nor reopened. The pilot never touches days 36-56.
The estimates are fixed before the design run and are not changed afterwards, whatever they turn out to be.

Handle-time spreads are the existing lognormal fits per category and channel on days 1-35.

## 2. Candidates (code: `opslens/policies.py`, runner: `eval/run_design_1530.py`)

- **OpsLens today**: the shipped policy, unchanged.
- **S1** = OpsLens today + lever 3 + lever 2. Settings `lost_lane`, `clock_cross_gate`.
  - Lever 3: if P(miss even if this agent starts now) ≥ 0.95, the ticket gets a value of 0.005-0.009
    (older is higher). That is below every savable ticket, so a free agent takes it only when nothing savable
    is left for them. The 8-hour guard is unchanged and still wins.
  - Lever 2: a cross-skill job is allowed only if
    P(fits at the slowdown) × (1 − cross reopen) > P(a trained agent starts and finishes in time) × (1 − trained reopen).
    A ticket that is lost for this agent is never given cross-skill. This replaces the 0.5 LightGBM gate.
  - The clock here is the existing one (next free capable agent). The queue value stays LightGBM, refreshed every 3 minutes.
- **S2** = S1 with the live risk value and a queue-aware clock. Settings `use_live_risk`, `queue_clock`.
  Waiting tickets are placed in slack order, lost ones last. Each goes to the earliest-free trained agent who
  speaks its language, and that agent's free time moves on by the expected work time. A ticket's "wait" is its
  start if it is not served by an agent free right now. LightGBM is re-scored at every decision.
  Clock blend weight: run at 0.25, 0.5 and 0.75. S2 uses the one with the lowest mean validation miss %,
  but 0.5 (the untuned value) stays unless another is lower by more than 0.05 points.
- **S3** = S2 + lever 5 (`p1_guard`), with S2's chosen weight. If a free agent is the earliest trained agent for a
  savable P1, and no other trained agent would be free before that P1's last start, the agent may take only that P1
  or a P1 with less slack.
- Levers 4 and 6 are not run. Lever 7 is not built.

## 3. Design run

- Validation days 36-42 (warm-up day 35). Seeds 1-10. Same tickets, same luck, same agents for every policy.
- Also run: the industry standard (Baseline D) and least slack + rescue (threshold 10 min, chosen in the first look).
- No staffing plan for anyone (the plan only covers test days; on validation days it changes nothing).

**A candidate passes** only if all four hold, against OpsLens today on the same seeds:
1. the 95% interval of the overall miss % difference is entirely below 0;
2. the mean P1 miss % difference is ≤ 0;
3. its mean P99 wait is no higher than the industry standard's;
4. its mean late minutes per 100 tickets is below the industry standard's (owner's change 2).

**Pick**: among passing candidates, the lowest mean miss %. Within 0.05 points, the simpler wins (S1, then S2, then S3).

## 4. Confirmation (only if a candidate passes)

- Once, on 20 fresh seeds (101-120), validation days 36-42, the picked candidate vs OpsLens today.
- The same four conditions. If any fails, OpsLens today stays. No second try on these seeds.
- Stop and report after this. No test-day run without the owner.

## 5. Ship bar for the test days (43-56, run once, later, with the owner's go-ahead)

- If a candidate was confirmed, it ships on 15/30/60 only if:
  - it beats the industry standard: 95% interval below 0 overall and on P1;
  - it beats least slack + rescue: 95% interval below 0 overall, and mean P1 difference ≤ 0;
  - routing alone (no staffing plan) is reported beside it.
- **Fallback (owner).** If no candidate passes or confirms, OpsLens today stays on the 15/30/60 floor,
  provided its single test-day run beats the industry standard (95% interval below 0 overall and on P1).
  The tie with least slack + rescue is reported openly. Only if that fails does the floor go back to main's 1 h / 4 h / 24 h.

## 6. Honesty rules

- No change to code, weights, estimates or this rule after a result is seen.
- If a bug is found after a run, the original result is kept and reported. A fix would be a new, labelled run, never a replacement.
- Every number from these runs is reported, passing or not: `design_1530.json`, `confirm_1530.json`.
