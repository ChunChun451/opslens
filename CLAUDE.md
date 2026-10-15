# OpsLens — the decision engine for support operations

Deviathon 2.0 finale · problem DEV_103 (Eternal Ltd) · GLA University Mathura · 29–31 Oct 2026
Team SoyaChaap: Jijnasu Mishra (owner, tech), Sneha Kumari (story, demo, business)

**OpsLens is the team's only finale project** (decided 15 Oct 2026); all days go to it.

**Plan v2 — 15 Oct 2026.** v1 is kept in `docs/CLAUDE_v1.md`. Every change from v1, the
reason for it and the 2026 research behind it are in `docs/PLAN.md`.

Read this file and `PROGRESS.md` at the start of every session. This file is the plan.
`PROGRESS.md` is the log of what is done. If anything here is wrong or impossible,
**stop and tell the owner** — never silently change the plan.

---

## 0. The pitch (everything we build serves this)

Existing helpdesk tools tell you a ticket is late. OpsLens tells you **which tickets will be
late, why, and what to do about it — and proves the plan works on days it has never seen.**
It finds recurring problems with evidence, forecasts the next 48 hours, scores every open
ticket's breach risk with reasons, assigns work with an optimiser, and measures the result
by replaying held-out days against two baselines in a fair simulator.

**And the judges can test it themselves:** change the staffing in the What-if panel and see
the effect in seconds, or plant a problem in fresh data and watch OpsLens find it.

