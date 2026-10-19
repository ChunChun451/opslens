# Plan v4 — from about 6/10 to 9–10 on every judging criterion (19 Oct 2026)

Plan v3 (`docs/PLAN_V3.md`) made OpsLens a product. Plan v4 answers one question: **what would a
harsh panel (an ops lead, an ML professor, an operations-research engineer, a software engineer)
need to see to give 9 or 10 on every criterion?** Ownership in Q&A is the owner's job; this plan
covers everything else. The panel's verdict on 19 Oct is in section 1. Every claim below is about
what we will MEASURE, not what we hope; where a result can go against us, the plan says what we
say then.

---

## 0. Rules for this plan (they protect the score we already have for rigour)
1. **Pre-register.** Every experiment's success rule is written here (section 3) and committed
   BEFORE it runs. The result is reported whatever it is.
2. **No tuning on test days or test months.** Food: choices on validation days 36–42, test days
   43–56 report only. Real desk: choices on the last 20% of the learning period, scored on the last 30%.
3. **A policy or model change needs** a validation design run + a confirmation on fresh seeds
   (as v5 did). Nothing ships on one lucky run.
4. **Every number on screen and in docs comes from `eval/results.json`**; `tests/test_doc_numbers.py`
   keeps guarding JUDGE_QA and DEMO_SCRIPT.
5. **Existing numbers must not move** unless a pre-registered change moves them on purpose. Every
   branch is reviewed like PR #1: compare every value in results.json, run all tests.
6. **After the code freeze (26 Oct evening):** a brand-new sealed world, generated then, run ONCE.
7. Free only, no new dependencies (CP-SAT is part of OR-Tools, already installed). Datasets must
   have a licence we can name.

---

## 1. Where we stand (harsh panel, 19 Oct) and where each item takes us

| Criterion | Now | Target | Why it is low now | Items |
|---|---|---|---|---|
| Identify patterns | 6 | 9 | We found the problems we planted ourselves; real-data findings are not validated | W4 |
| Predict bottlenecks | 6 | 9 | AUC 0.976 looks like the model learning our simulator; real forecast loses; bottleneck alerts never scored | W7 |
| Recommend actions | 5 | 9 | 11 of 12 staffing moves: no clear effect; staffing plan adds +0.06 pts | W5, W3 |
| Explain decisions | 8 | 10 | Explanations are shown but never tested for faithfulness | W8 |
| Measure impact | 6 | 9 | No outcome measured on the public data | W3, W9 |
| ML forecasting + anomaly detection | 7 | 9 | Same as patterns + prediction | W4, W7 |
| NLP / LLMs | 3 | 9 | 98% on partly templated text proves little; LLM is worse (90%) and sees 1.5% | W6 |
| Optimisation | 3 | 9 | Our ablation: greedy dispatch ties min-cost flow (−0.016 pts) | W5, W2 |
| Dashboard | 7 | 9 | Dense; no performance tracking over time; Simulate 20–40 s | W10 |
| D1 public dataset | 6 | 9 | The real world is the weaker half; no outcome there | W3, W4, W11 |
| D2 dashboard, bottlenecks | 8 | 10 | Bottleneck predictions not scored on screen | W7, W10 |
| D3 explainable recommendations | 6 | 9 | The recommendations people see mostly do not pay | W5, W8 |
| D4 baseline vs proposed | 7 | 10 | Thin on public data; baselines on real data are weak (priority field is 94% one value) | W3, W7 |
| Rigour | 9 | 10 | Already strong | W1, W12 |
| Real-world validity | 4 | 8–9 | Headline lives in a world we built (closed loop); simulator assumes 1 ticket per agent, the real log shows ~4.8 open at once | W1, W2, W3, W4 |
| Novelty | 5 | 8–9 | Risk-first dispatch is known; our new idea is not named | W11 |
| Clarity (product side) | 5 | 9 | Too many numbers per screen; owner could not explain it | W10, W12 |

**Honest ceilings:** without real food-delivery operations data (none with a licence exists — checked
18 Oct), a harsh judge gives real-world validity 8, maybe 9 if W1–W4 come out strong. Optimisation
reaches 9 only if the new roster optimiser measurably helps on test days; if it does not, we report
that and the score stays near 7. Everything else can reach 9–10 with the work below.

---

