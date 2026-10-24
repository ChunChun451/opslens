# realdesk_twin — a calibrated digital twin of the UCI service desk (Plan v4 W14)

## Pre-registration (committed before any twin run; nothing below may change after a run)

### Where the brief had to be adapted (found while exploring the LEARNING months only)
1. **Available hours cannot come from an agent's first-to-last event of a day**: the median agent-day
   spans 0.17 h (most agent-days have 1–2 events). Rule used instead: an agent is on duty
   **08:00–19:00** on every weekday of an ISO week in which they have at least one event in that team
   (08:00–19:00 holds 88.6% of the learning months' events); on Saturday/Sunday only agents with an event
   in that team on that day, same hours. 23% of Active intervals have no named agent; for a team-week with
   events but no named agent, one unnamed agent is added (someone did that work).
2. **Concurrency**: in the learning months an agent holds a median of **2** Active incidents at once (mean
   4.7). k (slots per agent, shared across all teams the agent serves that week) is calibrated on the
   grid {1, 2, 3, 5}, which contains the log's value.
3. **31% of incidents go New → Resolved with no Active time**: the fix happened while the log said New.
   Their work = share × their New hours at the team that resolved them (stated assumption).
4. **"Smallest uniform cut"** in the brief is read as **the largest cut that keeps the service**
   (the most agent-hours saved). Done on a grid, not by bisection, because nothing guarantees the
   missed rate is monotone in the cut.
5. **OpsLens's 1-hour features** must describe the twin, not reality: state, current team, team changes
   so far and the team's open load are taken from the twin at the incident's 1-hour mark; the rest
   (priority, impact, urgency, category, channel, first team, knowledge, hour, weekday, updates in
   the first hour) are the real values, which no policy changes.

### The model (opslens/realdesk_twin.py, own heapq simulator; simulate.py is built for the food floor)
- **Incidents**: all 24,918, opened at their real time.
- **Stages**, read from each incident's events in order until the first Resolved/Closed:
  Active → WORK(team, hours); Awaiting User Info / Vendor / Problem / Evidence → WAIT(hours);
  New → no stage (the twin makes its own pickup waits). Consecutive intervals of the same kind and
  team are merged. Teams follow the real sequence (routing as it really was).
- **WORK** needs a free slot of an on-duty agent of that team; it may start only while the agent is on
  duty and then runs to completion (wall-clock hours, like the log). Duration = share × real hours.
- **WAIT** = the real hours, fixed; the slot is released, and the incident queues again after it.
- **Twin pickup** = start of the incident's first WORK. **Twin resolution** = end of its last stage.
  Still unresolved when the twin ends (30 days after the last real event) = missed.
- **Queues**: one per team. **Desk policy**: priority (1 - Critical first), then oldest by opening time.
  A free agent takes the best item over all teams it serves; a new item goes to the on-duty agent of
  its team with the most free slots (ties: agent id). At 08:00 every on-duty agent fills its slots.
- **Deadline**: the W3 rule (91 h for 3 - Moderate, 325 h for 4 - Low). Scored incidents = Moderate/Low
  with a real resolution time (the real "missed" uses the same rule on real resolution times).

### Calibration (learning months only) and the validation gate (check months)
- Grid: share ∈ {0.1, 0.25, 0.5, 0.75, 1.0} × k ∈ {1, 2, 3, 5}, desk policy, whole log in one run.
- Loss on incidents opened in the LEARNING part: |missed % twin − real| / 3 + |log(median pickup twin /
  real)| / log(1.25) + |% picked up within 1 h twin − real| / 5. Lowest loss wins (ties: smaller k, then
  smaller share).
- **Gate, on incidents opened in the CHECK part (the same run)** — all three must hold:
  1. missed % (deadline rule) within **±3 points** of the real check months;
  2. median pickup wait within **±25%** of the real one;
  3. % picked up within 1 hour within **±5 points** of the real one.
  Pickup metrics use incidents whose real log records a pickup (first non-New state is not Resolved/Closed).
- **If the gate fails: the twin is not shown, nothing runs on the test months**, and we report
  "built, did not match reality" with the three numbers.

### OpsLens in the twin (chosen on the check months, only if the gate passed)
Candidates (OpsLens switched on at the first check incident, desk policy before; lowest missed % on
check incidents wins; ties: list order):
- A `risk`: the frozen early-warning model's P(miss), twin features at 1 h;
- B `rescue`: the frozen W3 rescue model (`fasttrack_second_look`, "would fast-track save it?");
- C `rescue_hopeless_last`: B, but an incident already past its deadline goes after all others (oldest first).
Ordering: higher score first, ties oldest. Before its 1-hour mark an incident's score is the model's mean
prediction on the learning incidents.

### The comparison (test months, run once) and the rules
- Twin-desk vs twin-OpsLens on the same incidents, delays, agents and agent-hours; OpsLens switched on at
  the first test incident. Missed % and pickup wait (median, mean) on test incidents, per test week;
  95% CI of OpsLens − desk by resampling whole test weeks (2,000, seed 0), paired.
- **Sensitivity**: share × 0.5, × 1, × 2 of the calibrated value (k fixed). Claim "OpsLens misses fewer
  in the twin" only if the CI of (OpsLens − desk) missed % is entirely below 0 at all three.
- **Same service with fewer agent-hours**: OpsLens with every on-duty window cut by c ∈ {0, 5, …, 50}%
  (shortened from the end of the day) vs desk at full hours. Reported: c_point = largest c with OpsLens(c)
  − desk(full) ≤ 0, and **c_proven = largest c whose CI is entirely below 0**; only c_proven is claimed,
  as "measured inside the validated twin".

## For the dashboard: exact shape (`results.realdesk.twin`) — filled after the run
(see below)
