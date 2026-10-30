# OpsLens v2

What changed after Round 1, why, and how every part works. The feedback was:

1. Run the LLM locally (Ollama) instead of calling the Gemini API.
2. Store the data in a proper database that can grow.
3. Separate the agent's screen from the admin's.
4. Make the screens much simpler, like Zendesk.
5. Build real agents on top of Postgres (and maybe Redis).

Added afterwards: RAG, so the AI answers from OpsLens's own data (section 6), and customer feedback,
entered by hand for now (section 7).

The principle we kept: **the optimiser and the risk model still decide who gets each ticket.** The LLM
agents read, write, explain and propose; they never replace the maths that produced the Round 1 result.

## What runs where

```
Browser ── /            sign-in page
         └─ /app/       the Round 1 dashboard: everything for the admin, only their own screen for an agent
                        (/admin/ and /agent/ from the earlier version redirect here)

FastAPI (server/app.py + server/v2.py + server/auth.py + server/feedback_api.py)
  ├─ live floor: the simulator runs today's weekday at the real clock      (opslens/live.py, unchanged)
  ├─ mirror thread: every 5 s writes what changed on the floor to Postgres  (opslens/mirror.py)
  ├─ agent worker thread: takes jobs from the queue, runs one agent at a time (opslens/agents.py)
  └─ /api/v2/*: tickets, summary, floor, actions, agents, proposals, feedback, stream

Postgres 16 ── tickets, users, sessions, teams, agent_profiles
            ├─ ticket_events, decisions, risk_scores   (partitioned by month)
            ├─ agent_runs, agent_steps, proposals       (every AI step)
            ├─ kb_articles, ticket_embeddings           (768-number vectors)
            ├─ rag_chunks                               (the RAG library, with meaning vectors)
            ├─ feedback                                 (customer reviews and admin notes)
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
- **Roles are checked on the server, not hidden in the browser:**
  - an **agent** sees their own tickets and their team's waiting queue, and can act only as themself;
  - an **admin** sees everything and decides: assignments, breaks, AI suggestions, the plan.
  Every `/api/v2` route checks the role, and a ticket outside your scope answers 404, not 403, so its
  existence is not revealed. The floor buttons (`/api/live/action`: take, decline, done, extra time,
  break, back) need a sign-in: an agent is refused (403) if they name anyone but themself, a stranger
  gets 401, and resetting the day is admin-only. This was found by trying it: the dashboard hid other
  agents but the endpoint behind it did not check, so one agent could send another on a break.
- **Signing in:** `admin` with password `123` for the admin. An **agent** chooses Agent, types their
  name (full, without the dot, first name only, or code such as `B01`), chooses their team and enters
  the password. Names are unique within a team, so this opens exactly one agent's dashboard; there is
  no list to pick from, and a right name with the wrong team or password gets nobody in. Each agent
  also has an email login (`a01@opslens.demo` …), seeded by `python -m opslens.seed`.
  The shared password `123` is for a laptop demo only: anyone who knows another agent's name and team
  could sign in as them. Give each agent their own password, or set `DEMO_PASSWORD`, before putting
  this anywhere shared.
- **The data behind the dashboard needs a sign-in too.** `/api/results` and `/api/live` answer 401
  without one. An agent asking `/api/live` gets only their own row, their own actions and decisions,
  no tickets at risk, and the other agents' statuses blanked; the admin gets everything. The tools
  (`/api/bot`, `/api/ask`, `/api/whatif`, `/api/plan/impact`, `/api/plant`, `/api/upload`,
  `/api/anyfile/*`, `/api/rag/status`, `/api/live/actions`, `/api/v2/feedback*`) are admin-only; an
  agent reads only their own feedback at `/api/v2/me/feedback`. Only the sign-in page, the
  page code and `/api/health` are open. A session check is cached for 5 seconds so the live screen's
  frequent refreshes stay cheap; signing out ends it at once. Without Postgres (the offline demo) the
  dashboard opens as before.

## 4. The screens

The screen is the Round 1 dashboard at `/app/`, in its own design. Version 2 adds sign-in in front of
it and splits who sees what:

- **Sign in** (`/`): username `admin` for the admin; an agent chooses Agent and gives their name, team
  and password (section 3).
- **Admin** gets the whole dashboard: Overview (live now), Team, Problems, Risks, Actions, Feedback,
  Proof, Your plan, Story mode and Ask OpsLens AI. "Agent view" shows any agent's screen, as before.
- **Agent** gets only their own screen: what is lined up next and why, what they are working on, Take
  it, Can't take it, Done, +5/+10/+20 min and On a break, their day and their feedback. No dropdown to
  be someone else, no admin tabs, no customer replies. Sign out is in the top bar.
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

## 6. RAG: the AI looks things up before it answers

**What RAG is.** Retrieval-Augmented Generation: the data is split into small pieces and each piece is
stored with its meaning (a list of numbers from an embedding model). When a question comes in, the few
pieces closest to it are found and given to the language model, which answers from them and says which
ones it used. The model reads our facts instead of guessing from memory.

**Where it is in OpsLens.**

- **Ask OpsLens AI** (sidebar, every admin page). A question goes, in order: a customer-style message
  to triage, a what-if to the engine, then RAG. The answer is written by the local model from the
  retrieved pieces, with [1] [2] citations you can click, a "Sources" list (type, title, how closely
  it matched, an excerpt, and an Open link to the right page), and a line saying whether every number
  in the answer was found in the sources. If RAG has nothing good, the prepared answers are used as
  before, and then the "did you mean" list.
- **Proof, AI with retrieval.** What is indexed, how often the right source is found, whether the
  answers are worded right, and whether retrieval helps read tickets.

**How it works** (`opslens/rag.py`, table `rag_chunks`, migration `008`):

1. **Pieces.** The 8 company policies, the 9 recurring problems (with their measured fix), the 18
   measured fixes and "all together", the sections of `eval/NUMBERS.md`, the README and these docs, the
   106 prepared answers, 320 past tickets (40 per category, training days only, masked), and every
   customer review with one summary of them all (section 7). The Proof page lists the current count.
   Fix effects are written in plain words ("131 fewer missed promises, likely between 88 and 174
   fewer") because the small model misreads minus signs and "95% range".
2. **Meaning.** Each piece is embedded with `nomic-embed-text` on the laptop GPU (about 14 ms a piece;
   the whole index builds in about 9 seconds) and stored in Postgres. With pgvector this becomes a
   vector index; without it, similarity is one matrix product in numpy.
3. **Search.** Meaning (65%) and exact words (35%, TF-IDF) together, because "Rs 300", "P1" or a
   ticket ID must match exactly. Past tickets and single reviews count 0.9; at most one past ticket and
   two reviews are shown, so rules and results come first. The feedback summary counts in full.
4. **Gate.** If nothing is close in meaning (below 0.58), or the model says the sources do not cover
   it, there is no RAG answer: off-topic questions such as "capital of France" get the fallback.
5. **Answer.** `qwen2.5:3b` gets the 5 pieces and a one-line glossary (missed means the promise time
   passed; lower is better) and must cite them. Every number it writes must appear in the pieces or
   the question; if not, it is asked once more.

6. **Wording check.** A number may only carry a comparison word (longer, fewer, more, higher…) that
   the sources give it. One answer said Hindi tickets wait "368 minutes longer"; the sources say
   "13.0 times longer", and 368 minutes is the whole wait. That answer is now caught and sent back
   once, and if it is still wrong the chatbot says what to check. Problem pieces also state the group
   and normal values in plain words ("for this group the mean wait is 368; for normal tickets it is
   28"), and the model is told to prefer measured sources over prepared answers when numbers differ.

Measured on 16 fact questions (`config/rag_faithful.yaml`, `python -m opslens.rag faith after`), each
with words the answer must contain: 14 of 16 before these checks, 15 of 16 in the first run after,
and 13 of 16 in the saved run, made after customer feedback was added and these docs were rewritten.
None of the saved answers contradicts its sources. The three it counts as wrong are right but
incomplete: two say Hindi refund tickets wait "13.0 times longer" without the 368 and 28 minutes,
and one says all fixes "save 574" instead of "574 fewer". Customer feedback was not among their
sources; these docs are, and their text changes from run to run. One real conflict was fixed on the
way: a prepared answer gave "3,810 fewer out of 5,864" without saying that compares with the
priority-first floor, and the model used it for "every fix at once"; it now says so and gives the 574.
With a 3-billion-parameter model and 16 questions, runs move a few answers either way; the code check
is what reliably stops a wrong number, and every answer still shows its sources.

Rebuild with `mingw32-make rag` after changing a policy, a result or the docs.

## 7. Customer feedback

**Entered by hand for now.** The food-delivery floor's customers are simulated, so they cannot write
feedback. The team wrote 44 customer reviews and 6 admin notes (`config/feedback.yaml`) to match the
patterns OpsLens found: Hindi refunds waiting too long, wrong items from one restaurant group, the
payment outage, the weekend dinner rush, phone transfers. Every screen labels a review "Customer ·
entered by hand". `python -m opslens.seed` loads them once (table `feedback`, migration `009`).

- **Admin, Feedback tab.** The customer rating (average, happy rated 4 or 5, unhappy rated 1 or 2,
  the spread of stars), what customers bring up by kind of complaint with the lowest-rated comment,
  the rating by team and by agent, and the latest feedback with filters. A form adds a customer's
  feedback (rating required) or the admin's own note to an agent (rating optional).
- **Admin notes are kept apart.** They show "From the admin" everywhere and never count in the
  customer rating, so the rating keeps meaning "how happy are customers".
- **Agents see their own.** The agent's screen shows "New feedback (n)" and a Your feedback card: their
  customer rating, the reviews and the admin's notes, newest first, with New on the unread ones and
  Mark as read. The server returns an agent only their own feedback; the full list, other agents'
  feedback and adding feedback are admin-only. When the admin opens an agent's screen they see the
  same card but cannot mark it read.
- **Private details are hidden** in a customer's text before it is saved, with the same masking as
  tickets.
- **Ask OpsLens AI can quote it.** Each review and a summary (rating overall, by kind of complaint and
  by team, computed in code) are RAG pieces with the label Customer feedback. Adding a review
  refreshes them in the background. Admin notes are coaching, not customer data, and stay out.

Adding the reviews to the library changes how much each word counts in search; the retrieval scores
in Measured were taken with them in.

## 8. What did not change

- The simulator, the optimiser, the risk model and every number in `eval/`.
- The classic dashboard at `/app/` with Proof, Replay and the real UCI desk.

## Run it

```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
mingw32-make seed
mingw32-make rag
mingw32-make serve
```

Postgres must be running with the `DATABASE_URL` from `.env.example`. `mingw32-make seed` also loads the
hand-written feedback, and `mingw32-make rag` adds it to the RAG library. Open http://localhost:8000/ and
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

### RAG: does it find the right source? (`mingw32-make rag-eval`)

26 test questions in `config/rag_eval.yaml`, written in different words from the sources, each with
the piece that should come back. Full output: [results/rag_retrieval.json](results/rag_retrieval.json).

| Search by | Right source first | Right source in the top 3 | Mean reciprocal rank |
|---|---|---|---|
| Meaning and words (used) | 81% | 96% | 0.88 |
| Meaning only | 81% | 92% | 0.87 |
| Words only | 50% | 65% | 0.62 |

Combining the two beats either alone. Before customer feedback was added it was 85%, 96% and 0.90
with meaning and words: the 45 feedback pieces change how much each word counts, and one question's
right source now comes second. These docs are part of the library, so they quote none of the test
questions; an earlier version quoted two, which helped one of them. The one question still missed in
the top 3 asks about leakage without using the word, and its prepared answer is written around it.

### RAG: does retrieval help read tickets? Yes (`mingw32-make eval-rag-blend`)

Where the routing classifier is less than 80% sure, its probabilities are blended with a
similarity-weighted vote of the 10 most similar past tickets (40% weight), from 16,000 tickets of the
training days (2,000 per category). No AI calls; it runs in about 6 minutes. The three settings were
chosen on the validation days out of 150 combinations, and the held-out test days were scored once.
Full output: [results/rag_blend.json](results/rag_blend.json).

| | Classifier alone | With similar past tickets |
|---|---|---|
| Validation days, 13,205 tickets (settings chosen here) | 98.24% | 98.51% |
| Test days, 26,728 tickets (scored once) | 98.20% | 98.55% |

On the test days it changed 1,171 unsure tickets, fixed 112 and broke 18: 94 more tickets reach the
right team, and the wrong-team count falls from about 482 to 388, roughly 20% fewer routing mistakes.
The vote alone, at the same settings, scores 97.99%; the gain comes from combining the two. The
simulated floor still routes with the categories frozen in Round 1, so its 8.79% is unchanged: this
is a measured improvement to reading tickets, not yet a re-run of the floor.

### RAG: what did not work, the AI reading tickets with examples (`mingw32-make eval-rag-classify`)

Before deciding a ticket's category, the AI is shown the 5 most similar past tickets with their
correct category, taken from 4,800 tickets of the training days only (600 per category). Same
held-out tickets as the earlier test. It took about 2 hours on the laptop, one AI call per ticket.
Full output: [results/rag_classification.json](results/rag_classification.json).

| On the 360 tickets the classifier is least sure of | Routing accuracy | Fixed | Broke |
|---|---|---|---|
| Classifier alone (what OpsLens uses) | 98.20% | | |
| The AI alone (measured before) | 97.51% | 12 | 196 |
| The AI shown 5 retrieved examples | 97.99% | 45 | 101 |
| A vote of the 5 nearest past tickets, no AI | 98.26% | 68 | 51 |

On a random 400 test tickets the AI with examples scored 90.31% (382 answered; the rest made the
small model loop), against 90.75% alone and 80.00% for the plain vote.

What this means: retrieval halves the damage the AI does when it may correct the classifier, but the
AI still does worse than the classifier alone. That is what led to the blend above: keep the
classifier, and let similar past tickets move it only where it is unsure.

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