## 2. The big idea to name (novelty): proof-carrying recommendations
Every recommendation OpsLens makes ships with its own **replayed effect, 95% interval and ceiling**:
"cross-train two Hindi agents: −26.8 missed SLAs over 14 unseen days [−39.0, −14.6]". Other tools
recommend; OpsLens recommends **and attaches the proof**, tested on worlds it never saw (W1), on a
real company's log (W3, W4), and with an LLM that cannot invent a number. This is the sentence the
pitch, the Proof screen and the README lead with.

---

## 3. Work items (what, why, how, the pre-registered rule, who)

### W1 — Robustness across worlds we did not design (validity 4 → 8, rigour → 10, novelty +)
- **What:** 30 random food-delivery worlds (seeds 7001–7030). Each world draws its parameters from
  wide ranges fixed here: volume ×0.7–1.4; lunch/dinner peak heights ±30%; category mix ±40%;
  Hindi share 5–25%; handle-time means ×0.7–1.3; skill-mismatch slowdown 1.2–2.0; absenteeism
  2–10%; team sizes ±2 agents; SLA targets P1 30–90 min, P2 2–6 h, P3 12–36 h; agent concurrency
  1–3 with the W2 slowdown; 5 random planted problems (data/plant.py).
- **How:** the routine pipeline with frozen hyperparameters and frozen optimiser weights: generate →
  classifier → risk model (train/validation days of that world) → forecast → staffing → simulate test
  days with OpsLens, industry standard (D), urgent-first (B), SLA-due (C) and least-slack-first,
  3 seeds, same tickets and luck. Nothing is tuned per world.
- **Rule (pre-registered):** we say "robust" only if OpsLens has the lowest missed-SLA rate in
  **≥ 27 of 30 worlds** and the median paired difference vs industry standard has a 95% CI below 0.
  We report every world, the worst three, and why OpsLens loses there.
- **Amendment (19 Oct, committed before any world ran):** (1) with k chats per agent the volume is
  also multiplied by k / (1 + s·(k−1)), so "volume ×0.7–1.4" means ×0.7–1.4 of today's LOAD (same
  reason as the W2 amendment). (2) Ties: OpsLens counts as lowest if it is within 0.05 points of the
  lowest (3 seeds cannot separate smaller gaps). (3) The planted problems are randomised through the
  generator's own settings (day and size of each spike, which restaurant cluster, IVR error rate,
  Team C weekend lift) rather than data/plant.py. (4) Classifier: local only in every world (30
  worlds would exhaust the free LLM quota; the LLM moves accuracy by ~0.1 point). (5) A code check
  runs on world seed 7000, which is NOT one of the 30 and is not reported as a result.
  (6) Fix found by that code check, before any of the 30 worlds ran: "today's load" means work ÷
  capacity, so the volume multiplier also accounts for team size, the handle-time scale and the
  category mix's average handle time, not only chats per agent (eval/run_worlds.py load_factor).
- **Output:** `eval/run_worlds.py` (+ `eval/run_world_compare.py` inside each world) →
  `eval/parts/worlds/<seed>.json` → `results.worlds`. Proof screen: "30 worlds we never designed".
- **Owner:** Claude 1 (this session). Touches: new eval file, generator overrides only (no default changes).
- **Result (19 Oct): rule NOT passed** — lowest in 19 of 30 (needed 27); median vs industry standard −8.19
  [−12.20, −3.28]. All 11 losses: sustained overload (≥1.06× load), all to least slack (PROGRESS.md W1 + W2).

### W2 — Concurrency: agents with 2–3 chats at once (validity, optimisation)
- **What:** the real UCI log shows an agent holds ~4.8 incidents open at once; chat agents often
  hold 2–3. Our main world assumes 1. Add a per-chat slowdown: with k chats open, each runs
  ×(1 + s·(k−1)), s an ASSUMPTION with a range.
- **How:** simulate.py change guarded by a regression test: with max_concurrent = 1 every existing
  number is identical. Main world, test days, 5 seeds, all policies; k ∈ {2, 3}, s ∈ {0.25, 0.5}.
  Also re-run the optimiser ablation under k = 3: does min-cost flow beat greedy when agents have
  several slots?
- **Rule:** "survives concurrency" only if OpsLens beats industry standard with CI < 0 in all four
  settings. If not: fix on validation days only, confirm on fresh seeds, or report the limit.
