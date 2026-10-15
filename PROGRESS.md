# OpsLens — progress log

Newest entry at the bottom. One entry per milestone (see `CLAUDE.md` section 1.2).

---

## Session 0 — 15 Oct 2026 — Planning (plan v2)

**Built**
- `CLAUDE.md` rewritten as plan v2. Original kept in `docs/CLAUDE_v1.md`.
- `docs/PLAN.md`: 23 changes from v1 with reasons, 2026 research links, risks, team tracks,
  demo outline, attack questions, day-1 checklist.

**Key decisions (all in `docs/PLAN.md` section 2)**
- 56 days of data (train 1–35, validation 36–42, test 43–56).
- 5 planted problems + decoys; blind recall on 20 random plant sets; live Plant-a-problem.
- Real data: UCI ServiceNow incident log (has `made_sla`).
- Classification cascade (local model first, LLM only when unsure).
- Decision tick 2 min for all policies; scarcity cost; starvation guard; Erlang-C staffing.
- LLM never writes digits; What-if tab; UI track in a parallel session from 18 Oct.

**Numbers printed:** none yet (planning only).

**Open issues**
- ~~TrueInk overlap~~ — resolved 15 Oct: OpsLens is the only finale project; all days go to it.
- Free LLM limits to be checked in our own accounts (blogs disagree).
- Project still in OneDrive; M1 moves it to `C:\dev\opslens` with its own git repo.

**Next step:** M1 in a new session at `C:\dev\opslens`.

---

## M1 — 15 Oct 2026 — Repo, LLM layer, privacy, data

**Built**
- Project moved to `C:\dev\opslens` (own git repo, branch `main`), outside OneDrive.
- Python 3.12.15 venv (`.venv`). Versions frozen in `requirements.lock.txt`
  (pandas 3.0.6, numpy 2.5.4, scikit-learn 1.9.1, lightgbm 4.7.0, ortools 9.15, openai 3.31).
- `opslens/config.py`: YAML loader + our own `.env` reader (no python-dotenv).
- `opslens/privacy.py`: 10 ordered regex masks (email, UPI, Luhn-checked card, Aadhaar, PAN,
  order ID, phone, house/flat, PIN, long numbers).
- `opslens/llm/`: `LLMClient.ask_json` = mask → cache → per-provider daily budget →
  per-minute window → send → JSON parse (+1 repair) → fallback → cache. Providers:
  Gemini (`gemini-3.1-flash-lite`), Groq (`openai/gpt-oss-20b`), mock.
- `scripts/download_data.py` + `data/SOURCES.md` (licences, SHA-256).
- `scripts/ping_llm.py` (`mingw32-make ping`): lists visible models, sends one real request.
- `Makefile` (works with `mingw32-make`), `pytest.ini` (temp files inside the project).

**Numbers printed**
- Tests: 31 passed (17 privacy, 14 LLM layer).
- Bitext: 26,872 rows, 27 intents. UCI: 141,712 events, 24,918 incidents, 2016–2017,
  `made_sla` False on 9,215 of 141,712 events (incident-level rate computed in M3).

**Open issues**
- ~~Ping not run yet~~ — done 15 Oct after keys were added: gemini-3.1-flash-lite OK (1.4 s);
  Groq `llama-3.1-8b-instant` is retired and `gpt-oss-20b` had used its 200k tokens/day (shared
  org quota), so the fallback is `qwen/qwen3.8-27b` (OK, 0.2 s; `gpt-oss-120b` also works).
- Bitext has no food intents → `data/text_bank.py` templates (M2).
- pytest needs `--basetemp=.pytest_tmp` on this PC (system temp folder is locked).

**Next step:** M2 — text bank, generator (56 days, 5 plants, decoys), simulator, baselines, CRN.

---

## M2 — 15 Oct 2026 — Generator, simulator, baselines, results contract

**Built**
- `config/generator.yaml` (all assumptions), `config/roster.yaml` (40 named agents; start hours
  and days off from a load-flattening search; planted skill gap + weekend gap in comments).
- `data/text_bank.py`: Bitext (food-flavoured) + English/Hinglish templates, typos, multi-issue, PII.
- `data/generate_ops.py`: 56 days, 5 planted problems (+ test-period surge) and 3 decoys;
  history by Baseline A; calibration report. `--tickets-only` for quick tuning.
- `opslens/simulate.py`: event-driven discrete-event simulator (FINISH/REOPEN/ARRIVAL/DECIDE),
  transfers, deliberate cross-skill work, reopens, absences, snapshots for the replay.
- `opslens/world.py`: World builder; CRN draws indexed by ticket number.
- `opslens/policies.py`: Baseline A (FIFO, team queue first), Baseline B (priority, then oldest).
- `opslens/impact.py`: KPIs under Turnaround / Productivity / Quality; paired 95% CI.
- `opslens/results_schema.py` + `eval/make_fixture.py` → `eval/fixture_results.json`
  (`meta.fixture = true`) and `eval/results.schema.json`.
- `eval/run_baselines.py`: A vs B on test days, 5 seeds.

**Numbers printed**
- 71,530 tickets. Baseline A history: breach 13.1% (target 12–18), utilisation 0.80
  (0.70–0.80), Team C weekend-dinner ρ 1.40 (1.2–1.5). Sim of 56 days: 11.0 s.
- Planted signals in history: Hindi refund/payment wait 301.7 vs 46.7 min (English);
  cluster 17 = 5.1% of wrong items vs 2.0% of tickets; transfers per 100: call 12.8, chat 2.6.
- Erlang C check: simulated wait 10.97 vs 10.79 min; P(wait) 0.644 vs 0.647.
- Test days 43–56, 5 seeds, 18,032 tickets: Baseline A 13.11% ± 2.23, Baseline B 6.82% ± 1.34,
  B − A = −6.29 [−7.50, −5.07]; P99 wait A 816 vs B 1,007 min.
- Tests: 50 passed.

**Plan changes (CLAUDE.md updated)**
- Decisions are event-driven for all policies (2-min tick only for shift starts): the Erlang-C
  test showed a fixed cadence leaves agents idle ~1 min per ticket.
- 3 Hindi + refund agents instead of 2 (with 2, waits averaged 15 h and never cleared).
- ~1,130 tickets/weekday and sale days ×1.35 (×1.6 created a 2-day backlog of 446 tickets).
- Team C weekend-dinner ρ target 1.2–1.5 (was 1.05–1.2) so the planted problem is visible.
- YAML gotcha: the key `off` is read as boolean false — renamed to `days_off`.

**Open issues**
- Test-day breach % varies a lot by seed (A: ±2.23) because of the day-47 surge and the sale
  day; paired CIs are still tight thanks to CRN.
- U1 dashboard shell is being built in a parallel session on branch `u1-dashboard-shell`.

**Next step:** M3 — ingest (+ UCI adapter), KPIs, classification cascade, LLM-named clusters.
