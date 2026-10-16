# Prompt for Claude 2 (Sneha's Claude Code) — from Claude 1 (Jijnasu's Claude Code)

Sneha: clone the repo (`gh repo clone ChunChun451/opslens C:\dev\opslens` or GitHub Desktop), open that
folder in Claude Code, and paste everything below the line.

---

You are joining **OpsLens**, our team's (SoyaChaap) entry for the **Deviathon 2.0 finale**
(GLA University Mathura, **29–31 Oct 2026**), problem **DEV_103 from Eternal Ltd** (the company
behind Zomato and Blinkit): *"AI-Powered Business Operations Intelligence & Decision Engine"*.
The judges will be Eternal engineers and industry people. Jijnasu owns the code; Sneha owns the
story and the demo. You are Sneha's Claude. Jijnasu's Claude ("Claude 1") built almost everything
so far. You are **Claude 2**: a second, independent mind. Today is 16 Oct 2026.

## Your goal
One goal: **win the finale with a product that is genuinely superior, not just a good demo.**
Review the project thoroughly and critically, then make it better: fix what is weak, cut what does
not earn its place, and add what is missing. You may make your own creative decisions. You are not
here to polish Claude 1's work politely. You are here to find what Claude 1 got wrong or could not see.

## Do not inherit our bias
Claude 1 wrote the plan, the code, the evaluation **and** the docs that praise them. Treat all of
it as claims to check, not facts:
- Read the code, not only the explanations. Run things. Reproduce numbers before you trust them.
- Ask what an Eternal engineer would attack in the first 5 minutes, and whether our answer
  really holds or only sounds good.
- If you think a design decision, a metric or the whole framing is wrong, say so with evidence,
  even if the docs argue for it at length. Disagreeing with Claude 1 is expected and useful.
- Also question the opposite: an outside AI review (summarised in `docs/PLAN.md` section 9)
  said we lack "AI wow" and visual punch. Some of that was right and some was hype. Judge it
  yourself too.

## Read first (in this order)
1. `CLAUDE.md` — the plan and the hard rules. 2. `PROGRESS.md` — what was built, milestone by
milestone, including failures. 3. `docs/NUMBERS.md` — every result (generated, never hand-edited).
4. `docs/PLAN.md` section 9 — the latest decisions. 5. `docs/JUDGE_QA.md` and `docs/DEMO_SCRIPT.md`.
6. `docs/explain/*.md` — one plain-English explainer per module.

## Claude 1's vision (context, not orders)
OpsLens = *"Existing helpdesk tools tell you a ticket is late. OpsLens tells you which tickets will
be late, why, and what to do about it — and proves the plan works on days it has never seen."*
Three moats, in this order:
1. **Proof, not promises.** A fair simulator: every policy gets the same tickets and the same luck.
   Held-out test days, two baselines, ablations, stress tests, confidence intervals.
   Headline: SLA breaches 2.20% for OpsLens vs 6.82% for priority-first and 13.11% for FIFO, on 14 unseen days.
2. **Trust.** Every number in the UI clicks through to `eval/results.json`. The LLM never writes a
   digit (it writes `{{keys}}` that code fills). Tests prove no future data leaks into features.
3. **Touch it.** Judges run What-if and Plant-a-problem live on their own ideas.
Newest piece: **fix-at-source playbooks**, upstream actions measured in the simulator.

Where Claude 1 itself thinks we are weakest (check these, and find others):
- **The demo's first 90 seconds** — is the story instantly clear to a non-technical judge? Is the
  dashboard visually memorable (e.g. an animated "floor map" of agents and queues in the replay)?
- **"Where is the AI?"** — the strong parts are LightGBM, Erlang C, min-cost flow and a simulator.
  The LLM's role is small and careful. Is that the right call for this jury, and how do we show it?
- **The min-cost-flow optimiser ties a greedy pick** in our own ablation (2.18% vs 2.20%). The gain
  comes from the risk-based value. Is our explanation convincing, or should something change?
- **The food-delivery data is synthetic** (generated, calibrated). The real-data checks are an old
  ServiceNow IT log (UCI). How much does this hurt, and what can still be done before the 29th?
- **Under OpsLens most playbooks are within noise**; only cross-training clearly helps. Reopens
  rise slightly (4.40% vs 3.93%). P99 wait has a large spread.
- Anything about code quality, tests, reproducibility, speed, or the offline demo
  (`make demo` must work with Wi-Fi off).

## Hard rules (non-negotiable unless the owner agrees)
- **Never show a number we did not compute.** Every number in the UI, docs or pitch comes from
  `eval/results.json` (re-generate with `make eval`). No invented ₹ figures, odds or percentages.
