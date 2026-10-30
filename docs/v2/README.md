# OpsLens v2

What changed after Round 1, why, and how every part works. The feedback was:

1. Run the LLM locally (Ollama) instead of calling the Gemini API.
2. Store the data in a proper database that can grow.
3. Separate the agent's screen from the admin's.
4. Make the screens much simpler, like Zendesk.
5. Build real agents on top of Postgres (and maybe Redis).

The principle we kept: **the optimiser and the risk model still decide who gets each ticket.** The LLM
agents read, write, explain and propose; they never replace the maths that produced the Round 1 result.

## What runs where

```
Browser ── /            sign-in page
         ├─ /agent/     agent workspace  (role: agent)
         ├─ /admin/     console          (role: admin)
         └─ /app/       classic analysis dashboard, unchanged

FastAPI (server/app.py + server/v2.py + server/auth.py)
  ├─ live floor: the simulator runs today's weekday at the real clock      (opslens/live.py, unchanged)
  ├─ mirror thread: every 5 s writes what changed on the floor to Postgres  (opslens/mirror.py)
  ├─ agent worker thread: takes jobs from the queue, runs one agent at a time (opslens/agents.py)
  └─ /api/v2/*: tickets, summary, floor, actions, agents, proposals, stream

Postgres 16 ── tickets, users, sessions, teams, agent_profiles
            ├─ ticket_events, decisions, risk_scores   (partitioned by month)
            ├─ agent_runs, agent_steps, proposals       (every AI step)
            ├─ kb_articles, ticket_embeddings           (768-number vectors)
            ├─ job_queue                                (FOR UPDATE SKIP LOCKED)
            └─ team_hourly                              (materialised view, refreshed every 60 s)

Ollama (127.0.0.1:11434) ── qwen2.5:3b for text, nomic-embed-text for search vectors
Redis (optional) ──────────── used for the bus when REDIS_URL answers; otherwise Postgres does it
```

## 1. The LLM runs on the laptop

- `config/providers.yaml`: `main: ollama`. Ollama exposes an OpenAI-compatible API, so the existing
  client (`opslens/llm/client.py`) talks to it unchanged: same PII masking, same cache, same JSON
  retry. Gemini stays as a fallback and is never needed.
- Model: `qwen2.5:3b` (1.9 GB). It fits fully in the 4 GB RTX 3050 and writes about 107 tokens a
  second. Output is capped at 600 tokens so a confused reply cannot run for minutes.
- Embeddings: `nomic-embed-text` (274 MB). Used to find the right policy for a ticket and similar
  solved tickets.
- Nothing leaves the machine. Customer text is masked before it reaches even the local model.

