# live.py — "Live now": today's day, simulated on this laptop, shown at the real clock

## What it does (5 lines)
- Overview → **Live now** shows today's date and the time, ticking.
- The first time it is opened, the server simulates one whole support day (about 20–40 s), twice:
  the industry standard and OpsLens, same customers, same agents, same luck.
- Every 5 seconds the page asks `GET /api/live?weekday=5&minute=1274.5`: "what does the floor look
  like now?" The engine answers from the simulated day: waiting customers, promises missed so far,
  each agent's tile, the customers most in danger (with reasons) and OpsLens's latest decisions.
- **Play the day fast** runs the clock at 3 simulated minutes per second from 17:00 (the dinner rush
  in about 2.5 minutes). **New luck** simulates the day again with another seed.

## Why it is built this way
- A real floor cannot be replayed; ours can. The customers are the practice company's tickets for the
  **test day with today's weekday** (Saturday → day 48), a day OpsLens never studied. The screen says so.
- Simulating the whole day once and revealing it minute by minute keeps every answer instant.
- The other screens are exam results on fixed days, so they keep their dates; this one is the only
  screen with today's date, because it is the only one computed now.

## Worked example (Saturday 24 Oct 2026, 13:56)
Industry standard: 10 promises missed so far today, 109 waiting. OpsLens: 7 missed. In danger:
T060062 (account, English) 60.7% — "61 Team D tickets waiting in this language". Just decided:
13:56 T059972 → Gaurav O., "P2 missing item, English, waiting 64 min".

## Weaknesses
- Simulated customers (the practice company's), not a real queue.
- Early morning is quiet: little happens before 07:00 (use "Play the day fast").
- The in-danger list is recorded every 10 simulated minutes, decisions as they happen.

## How to read the code
`opslens/live.py`: `simulate_live_day()` (one day, both ways of working, recording as it goes), then
`state_at()` (the floor at one minute). Server: `server/app.py` → `live()`. Page: `web/js/tabs/live.js`
→ `refresh()` and `draw()`. Tests: `tests/test_live.py`.
