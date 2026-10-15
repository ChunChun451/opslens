# OpsLens plan v2 — why it looks like this

Written 15 Oct 2026. `CLAUDE.md` is the plan we follow. This file explains **why** it was
changed from v1 (`docs/CLAUDE_v1.md`), what research backs it, the risks, and who does what.
Short sentences, simple words.

---

## 1. How we win

Most teams will build: a dashboard, a chatbot over the data, a classifier that predicts
SLA breach, maybe a greedy assignment rule. They will show charts and say "this will help".

We win by being the team that **proves it**, and lets the judges **test it themselves**:

| What judges usually see | What OpsLens shows |
|---|---|
| "Our model has 92% accuracy" | AUC, PR-AUC, calibration on held-out days, **and the same code on real ServiceNow data** |
| "Our system found the problems" | Recall on 5 planted problems **and on 20 random plant sets we did not design**, plus false alarms |
| "This will reduce breaches" | Replay of 14 unseen days, 2 baselines, same luck (CRN), 5 seeds, paired 95% CI, ablations, stress tests |
| "The AI explains itself" | Every number clicks to evidence; the LLM cannot write a number at all |
| A recorded demo | Judges move a slider (What-if) or plant their own problem, live |

The judges are Eternal engineers. They know support operations well. So realism matters:
food-delivery SLAs, Hinglish text, IVR mis-routing, partner (restaurant) issues, chat
concurrency. And they know Nugget, so we position OpsLens as the layer **behind** an AI
first-line: it runs the human floor that handles escalated tickets.

---

## 2. What changed from v1, and why

| # | Change | Why |
|---|---|---|
| 1 | Project moves to `C:\dev\opslens`, own git repo, Python 3.12 | The home folder is itself a git repo, so commits would go to the wrong repo. OneDrive would sync the venv and data. Python 3.14 is too new for some wheels. Same fix as TrueInk. |
| 2 | 30 days → **56 days**; train 1–35, validation 36–42, test 43–56 | 21 training days give only 2 weeks of "same hour last week" lags. 9 test days hold only one weekend, and planted problem 2 is a weekend problem. A separate validation week lets us choose thresholds and weights without touching test days. |
| 3 | SLAs proposed as P1 1 h / P2 4 h / P3 24 h | In food delivery a late-order complaint must be solved while the order is live. Eternal judges would find a 2 h P1 SLA unrealistic. Still config; confirm in M2. |
| 4 | **5th planted problem: IVR mis-routing → transfers.** Plus decoys | Gives the NLP part a real operational job (fewer transfers, measured in agent-hours), not just an accuracy number. Decoys make the false-alarm number meaningful. |
| 5 | **Blind recall on 20 random plant sets** | "4/4" on problems we designed looks rigged. "18/20 on random problems we did not design" is hard to attack. |
| 6 | **Live Plant-a-problem** demo | The strongest possible answer to "you only found what you planted": the judge plants it. |
| 7 | **Real data: UCI ServiceNow incident log** (core, not stretch) | Has a real `made_sla` flag, priorities, assignment groups, reassignments. Lets us show risk AUC and findings on real data. CC BY 4.0. |
| 8 | Text: Bitext + food-specific template generator with Hinglish | Bitext has no missing-item / wrong-item / restaurant intents. |
| 9 | Classification = **cascade** (local model first, LLM only when unsure) | Free-tier limits are now small (Flash-Lite ≈ 500–1,000 requests/day, reports disagree). 56k tickets through the LLM is risky and wasteful. Cascade is also the right story at Eternal scale (cost per 1M tickets). |
| 10 | Decision tick every **2 min for all policies** (v1: 15 min) | A 15-min batch adds up to 15 min of waiting — 25% of a 1 h SLA. Same cadence for every policy keeps the comparison fair. 15-min REPLAN stays for risk refresh and staffing. |
| 11 | Optimiser: **scarcity cost** + **starvation guard** | Scarcity cost is what beats greedy rules on planted problem 1 (keep the 2 Hindi+refund agents for Hindi refunds). Starvation guard stops the optimiser from "giving up" on late tickets to game the breach %, which a judge will ask about. |
| 12 | Staffing with **Erlang C** on the forecast's **upper band**, budget-neutral | Erlang C is the standard call-centre method; ops judges know it. Staffing to the upper band handles uncertainty. Budget-neutral (same agent-hours) keeps the comparison fair. |
| 13 | Forecast gets **conformal intervals** with coverage | A range with proven coverage is more useful than a single line, and cheap (a few lines of NumPy). |
| 14 | Risk: isotonic calibration, PR-AUC, Brier, "what would reduce this risk" | Probabilities must be honest because the optimiser multiplies them. "What would reduce risk" turns an explanation into an action. |
| 15 | SHAP from LightGBM's own `pred_contrib` | Same TreeSHAP maths, one less heavy dependency (`shap` pulls numba). |
| 16 | **LLM never writes a digit** (number keys filled by code) | Stronger than checking numbers after the fact: a made-up number is impossible by design. |
| 17 | Impact under the PS words: turnaround / productivity / service quality; paired CI | Maps 1:1 to the PS. Reopen rate and transfers add "service quality", which v1 lacked. |
| 18 | Stress tests (+25% volume, absenteeism, surprise spike) | "Works on days it has never seen" becomes "works in conditions it has never seen". |
| 19 | **What-if panel** (new tab) | Judges remember what they touched. The simulator already exists, so this is cheap. |
| 20 | Optional **challenger arena** (TabPFN-3, Chronos-2) | Answers "is this the best model?" honestly with 2026 state of the art. Eval-only, needs owner approval (adds torch). |
| 21 | **UI track U1 in a parallel session** from 18 Oct on fixture data | v1 started the UI on 23 Oct with zero slack. Fixture data is marked and blocked from the demo. |
| 22 | Cut list + "never cut" list | Decided now, calmly, not at 2 am on 26 Oct. |
| 23 | No Eternal / Zomato logos; external facts only in the pitch with sources | Avoids brand misuse; keeps the "every number is computed" rule honest. |

