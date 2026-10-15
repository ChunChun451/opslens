# opslens/patterns.py — finding recurring problems, with evidence

## What it does
- Reads the ticket history (days 1–42) and finds groups of tickets that are clearly worse than
  comparable tickets.
- Names the likely cause: capacity, skill gap, volume spike, partner issue or process.
- Writes an **evidence card** for each: the numbers, the comparison, 3 example tickets
  (PII-masked) and a recommended action.
- In the live period, checks every 15 minutes for sudden surges (live alerts).
- Never reads `data/planted.json`. Only `eval/` reads it, to score us.

## How it works, step by step
1. **Labels.** Each ticket gets: category, language, channel, team (the team that *owns* the
   category), priority, tier, and "when" (weekday/weekend × night/morning/lunch/afternoon/dinner/late).
2. **Capacity scan.** For each team × time window: work arriving (handle minutes) ÷ agent
   minutes on shift = ρ. ρ ≥ 1.2 while the team is staffed → "overloaded". The evidence covers
   the window and the next one, because the backlog spills over.
3. **Interaction scan.** For every pair of labels (e.g. Hindi × Team B), compare the mean wait
   with **both parents** (Hindi tickets of other teams; Team B tickets in other languages).
   Report only if it is ≥ 2× worse than both, with z ≥ 6. This tells "Hindi Team-B tickets are
   slow" apart from "Team B is slow" or "Hindi is slow".
4. **Process scan.** Groups with ≥ 3× more transfers per 100 tickets than the rest.
5. **Partner scan.** Restaurant clusters that send ≥ 2× the usual share of one category
   (two-proportion z-test).
6. **Spike scan.** Each category's daily count vs days of the **same type** (weekday or
   weekend), with a robust z-score (median and MAD). Known sale days are "explained", not alarms.
7. **Cause rules.** Plain if-then rules (see `classify_cause`): e.g. a language × team group
   where ≤ 4 agents have both skills = skill gap; a window with < 1.5 capable agents on shift =
   coverage gap.
8. **Merge.** Findings that cover mostly the same tickets are merged; the stronger stays.

## Worked example (real numbers, our history)
Hindi × Team B tickets (refunds and payment failures): **336 min** mean wait. Hindi tickets of
other teams: 66 min. Team B tickets in other languages: 55 min. Worse parent = 66 → ratio
**5.1×**, z far above 6 → finding. Cause rule: agents who speak Hindi *and* handle refunds or
payments = B01, B02, B05 → only 3 → **skill gap**.

Team C, weekend dinner: work ÷ agent-time **ρ = 1.45** with 3.5 agents on shift. Its tickets wait
58 min then and **322 min** on weekend late while the backlog clears → **capacity**.

## Results
- Main dataset: **5 of 5** planted problems found and correctly diagnosed (cause type right).
- Two findings we did not plant. We re-measured them on the 14 held-out days (43–56):
  "regional-language × weekday morning" **replicates** (2.0× the worse parent) — it is a real
  roster gap (few regional-language speakers start before 08:00); "Team B × weekday night"
  does **not** replicate (1.2×) → counted as a false alarm.
- Live detection on the test days (categories from the M3 classifier): the unseen day-47 app-bug surge was flagged **45 minutes**
  after it began; **1 false alert in 2 weeks**. The rule (z ≥ 4.5 on two checks in a row) was
  chosen on history days 15–42, never on test days.
- **Blind test:** 20 fresh 42-day datasets, each with 3 problems whose type, place and size
  were drawn at random by code after the finder was frozen (`data/plant.py`). Result:
  **57 of 60 found and correctly diagnosed (95%)** — capacity 10/10, partner 14/14, process
  10/10, volume spike 11/12, skill gap 12/14. On a clean dataset with no plants the finder
  shows 3 cards (real roster gaps such as thin regional-language mornings, or noise).
  On average 2.35 cards per set match no plant.

## Weaknesses
- Small groups with modest effects are missed: both blind misses of the skill-gap type were
  regional-language × Team C (about 1.4% of tickets), where waits rose less than 2×.
- A spike on the very last weekend day has few same-type days to compare with (missed once).
- Thresholds (2×, z ≥ 6, ρ ≥ 1.2) are fixed by hand. They were set on the main history; the
  blind test is how we check they generalise.
- One label pair at a time: a problem that needs three labels to describe (team × language ×
  time) shows up through its strongest pair.
- Waits measure the status quo (Baseline A). Under another routing policy some groups would
  look different.

## How to read the code
Open `find_patterns()` at the bottom of `opslens/patterns.py` (the whole flow in 15 lines),
then each `scan_*` function, then `classify_cause()`. Live alerts: `live_alerts()`.
Scoring is in `eval/recall.py` and `eval/run_patterns.py`; the blind test in `data/plant.py`
and `eval/run_blind.py`.
