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

---

## M3 — 15 Oct 2026 — Ingest, UCI adapter, KPIs, classification cascade, clusters

**Built**
- `opslens/ingest.py` (pydantic row check, timing recomputed from timestamps, splits),
  `opslens/adapters/uci_incidents.py` (events → incidents; as-of-time risk features),
  `opslens/kpis.py`, `opslens/classify.py` (local TF-IDF + LR, isotonic, LLM cascade),
  `opslens/clusters.py` (TF-IDF + KMeans per category, LLM names), `eval/run_classification.py`.
- Text realism: 12% vague first messages, 15% multi-issue (30% with the main issue second),
  and ~600 LLM-written message patterns (`data/llm_templates.json`, Groq Qwen — a different
  model from the classifier's Gemini). With hand templates only, accuracy was 99.9% (memorised).
- `config/calendar.yaml`: calendar facts split from `generator.yaml`, so the engine never reads
  the file that describes the planted problems (guard test added).
- LLM client: waits and retries once on "try again in Ns" (≤ 90 s); Groq paced to 1 request/min
  (its free tier allows 1,000 output tokens per minute) and capped at 900 output tokens; batches
  of 25.

**Numbers printed (test days 43-56, 18,032 tickets)**
- Menu choice 90.9% (calls 75.8%) → local 97.97% → cascade 98.08% (calls 95.7%, Hinglish 97.3%).
- Threshold 0.6 (chosen on validation); 1.54% sent to LLM (≈ 617 requests per 1M tickets);
  LLM fixed 57, broke 37. LLM alone on 400 random tickets: 90.0%.
- Wrong-team routing per 100: 5.71 → 1.20 (calls 14.83 → 2.54).
- UCI: 24,918 incidents; breach 36.6%; breach by reassignments 0/1/2/4+: 21.6/42.9/60.1/81.0%.

**Open issues**: cluster names sometimes repeat; synthetic text is cleaner than real tickets.

---

## M4 — 15 Oct 2026 — Patterns, live alerts, blind recall

**Built**: `opslens/patterns.py` (capacity, interaction, transfer, partner, spike scans; cause
rules; evidence cards; live alerts), `eval/recall.py`, `eval/run_patterns.py`, `data/plant.py`,
`eval/run_blind.py`; generator accepts generic plants (`extra_lifts`, `extra_partners`,
`extra_misrouting`) — main data verified identical.

**Numbers printed**
- Main data: 5/5 planted problems found and diagnosed (cause type correct). 2 unplanted findings:
  regional-language × weekday morning replicates on test days (2.0×); Team B × weekday night
  does not (1.2×) → 1 false alarm.
- Live alerts (rule z ≥ 4.5 twice in a row, chosen on days 15-42): day-47 surge flagged after
  45 min; 1 false alert in 2 weeks; sale-day alerts explained.
- **Blind test: 57/60 random plants found and diagnosed (95%)** over 20 datasets
  (capacity 10/10, partner 14/14, process 10/10, spike 11/12, skill gap 12/14); clean dataset 3 cards;
  2.35 unplanted cards per set.

**Open issues**: small groups with modest effects can be missed (regional-language × Team C).

---

## M5 — 15 Oct 2026 — Leak-proof features, risk model, reasons, UCI check

**Built**: `opslens/features.py` (QueueSnapshot → features; the same code will run inside the
simulator), `opslens/risk.py` (LightGBM + isotonic, TreeSHAP shares, counterfactual, save/load),
`eval/run_risk.py`, `tests/test_risk.py` (leakage test: change the future, features unchanged).

**Numbers printed (test days, still-savable waiting tickets, 26,811 snapshot rows)**
- AUC 0.976 (time-left rule 0.884, priority rule 0.790), PR-AUC 0.955, top-10% precision 0.996,
  Brier 0.055; at arrival AUC 0.966. Calibration 0.29 → 0.32, 0.74 → 0.78.
- UCI real data (7,476 test incidents): AUC 0.857 vs priority rule 0.552.

**Decision**: tickets already past SLA are excluded (with them the AUC was a misleading 0.992).

---

## M6 — 15 Oct 2026 — Forecast, conformal ranges, bottlenecks, staffing

**Built**: `opslens/forecast.py`, `opslens/staffing.py` (Erlang C, numpy coverage, greedy
budget-neutral moves, overload hours 3×, day hours only), `eval/run_forecast.py`, weekly plans
saved to `data/generated/staffing_plan.json`; simulator agents accept week-specific shift
overrides (`world.apply_staffing_plan`).

**Numbers printed (test days)**
- WAPE 0.305 vs naive 0.415 (Poisson floor 0.280); team-hour workload 0.235 vs 0.321.
- Conformal coverage 79.2% (80% range), 90.0% (90% range); sale day −16.6%.
- Plan days 43-49: C05 Monday off instead of Saturday, B02 Monday instead of Friday, C06 Friday
  instead of Tuesday, 3 starts 08:00 → 07:00; shortage 654 → 636 agent-hours.

**Next step:** M7 — OpsLens policy (rescue value, scarcity, starvation guard, min-cost flow),
weights chosen on validation days, OpsLens vs A/B on test days with paired CIs.