---

## 3. The 2026 research behind the choices

Newest first where possible. Older work is named only when it is still the reference.

**Model choice ("is this the best model?")**
- **TabPFN-3** (Prior Labs, May 2026) is the top single model on the TabArena tabular
  leaderboard; tuned LightGBM ranks lower. But its weights are licensed for research and
  internal evaluation only, it needs torch, and it is far slower than LightGBM per prediction.
  → We keep LightGBM in the product (milliseconds, TreeSHAP, free licence) and use TabPFN-3
  as an **eval-only ceiling check**. If LightGBM is within ~0.01 AUC, that is a strong slide.
  [arXiv 2605.13986](https://arxiv.org/abs/2605.13986) ·
  [model card / licence](https://huggingface.co/Prior-Labs/tabpfn_3) ·
  [state of tabular FMs 2026](https://mindfulmodeler.substack.com/p/the-state-of-tabular-foundation-models)
- **Chronos-2** (Amazon, Apache-2.0, 120M parameters, supports covariates, runs on CPU) ranked
  first among pretrained models on GIFT-Eval in an April 2026 snapshot.
  → Eval-only forecast challenger with the same pre-registered rule.
  [model card](https://huggingface.co/amazon/chronos-2) ·
  [TW3Cast, GIFT-Eval 2026](https://arxiv.org/pdf/2609.28506)

**Judge models by the decisions they cause**
- Decision-focused learning (ICLR 2026; "when and why traditional prediction models fail",
  2026) shows a model with better accuracy can make worse decisions.
  → We choose optimiser weights and the risk model on **simulated breaches on validation days**,
  not on AUC alone.
  [arXiv 2505.13564](https://arxiv.org/pdf/2505.13564) · [arXiv 2606.21773](https://arxiv.org/pdf/2606.21773)
- Conformal robustness in prediction-driven decisions (Sept 2026) → feed forecast **intervals**,
  not point forecasts, into staffing.
  [arXiv 2609.23170](https://arxiv.org/pdf/2609.23170)

**Cheap, honest classification**
- 2026 cascade papers (UCCI with isotonic-calibrated confidence; Conformal Cascade; Signed
  Rescue Routing) agree: raw confidence is miscalibrated; calibrate it, then send to the big model
  only when the small one is likely wrong.
  → Local TF-IDF model with isotonic calibration; LLM only below a threshold chosen on validation days.
  [UCCI 2605.18796](https://arxiv.org/html/2605.18796) ·
  [Conformal Cascade 2607.25018](https://arxiv.org/html/2607.25018v1) ·
  [Signed Rescue Routing 2609.07786](https://arxiv.org/html/2609.07786v1)

**A simulator judges can trust**
- The Digital Twin Counterfactual Framework (Apr 2026) defines a simulated counterfactual with a
  **shared noise draw** for both arms — exactly our common random numbers. Per-entity random
  streams (as in Vivarium) keep the pairing stable even when event order changes.
  → Each ticket's randomness is seeded by (seed, ticket_id).
  [arXiv 2604.01325](https://arxiv.org/abs/2604.01325) ·
  [Vivarium CRN](https://vivarium.readthedocs.io/en/latest/concepts/crn.html)
- Skill-based routing on real call-centre data (2025) reports load fairness and waiting time as
  secondary goals next to payoff. → We report load fairness and max wait, not only breach %.
  [arXiv 2506.20543](https://arxiv.org/abs/2506.20543)

**LLM numbers you can trust**
- CLEF-2026 CheckThat! finds numeric claims are the hardest for LLMs to get right;
  Proof-Carrying Numbers (2025) proposes binding each number to its source.
  → Our LLM writes keys, our code writes numbers.
  [CLEF-2026 2602.09516](https://arxiv.org/pdf/2602.09516) · [PCN 2509.06902](https://arxiv.org/pdf/2509.06902)

**Context for the pitch** (pitch only, with source on slide)
- Nugget, Eternal's AI support platform (Feb 2025): built in-house, handles a large share of
  queries automatically. [Outlook Business](https://www.outlookbusiness.com/start-up/news/zomato-launches-ai-based-platform-nugget-what-does-it-do)
- Gartner (Feb 2026): service will stay hybrid — AI for routine work, people for complex and
  sensitive cases. [CX Network](https://www.cxnetwork.com/artificial-intelligence/news/ai-wont-replace-human-customer-service-agents-gartner-predicts)

**Data**
- UCI incident event log (ServiceNow, CC BY 4.0, 24,918 incidents, has `made_sla`).
  [UCI 498](https://archive.ics.uci.edu/dataset/498/incident+management+process+enriched+event+log)
- Bitext customer-support dataset (CDLA-Sharing-1.0).
  [Hugging Face](https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset)

**Free LLM tiers (check in our own accounts on day 1 — blogs disagree)**
- Gemini: Pro left the free tier in 2026; Flash-Lite reported at ~15 RPM and 500–1,000 requests/day.
  [official limits page](https://ai.google.dev/gemini-api/docs/rate-limits) ·
  [PE Collective](https://pecollective.com/tools/gemini-free-tier-guide/)
- Groq: free tier reported at ~30 RPM and ~1,000 requests/day for gpt-oss models; Llama models
  may be gone. [official limits page](https://console.groq.com/docs/rate-limits) ·
  [klymentiev.com](https://klymentiev.com/blog/groq-pricing)

---

## 4. Risks and what we do about them

| Risk | Plan |
|---|---|
| ~~TrueInk (DEV_101) on the same days~~ | **Resolved 15 Oct:** OpsLens is the team's only finale project; all days go to it. TrueInk is paused. |
| Free LLM limits change or run out | Cascade keeps LLM calls in the hundreds, not tens of thousands. Cache everything. Mock provider for tests. Demo runs from cache. |
| OpsLens does not beat Baseline B by much | Report the truth. Ablations show where gains come from. The scarcity cost, starvation guard and mis-routing fix are designed for real effects; the calibration targets keep the floor busy enough that policy matters. |
| "Your simulator is rigged" | Erlang-C match test; same tickets/luck/cadence/headcount for all policies; weights chosen on validation days; stress tests on unseen conditions; code is plain and short. |
| "You only found what you planted" | 20 random plant sets; clean-data false alarms; UCI real data; live Plant-a-problem. |
| UI starts too late | U1 parallel session from 18 Oct on fixture data. |
| Wi-Fi at the venue | `make demo` uses cached results and needs no network. Backup video. |
| Owner cannot explain some code | Explain file + Q&A per milestone; plain code rules; M12 rehearsal without notes. |

---

## 5. Who does what

OpsLens is the only finale project (decided 15 Oct), so the owner's full time goes here.
That means: every milestone gets a proper review the same day, the live Plant-a-problem demo
is planned work (not a stretch), and the cut list is for emergencies only.

**Owner + Claude Code (engine):** M1 → M8 in order, one session per milestone, 15–22 Oct.
Then M9 → M12.

**Claude Code, parallel session (UI track U1, 18–22 Oct):** only `web/`, against
`eval/fixture_results.json` (made in M2). The owner reviews it lightly; judges will grill
the engine, not the CSS.

**Sneha (story, demo, business):**
| Date | Task |
|---|---|
| 16 Oct | Confirm finale format with organisers: pitch length, Q&A length, judging rubric, projector/HDMI, power, Wi-Fi. Update `DEMO_SCRIPT.md` timing. |
| 17–19 Oct | Research labelled assumptions with sources (cost per SLA breach, CSAT effect) → notes for `config/impact.yaml`. Draft the story ("Saturday, 8:47 pm, Team C…"). |
| 18 Oct | Design 2 secret plant sets with `data/plant.py` without telling the owner (extra blind test). |
| 20–24 Oct | Deck: problem → live demo → proof → impact → production path. Use only numbers from `docs/NUMBERS.md` (after the 22 Oct freeze). |
| 25–27 Oct | Run story mode until smooth; time it; record backup video; ask the owner Q&A questions daily. |

---

## 6. Demo outline (adjust when the format is known)

1. **Problem (30 s)** — "Saturday 8:47 pm. 140 tickets waiting. Which 10 will breach?"
2. **Replay (60 s)** — same Saturday, FIFO vs OpsLens side by side, breach counters running.
3. **Pattern (45 s)** — Hindi refunds evidence card → click to example tickets.
4. **At-risk ticket (45 s)** — probability, top 3 reasons, "what would reduce this risk".
5. **Recommendation + impact (45 s)** — assignment with reason; staffing move; the results
   table with CI and ablations.
6. **Your turn (60 s)** — a judge moves a What-if slider, or plants a problem.
7. **Close (15 s)** — "Proven on 14 unseen days, on real ServiceNow data, and on your problem."

---

## 7. Attack questions to prepare from day 1

- Isn't the data fake? → generator is open, calibrated, and the same code runs on real UCI data.
- Isn't the simulator built to make you win? → fairness rules, Erlang-C check, ablations.
- Leakage? → `features_at` test; train/validation/test by day; no tuning on test.
- Does OpsLens abandon hopeless tickets? → starvation guard; P90 and max wait reported.
- Your risk model was trained on FIFO history but used under OpsLens — distribution shift?
  → it predicts risk "if nothing changes", which is exactly the risk we act to prevent.
- Why not a deep model / TabPFN / Chronos? → challenger arena result, latency, licence.
- What happens at Eternal scale? → scale test, partitioning, cascade cost per 1M tickets.
- What if the LLM is down? → local tier classifies everything; cache; template brief.

---

## 8. Day-1 checklist (M1)

- [ ] Create `C:\dev\opslens`, copy `CLAUDE.md`, `PROGRESS.md`, `docs/`; `git init`.
- [ ] Python 3.12 venv (uv-managed CPython 3.12 is already on this PC).
- [ ] Gemini API key from Google AI Studio → `.env`. Check the free model list and limits there.
- [ ] Groq API key → `.env`. Check which free models exist today.
- [ ] Download Bitext + UCI into `data/public/`; fill `data/SOURCES.md`.
- [ ] Owner: decide on the challenger arena (adds torch, eval-only) — can wait until M8.
