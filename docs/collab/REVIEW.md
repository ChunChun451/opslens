# Claude 2 review of OpsLens — 17 Oct 2026

Reviewer: Claude 2 (Sneha's Claude). Commit reviewed: `64f42cf` (`main`).
Severity: **LOSE** = could lose us the finale · **POINTS** = costs points · **MINOR**.
**Update 17 Oct 07:08:** the official `make eval` (with LLM, commit after `7227fb8`) is now in
`eval/results.json`; numbers below are the official ones. Earlier, numbers marked *(C2 run)* came from my own re-run on Sneha's laptop
(`docs/collab/evidence/baseline_c_no_llm_17oct.json`, classifier without LLM because no keys
yet). They are **not** official until `make eval` writes them into `eval/results.json`.

---

## 0. Verdict in five lines

1. **The core claim survives a hard attack.** I added the baseline an Eternal engineer would
   name first — sort by SLA due time, the way Zendesk/Freshdesk already do — and OpsLens
   still wins clearly on test days: **5.40% → 2.20%, −3.20 points [−3.93, −2.46]** (official).
2. **The "you abandon late customers" attack is now answered with a number**, not a hope:
   minutes past SLA per 100 tickets **529 (OpsLens) vs 2,282 (priority-first) vs 4,189 (SLA due)**
   (official). That is the strongest new line for the pitch.
3. **But our current answer to that same question is wrong.** `docs/JUDGE_QA.md` Q26–Q28
   quote policy **v1** numbers (5.08%, P99 474 min, a 240-min guard). Said on stage, the
   dashboard (728 min) contradicts us in front of the judges.
4. Reproducibility is real: I regenerated the data and re-ran the simulator on another
   machine and got A 13.11% / B 6.82% / OpsLens 2.20% exactly; risk AUC 0.977 (official 0.976);
   UCI AUC 0.857 exact.
5. Several visible pieces do not earn their place yet (LLM brief on the first screen,
   staffing moves, most playbooks). Cut or reframe them; spend the remaining days on the story.

---

## 1. Ranked findings

### F1 — LOSE — Judge Q&A answers the most dangerous question with stale v1 numbers
- **Evidence:** `docs/JUDGE_QA.md:167-174` and `:185` say 5.08%, −1.74 [−2.35, −1.13],
  P90 130, P99 474 min and "a guard serves anything older than 240 minutes next". Those are
  policy v1 (`PROGRESS.md` M7). The shipped v3 (`config/optimizer.yaml`) gives 2.20%, P99 728
  min, and a late ticket drops to value 0.2 until it is **480 min past SLA**, and the guard
  **pauses while >150 tickets wait**. The `opslens/optimize.py` docstring also described v1
  (fixed in this branch).
- **Why it loses:** "Abandoning late tickets?" is in `DEMO_SCRIPT.md`'s practice list. v3 *does*
  deprioritise late tickets — by design. If Jijnasu says "474 minutes, 240-minute guard" and a
  judge opens the dashboard, our credibility (moat #2, Trust) is gone.
- **Proposal (text for Claude 1, who owns the rehearsal docs):** answer Q27 honestly:
  *"Yes, once a ticket has missed its SLA, OpsLens serves tickets that can still be saved
  first — and we measured the cost. Late customers are late by 230 min on average, about the
  same as FIFO (213), better than priority-first (328). Total minutes past SLA per 100 tickets:
  529 vs 2,282 for priority-first. A naive 'SLA due' sort that also skips late tickets leaves
  them 766 min late; that is why we added a guard."* (numbers once they are in results.json).
  Also refresh Q26 and Q28 to v3. **Add a check**: a test that every number in
  JUDGE_QA/DEMO_SCRIPT exists in `results.json` (my quick audit found only 6 orphans — UCI
  24,918/36.6%, Erlang 10.97/10.79, 6.29, 0.321 — but stale-yet-present numbers like 5.08 pass
  that check because `details.v1_record` keeps them, so the test must look up the
  *current* keys).

### F2 — LOSE (now fixed in this branch, needs official run) — no baseline a real ops lead would use
- **Evidence:** Baselines A (FIFO) and B (priority) are both blind to the SLA clock. Any
  helpdesk has a "due by" sort. Without it, a judge can say "you beat two strawmen".
- **What I did:** `opslens/policies.py::DeadlineQueuePolicy` (Baseline C): same team queues,
  menu routing and skill rules as A/B, sorted by SLA deadline with already-late tickets after
  the savable ones. No weights, so nothing to tune; ran on validation (36–42) first, then once
  on test (43–56). `eval/run_baseline_c.py`, wired into `make eval` and `NUMBERS.md`; 3 tests.
- **Result (official, test days, 5 seeds):**

  | | A FIFO | B priority | **C SLA due** | OpsLens | OpsLens − C |
  |---|---|---|---|---|---|
  | Breach % | 13.11 | 6.82 | **5.40** | 2.20 | −3.20 [−3.93, −2.46] |
  | P1 breach % | 27.34 | 9.13 | 8.94 | 4.89 | −4.05 [−5.67, −2.44] |
  | Min late, mean of breached | 213 | 328 | 766 | 230 | −536 |
  | Min late per 100 tickets | 2,820 | 2,282 | 4,189 | 529 | −3,660 |
  | P99 wait (min) | 816 | 1,007 | 1,435 | 728 | −707 |

  Validation days told the same story (C 4.80% vs OpsLens 2.17%).
- **Proposal:** Jijnasu runs `mingw32-make eval` (or `python eval/run_baseline_c.py` then
  `run_eval.py --assemble`) on his machine with the LLM cache, so this is official. Then show
  **C as the main comparison** in the pitch and Overview: "we beat the sort your helpdesk
  already has". Keep A/B as context.

### F3 — LOSE-risk — the test days were looked at three times
- **Evidence:** `PROGRESS.md` M8: v1 failed the +25% stress test **on test days**; v2 was
  designed in response; v2 then failed **on test days**; v3 was designed in response. Weights
  were picked on validation each time, but the *design changes* were triggered by test
  results. `DEMO_SCRIPT.md` already admits "Tuned on test? (yes — three runs, all kept)".
- **Why it matters:** honest disclosure is good, but a statistics-minded judge will say the
  2.20% is the best of three looks. It is the one soft spot in moat #1.
- **Proposal (before the 22 Oct freeze):** a **sealed second world**: run the generator with a
  new `data_seed` (same config, so same planted problems in new random places and new daily
  noise), retrain on its days 1–35, freeze, and evaluate A/B/C/OpsLens **once** on its 43–56.
  Report it whatever it says. Data is synthetic, so we can make a truly unseen test set —
  turn that weakness into a strength: *"the policy was frozen before this world existed."*
  Cost: ~1 h of compute, a `--data-seed`/output-dir option in `data/generate_ops.py` and the
  eval scripts. I can build this next (see section 4).

### F4 — POINTS — the first screen shows an LLM paragraph with wrong English
- **Evidence:** Overview → "Today's brief" (committed results): *"...OpsLens resulted in 2.2%
  while priority-first routing led to 6.8% and first-in-first-out routing caused 13.1%. The
  resolution speed for these methods reached 141 min and 198 min respectively. ...10,788 tickets
  fall under the top issue group, which sees 13.01 transfers compared to 2.56..."* Three methods,
  two numbers, "respectively"; P90 called "resolution speed"; "13.01 transfers" without
  "per 100". The `{{key}}` rule guarantees the *value*, not the *meaning*.
- **Proposal:** (a) put units into fact values (`13.0 per 100 tickets`), (b) give each key a
  one-word role and reject briefs that pair keys wrongly, or simply (c) show the template brief
  on Overview and move the LLM brief to a "drafted by AI" box with the keys visible. This is
  the only LLM text a judge sees in the first minute; it must be flawless.

### F5 — POINTS — "Where is the AI?": the LLM's best work is invisible, its weakest is on show
- My view: for Eternal engineers, LightGBM + Erlang C + a fair simulator **is** the right call;
  they ship that stack. Do not add a chatbot. But show the LLM where it truly wins:
  **phone (IVR) tickets routed right 75.8% → 95.7%, Hinglish 97.3%** (NUMBERS.md
  classification) and the playbook drafts (partner notice, IVR wording). One sentence in the
  pitch: *"Models where numbers matter, the LLM where language matters — and it is never
  allowed to write a number."*

### F6 — POINTS — features on screen that our own evidence says do nothing
- **Staffing moves:** ablation +0.05 [−0.06, +0.16] (noise). My run of `eval/run_forecast.py`:
  the plan cuts the forecast shortage only 657 → 639 agent-hours (~3%). Budget-neutral shift
  moves cannot fix a floor that is short at every dinner peak.
- **Optimiser vs greedy:** 2.18% vs 2.20% — agree with Claude 1's framing ("the value function
  is the engine"); never say "min-cost flow" in the first 5 minutes.
- **Playbooks under OpsLens:** only cross-training is clearly non-zero (−51 [−71, −30]); IVR,
  refund self-serve, kitchen check are within noise. "889 of 1,230 fewer breaches" mixes the
  policy gain with the playbook gain.
- **Proposal:** turn this into an insight instead of hiding it: *"We tested five upstream fixes.
  Moving shifts barely helps. Cross-training two Hindi agents does — that is where to spend."*
  Show one playbook (cross-training) in the demo; the rest in How we tested.

### F7 — POINTS — confidence intervals cover simulator luck only
- **Evidence:** `opslens/impact.py::paired_ci` is over 5 seeds; every seed replays the *same*
  18,032 test tickets (`run_opslens.run_one` builds the world from one `world_tickets.csv`).
  So "95% CI" means "if the handle times were redrawn", not "on another fortnight".
- **Proposal:** label it "over simulator seeds" (the UI subtitle already partly does), and add a
  per-day paired view (14 days × 5 seeds; OpsLens wins on how many days?). The sealed world
  (F3) is the stronger answer.

### F8 — POINTS — the risk AUC 0.977 invites "your simulator made it easy"
- Top feature by gain: `time_left_min` 0.39 (my re-run). On synthetic data breach is close to
  determined by time left and queue. Lead with the **UCI real-data AUC 0.857 vs 0.552** for the
  priority rule; quote 0.977 second. Also a UI string: "only 0 agents on shift can serve Hindi
  refund" → "no agent on shift can serve...".

### F9 — MINOR — reproducibility snags (found on a second machine)
- `tests/test_demo.py::test_demo_accepts_the_real_results` fails on a fresh clone until
  `make gen` has run; mark it to skip when `data/generated` is missing.
- `make eval` has no way to run without API keys (`run_classification.py --no-llm` exists but
  `run_eval.py` does not pass it). Add `--no-llm` passthrough for offline/second-machine runs.
- Windows long paths: clone needs `core.longpaths`; LightGBM's DLL fails to load from a long
  folder (WinError 206). Add one line to README.
- Reopens +0.45 points (cost of cross-skill rescues) and P99 spread (±189) are honest costs;
  keep them in the honest box.
- P3 tickets (18%) never breach (24 h SLA) — fine, but a judge may ask why they are in the
  breach-% denominator. Answer ready: it matches how SLA reports are read.

---

## 2. What is good and must not be broken
- **The simulator's fairness**: CRN draws per ticket and attempt (`opslens/simulate.py`),
  event-driven decisions for every policy, legality checks that raise on a cheating policy,
  hand-computed and Erlang-C tests. This is the spine of the project.
- **Reproducibility**: exact match on a second machine (section 0.4).
- **Honesty culture**: failed versions kept in results.json, the "What failed" box, ablations
  that show our own parts doing nothing. Judges reward this — keep it visible.
- **The no-digit LLM rule** and click-through evidence.
- **Blind recall 57/60** on random plants — the best answer to "you found what you planted".
- Code is plain and readable; module docstrings with real examples made this review fast.

---

## 3. How I think we win

**The one thing judges should remember:**
> *"Same agents, same hours: three-quarters fewer customer-minutes past the promise — and it
> beats the 'SLA due' sort your helpdesk already has, on days it never saw."*

(numbers: late minutes per 100 tickets 2,282 → 529 vs priority-first; breach 5.4% → 2.2% vs
SLA-due — once official.)

**Story (non-technical judge, first 90 seconds):**
1. Open on the **replay**, not on a number: Saturday dinner, three floors side by side, the
   queue rising and breaches ticking up. Name the floors in plain words: "first come first
   served", "urgent first", "due time first (what your helpdesk does)", "OpsLens".
2. Freeze at 21:30 and click one red ticket on the OpsLens floor → why it was picked
   (e.g. T060582: Hindi refund, risk 0.997 → 0.30 if a capable agent takes it now). *Then* show 2.2%.
3. Patterns → the cause → the one fix that works (cross-train two Hindi agents) → judge's turn.

**Floor map (outside review's "visual punch")**: worth one day of UI work *only* if it replaces
the bar charts as the opening, not as an extra tab. The current replay (two numbers per
floor) is the right data; it needs a picture.

## 4. What I propose to do next (my side), in order
1. Sealed second world (F3) — before the 22 Oct freeze.
2. Brief fix (F4) — units in facts + role check; template on Overview if the LLM fails it.
3. `--no-llm` passthrough + test skip + README line (F9).
4. Per-day win count (F7).
Claude 1 (rehearsal docs owner): F1 text, and F6 framing in DEMO_SCRIPT.

---

## 5. Round 2 (17 Oct, after reading the DEV_103 PDF itself)

| PS asks for | OpsLens | Verdict |
|---|---|---|
| Identify patterns | evidence cards, 5/5 planted, 57/60 blind | strong |
| Predict bottlenecks / SLA breaches | risk model, 48 h forecast with conformal bands | strong |
| Recommend actions by urgency, capacity, impact | optimiser; beats FIFO, priority **and** SLA-due | strong |
| Explain decisions | TreeSHAP reasons, click-to-evidence | good |
| Measure impact: turnaround, productivity, quality | turnaround and quality strong; **productivity flat** (5.29 → 5.30 tickets/agent-hour) | say it: the floor is demand-bound; the gain is fewer transfers (4.6 → 1.0 per 100) and agent-hours freed by playbooks |
| *"NLP or LLMs for classifying issues and summarising patterns"* | LLM on 1.5% of tickets + one brief | was weak where visible → **Ask OpsLens** |
| *"prototype using a provided or publicly available dataset"* | headline on generated data; UCI as a check | our biggest exposure → lead with UCI results, sealed world, Upload |

**Built in round 2:** Ask OpsLens (LLM routes, engine answers, grounding check, offline rules);
floor map in the replay (first on its tab); brief units; sealed-world script.
**Not built, on purpose:** a free-form chatbot (it would invent numbers), deep learning,
more playbooks (most are within noise).
