# OpsLens — the decision engine for support operations

Deviathon 2.0 finale · problem DEV_103 (Eternal Ltd) · GLA University Mathura · 29–31 Oct 2026
Team SoyaChaap: Jijnasu Mishra (owner, tech), Sneha Kumari (story, demo, business)

Read this file and `PROGRESS.md` at the start of every session. This file is the plan.
`PROGRESS.md` is the log of what is done. If anything here is wrong or impossible,
**stop and tell the owner** — never silently change the plan.

---

## 0. The one-paragraph pitch (everything we build serves this)

Existing helpdesk tools tell you a ticket is late. OpsLens tells you **which tickets will be
late, why, what to do about it — and proves the plan works on days it has never seen.**
It finds recurring problems with evidence, forecasts the next 48 hours, scores every open
ticket's breach risk with reasons, assigns work with an optimiser, and measures the result
by replaying held-out days against two baselines in a fair simulator.

---

## 1. How you (Claude Code) work on this project

### 1.1 The owner must understand every line
The owner will defend this code to Eternal's engineers. So:
- Plain Python and plain JavaScript. Functions and small dataclasses / pydantic models.
- No metaprogramming, no decorators beyond FastAPI's, no deep class hierarchies,
  no clever one-liners. A long clear function beats a short clever one.
- Type hints everywhere. Functions under ~60 lines where reasonable.
- Every module starts with a docstring: what it does, why it is designed this way,
  and one small example with real numbers.
- Comments explain **why**, not what.

### 1.2 Session protocol
**Start:** read `CLAUDE.md` + `PROGRESS.md`. Restate the milestone in 3 lines. Plan before coding.
**During:** small steps, run tests often. Develop on a small sample (e.g. 3 days of data),
then run the full size once at the end.
**End of every milestone:**
1. All tests pass (`make test`).
2. Append to `PROGRESS.md`: what was built, the key numbers printed, open issues, next step.
3. Write `docs/explain/<module>.md` (see 1.3).
4. Add 3–5 entries to `docs/JUDGE_QA.md` (see 1.4).
5. Commit with message `M<n>: <short summary>`.

**One milestone per session.** Do not start the next one unless asked.

### 1.3 Explain files (`docs/explain/<module>.md`)
Written for the owner, whose first language is not English: short sentences, simple
words, technical terms are fine. Each file has: what the module does (5 lines), how it
works step by step, **one worked example with real numbers**, its weaknesses, and how to
read the code (which function to open first).

### 1.4 Judge Q&A file (`docs/JUDGE_QA.md`)
For each module, add the questions a sharp industry judge would ask, each with a
model answer under 60 words that uses real numbers from our results. Include at least
one "attack" question per module (e.g. "isn't this data leakage?").

### 1.5 Hard rules
- **Free only.** Free libraries, free API tiers. No GPU needed.
- **Never show a number we did not compute.** Every number in the UI, the report or the
  pitch comes from `eval/results.json`. LLM-written text may only repeat computed numbers
  (validated in code).
- **No leakage.** A feature for a ticket at time t may only use information available
  before t. Train on days 1–21, evaluate on days 22–30 only.
- **The engine never reads `data/planted.json`.** Only `eval/` reads it, to score us.
- **Privacy first.** Ticket text is PII-masked before it is sent to any external API.
- **Ask before adding a dependency** that is not in section 3.
- **Never paste huge outputs** into the conversation; print summaries (saves usage).

---

## 2. Judging criteria → what we build → how we prove it

| PS requirement | OpsLens feature | Proof shown to judges |
|---|---|---|
| Identify patterns | Evidence cards from KPIs, delay decomposition, anomaly detection, LLM-named clusters | Planted-problem recall (target 4/4) and false-alarm count |
| Predict bottlenecks | 48 h demand forecast vs capacity; per-ticket breach risk | Forecast WAPE vs seasonal-naive; risk AUC and top-10% precision on held-out days |
| Recommend actions | Optimised assignment every 15 min + staffing moves | Simulator: breach %, P90 time vs 2 baselines, 5 seeds |
| Explain decisions | SHAP reasons per ticket, evidence per finding, reason per assignment | Click-through on any number in the UI |
| Measure impact | Simulator + ablations + impact translation | `docs/NUMBERS.md`, generated from results |
| Baseline vs proposed | Baseline A (FIFO), Baseline B (priority), OpsLens | Same tickets, common random numbers, held-out days |

