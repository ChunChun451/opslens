# OpsLens — demo script (7 minutes + Q&A)

For Sneha (story) and Jijnasu (driving the laptop). Every number below is from
`docs/NUMBERS.md`, generated from `eval/results.json`. If `make eval` is re-run, re-check them.
Confirm the real time limit with the organisers and cut from the bottom of each step.

## Before going on stage (10 minutes before)
1. Wi-Fi OFF. `mingw32-make demo` → "OpsLens demo: real results …". Open http://localhost:8000/.
2. Browser full screen, zoom so the Overview cards fit (projector check at 1366×768).
3. Warm the live endpoints once (they cache data on first use): run one What-if (day 48,
   no change) and the Upload "UCI example". Close the results.
4. Backup: the recorded video (see checklist at the end) on the desktop, and the laptop charger.

## 1. The problem (45 s) — Overview tab
**Sneha:** "Saturday night, 8:30. A food-delivery support floor: dinner orders peak, a
payment glitch, a sale. Some tickets will miss their SLA. Today's tools tell you *after*.
OpsLens tells you which ones, why, what to do — and proves it works on days it has never seen."
**Show:** the three breach cards — FIFO 13.1%, priority-first 6.8%, **OpsLens 2.2%** on 14 held-out
days; click the OpsLens number → the evidence popover (path in results.json, CI).

## 2. The replay (60 s) — Baseline vs OpsLens tab
**Play the replay:** Saturday 17 Oct, 18:00–24:00, same tickets, same luck.
**Jijnasu:** "Left FIFO, middle priority-first, right OpsLens. Breaches that evening: 83, 26 and
7." Point at the queue: peaks of 132 and 141 tickets vs 89.
**Sneha:** "Same agents, same hours. Only the decisions differ."

## 3. Why it happens (60 s) — Patterns tab
Open the card **"Hindi × Team B wait 5.1× longer"** → 336 min vs 66 and 55 min; cause: skill gap,
"only 3 agents speak Hindi and handle refunds/payments"; three example tickets (masked).
Then **"Team C overloaded on weekend dinner"** (work 1.45× agent-time) and **phone (IVR) tickets
transferred 5.1× more**. **Jijnasu:** "Found automatically — and we tested that on 20 sets of
problems we did not design: 57 of 60 found and diagnosed."

## 4. One ticket (45 s) — At-risk tickets tab
Open ticket T060582 (third in the list): Hindi customer, "mera paisa wapas karo please", **breach risk 0.997**. Reasons: no agent
on shift who can serve a Hindi refund (40% of the push), time left, Hindi customer.
"Assign now to a capable agent" → **0.29**. **Sneha:** "Not just a score — the reason and the fix."

## 5. The recommendation and the proof (75 s) — Recommendations, then How we tested
Recommendations: assignments with one-line reasons; staffing moves that keep the same people and
hours (e.g. C05 takes Monday off instead of Saturday).
How we tested: **OpsLens − priority-first −4.6 points (95% CI −6.0 to −3.2)**; Hindi customers
16.2% → 3.5%; P1 9.1% → 4.9%. Ablations: the risk model is the engine (+2.0 points without it).
**The honest box:** "Our first version failed the +25% volume stress test. We fixed it on
validation days only. Today, with 25% more tickets: 10.7% vs 29.1% for priority-first."

## 6. Your turn (60 s) — What-if or Plant-a-problem
Hand the mouse to a judge:
- **What-if:** pick a day, remove 2 agents from Team C, ×1.25 volume → simulate (~15 s): the three
  policies side by side.
- **Plant-a-problem:** "pick a category and an effect" → OpsLens gets 21 fresh days, is not told,
  and finds it (~20–40 s). Volume spikes and mislabels are found reliably; say upfront that a
  regional-language gap in a small team is the case it can miss.

## 7. Close (15 s)
**Sneha:** "Proven on 14 unseen days, on stress it never saw, on real ServiceNow data — and on
your problem, just now. OpsLens: from 'this ticket is late' to 'this is what we do now'."

---

## If something breaks
- What-if / Plant slow or failing → "the same numbers are in How we tested" and move on.
- Server down → restart `mingw32-make demo` (10 s). Projector problem → play the backup video.

## Backup video checklist (record on 27 Oct)
- 1920×1080, browser full screen, Wi-Fi off, `make demo` running.
- Follow steps 1–7 exactly (≈ 6 minutes), including one What-if and one Plant run.
- Save as `opslens_demo.mp4` on the desktop and on a USB stick.

## Practice questions (answers in docs/JUDGE_QA.md)
Data is fake? · Simulator rigged? · Leakage? · Tuned on test? (yes — three runs, all kept) ·
Why not an LLM for everything? · Why LightGBM? · Abandoning late tickets? · Scale? · Privacy?
