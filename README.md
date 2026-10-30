# OpsLens

A decision engine for customer-support operations. It finds why SLA deadlines are missed, predicts
which open tickets will miss theirs, decides who should take which ticket, and measures the result by
replaying held-out days in a simulator.

Deviathon 2.0 finale, problem DEV_103 (Eternal Ltd), team SoyaChaap.

## Result

Food-delivery promises: a live order (P1) in 15 minutes, P2 in 30, P3 in 60. On 14 held-out days with
the same customers and the same agents, OpsLens missed 8.79% of promises and industry-standard skills
routing missed 20.74%. Difference −11.95 points, 95% interval −14.88 to −9.02; live orders 8.08% vs
13.16%. OpsLens was lower on 14 of 14 days. The best published rule we found, least slack first with
cross-skill rescue, missed 9.76%.

## What it does

| Problem statement | OpsLens | Measured |
|---|---|---|
| Identify patterns | Evidence cards for capacity, skill gaps, spikes, partner and process issues | 4 of 5 planted problems found, 52 of 60 in a blind test; 3 of 3 real-data findings still hold on later months |
| Predict bottlenecks and breaches | 48-hour forecast with conformal bands; per-ticket breach risk with TreeSHAP reasons; a clock that counts each ticket's slack against its work time and the queue in front of it | Risk AUC 0.973; on the real UCI desk 0.857 vs 0.552 for its priority field |
| Recommend actions | Min-cost-flow assignment on rescue value, staffing moves, fixes at the source | All 18 recommendations together: −574.0 missed promises on the held-out days (95% interval −643.3 to −504.7) |
| Explain decisions | Top reasons per ticket, evidence per finding, runner-up agent per assignment | Removing a ticket's top reason lowers its risk more than a random feature in 99.2% of cases |
| Measure impact | Discrete-event simulator with common random numbers, 5 seeds, paired intervals | Sealed world generated after the freeze: 8.16% vs 18.73% |
| Public dataset | UCI ServiceNow incident log (CC BY 4.0, 24,918 incidents), or any uploaded CSV | Busiest real day: 53 of 102 real misses flagged in time, 16 by the priority field |
| Baseline vs proposed | FIFO, priority-first, SLA-due, skills routing, published scheduling rules (least slack, with rescue, clairvoyant) | Beats least slack + rescue by −0.98 points (95% interval −1.28 to −0.67) |

## Limits

- The food-delivery floor is simulated; no company publishes its support data. The real UCI desk is
  shown next to it on every screen.
- The 30 random worlds were run on the earlier floor (1 h / 4 h / 24 h promises); they are not yet
  re-run on 15/30/60. There, under sustained overload, least slack first missed fewer deadlines in 11 of 30.
- Without the staffing plan, OpsLens's routing alone ties least slack + rescue overall (9.83% vs 9.76%);
  it still misses fewer live orders (8.37% vs 11.03%).
- Cross-skill rescues raise reopens from 4.00% to 4.73%.
- On the real desk, "fast-track what is still unassigned after 1 hour" saves 115 missed deadlines;
  OpsLens saves 108.
- A digital twin of the real desk failed its validation gate, so no twin result is used.

Each rule above was written down before its run; the dashboard lists them under Proof, Rules we
wrote first.

## Run

Windows, Python 3.12:

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
copy .env.example .env
mingw32-make data
mingw32-make gen
mingw32-make test
mingw32-make eval
mingw32-make serve
```

Open `http://localhost:8000/` and sign in as `admin` or `agent` (password `123`). Sign-in needs Postgres
(see below); without it, `http://localhost:8000/app/` opens the dashboard directly. The assistant uses
the local Ollama model, with the `.env` keys (Gemini, Groq free tiers) as an optional fallback.
`mingw32-make demo` serves cached results with no network.

## Try

1. Overview, Live now: today's weekday simulated at the real clock, skills routing next to OpsLens.
2. Ask OpsLens AI: "what if Team C loses 2 agents on Saturday?". The LLM only picks the tool; the
   engine computes every number.
3. Problems, Plant a problem: hide a problem in fresh data and watch it get found.
4. Actions, Accept, then Your plan, Simulate: the day replayed with and without the change.
5. Real data, Upload a CSV: any export of tickets, incidents or orders, or the UCI example.
6. Team: who is doing what right now. Click a person, or switch the top bar to Agent, to see
   their own screen: the next ticket OpsLens lines up for them, why, and Take it / Can't take it.
7. Feedback: what customers say by team, agent and kind of complaint. Add a review or a note to an
   agent, then sign in as that agent to see it arrive under New feedback.

## Version 2

After Round 1:

- **Sign-in with two roles.** `admin` sees the whole dashboard. An agent signs in with their name, team
  and password and sees only their own work; the server checks this on every request.
- **Postgres** holds tickets, history, the AI's steps and the job queue, tested with a million tickets.
- **A local model through Ollama** (qwen2.5:3b) runs four AI agents; nothing leaves the laptop.
- **Problems show each fix's measured effect**, with Accept or Override feeding Your plan.
- **RAG.** Ask OpsLens AI answers from OpsLens's own policies, results, docs, past tickets and customer
  feedback, with sources and a check that every number and comparison is in them. Similar past
  tickets also help read tickets: 94 more reach the right team on the held-out days.
- **Customer feedback**, entered by hand for now because the floor's customers are simulated. The
  admin sees ratings by team, agent and kind of complaint and can add feedback or their own marked
  note; each agent sees their own with a New badge.

The optimiser still decides who gets each ticket, so the Round 1 result above is unchanged. Everything
about version 2, with its measurements, is in [docs/v2/README.md](docs/v2/README.md).

## Layout

- `opslens/` engine: ingest, classify, patterns, features, forecast, risk, optimize, staffing,
  policies, simulate, impact, realdesk, anyfile
- `eval/` experiments; `eval/results.json` is the source of every number, summarised in `eval/NUMBERS.md`
- `server/` FastAPI app and the assistant
- `web/` dashboard, plain HTML/JS/CSS, works offline
- `desk/` the v2 sign-in page, agent workspace and console
- `db/migrations/` the Postgres schema; `opslens/agents.py` the AI agents; `opslens/rag.py` retrieval
- `opslens/feedback.py` and `config/feedback.yaml` customer feedback, entered by hand
- `tests/` includes a check that every decimal number in this README exists in `eval/results.json`
- `data/SOURCES.md` datasets and licences