---

## 3. Tech stack (fixed — ask before changing)

- Python 3.11+, FastAPI, Uvicorn, pydantic v2, pandas, NumPy, SQLite (`sqlite3`)
- scikit-learn (TF-IDF, KMeans, metrics), LightGBM (risk + forecast), SHAP
- Google OR-Tools (`ortools`) — min-cost flow / assignment
- Our own discrete-event simulator using `heapq` (no simulation library — the owner must
  be able to explain every line)
- LLM via the `openai` SDK against OpenAI-compatible endpoints:
  main = Gemini Flash-Lite (free tier), fallback = Groq `llama-3.1-8b-instant`,
  tests = `mock` provider. Verify base URLs, model names and free limits on day 1;
  store them in `config/providers.yaml`.
- Frontend: plain HTML + vanilla JS + CSS; Chart.js bundled in `web/vendor/`
  (**the demo must work with Wi-Fi off**)
- pytest, `Makefile`
- Explicitly **not** used: deep learning, Streamlit, React, Docker (keep it simple to run).

---

## 4. Definitions (use these exact meanings everywhere)

- **Wait time** = first agent pickup − created_at. **Handle time** = time an agent actively works.
  **Resolution time** = resolved_at − created_at.
- **SLA breach** = resolution time > SLA for the ticket's priority (P1 2 h, P2 8 h, P3 24 h; config).
- **Utilisation** ρ = arrival rate ÷ (agents × tickets per agent-hour). ρ > 1 → backlog grows.
  Example: 120 tickets/h, 30 agents at 3/h → ρ = 1.33 → backlog grows 30/h.
- **Little's law**: number waiting = arrival rate × average wait. 120 waiting at 40/h → 3 h average wait.
- **P90 resolution time** = 90% of tickets resolve faster than this.
- **WAPE** = Σ|forecast − actual| ÷ Σ actual (preferred over MAPE, which breaks near zero).
- **Robust z** = 0.6745 × (x − median) ÷ MAD. Flag when > 3.5.
  Example: median 40, MAD 5, today 95 → z ≈ 7.4 → flag.
- **AUC** = probability a breached ticket gets a higher risk score than a non-breached one.
- **Top-10% precision** = share of the 10% riskiest tickets that actually breached.
- **Load fairness** = standard deviation of agent utilisation (lower = fairer).

---

## 5. Data

### 5.1 Ticket text (`data/public/`)
A public customer-support dataset for realistic text and intents (e.g. the Bitext
customer-support dataset). Record source, URL and licence in `data/SOURCES.md`.
Map its intents to our categories.

### 5.2 Operations generator (`data/generate_ops.py`, params in `config/generator.yaml`)
Public datasets lack timestamps, agents, skills and SLAs, so we generate this layer —
**and say so openly in the pitch.** Fixed seed.
- 30 days, ~1,000 tickets/day; food/quick-commerce pattern: lunch and dinner peaks,
  weekend lift, one sale-day surge.
- Ticket schema: `ticket_id, created_at, channel{chat,email,call}, category{late_delivery,
  missing_item, wrong_item, refund, payment_failure, app_bug, account, restaurant_partner},
  priority{P1,P2,P3}, language{en,hi,other}, customer_tier{normal,gold}, order_value_inr,
  restaurant_cluster_id, text`.
- Agents: 40 agents in 4 teams; each has `skills` (categories), `languages`, `shift`,
  `max_concurrent`. Handle time depends on category; skill mismatch × 1.6 slower (config).
- History is produced by running **Baseline A** in the simulator, so the historical
  data looks like a normal support floor.
- **Planted problems** → `data/planted.json` (engine never reads it):
  1. Hindi refunds wait long — only 2 agents have both skills.
  2. Team C overloaded every weekend dinner peak.
  3. Payment-failure spike on day 18 ("bad app release").
  4. Wrong-item tickets from one restaurant cluster are 3× normal.

### 5.3 Real data path
`Upload CSV` + column mapping in the UI, so the engine runs on any company's export.
Stretch: run the pattern + forecast modules on a second public dataset with real
timestamps, to answer "you only found what you planted".

---

## 6. Engine modules (`opslens/`)