**Why now:** AI agents (Eternal's own Nugget, launched 2025) now resolve routine chats.
The tickets that still reach humans are the hard, escalated, SLA-critical ones. OpsLens
runs that human floor.

**Our three moats** (say them in this order in the pitch):
1. **Proof, not promises** — counterfactual simulator, common random numbers, held-out days,
   two baselines, ablations, stress tests, confidence intervals.
2. **Trust** — every number clicks through to its evidence; the LLM never writes a digit;
   tests prove no future data leaks into features; recall is tested on random blind plants.
3. **Touch it** — What-if panel and Plant-a-problem, live, on the judges' own ideas.

---

## 1. How you (Claude Code) work on this project

### 1.1 The owner must understand every line
The owner will defend this code to Eternal's engineers. So:
- Plain Python and plain JavaScript. Functions and small dataclasses / pydantic models.
- No metaprogramming, no decorators beyond FastAPI's (and pytest fixtures), no deep class
  hierarchies, no clever one-liners. A long clear function beats a short clever one.
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
The UI track (U1) may run in a **parallel session** because it only touches `web/` and
reads fixture results (section 11). Two sessions never edit the same files.

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
  pitch comes from `eval/results.json`. The one exception: public context facts (e.g. about
  Nugget) may appear **in the pitch only**, with the source visible on the slide.
- **The LLM never writes a digit.** LLM text refers to numbers by key
  (`{{sim.opslens.breach_pct}}`); our code fills in the value. Any raw digit in LLM output →
  rejected → template text instead (section 6, `brief.py`).
- **Fixture numbers are always marked.** Fixture results carry `"fixture": true`; the UI
  shows a red FIXTURE banner; `make demo` refuses to start on fixture results.
- **No leakage.** A feature for a ticket at time t may only use information known before t.
- **No tuning on test days.** Train = days 1–35, validation = days 36–42 (all model,
  threshold and weight choices), test = days 43–56 (report only).
- **Fair comparison.** Every policy gets the same tickets, the same luck (common random
  numbers), the same decision moments, the same headcount and the same total agent-hours.
- **The engine never reads `data/planted.json`.** Only `eval/` reads it, to score us.
- **Privacy first.** Ticket text is PII-masked before it is sent to any external API.
- **Ask before adding a dependency** that is not in section 3.
- **No Eternal / Zomato / Blinkit logos or brand assets.** OpsLens is our own brand.
- **Never paste huge outputs** into the conversation; print summaries (saves usage).

### 1.6 Where the project lives
`C:\dev\opslens`, its own git repo, **outside OneDrive** (the home folder `C:\Users\chunc`
is itself a git repo, and OneDrive would sync the venv and data). Python 3.12 venv in
`.venv` (not 3.14: some wheels lag).

---

## 2. Problem-statement requirements → what we build → how we prove it

| PS requirement | OpsLens feature | Proof shown to judges |
|---|---|---|
| Identify patterns | Evidence cards: KPIs, delay decomposition, anomaly detection, LLM-named clusters | Planted recall (target 5/5) + false alarms; **blind recall on 20 random plant sets**; real-data findings (UCI) |
| Predict bottlenecks | 48 h forecast with conformal intervals vs capacity; per-ticket breach risk | WAPE vs seasonal-naive; interval coverage; risk AUC, PR-AUC, top-10% precision, Brier (held-out); AUC on real UCI SLA data |
| Recommend actions | Optimised assignment + Erlang-C staffing moves (budget-neutral) | Simulator: breach %, P90 time vs 2 baselines, 5 seeds, paired 95% CI |
| Explain decisions | TreeSHAP reasons per ticket, evidence per finding, reason per assignment, "what would reduce this risk" | Click-through on any number in the UI |
| Measure impact | Simulator + ablations + stress tests + impact translation | `docs/NUMBERS.md`, generated from results |
| Baseline vs proposed | Baseline A (FIFO per team), Baseline B (priority then oldest), OpsLens | Same tickets, common random numbers, held-out days |

The PS asks for impact on **"turnaround time, productivity, and service quality"**.
`impact.py` reports exactly under those three headings (section 6).

---

## 3. Tech stack (fixed — ask before changing)

- Python 3.12, FastAPI, Uvicorn, pydantic v2, pandas, NumPy, SQLite (`sqlite3`)
- scikit-learn (TF-IDF, logistic regression, KMeans, isotonic calibration, metrics)
- LightGBM (risk + forecast). **SHAP values come from LightGBM itself**
  (`predict(..., pred_contrib=True)` = TreeSHAP), so no `shap` package.
- Google OR-Tools (`ortools`) — `SimpleMinCostFlow`
- Our own discrete-event simulator using `heapq` (no simulation library — the owner must
  be able to explain every line)
- LLM via the `openai` SDK against OpenAI-compatible endpoints:
  main = Gemini Flash-Lite free tier `gemini-3.1-flash-lite` (verified 15 Oct),
  fallback = Groq free tier `qwen/qwen3.8-27b` (verified 15 Oct; `llama-3.1-8b-instant` is retired),
  tests = `mock` provider. Third-party reports of free limits disagree — **verify base URLs,
  model names and limits in our own accounts on day 1**; store them in `config/providers.yaml`.
- Frontend: plain HTML + vanilla JS + CSS; Chart.js bundled in `web/vendor/`
  (**the demo must work with Wi-Fi off**)
- Small supporting libraries: `pyyaml` (config files), `httpx` (FastAPI test client)
- pytest, `Makefile` (on Windows run it with `mingw32-make <target>`), Python 3.12 venv
- **Optional, eval-only, owner approval needed:** `torch` (CPU), `chronos-forecasting`
  (Chronos-2), `tabpfn` (TabPFN-3) for the challenger benchmark (section 7.11). Isolated in
  `eval/challengers/` with its own requirements file. The demo never needs them.
- Explicitly **not** used: deep learning in the product, Streamlit, React, Docker.

---

## 4. Definitions (use these exact meanings everywhere)

- **Wait time** = first agent pickup − created_at. **Handle time** = time an agent actively works.
  **Resolution (turnaround) time** = resolved_at − created_at.
- **SLA breach** = resolution time > SLA for the ticket's priority. Proposed for food delivery
  (config `sla.yaml`, confirm in M2): **P1 1 h** (live order: late, payment debited, missing at
  door), **P2 4 h**, **P3 24 h**.
- **Transfer** = a ticket moved to another team after an agent finds it is in the wrong queue.
  **Reopen** = customer comes back because the fix did not work. **Reopen rate** = reopens ÷ resolved.
- **Utilisation** ρ = arrival rate ÷ (agents × tickets per agent-hour). ρ > 1 → backlog grows.
  Example: 120 tickets/h, 30 agents at 3/h → ρ = 1.33 → backlog grows 30/h.
- **Little's law**: number waiting = arrival rate × average wait. 120 waiting at 40/h → 3 h average wait.
- **Erlang C** = the classic call-centre formula: given arrivals, handle time and agents, the
  chance a ticket must wait, and the average wait. Used for staffing and to check the simulator.
- **P90 resolution time** = 90% of tickets resolve faster than this.
- **WAPE** = Σ|forecast − actual| ÷ Σ actual (preferred over MAPE, which breaks near zero).
- **Conformal interval** = a forecast range built from past errors. **Coverage** = share of
  actual values that fell inside it (an 80% interval should cover ≈ 80%).
- **Robust z** = 0.6745 × (x − median) ÷ MAD. Flag when > 3.5.
  Example: median 40, MAD 5, today 95 → z ≈ 7.4 → flag.
- **Detection latency** = time from the start of a real spike to our first alert.
- **AUC** = probability a breached ticket gets a higher risk score than a non-breached one.
  **PR-AUC** = area under precision–recall (honest when breaches are rare).
- **Top-10% precision** = share of the 10% riskiest tickets that actually breached.
- **Brier score** = mean of (predicted probability − outcome)². Lower = better calibrated.
- **Paired 95% CI** = the range for (OpsLens − baseline) across seeds; same seed = same luck.
- **Load fairness** = standard deviation of agent utilisation (lower = fairer).

---

## 5. Data

### 5.1 Calendar and splits
**56 days (8 weeks): Mon 31 Aug – Sun 25 Oct 2026.** Day 1 = 31 Aug.
- Train / history: days 1–35. Validation: days 36–42. Test: days 43–56 (2 full weeks, 2 weekends).
- Patterns run on history (days 1–42). Live detection, risk, forecast and the simulator
  comparison are reported on test days only.

### 5.2 Ticket text (`data/public/`, `data/text_bank.py`)
- **Bitext customer-support dataset** (Hugging Face, CDLA-Sharing-1.0) for categories it covers
  (refund, payment, account, delivery/tracking).
- Bitext has no food-specific intents, so **missing_item, wrong_item, restaurant_partner,
  app_bug** come from a template-and-slot generator (dishes, restaurants, amounts) with typos,
  **Hinglish** variants ("khana abhi tak nahi aaya") and ~10% multi-issue/ambiguous tickets.
- Record every source, URL and licence in `data/SOURCES.md`. Say openly in the pitch that the
  text is partly synthetic.

### 5.3 Operations generator (`data/generate_ops.py`, params in `config/generator.yaml`)
Public datasets lack timestamps, agents, skills and SLAs, so we generate this layer —
**and say so openly in the pitch.** Fixed seed.
- ~1,130 tickets per weekday (~71.5k in 56 days); food/quick-commerce pattern: lunch and
  dinner peaks, weekend lift ×1.15, sale days ×1.35 (known events, days 25 and 50).
- Ticket schema: `ticket_id, created_at, channel{chat,email,call}, category{late_delivery,
  missing_item, wrong_item, refund, payment_failure, app_bug, account, restaurant_partner},
  selected_category (what the customer picked — may be wrong), priority{P1,P2,P3},
  language{en,hi,other}, customer_tier{normal,gold}, order_value_inr, restaurant_cluster_id, text`.
- Agents: 40 agents in 4 teams, every one listed in `config/roster.yaml` (team skills + extra
  skills, languages, shift start, days off; 9-hour shifts; `max_concurrent` = 1). Start hours
  and days off come from a small search that keeps each team's load flat over the week, so the
  status quo is reasonable, not a strawman. Handle time lognormal by category; skill mismatch
  × 1.6 slower and higher reopen chance; 5% absenteeism. All in config.
- **Calibration targets for Baseline A** (tune the generator until printed values hit them):
  overall breach 12–18%, mean utilisation 70–80%, Team C weekend-dinner ρ 1.2–1.5.
  Reached on 15 Oct: 13.1%, 0.80, 1.40.
- History is produced by running **Baseline A** in the simulator, so the historical
  data looks like a normal support floor.
- **Planted problems** → `data/planted.json` (engine never reads it). One per cause type:
  1. **Skill gap** — Hindi refunds/payments wait long: only 3 agents (none at night) have
     Hindi + refund skills. (With 2 the backlog never cleared — 15 h average waits — which is
     not a realistic floor.)
  2. **Capacity** — Team C overloaded every weekend dinner peak.
  3. **Volume spike** — payment-failure spike on day 18 ("bad app release"). Plus an **unseen
     test-period spike**: app_bug surge on day 47 (not in any forecast) → measures live
     detection latency and how each policy copes.
  4. **Partner issue** — wrong-item tickets from one restaurant cluster are 3× normal.
  5. **Process issue** — call-channel (IVR menu) tickets get the wrong `selected_category`
     25% of the time → transfers ("ping-pong").
- **Decoys** (must NOT be flagged): the two sale-day surges (known events) and one
  high-but-normal day inside natural variation. Each false flag counts as a false alarm.
- `data/plant.py` makes **random plant sets** (random segment, effect size, day) for the
  blind recall test and the live Plant-a-problem demo.

### 5.4 Real data (`data/public/uci_incidents/`)
**UCI "Incident management process enriched event log"** (ServiceNow, CC BY 4.0, 24,918
incidents, 141,712 events): has `made_sla`, `priority`, `assignment_group`,
`reassignment_count`, `opened_at`, `resolved_at`. Used for: risk AUC on a real SLA flag,
pattern findings (e.g. reassignment hot spots), forecast WAPE, and as the Upload-CSV demo
file. This answers "you only found what you planted".

### 5.5 Upload path
`Upload CSV` + column mapping in the UI, so the engine runs on any company's export.

---

## 6. Engine modules (`opslens/`)

**`privacy.py`** — masks phone numbers, emails, order IDs, card-like numbers, addresses, UPI IDs
→ `[PHONE]`, `[EMAIL]`, `[ORDER_ID]`… before any external API call. Tested.

**`ingest.py`** — load, validate (pydantic), clean; compute wait/handle/resolution, transfers,
reopens, breach flag. Adapter `adapters/uci_incidents.py` collapses the UCI event log into
one row per incident with as-of-time fields.

**`classify.py`** — a **cascade**, cheapest first:
1. Local: char + word TF-IDF → logistic regression, trained on resolved tickets' final
   category (known only after resolution, so only past tickets are used). Isotonic-calibrated
   confidence. Char n-grams handle typos and Hinglish spelling ("khana / khaana").
2. LLM batch (25–50 tickets/request) only for tickets below the confidence threshold. Threshold
   chosen on validation days. SQLite cache keyed by text hash; JSON validated, broken items
   retried once, then `unknown`.
Clusters: TF-IDF + KMeans per category; the LLM names each cluster and writes a root-cause
phrase from 10 masked sample tickets. Report: accuracy of local / cascade / LLM-only (500-ticket
sample), % sent to LLM, cost per 1M tickets, **transfers avoided** by routing on the
predicted category.

**`patterns.py`** — KPIs by category / team / language / hour / weekday / cluster; delay
decomposition (waiting vs handling vs transfer vs reopen); robust-z anomalies on daily counts
(history) and **hourly same-hour-of-week counts (live, test days)** with a known-event calendar
so sale days are not flagged. Every finding is an **evidence card**: metric, comparison
("Hindi refunds wait 3.1 h vs 0.9 h for English refunds"), cause type
(capacity / skill gap / volume spike / partner issue / process), affected volume, 3 example
tickets, and why it is not explained by a known event.

**`features.py`** — `features_at(ticket, t, state)` builds model features using only
information known at time t: category (predicted), priority, language, tier, age, time left to
SLA, queue length, free skilled agents, hour, weekday, recent arrival rate.
**A test proves no future data is used** (append future events → features unchanged).

**`forecast.py`** — hourly arrivals per category for the next 48 h. LightGBM (Poisson objective;
hour, weekday, lags 24 h / 168 h, rolling means, known-event flag). Baseline: same hour last
week. **Split-conformal 80% / 90% intervals** from validation-week errors; report WAPE for both
models and interval coverage on test days. Bottleneck = upper (P80) demand > capacity at ρ = 0.85.

**`risk.py`** — LightGBM P(breach) for open tickets, trained on snapshots from days 1–35,
isotonic-calibrated on 36–42, tested on 43–56. Report AUC, PR-AUC, top-10% precision, Brier,
calibration plot data. TreeSHAP (`pred_contrib=True`) → top 3 reasons per ticket in plain words
("Hindi refund +0.21"). **"What would reduce this risk"**: re-score with "skilled agent free
now" and show the drop. Same code run on UCI → real-data AUC.

**`optimize.py`** — at every decision tick, assign waiting tickets to free agent slots.
- Bipartite graph: ticket → agent edge only if the agent can handle it
  (language required; skill mismatch allowed with penalty).
- Edge value = urgency_weight[priority] × (0.2 + P(breach)) × impact
  (gold ×1.5, order value term) − mismatch_penalty − **scarcity_cost**.
- **Scarcity cost:** using an agent with a rare skill pair (e.g. Hindi + refund) on a ticket
  many others could take costs extra, so scarce skills stay free for tickets only they can do.
- **Starvation guard:** a ticket waiting longer than `max_wait` gets top value, so OpsLens
  never "gives up" on hopeless tickets to game the breach number. We report P90 and max wait.
- Each agent has capacity = free slots. Solve as min-cost flow (`SimpleMinCostFlow`, negated
  values). Time budget 1 s; on timeout fall back to greedy by value, and log it.
- Output each assignment with a one-line reason.
- Weights live in `config/optimizer.yaml` and are **chosen on validation days by simulated
  breaches** (decision-focused selection), never on test days.

**`staffing.py`** — from the forecast's upper (P80) band, compute needed agents per skill per
hour with **Erlang C** (wait target from config, ρ ≤ 0.85 cap). Propose **budget-neutral**
moves only — same headcount, same total agent-hours: move cross-skilled agents between teams,
shift starts ±1–2 h ("move 3 refund-skilled agents to Team C, Sat 19:00–23:00"). The simulator
measures each move's effect.

**`policies.py`** — one interface: `decide(state, now) -> list[Assignment]`.
Baseline A: each free agent takes the oldest ticket in their team's queue, then helps with
extra skills if their own queue is empty (routes by `selected_category`).
Baseline B: same, but highest priority first, then oldest.
OpsLens: predicted category + risk + optimiser (+ staffing changes applied to the schedule).
Ablation variants are flags on the OpsLens policy.

**`simulate.py`** — discrete-event simulator. Events in a `heapq`: `FINISH`, `REOPEN`,
`ARRIVAL`, `DECIDE`. The clock jumps event to event. **Decisions are event-driven and the same
for all policies:** right after any arrival, finish or reopen, the policy decides (like a real
floor where the next ticket is pulled at once), plus a 2-minute tick that catches shift starts.
(A fixed 2-minute cadence was tried first: agents then idle ~1 min between tickets, which the
Erlang-C test exposed.) OpsLens refreshes risk scores and staffing every 15 min inside its policy.
**Common random numbers:** each ticket's randomness (handle time, reopen, absenteeism draws)
comes from its own stream seeded by (seed, ticket_id), so all policies see identical tickets
and identical luck, whatever order events happen in.
Tests: tiny hand-computed cases (2 agents, 3 tickets) must pass exactly; an M/M/c steady-state
run must match **Erlang C** average wait within 5%.

**`whatif.py`** — run the simulator for one chosen day with changes (add/move agents, volume ×k,
policy) and return KPIs in a few seconds. Powers the What-if panel.

**`impact.py`** — per policy, under the PS headings:
**Turnaround** (breach %, mean and P90 resolution time, max backlog),
**Productivity** (tickets per agent-hour, agent-hours saved, transfers avoided),
**Service quality** (reopen rate, max wait, load fairness).
Paired differences vs each baseline with 95% CI over seeds. Optional ₹ view with an explicit,
configurable cost-per-breach assumption (`config/impact.yaml`, always labelled as an assumption).

**`brief.py`** — the LLM writes a short daily ops brief **with number keys, not digits**
(`"Breaches fell to {{sim.opslens.breach_pct}}%"`). Code checks every key exists in the
results and fills in the value. Any raw digit or unknown key → template fallback. Same
mechanism for cluster descriptions and "Explain this" text.

---

## 7. Evaluation (`eval/`) — the source of every claim

`make eval` reproduces everything and writes `eval/results.json` and `docs/NUMBERS.md`.
1. Planted recall (5 problems) + false alarms (decoys); **blind recall over 20 random plant
   sets**; false alarms on a clean dataset with no plants.
2. Classification: local vs cascade vs LLM-only accuracy; % escalated to LLM; transfers avoided.
3. Forecast: WAPE vs seasonal-naive (test days); conformal coverage.
4. Risk: AUC, PR-AUC, top-10% precision, Brier, calibration (test days); **UCI real-data AUC**.
5. Simulator, days 43–56, 5 seeds, mean ± std + paired 95% CI: Baseline A, Baseline B, OpsLens.
6. **Ablations:** without staffing; without risk scores; without optimiser (risk-sorted greedy);
   without classifier (route by `selected_category`); without scarcity cost.
7. Sensitivity: gold weight ×1 / ×1.5 / ×2; scarcity-cost weight; starvation-guard `max_wait`.
8. **Stress tests (conditions never seen in training):** +25% volume; 10% absenteeism;
   the day-47 surprise spike. Does OpsLens still beat both baselines?
9. Live detection latency for the day-47 spike.
10. Speed & scale: full pipeline time; optimiser time per step (median, max);
    scale test 5,000 waiting tickets × 500 agents.
11. *(Optional, owner approval)* **Challenger arena:** TabPFN-3 vs our LightGBM risk model,
    Chronos-2 vs our LightGBM forecast, same splits. Pre-registered rule: ship the challenger
    only if it wins by > 2% on the main metric **and** fits the latency budget; otherwise
    report it and keep LightGBM.
12. Simulator validation: Erlang C match (from the test suite).

---

## 8. Dashboard (`web/`, served by `server/app.py`)

Clean, light, large text for a projector; red accent used sparingly; OpsLens brand only.
Tabs:
1. **Overview** — breach %, backlog, top 3 issues, today's brief.
2. **Patterns** — evidence cards with example tickets. **Plant-a-problem** button.
3. **Forecast** — next 48 h demand band vs capacity; bottleneck hours highlighted.
4. **At-risk tickets** — ranked, probability + top reasons + "what would reduce this risk".
5. **Recommendations** — assignments with reasons; staffing moves with expected effect;
   Accept / Override buttons (logged — overrides are a learning signal).
6. **Baseline vs OpsLens** — results table, charts, and a **replay**: one busy Saturday
   evening animated side by side (queue length, breaches counting up).
7. **What-if** — sliders (agents per team, volume ×k, policy) → simulated KPIs in seconds.
8. **How we tested** — every eval number, ablations, stress tests, limitations.
9. **Upload data** — CSV + column mapping (UCI file as the ready example).
**Story mode** button: a guided walkthrough for the demo
(problem → replay → pattern → at-risk ticket → recommendation + impact → judge's turn: What-if
or Plant-a-problem). Every number is clickable to its evidence.

---

## 9. Non-goals (do not build)
Login/auth, real helpdesk integration, deep learning in the product, mobile app, cloud
deployment, a free-form chatbot. Instead write `docs/PRODUCTION.md`: helpdesk API integration,
scale to millions of tickets/day (partition by team/language), agent overrides tracked as a
signal, weekly retraining with drift checks, PII handling, how OpsLens sits behind an AI
first-line (escalated tickets only).

---

## 10. Folder layout

```
opslens/                     (C:\dev\opslens)
  CLAUDE.md  PROGRESS.md  README.md  Makefile  .env.example  requirements.txt
  config/   providers.yaml generator.yaml sla.yaml optimizer.yaml impact.yaml
  data/     SOURCES.md text_bank.py generate_ops.py plant.py public/ planted.json(generated)
  scripts/  download_data.py ping_llm.py
  opslens/
    config.py
    llm/      client.py base.py openai_compat.py mock.py cache.py ratelimit.py
    adapters/ uci_incidents.py
    results_schema.py
    privacy.py ingest.py classify.py patterns.py features.py forecast.py
    risk.py optimize.py staffing.py policies.py simulate.py whatif.py impact.py brief.py
  server/app.py
  web/      index.html app.js styles.css vendor/chart.umd.js
  eval/     run_eval.py results.json fixture_results.json challengers/(optional)
  tests/
  docs/     PLAN.md CLAUDE_v1.md explain/ JUDGE_QA.md NUMBERS.md PRODUCTION.md DEMO_SCRIPT.md
```

`Makefile` targets: `setup`, `data`, `ping`, `gen`, `test`, `eval`, `serve`, `demo`
(`demo` = serve from cached results with no network calls; refuses fixture results).

---

## 11. Milestones (one per session)

| # | Date | Milestone | Done when |
|---|---|---|---|
| M1 | 15 Oct | Move to `C:\dev\opslens` + own git; 3.12 venv; Makefile; config; LLM layer (providers, mock, cache, rate limit); privacy; download Bitext + UCI | Ping gets valid JSON from Gemini + Groq; PII tests pass; datasets + `SOURCES.md` in place |
| M2 | 16 Oct | Text bank + generator (56 days, 5 plants, decoys) + simulator + Baselines A/B + CRN + `results_schema.py` + fixture results | ~56k tickets; calibration targets printed and met; hand-computed + Erlang-C sim tests pass; baseline table printed |
| M3 | 17 Oct | Ingest (+ UCI adapter) + KPIs + classification cascade + named clusters | Accuracy table (local / cascade / LLM), % escalated, transfers avoided printed |
| M4 | 18 Oct | Patterns + anomalies (daily + live hourly) + evidence cards + blind-plant harness | Recall 5 plants + 20 random sets, false alarms, detection latency printed |
| M5 | 19 Oct | Features (leak-proof) + risk + calibration + reasons + UCI check | AUC, PR-AUC, top-10%, Brier, UCI AUC printed; leakage test passes |
| M6 | 20 Oct | Forecast + conformal + bottlenecks + Erlang-C staffing | WAPE vs naive, coverage printed; staffing moves listed |
| M7 | 21 Oct | Optimiser (scarcity, starvation guard) + OpsLens policy + weight choice on validation days | OpsLens vs A/B on test days, 5 seeds, paired CI printed |
| M8 | 22 Oct | `make eval`: ablations, sensitivity, stress, speed/scale, (challengers); `NUMBERS.md` | One command reproduces every number |
| — | 22 Oct | **Model + weight freeze** | No model changes after this |
| U1 | 18–22 Oct | *(parallel session)* UI shell on fixture results: layout, all tabs, charts, replay player, story-mode skeleton | Every tab renders from `fixture_results.json` with the FIXTURE banner |
| M9 | 23–24 Oct | Server + wire every tab to real results; click-to-evidence; Accept/Override log | Full flow works on generated data |
| M10 | 25 Oct | What-if panel, replay polish, brief (number keys), Upload CSV (UCI) | Demo flow works end to end |
| M11 | 26 Oct | Plant-a-problem live, `PRODUCTION.md`, README, speed, offline drill | `make demo` works with Wi-Fi off |
| M12 | 27 Oct | Rehearsal: `JUDGE_QA` complete, `DEMO_SCRIPT.md`, backup video | Owner answers every Q&A without notes |
| — | 28 Oct | Travel | No new features |

**Cut list if late** (cut from the top): challenger arena → live Plant-a-problem (keep the
blind-recall eval) → upload mapping UI (keep UCI preloaded) → Accept/Override → live hourly
detection (keep daily). **Never cut:** fair simulator, held-out eval, ablations,
click-to-evidence, offline demo.
