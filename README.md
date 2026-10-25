# OpsLens — the decision engine for support operations

**Every ticket is a promise.** A support floor gets about a thousand complaints a day, and every one
has a deadline. Helpdesk tools tell you a ticket is late. OpsLens tells you **why deadlines are
missed, which customers will miss theirs next, and what to do about it** — and every
recommendation comes with its own proof: replayed on days OpsLens never saw, with a 95% interval.

Deviathon 2.0 finale · problem DEV_103 (Eternal Ltd) · team SoyaChaap.

**Headline.** On 14 held-out days, the same customers and the same agents: OpsLens missed
**2.0%** of deadlines; the industry-standard way of routing missed **5.5%** (difference −3.46
points, 95% interval −4.77 to −2.15). OpsLens was lower on **14 of 14** days.

---

## The problem statement, answered line by line

| DEV_103 asks | What OpsLens does | The proof (from `eval/results.json`) | Where to see it |
|---|---|---|---|
| **Identify patterns** in historical data | Finds recurring problems (capacity, skill gaps, spikes, partner issues, process issues), each as an evidence card with example tickets | Found 5 of 5 planted problems; on a real company's log, 3 of 3 findings still hold on later months | Problems |
| **Predict bottlenecks**, delays, SLA breaches | A 48-hour forecast with an 80% band against capacity; every waiting ticket's chance of missing its deadline, with reasons | Risk AUC 0.977 (logistic regression 0.957); on real data 0.857 vs 0.552 for the desk's own priority field | Risks |
| **Recommend actions** by urgency, capacity, business impact | Who takes which ticket now (an optimiser over rescue value), fixes at the source, staffing changes; accept or override into *Your plan* | All 18 recommendations together: −48.8 missed deadlines over the held-out days (95% interval −63.1 to −34.5) | Actions, Your plan |
| **Explain its decisions** | Top reasons per ticket (TreeSHAP), evidence per finding, the runner-up agent for every assignment; every number clicks through to its source | Removing a ticket's top reason drops its risk more than a random feature in 98.9% of cases | Risks, any number |
| **Measure impact** on turnaround, productivity, service quality | A simulator replays the same day under each way of working: same customers, same luck | 2.0% vs 5.5% missed; lower on 14 of 14 days; sealed world made after the freeze: 2.2% vs 5.8% | Overview → Results, Proof |
| *Example:* "1,000 tickets a day… predict which are at risk… a dashboard of expected impact" | *Your plan*: accept a recommendation, simulate the day with and without it | Cross-training two Hindi-speaking agents alone: −26.8 missed deadlines | Actions → Your plan → Simulate |
| *Tech:* AI/ML forecasting + anomaly detection | LightGBM forecast with conformal bands; robust-z anomaly scan with a known-event calendar | Overload alerts on real data: precision 77.6%, recall 92.8% | Risks → Next 48 hours |
| *Tech:* NLP or LLMs to classify and summarise | Local classifier, LLM only for unsure tickets; the LLM writes words, never digits | Real public benchmark (BANKING77): 90.3% local, 91.0% with the LLM; with 10 examples per intent 68.5% → 78.7% | Proof → How we tested |
| *Tech:* optimisation for allocation | Min-cost flow over rescue value; exact CP-SAT roster tried | Honest: greedy ties min-cost flow at our scale, and CP-SAT did not beat the greedy roster — both shown | Proof → Rules |
| *Tech:* dashboard incl. **performance tracking** | Day-by-day tracking, a live floor simulated on this laptop, the ledger of every rule | Lower than the industry standard on 14 of 14 days | Overview → Live now |
| **Deliverable 1:** a public dataset | A real company's IT service desk (UCI ServiceNow log, CC BY 4.0, 24,918 incidents) on every screen | Shadow mode on the busiest real day: OpsLens flagged 53 of 102 real misses in time, the desk's priority field 16 | IT service desk → Shadow mode |
| **Deliverable 4:** baseline vs proposed, measurable | First come, urgent first, SLA due, the industry standard, published scheduling rules; 30 random worlds | Beats the industry standard in 29 of 30 worlds we did not design | Proof → Beyond our world |

## What we do NOT claim (we show these on screen)
- The food-delivery floor is **simulated** (no company publishes its support data). That is why the
  real public service desk is on every screen.
- In **sustained overload** (1.06× today's load or more for weeks), a published rule (least slack
  first) misses fewer deadlines than OpsLens in 11 worlds; OpsLens keeps gold customers and late
  customers better protected there. Pre-registered rule: lowest in 27 of 30 worlds — we got 19.
- On the real desk, a one-line rule ("fast-track what is still unassigned after 1 hour") ties
  OpsLens on the fast-track outcome: 115 vs 108 missed deadlines saved; the desk's own priority
  field saves 29.
- A digital twin of the real desk failed its own validation gate, so no twin result is shown.

Every one of these is a rule we **wrote down before the run** and kept on the *Rules we wrote first*
screen, kept or missed.

## Try it in five minutes
1. **Overview → Live now** — today's weekday, simulated on this laptop at your real clock: the
   industry standard and OpsLens side by side, the customers in danger right now, and why.
2. **Ask OpsLens** (top bar) — "what if Team C loses 2 agents on Saturday?", "kal raat refund wale
   kitne late honge?", "which customers will miss their deadline?". The LLM only chooses the tool;
   the engine computes every number.
3. **Problems → Plant a problem** — hide a problem in fresh data and watch OpsLens find it.
4. **Actions → Accept** a fix → **Your plan → Simulate** — the day replayed with and without it.
5. **IT service desk → Shadow mode** — a real day, OpsLens's warnings next to the desk's own.
6. **Proof → Rules we wrote first** — every rule, the date it was sealed, kept or missed.

## Run it (Windows)

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
copy .env.example .env        # optional free Gemini / Groq keys; without them Ask uses keyword rules
mingw32-make data             # the public datasets (Bitext, UCI)
mingw32-make gen              # generate the 56-day support floor
mingw32-make test             # all tests
mingw32-make eval             # reproduce every number: eval/results.json + docs/NUMBERS.md
mingw32-make demo             # the dashboard from cached results, no network: http://localhost:8000/
```

## How it works (four parts)
1. **Reads** each complaint and decides what it is about (local classifier, Hinglish too; LLM only when unsure).
2. **Finds patterns** in the history and **predicts**: the next 48 hours per team, and each waiting
   ticket's chance of missing its deadline, with reasons.
3. **Decides**: every few minutes, who takes which ticket, valuing the *rescue* (how much serving a
   ticket now lowers its risk), urgency and business impact; plus fixes at the source and staffing.
4. **Proves**: a discrete-event simulator replays held-out days under every policy with the same
   customers and the same luck (common random numbers); 95% intervals over seeds.

## Where things are
- `opslens/` — the engine, one explain file per module in `docs/explain/` (plain words, a worked example each).
- `eval/` — every experiment; `eval/results.json` is the only source of every number on screen and here.
- `server/` + `web/` — FastAPI and a plain HTML/JS dashboard that works offline.
- `docs/NUMBERS.md` — every number · `docs/JUDGE_QA.md` — hard questions · `docs/PRODUCTION.md` — the
  path to a real floor · `docs/PLAN_V4.md` — every pre-registered rule · `PROGRESS.md` — the log.
- `tests/` — `tests/test_doc_numbers.py` checks every decimal number in this README, the demo script
  and the Q&A against the current results (and says how often a made-up number would slip through).
