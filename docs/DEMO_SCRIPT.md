# OpsLens — demo script (7 minutes + Q&A)

For Sneha (story) and Jijnasu (laptop). Rewritten 18 Oct around the cold open (design v3, by
Claude 2). Every number below is in `eval/results.json`; `tests/test_doc_numbers.py` fails if one
is not. If `make eval` is re-run, run the tests and fix what they flag.
Confirm the real time limit with the organisers; cut from the bottom of each step.

## Before going on stage (10 minutes before)
1. `mingw32-make demo` → "OpsLens demo: real results …". Open http://localhost:8000/.
2. Projector check at 1366×768, browser full screen. Reload once so the cold open plays from
   the start when the judges look up (or use **Replay the night** at the bottom of the sidebar).
3. **Wi-Fi:** the demo works fully offline. Only Ask OpsLens uses the internet (the LLM reads the
   question). With a phone hotspot it understands anything, Hinglish included; without it, keyword
   rules still answer the questions below. Decide which before going on.
4. Warm the live endpoints once: one What-if (Saturday, no change) and one Ask OpsLens question.
5. Backup video on the desktop and on a USB stick, and the charger.

## 0. Cold open (40 s) — the app opens on it
Let it play in silence for the first seconds: Saturday 17 Oct, dinner rush, two floors side by
side. Left, the industry standard; right, OpsLens; a dot is a customer waiting, red means the
promise was missed.
**Sneha (as it ends on 21 vs 7):** "Every ticket is a promise to help a customer in time. Same
people. Same tickets. Different decisions. On this one evening, 21 missed promises against 7."
Click **See how**.

## 1. The claim, and why you can believe it (45 s) — Overview
**Jijnasu:** "That was one evening. Over 14 days OpsLens never saw, 2.20% of customers missed
their SLA, against 5.51% with industry-standard skills routing — the way helpdesks route today,
even with our AI triage added. 95% interval: −4.79 to −1.84 points."
**Sneha:** "And it is not luck: we built a second world after we froze the system and ran it
once. OpsLens 3.07%, the 'SLA due' sort 6.13%."

## 2. Nobody is abandoned (30 s) — Overview proof strip
**Jijnasu:** "The obvious trick would be to give up on late customers. We measured it: minutes
past the promise, per 100 tickets — 529 with OpsLens, 1,477 with the industry standard, 2,282 with
urgent-first."

## 3. Why the floor fails (45 s) — Recurring problems
Open **Hindi × Team B wait 5.1× longer**: 336 vs 66 min, cause *skill gap*, three masked example
tickets.
**Sneha:** "Nobody told OpsLens this. It found it — and on 20 sets of problems we hid at random,
it found 57 of 60."

## 4. One ticket (40 s) — Tickets at risk
Open **T060582** (third in the list): Hindi refund, "mera paisa wapas karo please", breach risk
0.997. Reason: no agent on shift can serve a Hindi refund (40% of the push). "Assign now to a
capable agent" → 0.29.
**Jijnasu:** "We tested the same risk model on a real ServiceNow incident log: it ranks real SLA
misses at 0.857, against 0.552 for the priority rule."

## 5. What to do about it (40 s) — What to do
Show **Fix at the source → Cross-train 2 Hindi-speaking agents** only: 51 fewer missed SLAs in two
weeks even with OpsLens running.
**Sneha:** "We tested six upstream fixes. Most barely help once OpsLens runs the floor. This one
does — so this is where to spend."

## 6. Your turn (60 s) — Ask OpsLens (top bar)
Hand the keyboard to a judge: *"What if Team C loses 2 agents on Saturday?"* — or in Hinglish,
*"agar saturday ko refund wale 3 log kam ho jaye"*.
**Jijnasu (pointing at the trace):** "The language model only understood the question. The
simulator answered it — every number you see was computed just now, for every policy."
If the judge prefers: **Plant-a-problem** on Recurring problems (hidden in fresh data, found or
not, honestly). Time both in rehearsal; say the wait out loud ("simulating the whole day").

## 7. The honest box and close (30 s) — How we tested
**Jijnasu:** "Our first version failed a stress test with 25% more tickets. We fixed it on
validation days only and kept every failure on record. Today, with 25% more tickets: 10.7% against
29.1% for urgent-first."
**Sneha:** "Proven on days it never saw, on a world built after we froze it, on real ServiceNow
data — and on your question, just now. OpsLens: every ticket is a promise; we help you keep it."

---

## If something breaks
- Ask OpsLens slow or offline → use the example questions (keyword rules) or go to Try a what-if.
- What-if / Plant failing → "the same numbers are in How we tested" and move on.
- Server down → restart `mingw32-make demo` (10 s). Projector problem → play the backup video.

## Backup video checklist (record on 27 Oct)
- 1920×1080, browser full screen, `make demo` running, hotspot on for Ask OpsLens.
- Follow steps 0–7 exactly (≈ 6 minutes), including one Ask OpsLens question.
- Save as `opslens_demo.mp4` on the desktop and on a USB stick.

## Practice questions (answers in docs/JUDGE_QA.md)
Data is fake? · Simulator rigged? · Leakage? · Tuned on test? (three looks, then a sealed world) ·
Abandoning late tickets? (lateness, Q27) · Where is the AI? (Ask OpsLens, IVR routing) · Greedy
ties your solver? (Q32b) · Why LightGBM? · Scale? · Privacy?