- **No tuning on test days.** Train days 1–35, validation 36–42 for every choice, test 43–56
  report-only. If you change the policy or a model, choose it on validation days, then run the
  test days once and record it. Earlier policies that failed are kept on record (see PROGRESS).
- **No leakage**, **fair comparison** (same tickets, luck, headcount, hours for every policy), the
  engine never reads `data/planted.json`, PII is masked before any API call, the LLM never writes a digit.
- **Free tools only**, no Eternal/Zomato/Blinkit logos. Ask Sneha/Jijnasu before adding a dependency.
- **Code the owner can defend:** plain Python and vanilla JS, small functions, type hints, a
  docstring with a real example per module, comments that say *why*. No clever metaprogramming.
- If you believe a rule is wrong, write the argument down in your review instead of breaking it.

## Setup (Windows)
- The repo has the code, docs, config and the official results (`eval/results.json`,
  `docs/NUMBERS.md`). It does NOT have secrets, downloaded datasets, generated data or the LLM cache
  (all git-ignored), so build them once:
  1. `.env`: copy `.env.example` to `.env` and paste the Gemini and Groq keys Sneha gives you
     (never commit `.env`). You share the free-tier limits with Jijnasu: keep LLM calls small.
  2. Python **3.12** (not 3.14): `mingw32-make setup` (make sure `python` on PATH is 3.12; else
     create `.venv` with the 3.12 interpreter yourself and `pip install -r requirements.txt`).
  3. `mingw32-make data` (downloads Bitext + UCI), `mingw32-make gen` (generates the 56 days),
     `mingw32-make test` (111 tests), then `mingw32-make eval` (~40 min, uses all CPU cores).
  4. `mingw32-make demo` → http://localhost:8000.
- Your re-run of `make eval` may differ slightly from the committed results (the LLM answers are
  not cached on your machine). The committed `eval/results.json` is the official one: do not
  commit a re-generated results file unless your change needs it, and then list what moved.
- The challenger arena (`eval/challengers/`, PyTorch in a separate `.venv-challengers`) is
  optional and eval-only. Ignore it unless you work on it.

## How we work together
- **GitHub is our shared space** (private repo `opslens`). Work on branches named
  `claude2/<topic>` (start with `claude2/review`), small commits with clear messages, push them,
  and open a **pull request into `main`** with `gh pr create` for each coherent change. Never push
  to `main`, never force-push or rewrite history. Claude 1 reviews your PRs (and you review
  Claude 1's: `gh pr list`, `gh pr diff <n>`, `gh pr review <n> --comment`); a human merges.
- Pull often (`git fetch`, then rebase or merge `origin/main` into your branch) so we do not drift.
- **Claude 1 is also working in parallel** on: the TabPFN challenger (`eval/challengers/`),
  the rehearsal docs, and appends to `PROGRESS.md`. Avoid editing those files. If you must, say so
  in the PR. Everything else is open to you.
- **Talk to Claude 1 through GitHub Issues**: label `for-claude-1` for your messages, findings
  and questions; Claude 1 writes to you with label `for-claude-2`. At the start of every session
  run `gh issue list --label for-claude-2` and answer what is open. One issue per topic; close it
  when settled. (`docs/collab/FROM_CLAUDE_1.md` holds Claude 1's first hello.)
- **Your usage window is limited** (Claude Pro). Keep a running log in
  `docs/collab/CLAUDE_2_LOG.md` (what you checked, decided, changed, what is next), so a fresh
  session can continue where you stopped.

## What to deliver, in this order
1. **`docs/collab/REVIEW.md` first, before big changes.** A ranked list of findings. For each:
   severity (would it lose us the finale / cost points / minor), the evidence (file:line, a
   command you ran, a number you reproduced), and what you propose. Include what is *good* and must not be broken.
   Include your own view on how to win: the story, the demo flow, the one thing judges should remember.
2. **Then make the changes** you believe in most, highest impact first. After any change that
   touches results, re-run `mingw32-make eval` and state which numbers moved and why.
   Keep `mingw32-make test` green and add tests for new logic.
3. **At the end of each session:** update your log, push, open or update the PR, post open
   questions as `for-claude-1` issues, and tell Sneha
   in plain words what changed, what is unverified, and what you recommend next.

## Dates
Model and weight freeze **22 Oct** (no model changes after). Rehearsal 27 Oct. Travel 28 Oct.
Finale 29–31 Oct. Spend the time where it most raises our chance of winning.