**`privacy.py`** — masks phone numbers, emails, order IDs, card-like numbers, addresses
→ `[PHONE]`, `[EMAIL]`, `[ORDER_ID]`… before any external API call. Tested.

**`ingest.py`** — load, validate (pydantic), clean; compute wait/handle/resolution, breach flag.

**`classify.py`** — LLM batch classification (25–50 tickets/request) → category +
short root-cause phrase; SQLite cache keyed by text hash; JSON validated, broken items
retried once, then marked `unknown`. TF-IDF + KMeans clusters per category; the LLM
names each cluster from 10 sample tickets. Accuracy measured on 200 hand-labelled tickets.

**`patterns.py`** — KPIs by category / team / language / hour / weekday; delay
decomposition (waiting vs handling vs reassignment); robust-z anomaly detection on daily
counts. Every finding is an **evidence card**: metric, comparison
("Hindi refunds wait 3.1 h vs 0.9 h for English refunds"), cause type
(capacity / skill gap / volume spike / partner issue), affected volume, 3 example tickets.

**`features.py`** — `features_at(ticket, t, state)` builds model features using only
information known at time t: category, priority, language, tier, age, queue length,
free skilled agents, hour, weekday, recent arrival rate. **A test proves no future data is used.**

**`forecast.py`** — hourly arrivals per category for the next 48 h (LightGBM: hour,
weekday, lags 24 h / 168 h, rolling means, known-event flag). Baseline: same hour last
week. Report WAPE for both. Bottleneck = forecast demand > scheduled capacity at target
ρ = 0.85.

**`risk.py`** — LightGBM P(breach) for open tickets, trained on days 1–21 snapshots,
tested on 22–30. Report AUC, top-10% precision, calibration plot data. SHAP → top 3
reasons per ticket in plain words ("Hindi refund +0.21").

**`optimize.py`** — every 15 simulated minutes, assign waiting tickets to free agent slots.
- Bipartite graph: ticket → agent edge only if the agent can handle it
  (language required; skill mismatch allowed with penalty).
- Edge value = urgency_weight[priority] × (0.2 + P(breach)) × impact
  (gold ×1.5, order value term) − mismatch_penalty. All weights in `config/optimizer.yaml`.
- Each agent has capacity = free slots. Solve as min-cost flow (`SimpleMinCostFlow`, negated
  values). Time budget 1 s; on timeout fall back to greedy by value, and log it.
- Output each assignment with a one-line reason.
- **Sensitivity analysis:** re-run eval with gold weight ×1, ×1.5, ×2 and show the trade-off.

**`staffing.py`** — from the forecast, compute needed agents per skill per hour for
ρ ≤ 0.85; propose concrete moves ("move 3 refund-skilled agents to Team C, Sat 19:00–23:00").

**`policies.py`** — one interface: `decide(state, now) -> list[Assignment]`.
Baseline A: each team takes its oldest ticket. Baseline B: highest priority, then oldest.
OpsLens: risk + optimiser (+ staffing changes applied to the schedule).

**`simulate.py`** — discrete-event simulator. Events in a `heapq`: `ARRIVAL`,
`FINISH`, `DECIDE` (every 15 min), `SHIFT_CHANGE`. The clock jumps event to event.
**Common random numbers:** each ticket's handle-time randomness is pre-drawn once per
seed, so all policies see identical tickets and identical luck. Unit tests with tiny
hand-computed cases (2 agents, 3 tickets) must pass exactly.

**`impact.py`** — per policy: breach %, mean and P90 resolution time, max backlog,
utilisation and load fairness, breaches avoided per day, agent-hours saved. Optional ₹ view
with an explicit, configurable cost-per-breach assumption (always labelled as an assumption).

**`brief.py`** — LLM writes a short daily ops brief from computed numbers only; a validator
checks every number in the text exists in the results, else falls back to a template.

---

## 7. Evaluation (`eval/`) — the source of every claim

`make eval` reproduces everything and writes `eval/results.json` and `docs/NUMBERS.md`.
1. Planted-problem recall + false alarms.
2. Classification accuracy on 200 hand-labelled tickets.
3. Forecast WAPE vs seasonal-naive (held-out days).
4. Risk AUC, top-10% precision, calibration (held-out days).
5. Simulator, days 22–30, 5 seeds, mean ± std: Baseline A, Baseline B, OpsLens.
6. **Ablations:** OpsLens without staffing; without risk scores (optimiser only);
   risk-sorted greedy without optimiser. Shows which part creates the gain.