- **Amendment (19 Oct, committed before any run):** at the same headcount, k chats per agent RAISE
  capacity (k = 2, s = 0.25 → each agent does 2 / 1.25 = 1.6× the work), so every policy drifts
  towards 0% missed and the test says little. **Primary test: equal load** — volume × k / (1 + s·(k−1))
  (×1.6, ×1.33, ×2.0, ×1.5 for (k, s) = (2, .25), (2, .5), (3, .25), (3, .5)), using the same
  ticket-copying method as the +25% volume stress test. The four settings at today's volume are
  reported too. Policies: first come (A), urgent first (B), SLA due (C), industry standard (D),
  OpsLens; 5 seeds; test days once. The rule above applies to the equal-load test. The slowdown is
  fixed when a chat starts (a chat started while the agent already has one open takes ×(1 + s)),
  a stated simplification.
- **Result (19 Oct): rule PASSED** — OpsLens beats industry standard in all four equal-load settings.
- **Output:** `eval/run_concurrency.py` → `results.concurrency` (settings, KPIs per policy, paired CIs,
  and the optimiser ablation at k = 3).
- **Owner:** Claude 1. Touches: opslens/simulate.py (guarded), config, new eval file.

### W3 — The real desk: an outcome, not just a prediction (D1, D4, measure impact, recommend)
- **What:** "36.6% missed for them — what for you?" A log cannot be replayed, so we answer with a
  fair, stated benchmark: **if the desk can fast-track 10%, 20% or 30% of new incidents, whose
  pick saves more missed deadlines?** Fast-track = no further pickup wait after the 1-hour mark.
- **How:** deadline rule per priority learned on the first 70% only (it matches the company's flag
  ~91% of the time); ceiling = instant pickup for every incident. Pickers, all scored at 1 hour:
  the desk's priority field; "still unassigned at 1 hour"; oldest first; logistic regression on the
  same features; OpsLens (LightGBM). Bootstrap CIs over test weeks.
- **Rule:** we claim OpsLens's pick is better only if it saves more misses than the BEST other
  picker with a CI excluding 0, at the 20% budget. Every picker and budget is shown.
- **Output:** `results.realdesk.fasttrack` (+ the three headings: turnaround hours saved, misses
  avoided, no productivity claim). Proof screen (real world) and Overview line.
- **Owner:** session "real-desk" (local). Touches: opslens/realdesk.py, eval/run_realdesk.py.

### W4 — Patterns proven on real data (patterns 6 → 9, anomaly detection)
- **What:** (a) **Out-of-time replication:** every real-desk finding is found on the learning months
  and re-measured on the later test months. (b) **Blind plants into the REAL log:** 20 random problem
  sets injected into the real UCI background (a category spike on a day, a team slowing down for a
  week, a category bouncing between teams), random sizes and days. (c) False alarms on the clean
  real test months.
- **Rule:** report recall, false alarms per month and detection delay, whatever they are. A finding
  "replicates" only if its gap keeps the same sign with a CI excluding 0 on the test months.
- **Output:** `results.realdesk.replication`, `results.realdesk.blind_plants`. Problems screen (real)
  shows "still true on later months" per card; Proof shows real-log plant recall.
- **Owner:** session "real-desk" (same as W3, same files).

### W5 — Optimisation that matters: a CP-SAT weekly roster (optimisation 3 → 9, recommend 5 → 9)
- **What:** today staffing.py makes greedy single moves; 11 of 12 have no clear effect. Replace it
  with a real **tour-scheduling optimiser** (OR-Tools CP-SAT): for each week, every agent's start
  hour and days off, same headcount, same hours per person, start within ±2 h of today, at most
  N changes per team (N chosen on validation). Objective: weighted shortfall vs Erlang-C need from
  the P80 forecast, per team and hour (overload hours ×3), plus a small penalty per change.
- **How:** compare on validation days 36–42, 5 seeds: published roster vs today's greedy moves vs
  CP-SAT roster. Then confirmation on fresh seeds. Test days once. Your plan items are rebuilt from
  the new moves (eval/run_plan_items.py) so each move still shows its effect alone.
- **Rule:** adopt only if CP-SAT beats today's greedy moves on validation with CI < 0 AND confirms
  on 20 fresh seeds. Otherwise keep greedy and report it.
- **Output:** `results.staffing_opt`; Actions screen shows the optimised week with reasons
  ("Team C short 2.2 agents Sat 19–23 at the P80 forecast").
- **Owner:** Claude 2 (GitHub). Touches: opslens/staffing.py, new opslens/roster_opt.py, its eval
  file, tests; Claude 1 re-runs the plan items after the merge.

