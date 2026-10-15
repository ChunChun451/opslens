# OpsLens

**The decision engine for support operations.** Existing helpdesk tools tell you a ticket is
late. OpsLens tells you which tickets *will* be late, why, and what to do about it — and
proves the plan works on days it has never seen.

Deviathon 2.0 · problem DEV_103 (Eternal Ltd) · team SoyaChaap.
Plan: [CLAUDE.md](CLAUDE.md) · reasons and research: [docs/PLAN.md](docs/PLAN.md) ·
progress log: [PROGRESS.md](PROGRESS.md) · every number: [docs/NUMBERS.md](docs/NUMBERS.md) ·
production path: [docs/PRODUCTION.md](docs/PRODUCTION.md) · judge Q&A: [docs/JUDGE_QA.md](docs/JUDGE_QA.md).

## What it does
1. **Finds recurring problems with evidence** — capacity, skill gaps, spikes, partner issues,
   process issues — each as an evidence card with numbers and example tickets.
2. **Predicts** the next 48 hours of work per team (with honest ranges) and every waiting
   ticket's chance of missing its SLA, with reasons.
3. **Recommends** who takes which ticket now (an optimiser) and budget-neutral shift changes.
4. **Proves it** by replaying 14 held-out days in a fair simulator against two baselines
   (first-in-first-out and priority-first), same tickets and same luck for every policy.

## Quick start (Windows)

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
copy .env.example .env        # paste your free Gemini and Groq keys (optional: LLM answers are cached)
mingw32-make data             # download the public datasets (Bitext, UCI)
mingw32-make gen              # generate the 56-day support floor (~1 min)
mingw32-make test             # all tests
mingw32-make eval             # reproduce every number: eval/results.json + docs/NUMBERS.md (~20 min)
mingw32-make serve            # dashboard at http://localhost:8000/
```

## Layout
- `opslens/` — the engine (privacy, ingest, classify, patterns, features, risk, forecast,
  staffing, optimize, policies, simulate, whatif, impact, brief). One explain file per module
  in `docs/explain/`.
- `data/` — data generator, text bank, planted problems (`planted.json` is read only by `eval/`).
- `eval/` — every experiment; `results.json` is the single source of every number shown.
- `server/` — FastAPI server; `web/` — the dashboard (plain HTML/JS, works offline).

## Data
See [data/SOURCES.md](data/SOURCES.md). The operations layer (timestamps, agents, SLAs) is
generated, and we say so openly; the risk model and pattern finder are also checked on a real
ServiceNow incident log from the UCI repository.