7. Weight sensitivity (gold ×1 / ×1.5 / ×2).
8. Speed: full pipeline time; optimiser time per 15-min step (median, max).

---

## 8. Dashboard (`web/`, served by `server/app.py`)

Clean, light, large text for a projector; Eternal-style red accent sparingly.
Tabs:
1. **Overview** — breach %, backlog, top 3 issues, today's brief.
2. **Patterns** — evidence cards with example tickets.
3. **Forecast** — next 48 h demand vs capacity; bottleneck hours highlighted.
4. **At-risk tickets** — ranked, probability + top reasons.
5. **Recommendations** — assignments with reasons; staffing moves with expected effect.
6. **Baseline vs OpsLens** — results table, charts, and a **replay**: one busy Saturday
   evening animated side by side (queue length, breaches counting up).
7. **How we tested** — every eval number, ablations, limitations.
8. **Upload data** — CSV + column mapping.
**Story mode** button: a guided 5-step walkthrough for the demo (problem → replay →
pattern → at-risk ticket → recommendation + impact).
Every number is clickable to its evidence.

---

## 9. Non-goals (do not build)
Login/auth, real helpdesk integration, deep learning, mobile app, cloud deployment.
Instead write `docs/PRODUCTION.md`: helpdesk API integration, scale to millions of
tickets/day (partition by team/language), agent overrides tracked as a signal, weekly
retraining with drift checks, PII handling.

---

## 10. Folder layout

```
opslens/
  CLAUDE.md  PROGRESS.md  README.md  Makefile  .env.example
  config/   providers.yaml generator.yaml sla.yaml optimizer.yaml
  data/     SOURCES.md generate_ops.py public/ planted.json(generated)
  opslens/
    llm/    base.py openai_compat.py mock.py cache.py ratelimit.py
    privacy.py ingest.py classify.py patterns.py features.py forecast.py
    risk.py optimize.py staffing.py policies.py simulate.py impact.py brief.py
  server/app.py
  web/      index.html app.js styles.css vendor/chart.umd.js
  eval/     run_eval.py results.json
  tests/
  docs/     explain/ JUDGE_QA.md NUMBERS.md PRODUCTION.md
```

`Makefile` targets: `setup`, `gen`, `test`, `eval`, `serve`, `demo`
(`demo` = serve from cached results with no network calls).

---

## 11. Milestones (one per session)

| # | Date | Milestone | Done when |
|---|---|---|---|
| M1 | 15 Oct | Repo, Makefile, config, LLM layer (providers, mock, cache, rate limit, privacy) | Ping script gets valid JSON from Gemini + Groq; PII test passes |
| M2 | 16 Oct | Generator + planted problems; simulator with Baselines A and B; CRN | 30k tickets; tiny hand-computed sim tests pass; baseline table printed |
| M3 | 17 Oct | Ingest + KPIs + classification + clusters | All tickets classified (cached); accuracy on labelled sample printed |
| M4 | 18 Oct | Patterns + anomalies + evidence cards | Planted recall + false alarms printed |
| M5 | 19 Oct | Features (leak-proof) + risk model + SHAP | AUC, top-10% precision printed; leakage test passes |
| M6 | 20 Oct | Forecast + bottlenecks + staffing | WAPE vs naive printed; staffing moves listed |
| M7 | 21 Oct | Optimiser + OpsLens policy | OpsLens vs baselines, 5 seeds, printed |
| M8 | 22 Oct | `make eval`: ablations, sensitivity, speed; NUMBERS.md | One command reproduces every number |
| — | 22 Oct | **Model + weight freeze** | No model changes after this |
| M9 | 23–24 Oct | Server + dashboard tabs 1–5, 7 | Full flow works on generated data |
| M10 | 25 Oct | Replay animation, story mode, brief, upload CSV | Demo flow works end to end |
| M11 | 26 Oct | PRODUCTION.md, README, polish, speed, tests | `make demo` works with Wi-Fi off |
| M12 | 27 Oct | Rehearsal support: JUDGE_QA complete, backup video checklist | Owner answers every Q&A without notes |
| — | 28 Oct | Travel | No new features |
