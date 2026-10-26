# OpsLens

A decision engine for customer-support operations. It finds why SLA deadlines are missed, predicts
which open tickets will miss theirs, decides who should take which ticket, and measures the result by
replaying held-out days in a simulator.

Deviathon 2.0 finale, problem DEV_103 (Eternal Ltd), team SoyaChaap.

## Result

On 14 held-out days with the same customers and the same agents, OpsLens missed 2.0% of deadlines and
industry-standard skills routing missed 5.5%. Difference −3.46 points, 95% interval −4.77 to −2.15.
OpsLens was lower on 14 of 14 days.

## What it does

| Problem statement | OpsLens | Measured |
|---|---|---|
| Identify patterns | Evidence cards for capacity, skill gaps, spikes, partner and process issues | 5 of 5 planted problems found; 3 of 3 real-data findings still hold on later months |
| Predict bottlenecks and breaches | 48-hour forecast with conformal bands; per-ticket breach risk with TreeSHAP reasons | Risk AUC 0.977; on the real UCI desk 0.857 vs 0.552 for its priority field |
| Recommend actions | Min-cost-flow assignment on rescue value, staffing moves, fixes at the source | All 18 recommendations together: −48.8 missed deadlines on the held-out days (95% interval −63.1 to −34.5) |
| Explain decisions | Top reasons per ticket, evidence per finding, runner-up agent per assignment | Removing a ticket's top reason lowers its risk more than a random feature in 98.9% of cases |
| Measure impact | Discrete-event simulator with common random numbers, 5 seeds, paired intervals | Sealed world generated after the freeze: 2.2% vs 5.8% |
| Public dataset | UCI ServiceNow incident log (CC BY 4.0, 24,918 incidents), or any uploaded CSV | Busiest real day: 53 of 102 real misses flagged in time, 16 by the priority field |
| Baseline vs proposed | FIFO, priority-first, SLA-due, skills routing, published scheduling rules, 30 random worlds | Beats skills routing in 29 of 30 worlds |

## Limits

- The food-delivery floor is simulated; no company publishes its support data. The real UCI desk is
  shown next to it on every screen.
- Under sustained overload a published rule (least slack first) misses fewer deadlines than OpsLens
  in 11 of 30 worlds.
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

Open http://localhost:8000/. The `.env` keys (Gemini, Groq free tiers) are optional; without them the
assistant falls back to keyword rules. `mingw32-make demo` serves cached results with no network.

## Try

1. Overview, Live now: today's weekday simulated at the real clock, skills routing next to OpsLens.
2. Ask OpsLens AI: "what if Team C loses 2 agents on Saturday?". The LLM only picks the tool; the
   engine computes every number.
3. Problems, Plant a problem: hide a problem in fresh data and watch it get found.
4. Actions, Accept, then Your plan, Simulate: the day replayed with and without the change.
5. Real data, Upload a CSV: any export of tickets, incidents or orders, or the UCI example.
6. Team: who is doing what right now. Click a person, or switch the top bar to Agent, to see
   their own screen: the next ticket OpsLens lines up for them, why, and Take it / Can't take it.

## Layout

- `opslens/` engine: ingest, classify, patterns, features, forecast, risk, optimize, staffing,
  policies, simulate, impact, realdesk, anyfile
- `eval/` experiments; `eval/results.json` is the source of every number, summarised in `eval/NUMBERS.md`
- `server/` FastAPI app and the assistant
- `web/` dashboard, plain HTML/JS/CSS, works offline
- `tests/` includes a check that every decimal number in this README exists in `eval/results.json`
- `data/SOURCES.md` datasets and licences