### W6 — NLP and LLMs on a real benchmark (NLP/LLM 3 → 9)
- **What:** (a) **Banking77** (real customer banking queries, 77 intents, CC BY 4.0 — verify): our
  local TF-IDF model, the cascade (LLM only on low confidence), LLM-only on a sample; accuracy,
  share sent to the LLM, cost per 1M tickets, latency; next to published results (cite the paper),
  also in the 10-examples-per-intent setting where LLMs should help most. (b) **LLM root-cause
  attribution:** the LLM reads each evidence card (not the planted truth) and names the cause type
  and a one-line root cause with number keys; accuracy vs planted truth on the 5 plants and the
  blind plant sets, vs our rule-based cause type. (c) **Ask OpsLens routing accuracy:** 60 questions
  (English + Hinglish) written and labelled BEFORE the run; LLM router vs keyword rules.
- **Rule:** report all; claim "the LLM adds value" only where the cascade beats local-only with a
  CI excluding 0 (Banking77) or the LLM beats rules on attribution/routing.
- **Output:** `results.nlp_bench`, `results.llm_eval`. Proof → How we tested; Problems cards show
  the LLM's root-cause line.
- **Owner:** Claude 2 (Sneha's Claude, GitHub, her own free keys). Touches: new files only
  (eval/run_nlp_bench.py, eval/run_llm_eval.py, data download script, tests).

### W7 — Predictions against strong baselines (prediction 6 → 9, D2, D4)
- **What:** (a) Food risk: a "time left to SLA" rule and logistic regression on the same snapshots
  vs LightGBM; reliability (calibration) chart. If the simple rule is close, we say so: the value is
  in estimating the *rescue* (risk if it waits minus risk if served now), and we measure that.
  (b) **Bottleneck alerts scored:** precision, recall and lead time of predicted overload hours on
  test days (food) and predicted overloaded team-days (real), vs the naive forecast. (c) Real-desk
  forecast: candidates {same day last week, learned, average of both}, chosen on check weeks.
- **Rule:** report all; the Risks screen shows the alert hit rate.
- **Owner:** Claude 2 (GitHub). Touches: new eval files; reads opslens/risk.py and forecast.py (the
  real-desk forecast part (c) goes to the real-desk session, which owns realdesk.py).

### W8 — Explanations tested for faithfulness (explain 8 → 10, D3)
- **What:** (a) **Deletion test:** remove a ticket's top reason → the risk must drop more than when
  a random feature is removed (share of tickets where it does). (b) **Reason correctness:** on the
  planted Hindi-refund segment, language/skill must be in the top 3 reasons (share). (c) **"Why not
  the other agent":** each assignment shows the runner-up agent and the value gap.
- **Owner:** Claude 2 (GitHub). Touches: new eval file; (c) adds the runner-up to the assignment
  reasons in opslens/optimize.py output only (no decision change; regression: same assignments).

### W9 — Impact under the three headings on both worlds (measure impact → 9)
Turnaround, productivity, service quality, for food (exists) and the real desk (from W3), plus the
₹ view labelled as an assumption. Owner: session "real-desk" with W3.

### W10 — Dashboard to 9–10 (dashboard, clarity, D2)
- **Performance tracking** (named in the problem statement): KPIs day by day over the test days,
  per team and per agent load (fairness), both worlds.
- **Design pass:** one claim per screen, plain words, at most 3 big numbers above the fold,
  projector 1366×768.
- **Simulate faster:** warm the plan workers at server start; target ≤ 10 s for a new plan
  (profile the one-day run first).
- **New proof, in plain words:** 30 worlds (W1), concurrency (W2), real-desk fast-track (W3),
  real-log plants (W4), NLP benchmark (W6), alert hit rate (W7), faithfulness (W8).
- **Story mode** on the six screens.
- **Owner:** session "web" (local) owns `web/` for the whole plan; engine items document their
  JSON shapes at the top of their explain file (as plan.md did).

### W11 — Feasibility and novelty, shown not told
- **Shadow mode on a real day:** the real desk's day replayed hour by hour in the dashboard: what
  OpsLens flags at each hour vs what then happened (from W3's scores). This is how a company would
  adopt it in week 1.
- `docs/PRODUCTION.md`: shadow → assist (Accept/Override) → auto-dispatch for low-risk tickets;
  API latency; scale (5,000 waiting × 500 agents); how it sits behind an AI first line.
- README + pitch lead with "proof-carrying recommendations" (section 2).
- **Owner:** Claude 1 (docs) + session "web" (shadow view).

### W12 — Freeze, sealed world 3, independent rating, rehearsal
- 26 Oct evening code freeze → full `make eval` once → **sealed world 3** (fresh seed, all baselines,
  concurrency setting included) run once → doc-number tests.
- `docs/JUDGE_PACKET.md`: what OpsLens is, how to run it, where every number comes from — for the
  independent Claude rater and for the real judges.
- Independent rating → presentation fixes only (no model changes after freeze).
- 27 Oct rehearsal + backup video.

---

## 4. Who does what (two writers never touch the same files)

| Worker | Items | Files it owns |
|---|---|---|
| Claude 1 (this session) | W1, W2, W11 docs, W12; reviews and merges every branch | simulate.py (guarded), eval/run_worlds.py, stress/ablation eval, docs |
| Claude 2 (GitHub, one `claude2/*` branch per item) | **W6, W7, W8, W5** (in that order), then a harsh review of the dashboard | new eval/data files; opslens/staffing.py + roster_opt.py (W5); optimize.py reason text only (W8c) |
| Session "real-desk" (local, own worktree) | W3, W4, W9, W7(c) | opslens/realdesk.py, eval/run_realdesk.py, a UCI plant module, tests |
| Session "web" (local, own worktree) | W10, W11 shadow view | web/ only |

Claude 2 runs on Sneha's account and machine, so the heaviest share of new engine work goes there:
it also saves the owner's usage. Claude 1 keeps the simulator change (W2) because every other
result depends on it.

Shared files (`eval/run_eval.py`, `opslens/results_schema.py`, `PROGRESS.md`, `JUDGE_QA.md`): each
worker adds ONE step line and ONE schema field and proposes doc text in its branch notes; Claude 1
merges and writes the shared docs. Usage note: four parallel sessions spend the plan's usage fast —
start W1/W2, W3/W4 and Claude 2's list first; W10 next.

---

## 5. Timeline (code freeze 26 Oct evening)
| Day | Work |
|---|---|
| Mon 19 Oct | This plan; pre-registration committed; W1/W2 start; real-desk session and Claude 2 (W6, W7) start |
| Tue 20 | W2 simulator change + regression test; W1 world generator; web session starts (W10); Claude 2: W6 LLM runs (daily quota), W7 |
| Wed 21 | W1 runs (30 worlds); W2 runs; W3/W4 results; Claude 2: W8, W5 design |
| Thu 22 | Review + merge W3/W4, W6, W7, W8; Claude 2: W5 validation runs |
| Fri 23 | W5 confirmation + test once; merge; web wires new proof sections |
| Sat 24 | Integration: full `make eval`; docs, JUDGE_QA, DEMO_SCRIPT; W11 |
| Sun 25 | Buffer for whatever failed; story mode; projector check |
| Mon 26 | Freeze (evening) → sealed world 3 once → judge packet → independent rating |
| Tue 27 | Presentation fixes only; rehearsal; backup video |

**Cut list (cut from the bottom first):** W9 → W11 shadow view → W8 (c) → W7 (c) → W4 (c) → W5.
**Never cut:** W1, W2, W3, W12.

---

## 6. What can go wrong, and what we say then
- **W1: OpsLens loses in some worlds.** Good to know before the judges: we show where and why
  ("worlds with almost no rare skills: no rescue to make, it ties"). A 25-of-30 result honestly
  explained still beats any team that tested on one world.
- **W2: concurrency breaks the win.** Fix on validation days with the v5 discipline, or state the
  limit: "built for 1–2 concurrent chats; at 3 the gain shrinks to X".
- **W3: the LightGBM pick does not beat logistic regression.** Then we say "a simple risk score
  already doubles the priority field; ours is the best of them / ties them" — still a real outcome
  on public data.
- **W5: CP-SAT does not beat greedy.** Report it; optimisation stays at ~7; the proof is still worth
  showing ("we tried the exact optimiser; the simple one is as good, so we keep it").
- **W6: LLM free quota runs out.** Cache everything; run in daily slices; `--no-llm` fallback,
  documented (as for sealed world 6262).

## 7. Not doing
New product models beyond CP-SAT, a mascot, deep learning, new datasets without a named licence,
any change after the freeze except presentation fixes.

## 8. Done means
An independent harsh rater, given `docs/JUDGE_PACKET.md` and the running app, scores every
criterion 9 or 10 except real-world validity (8+), and every number it quotes is in `results.json`.
