# OpsLens

**The decision engine for support operations.** Existing helpdesk tools tell you a ticket is
late. OpsLens tells you which tickets *will* be late, why, and what to do about it — and
proves the plan works on days it has never seen.

Deviathon 2.0 · problem DEV_103 (Eternal Ltd) · team SoyaChaap.
The full plan is in [CLAUDE.md](CLAUDE.md); the reasons behind it are in [docs/PLAN.md](docs/PLAN.md);
progress is logged in [PROGRESS.md](PROGRESS.md).

## Quick start (Windows)

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
copy .env.example .env        # then paste your free Gemini and Groq keys
mingw32-make data             # download public datasets (Bitext, UCI)
mingw32-make ping             # check both LLM providers answer
mingw32-make test             # run all tests
```

## Status

Built so far: privacy masking, LLM layer (Gemini + Groq + mock, cache, rate limits),
dataset download. See [PROGRESS.md](PROGRESS.md) for numbers and next steps.

## Data

See [data/SOURCES.md](data/SOURCES.md). The operations layer (timestamps, agents, SLAs) is
generated, and we say so openly; the risk model is also checked on a real ServiceNow incident
log from the UCI repository.
