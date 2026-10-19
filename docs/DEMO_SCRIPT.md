# OpsLens — demo script (7 minutes + Q&A)

For Sneha (story) and Jijnasu (laptop). Rewritten 19 Oct for Plan v3: six screens, two worlds,
a real plan. Read `docs/OPSLENS_IN_PLAIN_WORDS.md` first. Every number below is in
`eval/results.json`; `tests/test_doc_numbers.py` fails if one is not.
Confirm the real time limit with the organisers; cut from the bottom of each step.

## Before going on stage (10 minutes before)
1. `mingw32-make demo` → open http://localhost:8000/. Projector check at 1366×768, full screen.
2. Top bar on **Food delivery**.
3. Wi-Fi: everything works offline except Ask OpsLens's free-form questions (phone hotspot).
4. Warm up: one What-if. Then Accept "Cross-train 2 Hindi-speaking agents", open *Your plan*, keep
   Saturday 17 Oct, press **Simulate** (about 30 s the first time), then Undo it. On stage the same
   plan comes back at once. Do not restart the server after this. Backup video and charger ready.

## 0. Cold open (40 s) — it plays on its own
Two floors, Saturday dinner, same agents, same complaints. It ends on 24 vs 6 missed promises.
**Sneha:** "Every complaint is a promise to help a customer in time. Same people, same complaints,
different decisions: 24 broken promises against 6." Click **See how**.

## 1. Does it work? (45 s) — Proof
**Jijnasu:** "That was one evening. Over 14 days OpsLens never saw, 2.05% of customers missed their
deadline, against 5.51% with the industry-standard way of routing (95% interval −4.77 to −2.15
points). Same agents, same hours."

## 2. Why it goes wrong (45 s) — Problems
Open **Hindi × Team B wait 5.1× longer**: 336 vs 66 minutes, because only three agents speak
Hindi and handle refunds, and none work at night. **Sneha:** "Nobody told OpsLens. It found it, with
the proof and the example complaints."

## 3. What goes wrong next (40 s) — Risks
Open **T060582**: a Hindi refund, "mera paisa wapas karo please", 0.997 chance of missing its
deadline. The reasons are listed. Giving it to a capable agent now: 0.29.

## 4. What to do — and what it changes (60 s) — Actions
Top line: accept all 18 recommendations and 48.8 fewer of 379.8 customers miss their deadline.
**Accept** "Cross-train 2 Hindi-speaking agents": alone, 26.8 fewer missed deadlines over the 14
held-out days with OpsLens (79.0 with today's urgent-first routing). Open **Your plan**, Saturday is
picked, press **Simulate**: the whole day replayed with and without the plan, live. Then point at a
staffing move marked "no clear effect" and **Override** it ("Not now").
**Jijnasu:** "It even tells you which of its own ideas do not pay. The manager decides the big
things; OpsLens handles the 1,100 small ones and explains each."

## 5. Real data (60 s) — switch to **IT service desk**
**Sneha:** "Our food floor is simulated — no company publishes its complaints. So here is the same
engine on a real company's service desk, public data: 24,918 incidents, 36.6% missed their deadline."
Overview → where the time goes. Risks → **its riskiest 20% hold 49.9% of all missed deadlines;
the desk's own priority field, 24.6%.** **Jijnasu:** "And we show where it does not beat the real
desk — Proof says so."

## 6. Your turn (45 s) — back to Food delivery
Hand the keyboard to a judge: Ask OpsLens "what if Team C loses 2 agents on Saturday?", or
Proof → Try a what-if, or Problems → plant a problem.

## 7. Close (20 s)
**Sneha:** "Tested on days it never saw, on a world built after we froze it, and on a real company's
data. OpsLens: every ticket is a promise — it helps you keep it."

---

## If something breaks
- Simulate or Ask slow → "each action's measured effect is already in the plan" and move on.
- Server down → restart `mingw32-make demo` (10 s). Projector problem → backup video.

## Backup video checklist (record on 27 Oct)
1920×1080, full screen, steps 0–7 exactly (about 6 minutes), including one Accept → Simulate.

## Practice questions (answers in docs/JUDGE_QA.md)
Data is fake? · Why this public dataset? · Simulator rigged? · Tuned on test? · Abandoning late
tickets? · What does Accept do? · Does it beat the real desk at routing? (no) · "No clear effect" moves? · Where is the AI?