Results on the recorded classification test are in [Measured](#measured).

## 2. The database

**Why Postgres.** One database holds the transactional data (tickets, users), the history (events,
decisions, risk), the AI audit trail and the job queue. It is what a support desk would actually run.

**How it scales** (`db/migrations/001_init.sql`):

- **Partitioning by month.** `ticket_events`, `decisions` and `risk_scores` grow fastest (several rows
  per ticket). Each is split into one table per month (`ticket_events_2026_10` …). A query for last
  week only reads the last partition, and old months can be detached or archived in one statement
  instead of a huge delete. `store.ensure_partitions` creates the next months ahead of time.
- **A partial index for the hot path.** Agents only ever look at unsolved tickets, so
  `tickets_open_by_team` indexes `(team, sla_due_at) where status <> 'solved'`. It stays small however
  many solved tickets pile up.
- **Range filters, not casts.** "Today" is written `created_at >= current_date and created_at <
  current_date + 1` so Postgres can use the `created_at` index. The load test caught this.
- **A materialised view for charts.** `team_hourly` pre-counts tickets and misses per team per hour.
  It is refreshed `concurrently` every 60 s, so readers are never blocked.
- **A short cache.** The console summary is cached for 3 s (Redis if present, otherwise in memory),
  so 50 people refreshing the console cost one query.
- **Only changes are written.** The mirror keeps a fingerprint of every ticket and writes only rows
  whose status, owner, breach or risk changed; events and decisions are write-once.

**Redis or not.** `opslens/bus.py` uses Redis when `REDIS_URL` answers. Otherwise it does the same
three jobs in Postgres: pub/sub with `LISTEN/NOTIFY` (pushes floor changes to every screen over SSE),
a job queue with `FOR UPDATE SKIP LOCKED` (many workers can pull jobs without taking the same one),
and a TTL cache. Docker needs WSL on this laptop, so the demo runs Postgres natively; `docker-compose.yml`
starts Postgres with pgvector and Redis for a server. With pgvector, migration `002` turns the
embedding columns into `vector(768)` with HNSW indexes; without it they are `real[]` and similarity is
computed in numpy.

## 3. Separate screens and roles

- **Sign-in** (`server/auth.py`): passwords are hashed with Argon2. A session is a random 32-byte token
  in an httpOnly, SameSite cookie; only its SHA-256 is stored, so a database leak does not leak
  sessions. Five wrong passwords in a minute and that email waits. A wrong email and a wrong password
  get the same answer and take the same time, so nobody can probe which emails exist.
- **Roles are checked on the server for every request**, not hidden in the browser:
  - an **agent** sees their own tickets and their team's waiting queue, and can act only as themself;
  - an **admin** sees everything and decides: assignments, breaks, AI suggestions, the plan.
  Anything outside your scope answers 404, not 403, so its existence is not revealed.
- **Signing in for the demo:** username `admin` or `agent`, password `123` (`DEMO_PASSWORD` in
  `.env.example`). `agent` then lists the agents on shift right now, working ones first, and you pick
  who you are; the session belongs to that agent. "Switch agent" in the profile menu goes back to the
  list. Each agent also has their own login (`a01@opslens.demo` …), seeded by `python -m opslens.seed`.
  The password is for a laptop demo only; set `DEMO_PASSWORD` before putting this anywhere shared.

## 4. The screens

The screen is the Round 1 dashboard at `/app/`, in its own design. Version 2 adds sign-in in front of
it and splits who sees what:

- **Sign in** (`/`): username `admin` or `agent`, password `123`. As agent you then pick who you are
  from the agents on shift right now, working ones first, each with the ticket they are on.
- **Admin** gets the whole dashboard: Overview (live now), Team, Problems, Risks, Actions, Proof, Your
  plan, Story mode and Ask OpsLens AI. "Agent view" shows any agent's screen, as before.
- **Agent** gets only their own screen: what is lined up next and why, what they are working on, Take
  it, Can't take it, Done, +5/+10/+20 min and On a break, and their day. No dropdown to be someone
  else, no admin tabs, no customer replies. Switch agent and Sign out are in the top bar.
- **Recurring problems** now show the measured fix on each card: what to do, how many missed promises
  it saved over the 14 held-out days with its 95% range, and Accept or Override, which feed Your plan.
  Your plan replays a held-out day with and without the accepted fixes.
- Less on screen: the results date chip and the sidebar footer are gone; agents see only their work.

`/admin` and `/agent` from the earlier version redirect here. The APIs built for them
(`/api/v2/problems`, `/plan/simulate`, `/analysis`, assigning, breaks, notes, the policy guide and the
AI agents) are still there and tested.

Screens update by themselves: the server pushes a message over SSE whenever the floor changes, with a
15-second poll as a fallback.

## 5. The agents

All four use the same small runtime in `opslens/agents.py`:

- **A tool loop.** The model replies with one JSON object: either `{"tool": ..., "args": ...}` or
  `{"answer": ...}`. The code checks the tool is on that agent's list, drops unknown arguments, refuses
  a call with missing arguments or one it already made, and stops after a fixed number of steps.
- **Read-only tools with fixed SQL.** The model never writes SQL.
- **Every step is recorded** in `agent_runs` and `agent_steps` and can be opened on the AI page.
- **Code works out facts; the model words them.** A 3-billion-parameter model is unreliable at
  comparing numbers, adding up and reading raw JSON. So code turns the data into plain sentences,
  computes limits, totals and "busiest" or "most", and lists the actions that are actually possible.
  The model chooses, explains and writes.
- **People decide.** Nothing an agent proposes changes the floor until the admin approves it.

| Agent | When | What it does | Guardrail |
|---|---|---|---|
| Intake | every new ticket, in the background | reads the message; stores its search vector; writes category, urgency and a 12-word summary | if its category differs from the router's, the ticket page says so; it never re-routes on its own |
| Reply copilot | API only (`POST /api/v2/copilot`); the screens no longer offer it, because OpsLens does not message customers | reads the ticket, finds the two closest policies by meaning, drafts a reply, then checks every claim against the policy and removes unsupported ones | order-value limits are computed in code and given to it as a fact; it never sends anything |
| Floor analyst | every 15 minutes, or Check the floor now | reads today's numbers, tickets at risk, who is free; code lists the actions that are possible (a free agent with the right skill and language, or a ticket nobody can take); the model picks the urgent ones and says why | it can only pick from the checked list; a reassignment is checked again at approval and then goes through the optimiser's own take path; stale suggestions expire |
| Ask OpsLens | the admin types a question | answers from the live numbers, written as plain facts | every number in the answer must appear in the facts; if not, it is asked again, and the screen says whether every number was found |

## 6. What did not change

- The simulator, the optimiser, the risk model and every number in `eval/`.
- The classic dashboard at `/app/` with Proof, Replay and the real UCI desk.

## Run it

```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
mingw32-make seed
mingw32-make serve
```

Postgres must be running with the `DATABASE_URL` from `.env.example`. Open http://localhost:8000/ and
sign in with a demo account. `OPSLENS_MIRROR=0` and `OPSLENS_AGENTS=0` turn the background threads off.

## Measured

All on this laptop (i5-10500H, 16 GB RAM, RTX 3050 4 GB, Postgres 16 with default settings).

### Scale: a million tickets (`mingw32-make load`)

`scripts/load_test.py` creates a separate `opslens_load` database, loads 30 days of synthetic history
and times the queries the screens actually run, then puts 40 signed-in users on the real API at once.
Full output: [results/load_test.json](results/load_test.json).

| What | Size or time |
|---|---|
| Rows loaded | 1,000,000 tickets, 2,998,142 events, 999,544 decisions (813 MB) in 81 s, 61,646 rows a second |
| Team queue (agent's view) | 3.65 ms median, 3.86 ms p95 |
| An agent's own open tickets | 3.03 ms median |
| Today's numbers for the console | 9.99 ms median |
| One ticket with its whole history | 0.31 ms median |
| 30-day missed rate per team per day, raw | 650.61 ms median (reads every ticket) |
| The same from the `team_daily` view | 0.38 ms median; the view refreshes in 0.87 s every 10 minutes |
| Last week's events (replay) | 392.12 ms median, reading one or two monthly partitions |
| API, 40 users with no pause between requests | 199.2 requests a second, 0 errors, 196.1 ms median, 252.0 ms p95, 308.6 ms p99 |

The hot paths stay in single-digit milliseconds at a million tickets because of the partial index on
unsolved tickets and the range filter on `created_at`. The raw 30-day query was the one slow screen
query, which is why `team_daily` exists. The API figure is one Python process; the latency is the
process queueing 40 constant callers, not the database (the same test on 20,000 tickets gave 269
requests a second). More uvicorn workers or more servers behind a load balancer scale it out, since all
state is in Postgres.

### The local model against the cloud model (`mingw32-make eval-local`)

`scripts/eval_local_llm.py` repeats the recorded classification test with `qwen2.5:3b` on Ollama
instead of Gemini, on exactly the same tickets, and writes
[results/local_llm_classification.json](results/local_llm_classification.json). It does not touch
`eval/`.

| | Cloud (recorded) | Local qwen2.5:3b |
|---|---|---|
| The LLM alone, 400 random test tickets | 91.5% | 90.75% |
| Routing when the LLM may override the local classifier on its 360 least sure tickets | 98.22% | 97.51% |
| Local classifier alone | 98.20% | 98.20% |
| Time per ticket | | 0.35 s, on the laptop GPU |

On its own the local model is almost as good as the cloud one. But on the hardest 1.35% of tickets,
the ones the local classifier is least sure of, the 3B model fixed 12 and broke 196 (the cloud model
fixed 60 and broke 55). So in v2 the local LLM never overrides the router. The intake agent only
flags a disagreement on the ticket page for a person to look at. The simulated floor still uses the
categories recorded in Round 1 (the local classifier plus the cloud model's answers on that 1.35%), so
every Round 1 number stands; for new tickets the honest choice is the local classifier alone, at 98.20%.
23 of the 360 got no usable reply and kept the local answer.

### The agents, tried on today's floor

| Agent | Typical time | Seen working | Seen failing, and what we changed |
|---|---|---|---|
| Intake | 1.5 to 2 s a ticket | fills category, urgency and summary for every new ticket | dropped the summary and called English Hindi; fixed by a worked example in the prompt |
| Reply copilot | 6 to 12 s | picks the right policy; applies the Rs 300 photo rule correctly | said "Rs 473 is below Rs 300" and invented limits; fixed by computing the limit in code; some drafts still need editing |
| Floor analyst | 2 to 4 s | "6 of 115 missed; 2 waiting, both overdue; nobody free handles payment_failure in Hindi" | called an overdue floor calm when given raw JSON; fixed by plain-sentence facts and a checked action list |
| Ask OpsLens | 2 to 3 s | "Team B has missed the most promises today with 3" | answered 17 from the wrong table; fixed by facts in sentences, precomputed "most" and "busiest", and the number check |

A bigger local model (`qwen2.5:7b`, 4.7 GB) would write better drafts but does not fit the 4 GB GPU,
so it would run partly on the CPU at a fraction of the speed. The model is one line in
`config/providers.yaml`.
