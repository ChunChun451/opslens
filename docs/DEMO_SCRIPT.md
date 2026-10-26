# OpsLens — demo script (7 minutes + Q&A)

For Sneha (story) and Jijnasu (laptop). Rewritten 24 Oct for the current dashboard: it follows the
nine steps of **Story mode**, so you can press *Story mode* and talk along. Every number below is in
`eval/results.json`; `tests/test_doc_numbers.py` checks the decimal ones. Confirm the time limit with
the organisers; if short, cut steps 6 and 8 first.

## Before going on stage (10 minutes before)
1. Start the server **at least 5 minutes early** (`mingw32-make demo`): it simulates today's Live now
   day at start-up, so the first screen is ready, not "Starting…".
2. Open http://localhost:8000/ full screen at 1366×768. Press **Esc** to skip the festive splash.
   Check **Neon vs Light** in the room: on a washed-out projector, Light reads better.
3. Warm up once: one What-if, and in *Your plan* accept "Cross-train 2 Hindi-speaking agents" →
   Simulate (about 30 s the first time) → Undo. On stage the same plan returns at once.
4. Wi-Fi or a phone hotspot for Ask OpsLens's free-form questions (offline it uses keyword rules).
5. Backup video and charger ready.

## 1. The problem, live (45 s) — Overview → Live now
**Sneha:** "Every complaint is a promise to help a customer in time. This is today, simulated on this
laptop at the real clock: the same customers and the same agents, run two ways — the industry-standard
routing and OpsLens. Watch the promises missed so far."

## 2. 1,000 customers, one picture (40 s) — Overview → Results on the test days
**Jijnasu:** "That is one day. Over 14 days OpsLens never saw: 2.0% of customers missed their deadline,
against 5.5% with the industry standard. OpsLens was lower on 14 of 14 days. And on a world we
generated after freezing the model: 2.2% against 5.8%."

## 3. A pattern, with its evidence (40 s) — Problems
Open **Hindi × Team B**: Hindi refunds wait 5.1× longer (336 vs 66 minutes), because only three
agents speak Hindi and handle refunds, and none work at night. **Sneha:** "Nobody told OpsLens. It
found it, with the proof and the example complaints."

## 4. One ticket, before it is late (40 s) — Risks
Open **T060582**: a Hindi refund, "mera paisa wapas karo please". Almost certain to miss its deadline;
the reasons are listed, and the faithfulness test says they are the real ones (98.9%). **Jijnasu:** "If
a Hindi refund agent took it now, its risk would fall to 29%. When nobody like that is on shift,
OpsLens weighs a rescue by another team instead."

## 5. What it is worth, with confidence intervals (60 s) — Proof → Side by side, then Actions
**Jijnasu:** "Same customers, same luck: −3.46 points against the industry standard, 95% interval
−4.77 to −2.15." Then **Actions → Accept** "Cross-train 2 Hindi-speaking agents" → **Your plan**:
alone, 26.8 fewer missed deadlines over the held-out days. Press **Simulate**. **Sneha:** "The manager
decides the big things; OpsLens handles the thousand small ones and explains each."

## 6. Beyond the world we built (30 s) — Proof → Beyond our world
"30 random support floors we did not design: OpsLens beat the industry standard on 29. We also wrote
down, before the run, that it would be the best of all six methods in 27 of 30. It was 19. The losses
are floors in sustained overload; even there it protects gold customers and late customers better."

## 7. A real day at a real desk (50 s) — Real data (UCI ServiceNow example) → Shadow mode
**Sneha:** "Our food floor is simulated — no company publishes its complaints. So here is a real
company's IT desk, public data, a real day: Thursday 5 May 2016. OpsLens only watched. Of the 102
incidents that really missed their deadline, it warned about 53 in time. The desk's own priority
field: 16."

## 8. What we bet on, and what we lost (30 s) — Proof → Rules we wrote first
**Jijnasu:** "Every rule we wrote before running a test, with the date git sealed it — the ones we
missed stay on screen. A team that never misses is not testing hard enough."

## 9. Your turn (45 s) — the judges
Hand over the keyboard: **Ask OpsLens** "kal raat refund wale kitne late honge?" or "what if Team C
loses 2 agents on Saturday?"; or **Proof → Try a what-if**; or **Problems → Plant a problem**.
If a judge brought a file: **Real data → Upload a CSV**, drop it, read the five sentences aloud ("it
starts at…, a miss is…, it learns on your first 70%"), press **Analyse my file**. It lands on their
Overview; click through Shadow mode, Problems, Risks, Actions and Proof on their own data. **Sneha:**
"Every number here is from your file, scored on your later rows it never saw. What your file does
not have, the screen says by name: no priority column, no comparison with your priority field."

## Close (15 s)
**Sneha:** "Tested on days it never saw, on worlds we did not design, and on a real company's data —
and honest about where it loses. OpsLens: every ticket is a promise; it helps you keep it."

---

## If something breaks
- Live now still "Starting…" → go to *Results on the test days* and come back later.
- Simulate or Ask slow → "each action's measured effect is already in the plan" and move on.
- Server down → restart `mingw32-make demo` (it warms Live now again). Projector problem → backup video.
- A judge's file is refused → read the one sentence aloud (it says why and what to try), then *or try the
  UCI example* on the same card. A file without an on-time column gets an assumed promise: say so, and type theirs.

## Backup video (record on 27 Oct)
1920×1080, full screen, steps 1–9 exactly (about 6 minutes), including one Accept → Simulate.

## Practice questions (answers in docs/JUDGE_QA.md; the short list in docs/OWNER_CHEATSHEET.md)
Data is fake? · Why this public dataset? · Simulator rigged? · Tuned on test? · Where does it lose? ·
What does Accept do? · Does it beat the real desk at routing? (no) · Where is the AI? · Is the
optimiser needed?
